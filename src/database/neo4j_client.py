"""Neo4j database connection and operations"""

import logging
import threading
from typing import Optional, List, Dict, Any, Iterator
from contextlib import contextmanager
from neo4j import GraphDatabase, Driver, Session, Transaction

from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Neo4jClient:
    """Neo4j client for graph database operations"""
    
    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self.driver: Optional[Driver] = None
    
    def connect(self):
        """Establish connection to Neo4j"""
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            # Verify connectivity
            self.driver.verify_connectivity()
            logger.info("Neo4j connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
    
    def close(self):
        """Close Neo4j connection"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")
    
    @contextmanager
    def get_session(self) -> Iterator[Session]:
        """Get a Neo4j session"""
        if not self.driver:
            raise RuntimeError("Driver not initialized. Call connect() first.")
        
        session = self.driver.session()
        try:
            yield session
        finally:
            session.close()
    
    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return results"""
        with self.get_session() as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]
    
    def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a write query in a transaction"""
        with self.get_session() as session:
            result = session.execute_write(
                lambda tx: list(tx.run(query, parameters or {}))
            )
            return [dict(record) for record in result]
    
    def create_company(
        self,
        company_id: str,
        name: str,
        properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a Company node"""
        query = """
            MERGE (c:Company {id: $id})
            SET c.name = $name
            SET c += $properties
            RETURN c
        """
        
        result = self.execute_write(
            query,
            {
                "id": company_id,
                "name": name,
                "properties": properties
            }
        )
        return result[0]["c"] if result else {}
    
    def create_person(
        self,
        person_id: str,
        name: str,
        properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a Person node"""
        query = """
            MERGE (p:Person {id: $id})
            SET p.name = $name
            SET p += $properties
            RETURN p
        """
        
        result = self.execute_write(
            query,
            {
                "id": person_id,
                "name": name,
                "properties": properties
            }
        )
        return result[0]["p"] if result else {}
    
    def create_vc_partner(
        self,
        partner_id: str,
        name: str,
        properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a VCPartner node"""
        query = """
            MERGE (v:VCPartner {id: $id})
            SET v.name = $name
            SET v += $properties
            RETURN v
        """
        
        result = self.execute_write(
            query,
            {
                "id": partner_id,
                "name": name,
                "properties": properties
            }
        )
        return result[0]["v"] if result else {}
    
    def create_interaction(
        self,
        interaction_id: str,
        properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create an Interaction node"""
        query = """
            MERGE (i:Interaction {id: $id})
            SET i += $properties
            RETURN i
        """
        
        result = self.execute_write(
            query,
            {
                "id": interaction_id,
                "properties": properties
            }
        )
        return result[0]["i"] if result else {}
    
    def create_sector(self, sector_name: str) -> Dict[str, Any]:
        """Create or get a Sector node"""
        query = """
            MERGE (s:Sector {name: $name})
            RETURN s
        """
        
        result = self.execute_write(query, {"name": sector_name})
        return result[0]["s"] if result else {}
    
    def create_tag(self, tag_name: str) -> Dict[str, Any]:
        """Create or get a Tag node"""
        query = """
            MERGE (t:Tag {name: $name})
            RETURN t
        """
        
        result = self.execute_write(query, {"name": tag_name})
        return result[0]["t"] if result else {}
    
    def create_relationship(
        self,
        from_id: str,
        from_label: str,
        to_id: str,
        to_label: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create a relationship between two nodes (both matched by `id` property)"""
        query = f"""
            MATCH (a:{from_label} {{id: $from_id}})
            MATCH (b:{to_label} {{id: $to_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r += $properties
            RETURN r
        """

        result = self.execute_write(
            query,
            {
                "from_id": from_id,
                "to_id": to_id,
                "properties": properties or {}
            }
        )
        if not result:
            logger.warning(
                f"create_relationship no-op: ({from_label} id={from_id})-"
                f"[:{rel_type}]->({to_label} id={to_id}) — node(s) missing"
            )
        return len(result) > 0

    def link_company_to_sector(self, company_id: str, sector_name: str) -> bool:
        """Link a Company to a Sector node (matched by `name`)"""
        query = """
            MATCH (c:Company {id: $cid})
            MATCH (s:Sector {name: $sname})
            MERGE (c)-[r:IN_SECTOR]->(s)
            RETURN r
        """
        result = self.execute_write(query, {"cid": company_id, "sname": sector_name})
        return len(result) > 0

    def link_company_to_tag(self, company_id: str, tag_name: str) -> bool:
        """Link a Company to a Tag node (matched by `name`)"""
        query = """
            MATCH (c:Company {id: $cid})
            MATCH (t:Tag {name: $tname})
            MERGE (c)-[r:TAGGED_WITH]->(t)
            RETURN r
        """
        result = self.execute_write(query, {"cid": company_id, "tname": tag_name})
        return len(result) > 0
    
    def create_similar_to_relationship(
        self,
        company_id_1: str,
        company_id_2: str,
        score: float
    ) -> bool:
        """Create SIMILAR_TO relationship between companies"""
        query = """
            MATCH (c1:Company {id: $id1})
            MATCH (c2:Company {id: $id2})
            MERGE (c1)-[r:SIMILAR_TO]->(c2)
            SET r.score = $score
            RETURN r
        """
        
        result = self.execute_write(
            query,
            {
                "id1": company_id_1,
                "id2": company_id_2,
                "score": score
            }
        )
        return len(result) > 0
    
    def get_company_by_id(self, company_id: str) -> Optional[Dict[str, Any]]:
        """Get company by ID with all relationships"""
        query = """
            MATCH (c:Company {id: $id})
            OPTIONAL MATCH (c)-[:HAS_CONTACT]->(p:Person)
            OPTIONAL MATCH (c)-[:IN_SECTOR]->(s:Sector)
            OPTIONAL MATCH (c)-[:TAGGED_WITH]->(t:Tag)
            OPTIONAL MATCH (c)<-[:ABOUT]-(i:Interaction)
            OPTIONAL MATCH (v:VCPartner)-[:OWNS]->(c)
            RETURN c, 
                   collect(DISTINCT p) as contacts,
                   s,
                   collect(DISTINCT t) as tags,
                   collect(DISTINCT i) as interactions,
                   collect(DISTINCT v) as owners
        """
        
        result = self.execute_query(query, {"id": company_id})
        return result[0] if result else None
    
    def find_similar_companies(
        self,
        company_id: str,
        threshold: float = 0.75,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Find similar companies"""
        query = """
            MATCH (c:Company {id: $id})-[r:SIMILAR_TO]->(similar:Company)
            WHERE r.score >= $threshold
            RETURN similar, r.score as similarity_score
            ORDER BY r.score DESC
            LIMIT $limit
        """
        
        return self.execute_query(
            query,
            {
                "id": company_id,
                "threshold": threshold,
                "limit": limit
            }
        )
    
    def get_recent_interactions(
        self,
        company_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent interactions for a company"""
        query = """
            MATCH (c:Company {id: $id})<-[:ABOUT]-(i:Interaction)
            RETURN i
            ORDER BY i.occurred_at DESC
            LIMIT $limit
        """
        
        return self.execute_query(query, {"id": company_id, "limit": limit})
    
    # Explicit, idempotent schema statements (BUG-051: avoids fragile
    # split-on-semicolon parsing of comment-heavy .cypher files).
    SCHEMA_STATEMENTS: List[str] = [
        "CREATE CONSTRAINT company_id IF NOT EXISTS FOR (c:Company) REQUIRE c.id IS UNIQUE",
        "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.name)",
        "CREATE INDEX company_sector IF NOT EXISTS FOR (c:Company) ON (c.sector)",
        "CREATE INDEX company_stage IF NOT EXISTS FOR (c:Company) ON (c.stage)",
        "CREATE INDEX company_verdict IF NOT EXISTS FOR (c:Company) ON (c.verdict)",
        "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE",
        "CREATE INDEX person_email IF NOT EXISTS FOR (p:Person) ON (p.email)",
        "CREATE CONSTRAINT vc_partner_id IF NOT EXISTS FOR (v:VCPartner) REQUIRE v.id IS UNIQUE",
        "CREATE INDEX vc_partner_name IF NOT EXISTS FOR (v:VCPartner) ON (v.name)",
        "CREATE CONSTRAINT interaction_id IF NOT EXISTS FOR (i:Interaction) REQUIRE i.id IS UNIQUE",
        "CREATE INDEX interaction_type IF NOT EXISTS FOR (i:Interaction) ON (i.type)",
        "CREATE INDEX interaction_occurred_at IF NOT EXISTS FOR (i:Interaction) ON (i.occurred_at)",
        "CREATE CONSTRAINT sector_name IF NOT EXISTS FOR (s:Sector) REQUIRE s.name IS UNIQUE",
        "CREATE CONSTRAINT tag_name IF NOT EXISTS FOR (t:Tag) REQUIRE t.name IS UNIQUE",
    ]

    def initialize_schema(self) -> None:
        """Initialize Neo4j schema (constraints and indexes). Idempotent."""
        with self.get_session() as session:
            for stmt in self.SCHEMA_STATEMENTS:
                try:
                    session.run(stmt)
                    logger.debug(f"Executed schema statement: {stmt[:60]}...")
                except Exception as e:
                    logger.warning(f"Schema statement skipped ({stmt[:40]}...): {e}")
        logger.info("Neo4j schema initialized")


# Global client instance (thread-safe lazy init — BUG-052)
_neo4j_client: Optional[Neo4jClient] = None
_neo4j_client_lock = threading.Lock()


def get_neo4j_driver() -> Neo4jClient:
    """Get or create Neo4j client (double-checked locking)."""
    global _neo4j_client
    if _neo4j_client is None:
        with _neo4j_client_lock:
            if _neo4j_client is None:
                client = Neo4jClient()
                client.connect()
                _neo4j_client = client
    return _neo4j_client

# Made with Bob
