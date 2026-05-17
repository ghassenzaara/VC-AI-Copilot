"""LLM-based Cluster Naming — names each cluster from its actual members.

Reads `:Company-[:BELONGS_TO_CLUSTER]->:Cluster` straight from Neo4j (per user)
so the LLM sees every company in the cluster, not a stale 5-row sample. Names
are written back to both `market_clusters.name/description` (PG) and the
`:Cluster` node in Neo4j.
"""

import logging
from collections import Counter
from typing import Any, Dict, List, Tuple

from src.llm.watsonx_client import WatsonXClient
from src.database.postgres import PostgresClient
from src.database.neo4j_client import Neo4jClient


logger = logging.getLogger(__name__)


class ClusterNamer:
    """Generates LLM-powered names and descriptions for clusters."""

    def __init__(
        self,
        watsonx_client: WatsonXClient,
        postgres_client: PostgresClient,
        neo4j_client: Neo4jClient,
    ):
        self.client = watsonx_client
        self.postgres = postgres_client
        self.neo4j = neo4j_client
        self.logger = logging.getLogger(self.__class__.__name__)

    def name_all_clusters(self, clerk_id: str) -> Dict[str, Any]:
        self.logger.info("Starting cluster naming for user=%s", clerk_id)

        # Every cluster the user owns that doesn't already have a name.
        clusters = self.postgres.execute_query(
            """
            SELECT id, cluster_number
            FROM market_clusters
            WHERE owner_clerk_id = %s AND name IS NULL
            ORDER BY cluster_number
            """,
            (clerk_id,),
            fetch=True,
        )

        if not clusters:
            self.logger.info("No unnamed clusters found for user=%s", clerk_id)
            return {"named": 0, "total": 0}

        self.logger.info("Naming %d clusters for user=%s...", len(clusters), clerk_id)

        named_count = 0
        for cluster in clusters:
            cluster_id = str(cluster['id'])
            cluster_number = cluster['cluster_number']
            try:
                companies = self._fetch_cluster_members(clerk_id, cluster_id)
                if not companies:
                    self.logger.warning(
                        "Cluster %s (#%s) has zero members — skipping naming",
                        cluster_id, cluster_number,
                    )
                    continue

                name, description = self._generate_cluster_name(cluster_number, companies)
                self._store_cluster_name(clerk_id, cluster_id, name, description)
                named_count += 1
                self.logger.info(
                    "Cluster %s (%d companies): %s",
                    cluster_number, len(companies), name,
                )
            except Exception as e:
                self.logger.error("Failed to name cluster %s: %s", cluster_id, e)

        return {"named": named_count, "total": len(clusters)}

    # ------------------------------------------------------------------
    # Naming pipeline
    # ------------------------------------------------------------------

    def _fetch_cluster_members(
        self, clerk_id: str, cluster_id: str
    ) -> List[Dict[str, Any]]:
        """Return every company in the cluster with the fields the LLM needs."""
        query = """
            MATCH (cl:Cluster {clerk_id: $clerk_id, id: $cluster_id})
                  <-[:BELONGS_TO_CLUSTER]-(c:Company {clerk_id: $clerk_id})
            RETURN c.name           AS name,
                   c.one_liner      AS one_liner,
                   c.sector         AS sector,
                   c.stage          AS stage,
                   c.tags           AS tags,
                   c.key_strengths  AS key_strengths,
                   c.deal_momentum  AS deal_momentum
            ORDER BY c.name
        """
        return self.neo4j.execute_query(
            query, {"clerk_id": clerk_id, "cluster_id": cluster_id}
        )

    def _generate_cluster_name(
        self,
        cluster_number: int,
        companies: List[Dict[str, Any]],
    ) -> Tuple[str, str]:
        prompt = self._build_naming_prompt(cluster_number, companies)
        response = self.client.generate_json(
            prompt=prompt,
            temperature=0.3,
            max_tokens=500,
        )
        name = response.get('name') or f"Cluster {cluster_number}"
        description = response.get('description') or ''
        return name, description

    def _build_naming_prompt(
        self,
        cluster_number: int,
        companies: List[Dict[str, Any]],
    ) -> str:
        sectors = [c['sector'] for c in companies if c.get('sector')]
        stages = [c['stage'] for c in companies if c.get('stage')]
        tags: List[str] = []
        for c in companies:
            if c.get('tags') and isinstance(c['tags'], list):
                tags.extend(c['tags'])

        common_sectors = [s for s, _ in Counter(sectors).most_common(5)]
        common_stages = [s for s, _ in Counter(stages).most_common(3)]
        common_tags = [t for t, _ in Counter(tags).most_common(8)]

        company_lines = []
        for i, c in enumerate(companies, 1):
            bits = [c.get('name') or 'Unknown']
            if c.get('sector'):
                bits.append(f"sector={c['sector']}")
            if c.get('stage'):
                bits.append(f"stage={c['stage']}")
            line = f"{i}. {bits[0]}"
            if len(bits) > 1:
                line += f" ({', '.join(bits[1:])})"
            if c.get('one_liner'):
                line += f" — {c['one_liner']}"
            company_lines.append(line)
        companies_block = "\n".join(company_lines)

        return f"""You are naming a market cluster of similar VC-tracked companies.

The cluster contains {len(companies)} companies, listed below with their sector, stage, and one-liner.

**Aggregate signals across the cluster:**
- Sectors (most common first): {common_sectors or 'none'}
- Stages (most common first): {common_stages or 'none'}
- Tags (most common first): {common_tags or 'none'}

**All companies in the cluster:**
{companies_block}

**Task:**
Read the full list of companies above and produce:
1. A concise, specific cluster name (2-5 words) that captures the PROBLEM these companies solve or the DOMAIN they serve.
2. A 1-2 sentence description explaining the shared problem space or end-user.

**CRITICAL — Name by problem, not by technology:**
- Almost every company today uses AI / LLMs / agentic workflows. AI is the tool, NOT the differentiator.
- Do NOT use the words "AI", "LLM", "Agent", "Agentic", "GPT", "ML", "Machine Learning", "Generative" in the name.
- Cluster the companies by the WHO they sell to or the WHAT problem they solve.
- Good examples (problem-focused): "Construction Project Management", "Legal Contract Review",
  "Healthcare Diagnostics", "Developer Productivity Tools", "Customer Support Automation",
  "Logistics & Freight", "Personal Finance", "Recruiting & Hiring", "Sales Outreach",
  "Climate Monitoring", "Cybersecurity Detection".
- Bad examples (technology-focused — DO NOT do this): "AI for Construction",
  "Agentic Legal Tools", "LLM-Powered Support", "Generative Sales Bots".
- Avoid filler words like "Startups", "Platform", "Solutions" unless they truly add meaning.

**Output Format:**
Return ONLY valid JSON, no prose:
{{
  "name": "Cluster Name Here",
  "description": "Brief description of what unites these companies — what problem or who they serve."
}}"""

    def _store_cluster_name(
        self,
        clerk_id: str,
        cluster_id: str,
        name: str,
        description: str,
    ):
        self.postgres.execute_query(
            """
            UPDATE market_clusters
            SET name = %s,
                description = %s,
                updated_at = NOW()
            WHERE id = %s AND owner_clerk_id = %s
            """,
            (name, description, cluster_id, clerk_id),
            fetch=False,
        )

        self.neo4j.execute_write(
            """
            MATCH (cl:Cluster {clerk_id: $clerk_id, id: $cluster_id})
            SET cl.name = $name,
                cl.description = $description
            """,
            {
                "clerk_id": clerk_id,
                "cluster_id": cluster_id,
                "name": name,
                "description": description,
            },
        )
