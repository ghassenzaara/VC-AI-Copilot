"""Mock data loader for mock_data.json.

The mock file is already shaped for direct LLM consumption: each company entry
carries an `interactions[]` array where every item has rich human-readable
fields (granola has `summary_text` + full `transcript`, gmail has `body` +
`subject`, slack has `text` + `reactions`, etc.). The relevance filter and
extraction engine both JSON-serialize whatever dict they receive and hand it to
the LLM — no normalization needed.

This loader is therefore a near-passthrough. It only:
  1. Promotes `organization.name` / `organization.domain` to top-level
     `company_name` / `company_domain` (what the engines key on).
  2. Keeps the CRM-style top-level fields (`organization`, `founder`,
     `opportunity`, `field_values`) so the extractor can see sector/stage/MRR/
     sentiment/owner — which would otherwise be lost.
  3. Leaves the interactions array exactly as written in the file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


logger = logging.getLogger(__name__)


def normalize_company(raw_company: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a single mock_data.json company entry for the pipeline.

    Pass-through: no shape changes to interactions.
    """
    org = raw_company.get("organization") or {}
    return {
        "company_name": org.get("name") or raw_company.get("id") or "Unknown",
        "company_domain": org.get("domain") or "",
        "company_id": org.get("domain") or raw_company.get("id"),
        "interactions": raw_company.get("interactions") or [],
        # CRM-style facts the extractor wants to see alongside the interactions.
        "organization": org,
        "founder": raw_company.get("founder") or {},
        "opportunity": raw_company.get("opportunity") or {},
        "field_values": raw_company.get("field_values") or {},
        "metadata": {
            "mock_id": raw_company.get("id"),
            "sources": raw_company.get("sources") or [],
            "organization_domain": org.get("domain"),
        },
    }


def load_mock_companies(path: Optional[Path | str] = None) -> List[Dict[str, Any]]:
    """Load all companies from mock_data.json.

    Args:
        path: Path to mock_data.json. Defaults to the project-root copy.

    Returns:
        List of pipeline-ready company dicts.
    """
    if path is None:
        path = Path(__file__).resolve().parents[2] / "mock_data.json"
    path = Path(path)

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    raw_companies: Iterable[Dict[str, Any]] = payload.get("companies") or []
    return [normalize_company(c) for c in raw_companies]


# Made with Bob
