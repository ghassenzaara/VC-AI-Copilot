"""Hidden admin endpoints — not advertised in the public API surface.

Gated behind a shared-secret bearer token (ADMIN_PIPELINE_TOKEN). The mock
pipeline now requires a `clerk_id` in the request payload so the ingested
data is attributed to that user (per-user isolation).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from src.ingestion.mock_loader import load_mock_companies
from src.pipeline.clustering import MarketMapClusterer
from src.llm.cluster_namer import ClusterNamer


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ----------------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------------

_TOKEN_ENV = "ADMIN_PIPELINE_TOKEN"


def _expected_token() -> Optional[str]:
    raw = os.environ.get(_TOKEN_ENV)
    if raw is None:
        return None
    raw = raw.strip()
    return raw or None


def _verify_token(provided: Optional[str]) -> None:
    expected = _expected_token()
    if expected is None:
        logger.warning(
            "Admin endpoint accessed without %s configured. Set the env var "
            "to require a token.",
            _TOKEN_ENV,
        )
        return
    if provided is None or not secrets.compare_digest(provided.strip(), expected):
        raise HTTPException(status_code=401, detail="Invalid admin token")


# ----------------------------------------------------------------------------
# Payloads
# ----------------------------------------------------------------------------

class RunMockPipelineRequest(BaseModel):
    """Body for /admin/run-mock-pipeline.

    clerk_id is REQUIRED so the ingested mock data is attributed to a real
    user (FK to users.clerk_id). Make sure the user exists — sign in at least
    once via the frontend before running, or insert a row manually.
    """
    clerk_id: str


# ----------------------------------------------------------------------------
# SSE helpers
# ----------------------------------------------------------------------------

def _sse(event: str, payload: Dict[str, Any]) -> str:
    data = json.dumps(payload, default=str)
    return f"event: {event}\ndata: {data}\n\n"


# ----------------------------------------------------------------------------
# Pipeline runner
# ----------------------------------------------------------------------------

async def _run_full_pipeline(
    request: Request,
    clerk_id: str,
) -> AsyncIterator[str]:
    pipeline = getattr(request.app.state, "pipeline", None)
    similarity = getattr(request.app.state, "similarity", None)

    if pipeline is None or similarity is None:
        yield _sse("error", {"message": "Pipeline not initialized"})
        return

    relevance_filter = pipeline.relevance_filter
    extraction_engine = pipeline.extraction_engine
    storage_orchestrator = pipeline.storage_orchestrator
    geocoding = pipeline.geocoding
    postgres = pipeline.postgres
    neo4j = pipeline.neo4j
    pro_client = pipeline.pro_client

    yield _sse("step", {"step": "boot", "status": "running", "clerk_id": clerk_id})

    # Make sure the user row exists before any FK insert hits it.
    try:
        await run_in_threadpool(postgres.upsert_user, clerk_id, None, None)
        await run_in_threadpool(
            neo4j.execute_write,
            "MERGE (u:User {clerk_id: $clerk_id}) "
            "ON CREATE SET u.created_at = datetime() "
            "RETURN u",
            {"clerk_id": clerk_id},
        )
    except Exception as e:
        logger.exception("Failed to ensure user exists")
        yield _sse("error", {"step": "ensure_user", "message": str(e)})
        return

    # --------------------- Load mock data ---------------------
    mock_path = Path(__file__).resolve().parents[2] / "mock_data.json"
    yield _sse("step", {"step": "load_mock", "status": "starting", "path": str(mock_path)})
    try:
        companies = await run_in_threadpool(load_mock_companies, mock_path)
    except Exception as e:
        logger.exception("Failed to load mock_data.json")
        yield _sse("error", {"step": "load_mock", "message": str(e)})
        return
    yield _sse(
        "step",
        {"step": "load_mock", "status": "done", "company_count": len(companies)},
    )

    # --------------------- Per-company processing ---------------------
    company_ids: List[str] = []
    successes = 0
    failures = 0

    for i, company in enumerate(companies, 1):
        company_name = company.get("company_name") or "Unknown"
        company_domain = company.get("company_domain")
        yield _sse(
            "company",
            {
                "index": i,
                "total": len(companies),
                "company": company_name,
                "domain": company_domain,
                "status": "starting",
                "interactions": len(company.get("interactions") or []),
            },
        )

        try:
            # 1. Filter
            yield _sse("substep", {"company": company_name, "phase": "filter", "status": "running"})
            filtered = await run_in_threadpool(
                relevance_filter.filter_company_data, company
            )
            yield _sse(
                "substep",
                {
                    "company": company_name,
                    "phase": "filter",
                    "status": "done",
                    "kept": len(filtered.get("interactions") or []),
                    "total": len(company.get("interactions") or []),
                },
            )
            if not filtered.get("interactions"):
                yield _sse(
                    "company",
                    {"company": company_name, "status": "skipped", "reason": "no_relevant"},
                )
                failures += 1
                continue

            # 2. Extract
            yield _sse("substep", {"company": company_name, "phase": "extract", "status": "running"})
            extraction = await run_in_threadpool(extraction_engine.extract, filtered)
            yield _sse(
                "substep",
                {
                    "company": company_name,
                    "phase": "extract",
                    "status": "done",
                    "confidence": getattr(extraction.extraction_meta, "confidence", None),
                    "warnings": len(getattr(extraction.extraction_meta, "warnings", []) or []),
                },
            )

            # 3. Store (Neo4j + PostgreSQL) — scoped to clerk_id
            yield _sse("substep", {"company": company_name, "phase": "store", "status": "running"})
            storage_result = await run_in_threadpool(
                storage_orchestrator.store_extraction, clerk_id, extraction
            )
            company_id = storage_result["neo4j"]["company_id"]
            company_ids.append(company_id)
            yield _sse(
                "substep",
                {
                    "company": company_name,
                    "phase": "store",
                    "status": "done",
                    "company_id": company_id,
                },
            )

            # 4. Embedding (per-user)
            yield _sse("substep", {"company": company_name, "phase": "embed", "status": "running"})
            await run_in_threadpool(
                similarity.generate_company_embedding,
                clerk_id,
                company_id,
                extraction.company.model_dump(),
            )
            yield _sse(
                "substep",
                {"company": company_name, "phase": "embed", "status": "done"},
            )

            # 5. Optional: geocode (best-effort)
            if geocoding and extraction.company.location:
                try:
                    coords = await run_in_threadpool(
                        geocoding.geocode, extraction.company.location
                    )
                    if coords:
                        await run_in_threadpool(
                            neo4j.execute_write,
                            "MATCH (c:Company {clerk_id: $clerk_id, id: $id}) "
                            "SET c.lat = $lat, c.lng = $lng",
                            {
                                "clerk_id": clerk_id,
                                "id": company_id,
                                "lat": coords[0],
                                "lng": coords[1],
                            },
                        )
                        yield _sse(
                            "substep",
                            {
                                "company": company_name,
                                "phase": "geocode",
                                "status": "done",
                                "coords": list(coords),
                            },
                        )
                except Exception as geo_err:
                    logger.warning("Geocoding failed for %s: %s", company_name, geo_err)

            successes += 1
            yield _sse(
                "company",
                {
                    "company": company_name,
                    "company_id": company_id,
                    "status": "done",
                },
            )

        except Exception as e:
            failures += 1
            logger.exception("Pipeline failed for %s", company_name)
            yield _sse(
                "company",
                {"company": company_name, "status": "failed", "error": str(e)},
            )

    yield _sse(
        "step",
        {
            "step": "per_company",
            "status": "done",
            "successes": successes,
            "failures": failures,
        },
    )

    # --------------------- Similarity (per-user, cross-company) ---------------------
    yield _sse("step", {"step": "similarity", "status": "running"})
    try:
        sim_stats = await run_in_threadpool(
            similarity.compute_all_similarities, clerk_id, 0.75, 10
        )
        yield _sse("step", {"step": "similarity", "status": "done", **(sim_stats or {})})
    except Exception as e:
        logger.exception("Similarity computation failed")
        yield _sse("step", {"step": "similarity", "status": "failed", "error": str(e)})

    # --------------------- Clustering ---------------------
    yield _sse("step", {"step": "clustering", "status": "running"})
    try:
        clusterer = MarketMapClusterer(
            postgres_client=postgres,
            neo4j_client=neo4j,
            algorithm="kmeans",
        )
        cluster_stats = await run_in_threadpool(clusterer.compute_clusters, clerk_id)
        yield _sse(
            "step",
            {"step": "clustering", "status": "done", **(cluster_stats or {})},
        )
    except Exception as e:
        logger.exception("Clustering failed")
        yield _sse("step", {"step": "clustering", "status": "failed", "error": str(e)})

    # --------------------- Cluster naming ---------------------
    yield _sse("step", {"step": "naming", "status": "running"})
    try:
        namer = ClusterNamer(
            watsonx_client=pro_client,
            postgres_client=postgres,
            neo4j_client=neo4j,
        )
        naming_stats = await run_in_threadpool(namer.name_all_clusters, clerk_id)
        yield _sse("step", {"step": "naming", "status": "done", **(naming_stats or {})})
    except Exception as e:
        logger.exception("Cluster naming failed")
        yield _sse("step", {"step": "naming", "status": "failed", "error": str(e)})

    # --------------------- Done ---------------------
    yield _sse(
        "done",
        {
            "companies_processed": successes,
            "companies_failed": failures,
            "company_ids": company_ids,
            "clerk_id": clerk_id,
        },
    )


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------

@router.get("/ping")
async def admin_ping(x_admin_token: Optional[str] = Header(None)) -> Dict[str, Any]:
    _verify_token(x_admin_token)
    return {
        "ok": True,
        "token_required": _expected_token() is not None,
    }


@router.post("/wipe-databases")
async def wipe_databases(
    request: Request,
    x_admin_token: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Wipe both PostgreSQL data and the Neo4j graph (all users, all data)."""
    _verify_token(x_admin_token)

    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    postgres = pipeline.postgres
    neo4j = pipeline.neo4j

    # Order matters because of FKs.
    pg_tables = [
        "company_cluster_assignments",
        "cluster_metadata",
        "market_clusters",
        "company_embeddings",
        "extraction_metadata",
        "team_debates",
        "decision_records",
        "interaction_content",
        "company_signals",
        "company_news",
        "company_snapshots",
        "users",
    ]
    pg_results: Dict[str, str] = {}
    for table in pg_tables:
        try:
            await run_in_threadpool(
                postgres.execute_query,
                f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE",
                None,
                False,
            )
            pg_results[table] = "wiped"
        except Exception as e:
            pg_results[table] = f"skipped ({type(e).__name__})"
            logger.warning("Wipe skipped %s: %s", table, e)

    try:
        await run_in_threadpool(
            neo4j.execute_write,
            "MATCH (n) DETACH DELETE n",
            {},
        )
        neo4j_result = "wiped"
    except Exception as e:
        logger.exception("Failed to wipe Neo4j")
        neo4j_result = f"failed: {e}"

    return {
        "postgres": pg_results,
        "neo4j": neo4j_result,
    }


@router.post("/run-mock-pipeline")
async def run_mock_pipeline(
    request: Request,
    payload: RunMockPipelineRequest,
    x_admin_token: Optional[str] = Header(None),
) -> StreamingResponse:
    """Run the full extraction pipeline against mock_data.json for one user.

    Body: `{"clerk_id": "user_xxx"}` — REQUIRED. Ingested data is attributed
    to that user via the owner_clerk_id FK chain.
    """
    _verify_token(x_admin_token)
    clerk_id = payload.clerk_id

    async def event_stream() -> AsyncIterator[bytes]:
        yield (": stream-open\n" + (" " * 2048) + "\n\n").encode("utf-8")
        try:
            async for chunk in _run_full_pipeline(request, clerk_id):
                yield chunk.encode("utf-8")
                await asyncio.sleep(0)
        except Exception as e:
            logger.exception("Unhandled error in pipeline stream")
            yield _sse("error", {"message": str(e)}).encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
