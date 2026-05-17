"""PostgreSQL database connection and operations (multi-tenant by owner_clerk_id)"""

import logging
import threading
from typing import Optional, List, Dict, Any, Iterator
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import SimpleConnectionPool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PostgresClient:
    """PostgreSQL client with connection pooling."""

    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or settings.postgres_url
        self.pool: Optional[SimpleConnectionPool] = None
        self.engine = None
        self.SessionLocal = None

    def initialize(self, min_conn: int = 1, max_conn: int = 10):
        try:
            self.pool = SimpleConnectionPool(
                min_conn,
                max_conn,
                self.connection_string
            )
            self.engine = create_engine(self.connection_string)
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            logger.info("PostgreSQL connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL pool: {e}")
            raise

    @contextmanager
    def get_connection(self):
        if not self.pool:
            raise RuntimeError("Connection pool not initialized")

        conn = self.pool.getconn()
        try:
            try:
                from pgvector.psycopg2 import register_vector
                register_vector(conn)
            except ImportError:
                pass
            except Exception as e:
                logger.debug(f"pgvector registration skipped: {e}")

            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            self.pool.putconn(conn)

    @contextmanager
    def get_session(self) -> Iterator[Session]:
        if not self.SessionLocal:
            raise RuntimeError("SessionLocal not initialized")

        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session error: {e}")
            raise
        finally:
            session.close()

    def execute_query(
        self,
        query: str,
        params: Optional[tuple] = None,
        fetch: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if fetch:
                    return [dict(row) for row in cursor.fetchall()]
                return None

    def execute_many(self, query: str, data: List[tuple]) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(query, data)

    # ------------------------------------------------------------------
    # Tenancy
    # ------------------------------------------------------------------

    def upsert_user(
        self,
        clerk_id: str,
        email: Optional[str],
        full_name: Optional[str],
    ) -> None:
        """Insert or refresh a row in `users`. Called on every authed request."""
        query = """
            INSERT INTO users (clerk_id, email, full_name, last_seen_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (clerk_id) DO UPDATE SET
                email        = COALESCE(EXCLUDED.email, users.email),
                full_name    = COALESCE(EXCLUDED.full_name, users.full_name),
                last_seen_at = NOW()
        """
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (clerk_id, email, full_name))

    # ------------------------------------------------------------------
    # Domain writes — every method takes owner_clerk_id
    # ------------------------------------------------------------------

    def insert_interaction_content(
        self,
        owner_clerk_id: str,
        neo4j_interaction_id: str,
        full_transcript: Optional[str] = None,
        summary: Optional[str] = None,
        takeaways: Optional[Any] = None,
        topics: Optional[Any] = None,
        quotes: Optional[Any] = None,
        metrics_mentioned: Optional[Any] = None
    ) -> str:
        query = """
            INSERT INTO interaction_content
            (owner_clerk_id, neo4j_interaction_id, full_transcript, summary,
             takeaways, topics, quotes, metrics_mentioned)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (owner_clerk_id, neo4j_interaction_id) DO UPDATE SET
                full_transcript   = EXCLUDED.full_transcript,
                summary           = EXCLUDED.summary,
                takeaways         = EXCLUDED.takeaways,
                topics            = EXCLUDED.topics,
                quotes            = EXCLUDED.quotes,
                metrics_mentioned = EXCLUDED.metrics_mentioned
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        owner_clerk_id,
                        neo4j_interaction_id,
                        full_transcript,
                        summary,
                        psycopg2.extras.Json(takeaways) if takeaways else None,
                        psycopg2.extras.Json(topics) if topics else None,
                        psycopg2.extras.Json(quotes) if quotes else None,
                        psycopg2.extras.Json(metrics_mentioned) if metrics_mentioned else None,
                    ),
                )
                return cursor.fetchone()[0]

    def insert_company_embedding(
        self,
        owner_clerk_id: str,
        company_id: str,
        embedding: List[float],
        embedding_text: str
    ) -> str:
        """Upsert per-user company embedding for vector search."""
        query = """
            INSERT INTO company_embeddings
                (owner_clerk_id, company_id, embedding, embedding_text)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (owner_clerk_id, company_id) DO UPDATE
              SET embedding      = EXCLUDED.embedding,
                  embedding_text = EXCLUDED.embedding_text,
                  generated_at   = NOW()
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (owner_clerk_id, company_id, embedding, embedding_text))
                return cursor.fetchone()[0]

    def search_similar_companies(
        self,
        owner_clerk_id: str,
        embedding: List[float],
        limit: int = 10,
        threshold: float = 0.75
    ) -> List[Dict[str, Any]]:
        """Per-user vector similarity search."""
        query = """
            SELECT
                company_id,
                embedding_text,
                1 - (embedding <=> %s::vector) as similarity
            FROM company_embeddings
            WHERE owner_clerk_id = %s
              AND 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """

        return self.execute_query(
            query,
            (embedding, owner_clerk_id, embedding, threshold, embedding, limit)
        )

    def insert_extraction_metadata(
        self,
        owner_clerk_id: str,
        company_id: str,
        model_used: str,
        confidence: float,
        warnings: Optional[Any] = None
    ) -> str:
        query = """
            INSERT INTO extraction_metadata
                (owner_clerk_id, company_id, model_used, confidence, warnings)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        owner_clerk_id,
                        company_id,
                        model_used,
                        confidence,
                        psycopg2.extras.Json(warnings) if warnings else None,
                    ),
                )
                return cursor.fetchone()[0]

    def insert_team_debate(
        self,
        owner_clerk_id: str,
        company_id: str,
        detected: bool,
        for_arguments: Optional[Any] = None,
        against_arguments: Optional[Any] = None,
        open_questions: Optional[Any] = None
    ) -> str:
        query = """
            INSERT INTO team_debates
            (owner_clerk_id, company_id, detected, for_arguments, against_arguments, open_questions)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        owner_clerk_id,
                        company_id,
                        detected,
                        psycopg2.extras.Json(for_arguments) if for_arguments else None,
                        psycopg2.extras.Json(against_arguments) if against_arguments else None,
                        psycopg2.extras.Json(open_questions) if open_questions else None,
                    ),
                )
                return cursor.fetchone()[0]

    def insert_decision_record(
        self,
        owner_clerk_id: str,
        company_id: str,
        verdict: str,
        rationale: Optional[str] = None,
        conditions: Optional[Any] = None,
        check_size: Optional[str] = None,
        valuation: Optional[str] = None,
        decided_at: Optional[str] = None
    ) -> str:
        query = """
            INSERT INTO decision_records
            (owner_clerk_id, company_id, verdict, rationale, conditions, check_size, valuation, decided_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        owner_clerk_id,
                        company_id,
                        verdict,
                        rationale,
                        psycopg2.extras.Json(conditions) if conditions else None,
                        check_size,
                        valuation,
                        decided_at,
                    ),
                )
                return cursor.fetchone()[0]

    def insert_company_snapshot(
        self,
        owner_clerk_id: str,
        company_id: str,
        domain: Optional[str] = None,
        headcount: Optional[int] = None,
        open_roles: Optional[int] = None,
        funding: Optional[Any] = None,
        fetched_at: Optional[str] = None
    ) -> str:
        query = """
            INSERT INTO company_snapshots
            (owner_clerk_id, company_id, domain, headcount, open_roles, funding, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        owner_clerk_id,
                        company_id,
                        domain,
                        headcount,
                        open_roles,
                        psycopg2.extras.Json(funding) if funding else None,
                        fetched_at,
                    ),
                )
                return cursor.fetchone()[0]

    def insert_company_news(
        self,
        owner_clerk_id: str,
        company_id: str,
        headline: str,
        url: Optional[str] = None,
        published_at: Optional[str] = None,
        source: Optional[str] = None
    ) -> str:
        query = """
            INSERT INTO company_news
                (owner_clerk_id, company_id, headline, url, published_at, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (owner_clerk_id, company_id, headline, url, published_at, source),
                )
                return cursor.fetchone()[0]

    def insert_company_signal(
        self,
        owner_clerk_id: str,
        company_id: str,
        label: str,
        detected_at: Optional[str] = None
    ) -> str:
        query = """
            INSERT INTO company_signals
                (owner_clerk_id, company_id, label, detected_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (owner_clerk_id, company_id, label, detected_at))
                return cursor.fetchone()[0]

    def update_decision_record(
        self,
        owner_clerk_id: str,
        record_id: str,
        verdict: Optional[str] = None,
        check_size: Optional[str] = None,
        valuation: Optional[str] = None
    ) -> bool:
        query = """
            UPDATE decision_records
            SET verdict    = COALESCE(%s, verdict),
                check_size = COALESCE(%s, check_size),
                valuation  = COALESCE(%s, valuation)
            WHERE id = %s AND owner_clerk_id = %s
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (verdict, check_size, valuation, record_id, owner_clerk_id),
                )
                return cursor.rowcount > 0

    def get_company_snapshot(
        self,
        owner_clerk_id: str,
        company_id: str,
    ) -> Optional[Dict[str, Any]]:
        query = """
            SELECT * FROM company_snapshots
            WHERE owner_clerk_id = %s AND company_id = %s
            ORDER BY fetched_at DESC
            LIMIT 1
        """
        result = self.execute_query(query, (owner_clerk_id, company_id))
        return result[0] if result else None

    def get_company_news(
        self,
        owner_clerk_id: str,
        company_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT * FROM company_news
            WHERE owner_clerk_id = %s AND company_id = %s
            ORDER BY published_at DESC
            LIMIT %s
        """
        return self.execute_query(query, (owner_clerk_id, company_id, limit)) or []

    def get_company_signals(
        self,
        owner_clerk_id: str,
        company_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT * FROM company_signals
            WHERE owner_clerk_id = %s AND company_id = %s
            ORDER BY detected_at DESC
            LIMIT %s
        """
        return self.execute_query(query, (owner_clerk_id, company_id, limit)) or []

    def close(self):
        if self.pool:
            self.pool.closeall()
            logger.info("PostgreSQL connection pool closed")


# Global client instance (thread-safe lazy init)
_postgres_client: Optional[PostgresClient] = None
_postgres_client_lock = threading.Lock()


def get_postgres_connection() -> PostgresClient:
    global _postgres_client
    if _postgres_client is None:
        with _postgres_client_lock:
            if _postgres_client is None:
                client = PostgresClient()
                client.initialize()
                _postgres_client = client
    return _postgres_client
