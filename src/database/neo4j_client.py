"""Neo4j database connection and operations (multi-tenant: per-clerk_id subgraphs)

Every domain node carries a `clerk_id` property and is connected to a
`:User {clerk_id}` node via `[:OWNS]`. Uniqueness is composite on
`(clerk_id, id)` so two users can both have a Company with id="acme" without
collision.
"""

import logging
import threading
from typing import Optional, List, Dict, Any, Iterator
from contextlib import contextmanager
from neo4j import GraphDatabase, Driver, Session

from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Neo4jClient:
    """Neo4j client for graph database operations (per-user isolated)."""

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
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            self.driver.verify_connectivity()
            logger.info("Neo4j connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise

    def close(self):
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")

    @contextmanager
    def get_session(self) -> Iterator[Session]:
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
        with self.get_session() as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]

    def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            result = session.execute_write(
                lambda tx: list(tx.run(query, parameters or {}))
            )
            return [dict(record) for record in result]

    # ------------------------------------------------------------------
    # Node creation — every call requires clerk_id and links to :User
    # ------------------------------------------------------------------

    def create_company(
        self,
        clerk_id: str,
        company_id: str,
        name: str,
        properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        query = """
            MERGE (u:User {clerk_id: $clerk_id})
            MERGE (c:Company {clerk_id: $clerk_id, id: $id})
            SET c.name = $name
            SET c += $properties
            MERGE (u)-[:OWNS]->(c)
            RETURN c
        """
        result = self.execute_write(
            query,
            {
                "clerk_id": clerk_id,
                "id": company_id,
                "name": name,
                "properties": properties,
            },
        )
        return result[0]["c"] if result else {}

    def create_person(
        self,
        clerk_id: str,
        person_id: str,
        name: str,
        properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        query = """
            MERGE (u:User {clerk_id: $clerk_id})
            MERGE (p:Person {clerk_id: $clerk_id, id: $id})
            SET p.name = $name
            SET p += $properties
            MERGE (u)-[:OWNS]->(p)
            RETURN p
        """
        result = self.execute_write(
            query,
            {
                "clerk_id": clerk_id,
                "id": person_id,
                "name": name,
                "properties": properties,
            },
        )
        return result[0]["p"] if result else {}

    def create_vc_partner(
        self,
        clerk_id: str,
        partner_id: str,
        name: str,
        properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        query = """
            MERGE (u:User {clerk_id: $clerk_id})
            MERGE (v:VCPartner {clerk_id: $clerk_id, id: $id})
            SET v.name = $name
            SET v += $properties
            MERGE (u)-[:OWNS]->(v)
            RETURN v
        """
        result = self.execute_write(
            query,
            {
                "clerk_id": clerk_id,
                "id": partner_id,
                "name": name,
                "properties": properties,
            },
        )
        return result[0]["v"] if result else {}

    def create_interaction(
        self,
        clerk_id: str,
        interaction_id: str,
        properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        query = """
            MERGE (u:User {clerk_id: $clerk_id})
            MERGE (i:Interaction {clerk_id: $clerk_id, id: $id})
            SET i += $properties
            MERGE (u)-[:OWNS]->(i)
            RETURN i
        """
        result = self.execute_write(
            query,
            {
                "clerk_id": clerk_id,
                "id": interaction_id,
                "properties": properties,
            },
        )
        return result[0]["i"] if result else {}

    def create_sector(self, clerk_id: str, sector_name: str) -> Dict[str, Any]:
        query = """
            MERGE (u:User {clerk_id: $clerk_id})
            MERGE (s:Sector {clerk_id: $clerk_id, name: $name})
            MERGE (u)-[:OWNS]->(s)
            RETURN s
        """
        result = self.execute_write(
            query, {"clerk_id": clerk_id, "name": sector_name}
        )
        return result[0]["s"] if result else {}

    def create_tag(self, clerk_id: str, tag_name: str) -> Dict[str, Any]:
        query = """
            MERGE (u:User {clerk_id: $clerk_id})
            MERGE (t:Tag {clerk_id: $clerk_id, name: $name})
            MERGE (u)-[:OWNS]->(t)
            RETURN t
        """
        result = self.execute_write(
            query, {"clerk_id": clerk_id, "name": tag_name}
        )
        return result[0]["t"] if result else {}

    def create_relationship(
        self,
        clerk_id: str,
        from_id: str,
        from_label: str,
        to_id: str,
        to_label: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create a relationship between two id-based nodes scoped to one user."""
        query = f"""
            MATCH (a:{from_label} {{clerk_id: $clerk_id, id: $from_id}})
            MATCH (b:{to_label} {{clerk_id: $clerk_id, id: $to_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r += $properties
            RETURN r
        """
        result = self.execute_write(
            query,
            {
                "clerk_id": clerk_id,
                "from_id": from_id,
                "to_id": to_id,
                "properties": properties or {},
            },
        )
        if not result:
            logger.warning(
                "create_relationship no-op (user=%s): (%s id=%s)-[:%s]->(%s id=%s) — node(s) missing",
                clerk_id, from_label, from_id, rel_type, to_label, to_id,
            )
        return len(result) > 0

    def link_company_to_sector(self, clerk_id: str, company_id: str, sector_name: str) -> bool:
        query = """
            MATCH (c:Company {clerk_id: $clerk_id, id: $cid})
            MATCH (s:Sector {clerk_id: $clerk_id, name: $sname})
            MERGE (c)-[r:IN_SECTOR]->(s)
            RETURN r
        """
        result = self.execute_write(
            query, {"clerk_id": clerk_id, "cid": company_id, "sname": sector_name}
        )
        return len(result) > 0

    def link_company_to_tag(self, clerk_id: str, company_id: str, tag_name: str) -> bool:
        query = """
            MATCH (c:Company {clerk_id: $clerk_id, id: $cid})
            MATCH (t:Tag {clerk_id: $clerk_id, name: $tname})
            MERGE (c)-[r:TAGGED_WITH]->(t)
            RETURN r
        """
        result = self.execute_write(
            query, {"clerk_id": clerk_id, "cid": company_id, "tname": tag_name}
        )
        return len(result) > 0

    def create_similar_to_relationship(
        self,
        clerk_id: str,
        company_id_1: str,
        company_id_2: str,
        score: float
    ) -> bool:
        query = """
            MATCH (c1:Company {clerk_id: $clerk_id, id: $id1})
            MATCH (c2:Company {clerk_id: $clerk_id, id: $id2})
            MERGE (c1)-[r:SIMILAR_TO]->(c2)
            SET r.score = $score
            RETURN r
        """
        result = self.execute_write(
            query,
            {
                "clerk_id": clerk_id,
                "id1": company_id_1,
                "id2": company_id_2,
                "score": score,
            },
        )
        return len(result) > 0

    def get_company_by_id(
        self,
        clerk_id: str,
        company_id: str,
    ) -> Optional[Dict[str, Any]]:
        query = """
            MATCH (c:Company {clerk_id: $clerk_id, id: $id})
            OPTIONAL MATCH (c)-[:HAS_CONTACT]->(p:Person {clerk_id: $clerk_id})
            OPTIONAL MATCH (c)-[:IN_SECTOR]->(s:Sector {clerk_id: $clerk_id})
            OPTIONAL MATCH (c)-[:TAGGED_WITH]->(t:Tag {clerk_id: $clerk_id})
            OPTIONAL MATCH (c)<-[:ABOUT]-(i:Interaction {clerk_id: $clerk_id})
            OPTIONAL MATCH (v:VCPartner {clerk_id: $clerk_id})-[:OWNS]->(c)
            RETURN c,
                   collect(DISTINCT p) as contacts,
                   s,
                   collect(DISTINCT t) as tags,
                   collect(DISTINCT i) as interactions,
                   collect(DISTINCT v) as owners
        """
        result = self.execute_query(query, {"clerk_id": clerk_id, "id": company_id})
        return result[0] if result else None

    def find_similar_companies(
        self,
        clerk_id: str,
        company_id: str,
        threshold: float = 0.75,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        query = """
            MATCH (c:Company {clerk_id: $clerk_id, id: $id})-[r:SIMILAR_TO]->(similar:Company)
            WHERE r.score >= $threshold
            RETURN similar, r.score as similarity_score
            ORDER BY r.score DESC
            LIMIT $limit
        """
        return self.execute_query(
            query,
            {
                "clerk_id": clerk_id,
                "id": company_id,
                "threshold": threshold,
                "limit": limit,
            },
        )

    def get_recent_interactions(
        self,
        clerk_id: str,
        company_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        query = """
            MATCH (c:Company {clerk_id: $clerk_id, id: $id})<-[:ABOUT]-(i:Interaction {clerk_id: $clerk_id})
            RETURN i
            ORDER BY i.occurred_at DESC
            LIMIT $limit
        """
        return self.execute_query(
            query, {"clerk_id": clerk_id, "id": company_id, "limit": limit}
        )

    # ------------------------------------------------------------------
    # Bootstrap — composite uniqueness + clerk_id indexes
    # ------------------------------------------------------------------

    SCHEMA_STATEMENTS: List[str] = [
        # Tenant root
        "CREATE CONSTRAINT user_clerk_id IF NOT EXISTS FOR (u:User) REQUIRE u.clerk_id IS UNIQUE",
        # Composite uniqueness on (clerk_id, id|name)
        "CREATE CONSTRAINT company_clerk_unique IF NOT EXISTS FOR (c:Company) REQUIRE (c.clerk_id, c.id) IS UNIQUE",
        "CREATE CONSTRAINT person_clerk_unique IF NOT EXISTS FOR (p:Person) REQUIRE (p.clerk_id, p.id) IS UNIQUE",
        "CREATE CONSTRAINT vc_partner_clerk_unique IF NOT EXISTS FOR (v:VCPartner) REQUIRE (v.clerk_id, v.id) IS UNIQUE",
        "CREATE CONSTRAINT interaction_clerk_unique IF NOT EXISTS FOR (i:Interaction) REQUIRE (i.clerk_id, i.id) IS UNIQUE",
        "CREATE CONSTRAINT sector_clerk_unique IF NOT EXISTS FOR (s:Sector) REQUIRE (s.clerk_id, s.name) IS UNIQUE",
        "CREATE CONSTRAINT tag_clerk_unique IF NOT EXISTS FOR (t:Tag) REQUIRE (t.clerk_id, t.name) IS UNIQUE",
        "CREATE CONSTRAINT cluster_clerk_unique IF NOT EXISTS FOR (cl:Cluster) REQUIRE (cl.clerk_id, cl.id) IS UNIQUE",
        # Per-user lookup indexes
        "CREATE INDEX company_clerk_id IF NOT EXISTS FOR (c:Company) ON (c.clerk_id)",
        "CREATE INDEX person_clerk_id IF NOT EXISTS FOR (p:Person) ON (p.clerk_id)",
        "CREATE INDEX interaction_clerk_id IF NOT EXISTS FOR (i:Interaction) ON (i.clerk_id)",
        "CREATE INDEX cluster_clerk_id IF NOT EXISTS FOR (cl:Cluster) ON (cl.clerk_id)",
        # Existing search indexes
        "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.name)",
        "CREATE INDEX company_sector IF NOT EXISTS FOR (c:Company) ON (c.sector)",
        "CREATE INDEX company_stage IF NOT EXISTS FOR (c:Company) ON (c.stage)",
        "CREATE INDEX company_verdict IF NOT EXISTS FOR (c:Company) ON (c.verdict)",
        "CREATE INDEX person_email IF NOT EXISTS FOR (p:Person) ON (p.email)",
        "CREATE INDEX vc_partner_name IF NOT EXISTS FOR (v:VCPartner) ON (v.name)",
        "CREATE INDEX interaction_type IF NOT EXISTS FOR (i:Interaction) ON (i.type)",
        "CREATE INDEX interaction_occurred_at IF NOT EXISTS FOR (i:Interaction) ON (i.occurred_at)",
    ]

    # Old (pre-multi-tenant) constraints we need to drop so they don't conflict
    # with the new composite uniqueness on (clerk_id, id|name).
    LEGACY_CONSTRAINTS_TO_DROP: List[str] = [
        "DROP CONSTRAINT company_id IF EXISTS",
        "DROP CONSTRAINT person_id IF EXISTS",
        "DROP CONSTRAINT vc_partner_id IF EXISTS",
        "DROP CONSTRAINT interaction_id IF EXISTS",
        "DROP CONSTRAINT sector_name IF EXISTS",
        "DROP CONSTRAINT tag_name IF EXISTS",
    ]

    def initialize_schema(self) -> None:
        """Initialize Neo4j schema (drops legacy single-col constraints, then
        creates composite-per-user ones). Idempotent."""
        with self.get_session() as session:
            for stmt in self.LEGACY_CONSTRAINTS_TO_DROP:
                try:
                    session.run(stmt)
                    logger.debug("Dropped legacy constraint: %s", stmt)
                except Exception as e:
                    logger.debug("Legacy drop skipped (%s): %s", stmt, e)
            for stmt in self.SCHEMA_STATEMENTS:
                try:
                    session.run(stmt)
                    logger.debug("Executed schema statement: %s", stmt[:60])
                except Exception as e:
                    logger.warning("Schema statement skipped (%s): %s", stmt[:40], e)
        logger.info("Neo4j schema initialized (multi-tenant)")


# Global client instance (thread-safe lazy init)
_neo4j_client: Optional[Neo4jClient] = None
_neo4j_client_lock = threading.Lock()


def get_neo4j_driver() -> Neo4jClient:
    global _neo4j_client
    if _neo4j_client is None:
        with _neo4j_client_lock:
            if _neo4j_client is None:
                client = Neo4jClient()
                client.connect()
                _neo4j_client = client
    return _neo4j_client
