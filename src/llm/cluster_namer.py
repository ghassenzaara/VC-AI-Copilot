"""LLM-based Cluster Naming - Generates meaningful names for market clusters

This module uses IBM WatsonX (Llama 3.3 70B Instruct) to analyze cluster
metadata and generate descriptive, professional names for market map clusters.
"""

import logging
from typing import Dict, Any, List, Tuple

from src.llm.watsonx_client import WatsonXClient
from src.database.postgres import PostgresClient


logger = logging.getLogger(__name__)


class ClusterNamer:
    """Generates LLM-powered names and descriptions for clusters"""
    
    def __init__(
        self,
        watsonx_client: WatsonXClient,
        postgres_client: PostgresClient
    ):
        """Initialize cluster namer
        
        Args:
            watsonx_client: WatsonX client (should use "pro" model)
            postgres_client: PostgreSQL client
        """
        self.client = watsonx_client
        self.postgres = postgres_client
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def name_all_clusters(self) -> Dict[str, Any]:
        """Generate names for all clusters
        
        Returns:
            Dict with naming statistics
        """
        self.logger.info("Starting cluster naming...")
        
        # Fetch all clusters
        query = """
            SELECT 
                mc.id,
                mc.cluster_number,
                cm.common_sectors,
                cm.common_stages,
                cm.common_tags,
                cm.sample_companies
            FROM market_clusters mc
            LEFT JOIN cluster_metadata cm ON cm.cluster_id = mc.id
            WHERE mc.name IS NULL
        """
        clusters = self.postgres.execute_query(query, fetch=True)
        
        if not clusters:
            self.logger.info("No unnamed clusters found")
            return {"named": 0}
        
        self.logger.info(f"Naming {len(clusters)} clusters...")
        
        named_count = 0
        for cluster in clusters:
            try:
                name, description = self._generate_cluster_name(cluster)
                self._store_cluster_name(cluster['id'], name, description)
                named_count += 1
                self.logger.info(f"Cluster {cluster['cluster_number']}: {name}")
            except Exception as e:
                self.logger.error(f"Failed to name cluster {cluster['id']}: {e}")
        
        return {"named": named_count, "total": len(clusters)}
    
    def _generate_cluster_name(
        self,
        cluster: Dict[str, Any]
    ) -> Tuple[str, str]:
        """Generate name and description for a cluster
        
        Returns:
            (name, description)
        """
        prompt = self._build_naming_prompt(cluster)
        
        response = self.client.generate_json(
            prompt=prompt,
            temperature=0.3,  # Slightly creative
            max_tokens=500
        )
        
        name = response.get('name', f"Cluster {cluster['cluster_number']}")
        description = response.get('description', '')
        
        return name, description
    
    def _build_naming_prompt(self, cluster: Dict[str, Any]) -> str:
        """Build prompt for cluster naming"""
        # Parse JSON fields
        import json
        common_sectors = json.loads(cluster.get('common_sectors') or '[]')
        common_stages = json.loads(cluster.get('common_stages') or '[]')
        common_tags = json.loads(cluster.get('common_tags') or '[]')
        sample_companies = json.loads(cluster.get('sample_companies') or '[]')
        
        return f"""You are analyzing a cluster of similar companies in a VC portfolio.

**Cluster Metadata:**
- Common Sectors: {common_sectors}
- Common Stages: {common_stages}
- Common Tags: {common_tags}

**Sample Companies:**
{self._format_sample_companies(sample_companies)}

**Task:**
Generate a concise, descriptive name for this cluster that captures the common theme.
Also provide a 1-2 sentence description explaining what unites these companies.

**Guidelines:**
- Name should be 2-5 words, professional, and specific
- Focus on the business model, technology, or market segment
- Examples: "Enterprise AI Infrastructure", "B2B SaaS Platforms", "Climate Tech Hardware"
- Avoid generic terms like "Tech Startups" or "Software Companies"

**Output Format:**
Return ONLY valid JSON:
{{
  "name": "Cluster Name Here",
  "description": "Brief description of what unites these companies."
}}"""
    
    def _format_sample_companies(self, sample_companies: List[Dict]) -> str:
        """Format sample companies for prompt"""
        if not sample_companies:
            return "No sample companies available"
        
        lines = []
        for i, company in enumerate(sample_companies, 1):
            name = company.get('name', 'Unknown')
            one_liner = company.get('one_liner', 'No description')
            lines.append(f"{i}. {name}: {one_liner}")
        
        return "\n".join(lines)
    
    def _store_cluster_name(
        self,
        cluster_id: str,
        name: str,
        description: str
    ):
        """Store cluster name and description"""
        query = """
            UPDATE market_clusters
            SET name = %s,
                description = %s,
                updated_at = NOW()
            WHERE id = %s
        """
        self.postgres.execute_query(query, (name, description, cluster_id))


# Made with Bob