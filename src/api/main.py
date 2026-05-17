"""FastAPI Main Application — multi-tenant via Clerk JWT.

Every domain route depends on `get_current_user_provisioned`, which verifies
the bearer token, upserts the user in Postgres, and ensures a `:User` node
exists in Neo4j. Public liveness routes (`/`, `/health`, `/status`) are
unauthenticated.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from src.pipeline.coordinator import PipelineCoordinator
from src.pipeline.similarity import SimilarityComputer
from src.pipeline.clustering import MarketMapClusterer
from src.pipeline.geocoding import get_geocoding_service
from src.llm.cluster_namer import ClusterNamer
from src.database.postgres import get_postgres_connection
from src.database.neo4j_client import get_neo4j_driver
from src.api.admin import router as admin_router
from src.api.queries import router as queries_router
from src.api.auth import ClerkUser, get_current_user_provisioned


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Global pipeline coordinator
pipeline: Optional[PipelineCoordinator] = None
similarity_computer: Optional[SimilarityComputer] = None


def _bootstrap_postgres_schema() -> None:
    """Apply src/database/migrations/schema.sql at startup (idempotent)."""
    from pathlib import Path
    schema_path = Path(__file__).resolve().parents[1] / "database" / "migrations" / "schema.sql"
    if not schema_path.exists():
        logger.warning("Schema file not found at %s; skipping bootstrap.", schema_path)
        return
    sql = schema_path.read_text(encoding="utf-8")
    pg = get_postgres_connection()
    try:
        with pg.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        logger.info("PostgreSQL schema applied/verified from %s", schema_path)
    except Exception as e:
        logger.error("Failed to apply schema.sql at startup: %s", e)


def _bootstrap_neo4j_schema() -> None:
    """Apply composite per-user constraints and indexes at startup (idempotent)."""
    try:
        get_neo4j_driver().initialize_schema()
    except Exception as e:
        logger.error("Failed to bootstrap Neo4j schema: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, similarity_computer

    logger.info("Starting VC Intelligence API...")
    try:
        _bootstrap_postgres_schema()
        _bootstrap_neo4j_schema()

        pipeline = PipelineCoordinator()
        logger.info("Pipeline coordinator initialized")

        postgres = get_postgres_connection()
        neo4j = get_neo4j_driver()
        similarity_computer = SimilarityComputer(
            postgres_client=postgres,
            neo4j_client=neo4j,
            watsonx_client=pipeline.flash_client,
        )
        logger.info("Similarity computer initialized")

        app.state.pipeline = pipeline
        app.state.similarity = similarity_computer

        logger.info("API startup complete")
    except Exception as e:
        logger.error("Failed to initialize API: %s", e)
        raise

    yield

    logger.info("Shutting down VC Intelligence API...")
    if pipeline:
        pipeline.close()
    logger.info("API shutdown complete")


app = FastAPI(
    title="VC Intelligence API",
    description="Knowledge graph and intelligence platform for venture capital deal flow",
    version="1.0.0",
    lifespan=lifespan,
)


# CORS — restrict to the configured frontend origin(s).
# ALLOWED_ORIGINS: comma-separated exact origins (e.g. https://vista.vercel.app)
# ALLOWED_ORIGIN_REGEX: optional regex (e.g. https://vista-.*\.vercel\.app) to
#   cover Vercel preview / branch deploys without listing each one.
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_origins = [
    o.strip().rstrip("/")
    for o in os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",")
    if o.strip()
]
_origin_regex = os.environ.get("ALLOWED_ORIGIN_REGEX") or None

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Hidden admin router (guarded by ADMIN_PIPELINE_TOKEN)
app.include_router(admin_router)
# Per-user query endpoints
app.include_router(queries_router)


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class ProcessCompanyRequest(BaseModel):
    company_domain: str
    limit_per_source: int = 100


class ProcessCompaniesRequest(BaseModel):
    company_domains: Optional[List[str]] = None
    limit_per_source: int = 100


class CompanySimilarityRequest(BaseModel):
    company_id: str
    threshold: float = 0.75
    limit: int = 10


class HealthResponse(BaseModel):
    status: str
    version: str
    components: dict


# ============================================
# HEALTH & STATUS ENDPOINTS (unauthenticated)
# ============================================

@app.get("/", response_model=HealthResponse)
async def root():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": pipeline.get_pipeline_status() if pipeline else {},
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": pipeline.get_pipeline_status(),
    }


@app.get("/status")
async def get_status():
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    return pipeline.get_pipeline_status()


# ============================================
# PIPELINE ENDPOINTS (authenticated)
# ============================================

@app.post("/pipeline/process-company")
async def process_company(
    request: ProcessCompanyRequest,
    background_tasks: BackgroundTasks,
    user: ClerkUser = Depends(get_current_user_provisioned),
):
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    try:
        result = pipeline.process_single_company(
            clerk_id=user.clerk_id,
            company_domain=request.company_domain,
            limit_per_source=request.limit_per_source,
        )

        if (
            similarity_computer
            and result.get('success')
            and result.get('stats', {}).get('company_id')
        ):
            company_id = result['stats']['company_id']
            background_tasks.add_task(
                similarity_computer.compute_similarities,
                clerk_id=user.clerk_id,
                company_id=company_id,
            )

        return result
    except Exception as e:
        logger.error("Failed to process company: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pipeline/process-companies")
async def process_companies(
    request: ProcessCompaniesRequest,
    user: ClerkUser = Depends(get_current_user_provisioned),
):
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    try:
        if request.company_domains:
            results = pipeline.process_company_list(
                clerk_id=user.clerk_id,
                company_domains=request.company_domains,
                limit_per_source=request.limit_per_source,
            )
        else:
            results = pipeline.process_all_companies(
                clerk_id=user.clerk_id,
                limit_per_source=request.limit_per_source,
            )

        return {
            "total": len(results),
            "successful": sum(1 for r in results if r.get('success')),
            "results": results,
        }
    except Exception as e:
        logger.error("Failed to process companies: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# SIMILARITY ENDPOINTS (authenticated)
# ============================================

@app.post("/similarity/compute")
async def compute_similarity(
    request: CompanySimilarityRequest,
    user: ClerkUser = Depends(get_current_user_provisioned),
):
    if not similarity_computer:
        raise HTTPException(status_code=503, detail="Similarity computer not initialized")

    try:
        similar = similarity_computer.compute_similarities(
            clerk_id=user.clerk_id,
            company_id=request.company_id,
            threshold=request.threshold,
            limit=request.limit,
        )
        return {
            "company_id": request.company_id,
            "similar_companies": similar,
        }
    except Exception as e:
        logger.error("Failed to compute similarities: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/similarity/compute-all")
async def compute_all_similarities(
    threshold: float = 0.75,
    limit: int = 10,
    user: ClerkUser = Depends(get_current_user_provisioned),
):
    if not similarity_computer:
        raise HTTPException(status_code=503, detail="Similarity computer not initialized")

    try:
        return similarity_computer.compute_all_similarities(
            clerk_id=user.clerk_id,
            threshold=threshold,
            limit=limit,
        )
    except Exception as e:
        logger.error("Failed to compute all similarities: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# GEOCODING ENDPOINT (authenticated)
# ============================================

@app.get("/geocode")
async def geocode_location(
    location: str,
    user: ClerkUser = Depends(get_current_user_provisioned),
):
    geocoding = get_geocoding_service()
    coords = geocoding.geocode(location)
    if not coords:
        raise HTTPException(status_code=404, detail=f"Location not found: {location}")
    return {
        "location": location,
        "latitude": coords[0],
        "longitude": coords[1],
    }


# ============================================
# CLUSTERING / MARKET MAP (authenticated)
# ============================================

@app.get("/market-map")
async def get_market_map(
    user: ClerkUser = Depends(get_current_user_provisioned),
):
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    try:
        postgres = get_postgres_connection()
        neo4j = get_neo4j_driver()

        clusters = postgres.execute_query(
            """
            SELECT
                mc.id,
                mc.cluster_number,
                mc.name,
                mc.description,
                mc.company_count,
                cm.common_sectors,
                cm.common_stages,
                cm.common_tags
            FROM market_clusters mc
            LEFT JOIN cluster_metadata cm
              ON cm.cluster_id = mc.id AND cm.owner_clerk_id = mc.owner_clerk_id
            WHERE mc.owner_clerk_id = %s
            ORDER BY mc.cluster_number
            """,
            (user.clerk_id,),
            fetch=True,
        )

        if not clusters:
            return {"clusters": [], "total_companies": 0}

        result_clusters = []
        total_companies = 0
        for cluster in clusters:
            companies = neo4j.execute_query(
                """
                MATCH (c:Company {clerk_id: $clerk_id})-[:BELONGS_TO_CLUSTER]->(cl:Cluster {clerk_id: $clerk_id, id: $cluster_id})
                RETURN c.id as id, c.name as name, c.one_liner as one_liner,
                       c.sector as sector, c.stage as stage, c.verdict as verdict,
                       c.deal_momentum as momentum, c.tags as tags
                ORDER BY c.name
                """,
                {"clerk_id": user.clerk_id, "cluster_id": str(cluster['id'])},
            )

            result_clusters.append({
                "id": str(cluster['id']),
                "cluster_number": cluster['cluster_number'],
                "name": cluster['name'],
                "description": cluster['description'],
                "company_count": len(companies),
                "common_sectors": cluster.get('common_sectors') or [],
                "common_stages": cluster.get('common_stages') or [],
                "common_tags": cluster.get('common_tags') or [],
                "companies": companies,
            })
            total_companies += len(companies)

        return {"clusters": result_clusters, "total_companies": total_companies}
    except Exception as e:
        msg = str(e).lower()
        if "does not exist" in msg or "undefined" in msg or "relation" in msg:
            logger.warning("Market map tables not present — returning empty: %s", e)
            return {"clusters": [], "total_companies": 0}
        logger.error("Failed to fetch market map: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/market-map/regenerate")
async def regenerate_market_map(
    user: ClerkUser = Depends(get_current_user_provisioned),
):
    """Wipe this user's clusters, re-run clustering, re-run LLM naming.

    Only the calling user's cluster data is touched — companies, embeddings,
    and similarity edges are preserved.
    """
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    postgres = get_postgres_connection()
    neo4j = get_neo4j_driver()

    try:
        # Wipe this user's cluster data (FK order: assignments → metadata → clusters).
        await run_in_threadpool(
            postgres.execute_query,
            "DELETE FROM company_cluster_assignments WHERE owner_clerk_id = %s",
            (user.clerk_id,),
            False,
        )
        await run_in_threadpool(
            postgres.execute_query,
            "DELETE FROM cluster_metadata WHERE owner_clerk_id = %s",
            (user.clerk_id,),
            False,
        )
        await run_in_threadpool(
            postgres.execute_query,
            "DELETE FROM market_clusters WHERE owner_clerk_id = %s",
            (user.clerk_id,),
            False,
        )
        # Detach-delete the user's Cluster nodes (removes BELONGS_TO_CLUSTER
        # edges and the OWNS edge to :User in one shot).
        await run_in_threadpool(
            neo4j.execute_write,
            "MATCH (cl:Cluster {clerk_id: $clerk_id}) DETACH DELETE cl",
            {"clerk_id": user.clerk_id},
        )

        # 2. Re-run clustering for this user.
        clusterer = MarketMapClusterer(
            postgres_client=postgres,
            neo4j_client=neo4j,
            algorithm="kmeans",
        )
        cluster_stats = await run_in_threadpool(
            clusterer.compute_clusters, user.clerk_id
        )

        # 3. Re-run LLM naming for this user's freshly-created clusters.
        namer = ClusterNamer(
            watsonx_client=pipeline.pro_client,
            postgres_client=postgres,
            neo4j_client=neo4j,
        )
        naming_stats = await run_in_threadpool(
            namer.name_all_clusters, user.clerk_id
        )

        return {
            "status": "ok",
            "clustering": cluster_stats,
            "naming": naming_stats,
        }
    except ValueError as e:
        # MarketMapClusterer raises ValueError when there are <3 companies.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to regenerate market map for user=%s", user.clerk_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/market-map/cluster/{cluster_id}")
async def get_cluster_details(
    cluster_id: str,
    user: ClerkUser = Depends(get_current_user_provisioned),
):
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    try:
        postgres = get_postgres_connection()
        neo4j = get_neo4j_driver()

        result = postgres.execute_query(
            """
            SELECT
                mc.id,
                mc.cluster_number,
                mc.name,
                mc.description,
                mc.company_count,
                cm.common_sectors,
                cm.common_stages,
                cm.common_tags,
                cm.sample_companies
            FROM market_clusters mc
            LEFT JOIN cluster_metadata cm
              ON cm.cluster_id = mc.id AND cm.owner_clerk_id = mc.owner_clerk_id
            WHERE mc.id = %s AND mc.owner_clerk_id = %s
            """,
            (cluster_id, user.clerk_id),
            fetch=True,
        )

        if not result:
            raise HTTPException(status_code=404, detail="Cluster not found")

        cluster = result[0]

        companies = neo4j.execute_query(
            """
            MATCH (c:Company {clerk_id: $clerk_id})-[:BELONGS_TO_CLUSTER]->(cl:Cluster {clerk_id: $clerk_id, id: $cluster_id})
            RETURN c.id as id, c.name as name, c.one_liner as one_liner,
                   c.sector as sector, c.stage as stage, c.verdict as verdict,
                   c.deal_momentum as momentum, c.tags as tags,
                   c.last_touch_at as last_touch_at, c.owner as owner
            ORDER BY c.name
            """,
            {"clerk_id": user.clerk_id, "cluster_id": str(cluster_id)},
        )

        return {
            "id": str(cluster['id']),
            "cluster_number": cluster['cluster_number'],
            "name": cluster['name'],
            "description": cluster['description'],
            "company_count": len(companies),
            "common_sectors": cluster.get('common_sectors') or [],
            "common_stages": cluster.get('common_stages') or [],
            "common_tags": cluster.get('common_tags') or [],
            "sample_companies": cluster.get('sample_companies') or [],
            "companies": companies,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch cluster details: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
