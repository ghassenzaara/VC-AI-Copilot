"""Query endpoints for the frontend (multi-tenant: per-clerk_id filtering).

Reads from Neo4j (per-user company graph) and PostgreSQL (per-user content).
Returns shapes that match the frontend's TypeScript interfaces in
`frontend/lib/types.ts`. Empty per-user state returns empty lists, not 500s.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.auth import ClerkUser, get_current_user_provisioned


logger = logging.getLogger(__name__)

router = APIRouter(tags=["queries"])


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _get_clients(request: Request):
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    return pipeline.postgres, pipeline.neo4j


def _json_loaded(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ----------------------------------------------------------------------------
# StartupSummary list — backs /startups page + dashboard
# ----------------------------------------------------------------------------

@router.get("/companies")
async def list_companies(
    request: Request,
    user: ClerkUser = Depends(get_current_user_provisioned),
) -> List[Dict[str, Any]]:
    """List the calling user's companies in StartupSummary shape."""
    _, neo4j = _get_clients(request)

    query = """
    MATCH (c:Company {clerk_id: $clerk_id})
    OPTIONAL MATCH (p:VCPartner {clerk_id: $clerk_id})-[:OWNS]->(c)
    RETURN
        c.id              AS id,
        c.name            AS name,
        c.one_liner       AS one_liner,
        c.sector          AS sector,
        c.stage           AS stage,
        c.pipeline_stage  AS pipeline_stage,
        c.deal_momentum   AS momentum,
        c.verdict         AS verdict,
        c.last_touch_at   AS last_touch_at,
        c.tags            AS tags,
        coalesce(p.name, '') AS owner
    ORDER BY coalesce(c.last_touch_at, '') DESC
    """
    try:
        rows = neo4j.execute_query(query, {"clerk_id": user.clerk_id})
    except Exception as e:
        logger.exception("Failed to list companies for user=%s", user.clerk_id)
        raise HTTPException(status_code=500, detail=str(e))

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "id": r.get("id") or "",
            "name": r.get("name") or "Unknown",
            "one_liner": r.get("one_liner") or "",
            "sector": r.get("sector") or "Uncategorized",
            "stage": r.get("stage"),
            "pipeline_stage": r.get("pipeline_stage") or "Tracking",
            "momentum": r.get("momentum") or "stable",
            "verdict": r.get("verdict") or "tracking",
            "last_touch_at": r.get("last_touch_at") or "",
            "owner": r.get("owner") or "Unassigned",
            "tags": _ensure_list(r.get("tags")),
        })
    return out


# ----------------------------------------------------------------------------
# Full ExtractionOutput for a single company — backs /startups/[id] page
# ----------------------------------------------------------------------------

@router.get("/companies/{company_id}/full")
async def get_company_full(
    company_id: str,
    request: Request,
    user: ClerkUser = Depends(get_current_user_provisioned),
) -> Dict[str, Any]:
    """Return the full ExtractionOutput payload, scoped to the calling user."""
    postgres, neo4j = _get_clients(request)
    clerk_id = user.clerk_id

    # ---- Company core ----
    company_q = """
    MATCH (c:Company {clerk_id: $clerk_id, id: $id})
    OPTIONAL MATCH (p:VCPartner {clerk_id: $clerk_id})-[:OWNS]->(c)
    RETURN c, coalesce(p.name, '') AS owner_name
    """
    company_rows = neo4j.execute_query(company_q, {"clerk_id": clerk_id, "id": company_id})
    if not company_rows:
        raise HTTPException(status_code=404, detail="Company not found")
    c = company_rows[0]["c"]
    owner_name = company_rows[0]["owner_name"]

    # ---- People (Contacts) ----
    contacts_q = """
    MATCH (person:Person {clerk_id: $clerk_id})-[:WORKS_AT]->(c:Company {clerk_id: $clerk_id, id: $id})
    RETURN person.name AS name, person.role AS role, person.email AS email,
           person.notes AS notes, person.is_primary AS is_primary
    ORDER BY person.is_primary DESC, person.name
    """
    contact_rows = neo4j.execute_query(contacts_q, {"clerk_id": clerk_id, "id": company_id})
    contacts: List[Dict[str, Any]] = []
    for r in contact_rows:
        contacts.append({
            "name": r.get("name") or "",
            "role": r.get("role") or "Other",
            "is_primary": bool(r.get("is_primary")),
            "email": r.get("email"),
            "phone": None,
            "linkedin": None,
            "twitter": None,
            "notes": r.get("notes"),
        })

    # ---- Interactions (graph) + content (postgres) ----
    interactions_q = """
    MATCH (i:Interaction {clerk_id: $clerk_id})-[:ABOUT]->(c:Company {clerk_id: $clerk_id, id: $id})
    RETURN i.id AS id, i.type AS type, i.title AS title, i.subtitle AS subtitle,
           i.occurred_at AS occurred_at, i.duration_minutes AS duration_minutes,
           i.channel AS channel, i.sentiment AS sentiment,
           i.participants AS participants,
           i.source_type AS source_type, i.source_url AS source_url,
           i.source_external_id AS source_external_id
    ORDER BY i.occurred_at DESC
    """
    interaction_rows = neo4j.execute_query(
        interactions_q, {"clerk_id": clerk_id, "id": company_id}
    )

    content_rows: List[Dict[str, Any]] = []
    if interaction_rows:
        try:
            ids = [r["id"] for r in interaction_rows if r.get("id")]
            if ids:
                placeholders = ",".join(["%s"] * len(ids))
                content_rows = postgres.execute_query(
                    f"""
                    SELECT neo4j_interaction_id, full_transcript, summary,
                           takeaways, topics, quotes, metrics_mentioned
                    FROM interaction_content
                    WHERE owner_clerk_id = %s
                      AND neo4j_interaction_id IN ({placeholders})
                    """,
                    tuple([clerk_id, *ids]),
                ) or []
        except Exception as e:
            logger.warning("Failed to fetch interaction_content: %s", e)
    content_by_id = {r["neo4j_interaction_id"]: r for r in content_rows}

    interactions: List[Dict[str, Any]] = []
    for r in interaction_rows:
        content = content_by_id.get(r.get("id")) or {}
        what_happened = {
            "summary": content.get("summary") or "",
            "takeaways": _ensure_list(_json_loaded(content.get("takeaways"))),
            "topics": _ensure_list(_json_loaded(content.get("topics"))),
            "metrics_mentioned": _ensure_list(_json_loaded(content.get("metrics_mentioned"))),
            "quotes": _ensure_list(_json_loaded(content.get("quotes"))),
        }
        source = None
        if r.get("source_type"):
            source = {
                "type": r["source_type"],
                "url": r.get("source_url"),
                "external_id": r.get("source_external_id"),
            }
        interactions.append({
            "id": r.get("id") or "",
            "type": r.get("type") or "other",
            "title": r.get("title") or "",
            "subtitle": r.get("subtitle"),
            "occurred_at": r.get("occurred_at") or "",
            "duration_minutes": r.get("duration_minutes"),
            "channel": r.get("channel") or "other",
            "sentiment": r.get("sentiment") or "neutral",
            "participants": _ensure_list(r.get("participants")),
            "source": source,
            "what_happened": what_happened,
        })

    # ---- Team debate + decision record + extraction meta (postgres) ----
    team_debate = {
        "detected": False,
        "for_arguments": [],
        "against_arguments": [],
        "open_questions": [],
    }
    try:
        td_rows = postgres.execute_query(
            """
            SELECT detected, for_arguments, against_arguments, open_questions
            FROM team_debates
            WHERE owner_clerk_id = %s AND company_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (clerk_id, company_id),
        )
        if td_rows:
            row = td_rows[0]
            team_debate = {
                "detected": bool(row.get("detected")),
                "for_arguments": _ensure_list(_json_loaded(row.get("for_arguments"))),
                "against_arguments": _ensure_list(_json_loaded(row.get("against_arguments"))),
                "open_questions": _ensure_list(_json_loaded(row.get("open_questions"))),
            }
    except Exception as e:
        logger.warning("team_debates fetch failed for %s: %s", company_id, e)

    decision_record = {
        "verdict": c.get("verdict") or "tracking",
        "decided_at": c.get("decided_at"),
        "rationale": None,
        "conditions": [],
        "check_size": c.get("check_size"),
        "valuation": c.get("valuation"),
    }
    try:
        dr_rows = postgres.execute_query(
            """
            SELECT verdict, rationale, conditions, check_size, valuation, decided_at
            FROM decision_records
            WHERE owner_clerk_id = %s AND company_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (clerk_id, company_id),
        )
        if dr_rows:
            row = dr_rows[0]
            decision_record = {
                "verdict": row.get("verdict") or "tracking",
                "decided_at": row.get("decided_at").isoformat() if row.get("decided_at") else None,
                "rationale": row.get("rationale"),
                "conditions": _ensure_list(_json_loaded(row.get("conditions"))),
                "check_size": row.get("check_size"),
                "valuation": row.get("valuation"),
            }
    except Exception as e:
        logger.warning("decision_records fetch failed for %s: %s", company_id, e)

    extraction_meta = {
        "model": "unknown",
        "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "confidence": 0.0,
        "warnings": [],
    }
    try:
        em_rows = postgres.execute_query(
            """
            SELECT model_used, confidence, warnings, extracted_at
            FROM extraction_metadata
            WHERE owner_clerk_id = %s AND company_id = %s
            ORDER BY extracted_at DESC LIMIT 1
            """,
            (clerk_id, company_id),
        )
        if em_rows:
            row = em_rows[0]
            extraction_meta = {
                "model": row.get("model_used") or "unknown",
                "extracted_at": (
                    row["extracted_at"].isoformat() if row.get("extracted_at") else
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                ),
                "confidence": float(row.get("confidence") or 0.0),
                "warnings": _ensure_list(_json_loaded(row.get("warnings"))),
            }
    except Exception as e:
        logger.warning("extraction_metadata fetch failed for %s: %s", company_id, e)

    return {
        "company": {
            "id": c.get("id"),
            "name": c.get("name") or "Unknown",
            "one_liner": c.get("one_liner"),
            "sector": c.get("sector"),
            "stage": c.get("stage"),
            "location": c.get("location"),
            "website": c.get("website"),
            "tags": _ensure_list(c.get("tags")),
            "first_met_at": c.get("first_met_at"),
            "key_strengths": _ensure_list(c.get("key_strengths")),
            "key_concerns": _ensure_list(c.get("key_concerns")),
            "deal_momentum": c.get("deal_momentum"),
            "source": (
                {"types": _ensure_list(c.get("source_types")), "external_id": c.get("external_id")}
                if c.get("external_id") or c.get("source_types") else None
            ),
        },
        "deal_status": {
            "pipeline_stage": c.get("pipeline_stage") or "Tracking",
            "last_touch_at": c.get("last_touch_at") or "",
            "next_step": c.get("next_step"),
            "owner": owner_name or None,
        },
        "contacts": contacts,
        "interactions": interactions,
        "team_debate": team_debate,
        "decision_record": decision_record,
        "company_now": {
            "domain": None,
            "fetched_at": None,
            "headcount": None,
            "open_roles": None,
            "funding": {"last_round_stage": None, "last_round_amount_usd": None, "total_raised_usd": None},
            "latest_news": [],
            "signals": [],
        },
        "extraction_meta": extraction_meta,
    }


# ----------------------------------------------------------------------------
# Dashboard summary — per-user KPIs, momentum split, funnel, trend, activity
# ----------------------------------------------------------------------------

@router.get("/dashboard/summary")
async def dashboard_summary(
    request: Request,
    user: ClerkUser = Depends(get_current_user_provisioned),
) -> Dict[str, Any]:
    _, neo4j = _get_clients(request)

    rows = neo4j.execute_query(
        """
        MATCH (c:Company {clerk_id: $clerk_id})
        OPTIONAL MATCH (p:VCPartner {clerk_id: $clerk_id})-[:OWNS]->(c)
        RETURN c.id AS id, c.name AS name, c.sector AS sector,
               c.pipeline_stage AS pipeline_stage,
               c.deal_momentum AS momentum,
               c.verdict AS verdict,
               c.first_met_at AS first_met_at,
               c.last_touch_at AS last_touch_at,
               coalesce(p.name, '') AS owner
        ORDER BY coalesce(c.last_touch_at, '') DESC
        """,
        {"clerk_id": user.clerk_id},
    )

    total = len(rows)
    invested = sum(1 for r in rows if (r.get("verdict") or "") == "invested")
    accelerating = sum(1 for r in rows if (r.get("momentum") or "") == "accelerating")
    needs_followup = sum(1 for r in rows if (r.get("pipeline_stage") or "") != "Decision")

    pipeline_stages = ["Tracking", "First call", "Diligence", "IC review", "Decision"]
    funnel = [
        {"stage": s, "count": sum(1 for r in rows if r.get("pipeline_stage") == s)}
        for s in pipeline_stages
    ]

    momentums = ["accelerating", "stable", "stalling", "dead"]
    momentum_split = [
        {"label": m, "count": sum(1 for r in rows if r.get("momentum") == m)}
        for m in momentums
    ]

    trend: List[Dict[str, Any]] = []
    if rows:
        now = datetime.now(timezone.utc)
        for back in range(5, -1, -1):
            year = now.year + (now.month - 1 - back) // 12
            month = (now.month - 1 - back) % 12 + 1
            key = f"{year:04d}-{month:02d}"
            count = sum(
                1 for r in rows
                if isinstance(r.get("first_met_at"), str)
                and r["first_met_at"][:7] <= key
            )
            trend.append({
                "month": datetime(year, month, 1).strftime("%b"),
                "value": count,
            })

    recent_activity = [
        {
            "id": f"act_{r['id']}",
            "companyId": r["id"],
            "company": r.get("name") or "Unknown",
            "text": (
                f"{r.get('pipeline_stage') or 'Tracking'} · "
                f"{(r.get('verdict') or 'tracking').title()}"
            ),
            "at": r.get("last_touch_at") or "",
        }
        for r in rows[:8] if r.get("id")
    ]

    top_deals = [
        {
            "id": r["id"],
            "name": r.get("name") or "Unknown",
            "sector": r.get("sector") or "Uncategorized",
            "pipeline_stage": r.get("pipeline_stage") or "Tracking",
            "momentum": r.get("momentum") or "stable",
            "verdict": r.get("verdict") or "tracking",
            "owner": r.get("owner") or "Unassigned",
            "last_touch_at": r.get("last_touch_at") or "",
        }
        for r in rows[:6] if r.get("id")
    ]

    return {
        "kpis": {
            "total_deals": total,
            "invested": invested,
            "accelerating": accelerating,
            "needs_followup": needs_followup,
        },
        "funnel": funnel,
        "momentum_split": momentum_split,
        "pipeline_trend": trend,
        "recent_activity": recent_activity,
        "top_deals": top_deals,
    }
