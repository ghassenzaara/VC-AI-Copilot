"""PostgreSQL database connection and operations"""

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
    """PostgreSQL client with connection pooling"""
    
    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or settings.postgres_url
        self.pool: Optional[SimpleConnectionPool] = None
        self.engine = None
        self.SessionLocal = None
        
    def initialize(self, min_conn: int = 1, max_conn: int = 10):
        """Initialize connection pool"""
        try:
            self.pool = SimpleConnectionPool(
                min_conn,
                max_conn,
                self.connection_string
            )
            
            # Also create SQLAlchemy engine for ORM operations
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
        """Get a connection from the pool. Registers pgvector type adapter
        on checkout so embedding inserts/searches accept List[float] directly."""
        if not self.pool:
            raise RuntimeError("Connection pool not initialized")

        conn = self.pool.getconn()
        try:
            # Register pgvector adapter so embedding columns accept List[float]
            try:
                from pgvector.psycopg2 import register_vector
                register_vector(conn)
            except ImportError:
                pass  # pgvector not installed; embedding ops will fail loudly when used
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
        """Get SQLAlchemy session"""
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
        """Execute a query and optionally fetch results"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if fetch:
                    return [dict(row) for row in cursor.fetchall()]
                return None
    
    def execute_many(
        self,
        query: str,
        data: List[tuple]
    ) -> None:
        """Execute query with multiple parameter sets"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(query, data)
    
    def insert_interaction_content(
        self,
        neo4j_interaction_id: str,
        full_transcript: Optional[str] = None,
        summary: Optional[str] = None,
        takeaways: Optional[Any] = None,
        topics: Optional[Any] = None,
        quotes: Optional[Any] = None,
        metrics_mentioned: Optional[Any] = None
    ) -> str:
        """Insert interaction content"""
        query = """
            INSERT INTO interaction_content
            (neo4j_interaction_id, full_transcript, summary, takeaways, topics, quotes, metrics_mentioned)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        neo4j_interaction_id,
                        full_transcript,
                        summary,
                        psycopg2.extras.Json(takeaways) if takeaways else None,
                        psycopg2.extras.Json(topics) if topics else None,
                        psycopg2.extras.Json(quotes) if quotes else None,
                        psycopg2.extras.Json(metrics_mentioned) if metrics_mentioned else None
                    )
                )
                return cursor.fetchone()[0]
    
    def insert_company_embedding(
        self,
        company_id: str,
        embedding: List[float],
        embedding_text: str
    ) -> str:
        """Upsert company embedding for vector search (BUG-065).

        Requires migration 002 (UNIQUE constraint on company_id).
        """
        query = """
            INSERT INTO company_embeddings (company_id, embedding, embedding_text)
            VALUES (%s, %s, %s)
            ON CONFLICT (company_id) DO UPDATE
              SET embedding = EXCLUDED.embedding,
                  embedding_text = EXCLUDED.embedding_text,
                  generated_at = NOW()
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (company_id, embedding, embedding_text))
                return cursor.fetchone()[0]
    
    def search_similar_companies(
        self,
        embedding: List[float],
        limit: int = 10,
        threshold: float = 0.75
    ) -> List[Dict[str, Any]]:
        """Search for similar companies using vector similarity"""
        query = """
            SELECT 
                company_id,
                embedding_text,
                1 - (embedding <=> %s::vector) as similarity
            FROM company_embeddings
            WHERE 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        
        return self.execute_query(
            query,
            (embedding, embedding, threshold, embedding, limit)
        )
    
    def insert_extraction_metadata(
        self,
        company_id: str,
        model_used: str,
        confidence: float,
        warnings: Optional[Any] = None
    ) -> str:
        """Insert extraction metadata"""
        query = """
            INSERT INTO extraction_metadata (company_id, model_used, confidence, warnings)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        company_id,
                        model_used,
                        confidence,
                        psycopg2.extras.Json(warnings) if warnings else None
                    )
                )
                return cursor.fetchone()[0]
    
    def insert_team_debate(
        self,
        company_id: str,
        detected: bool,
        for_arguments: Optional[Any] = None,
        against_arguments: Optional[Any] = None,
        open_questions: Optional[Any] = None
    ) -> str:
        """Insert team debate record"""
        query = """
            INSERT INTO team_debates 
            (company_id, detected, for_arguments, against_arguments, open_questions)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        company_id,
                        detected,
                        psycopg2.extras.Json(for_arguments) if for_arguments else None,
                        psycopg2.extras.Json(against_arguments) if against_arguments else None,
                        psycopg2.extras.Json(open_questions) if open_questions else None
                    )
                )
                return cursor.fetchone()[0]
    
    def insert_decision_record(
        self,
        company_id: str,
        verdict: str,
        rationale: Optional[str] = None,
        conditions: Optional[Any] = None,
        check_size: Optional[str] = None,
        valuation: Optional[str] = None,
        decided_at: Optional[str] = None
    ) -> str:
        """Insert decision record (single-shot with all extraction fields)"""
        query = """
            INSERT INTO decision_records
            (company_id, verdict, rationale, conditions, check_size, valuation, decided_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        company_id,
                        verdict,
                        rationale,
                        psycopg2.extras.Json(conditions) if conditions else None,
                        check_size,
                        valuation,
                        decided_at
                    )
                )
                return cursor.fetchone()[0]
    
    def insert_company_snapshot(
        self,
        company_id: str,
        domain: Optional[str] = None,
        headcount: Optional[int] = None,
        open_roles: Optional[int] = None,
        funding: Optional[Any] = None,
        fetched_at: Optional[str] = None
    ) -> str:
        """Insert company snapshot"""
        query = """
            INSERT INTO company_snapshots
            (company_id, domain, headcount, open_roles, funding, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        company_id,
                        domain,
                        headcount,
                        open_roles,
                        psycopg2.extras.Json(funding) if funding else None,
                        fetched_at
                    )
                )
                return cursor.fetchone()[0]
    
    def insert_company_news(
        self,
        company_id: str,
        headline: str,
        url: Optional[str] = None,
        published_at: Optional[str] = None,
        source: Optional[str] = None
    ) -> str:
        """Insert company news article"""
        query = """
            INSERT INTO company_news (company_id, headline, url, published_at, source)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (company_id, headline, url, published_at, source))
                return cursor.fetchone()[0]
    
    def insert_company_signal(
        self,
        company_id: str,
        label: str,
        detected_at: Optional[str] = None
    ) -> str:
        """Insert company signal"""
        query = """
            INSERT INTO company_signals (company_id, label, detected_at)
            VALUES (%s, %s, %s)
            RETURNING id
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (company_id, label, detected_at))
                return cursor.fetchone()[0]
    
    def update_decision_record(
        self,
        record_id: str,
        verdict: Optional[str] = None,
        check_size: Optional[str] = None,
        valuation: Optional[str] = None
    ) -> bool:
        """Update decision record with missing fields"""
        query = """
            UPDATE decision_records
            SET verdict = COALESCE(%s, verdict),
                check_size = COALESCE(%s, check_size),
                valuation = COALESCE(%s, valuation)
            WHERE id = %s
            RETURNING id
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (verdict, check_size, valuation, record_id))
                return cursor.rowcount > 0
    
    def get_company_snapshot(self, company_id: str) -> Optional[Dict[str, Any]]:
        """Get latest company snapshot"""
        query = """
            SELECT * FROM company_snapshots
            WHERE company_id = %s
            ORDER BY fetched_at DESC
            LIMIT 1
        """
        
        result = self.execute_query(query, (company_id,))
        return result[0] if result else None
    
    def get_company_news(
        self,
        company_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get company news articles"""
        query = """
            SELECT * FROM company_news
            WHERE company_id = %s
            ORDER BY published_at DESC
            LIMIT %s
        """
        
        return self.execute_query(query, (company_id, limit)) or []
    
    def get_company_signals(
        self,
        company_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get company signals"""
        query = """
            SELECT * FROM company_signals
            WHERE company_id = %s
            ORDER BY detected_at DESC
            LIMIT %s
        """
        
        return self.execute_query(query, (company_id, limit)) or []
    
    def close(self):
        """Close all connections"""
        if self.pool:
            self.pool.closeall()
            logger.info("PostgreSQL connection pool closed")


# Global client instance (thread-safe lazy init — BUG-052)
_postgres_client: Optional[PostgresClient] = None
_postgres_client_lock = threading.Lock()


def get_postgres_connection() -> PostgresClient:
    """Get or create PostgreSQL client (double-checked locking)."""
    global _postgres_client
    if _postgres_client is None:
        with _postgres_client_lock:
            if _postgres_client is None:
                client = PostgresClient()
                client.initialize()
                _postgres_client = client
    return _postgres_client

# Made with Bob
