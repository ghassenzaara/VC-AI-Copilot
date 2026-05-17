"""Clerk JWT authentication for the FastAPI backend.

Verifies session tokens issued by Clerk against the JWKS endpoint configured
in `settings.clerk_jwks_url`. Keys are cached in process and refreshed on a
cache miss so Clerk key rotation is handled without restarts.

Two FastAPI dependencies are exposed:
  - `get_current_user`              — verify only; no DB writes
  - `get_current_user_provisioned`  — verify + lazy upsert into `users` (PG)
                                      + MERGE `:User {clerk_id}` (Neo4j)

Every route that touches per-user data must depend on `get_current_user_provisioned`
so the FK from owner_clerk_id → users(clerk_id) is always satisfied.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from jwt import PyJWKClient, PyJWTError

from src.config import get_settings


logger = logging.getLogger(__name__)


@dataclass
class ClerkUser:
    """Minimum identity surface the rest of the backend cares about."""
    clerk_id: str
    email: Optional[str]
    full_name: Optional[str]
    raw_claims: Dict[str, Any]


class JWKSCache:
    """Thin async-safe wrapper around PyJWKClient.

    PyJWKClient is sync and caches keys in memory keyed by `kid`. We wrap it
    in an asyncio lock so two concurrent requests can't both trigger a cold
    fetch, and so we can refresh on cache miss (covers Clerk key rotation).
    """

    def __init__(self, jwks_url: str) -> None:
        self._jwks_url = jwks_url
        # cache_keys=True so PyJWKClient holds onto fetched keys
        self._client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
        self._lock = asyncio.Lock()

    async def get_signing_key(self, kid: str):
        """Return the signing key for `kid`; force a JWKS refresh on miss."""
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None, self._client.get_signing_key, kid
            )
        except Exception:
            # Force refresh: rebuild the client so the next lookup re-fetches.
            async with self._lock:
                self._client = PyJWKClient(
                    self._jwks_url, cache_keys=True, lifespan=3600
                )
            return await loop.run_in_executor(
                None, self._client.get_signing_key, kid
            )


_jwks_cache: Optional[JWKSCache] = None


def _get_jwks_cache() -> JWKSCache:
    global _jwks_cache
    if _jwks_cache is None:
        settings = get_settings()
        if not settings.clerk_jwks_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Clerk authentication is not configured (CLERK_JWKS_URL missing)",
            )
        _jwks_cache = JWKSCache(settings.clerk_jwks_url)
    return _jwks_cache


def _extract_bearer(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be `Bearer <token>`",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = parts[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def _verify_clerk_token(token: str) -> Dict[str, Any]:
    """Verify a Clerk session token and return its claims."""
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
    except PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed token header: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    kid = header.get("kid")
    if not kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing `kid` header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jwks = _get_jwks_cache()
    try:
        signing_key = await jwks.get_signing_key(kid)
    except Exception as e:
        logger.warning("JWKS lookup failed for kid=%s: %s", kid, e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to resolve token signing key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    decode_kwargs: Dict[str, Any] = {
        "algorithms": ["RS256"],
        "options": {"require": ["exp", "iat", "sub"]},
    }
    if settings.clerk_issuer:
        decode_kwargs["issuer"] = settings.clerk_issuer
    if settings.clerk_audience:
        decode_kwargs["audience"] = settings.clerk_audience
    else:
        # Clerk session tokens often omit `aud`; skip that check explicitly.
        decode_kwargs["options"]["verify_aud"] = False

    try:
        claims = jwt.decode(token, signing_key.key, **decode_kwargs)
    except PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims


def _build_clerk_user(claims: Dict[str, Any]) -> ClerkUser:
    clerk_id = claims.get("sub")
    if not clerk_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing `sub` claim",
        )
    email = (
        claims.get("email")
        or claims.get("primary_email_address")
        or claims.get("email_address")
    )
    full_name = claims.get("name") or claims.get("full_name")
    if not full_name:
        given = claims.get("given_name") or claims.get("first_name") or ""
        family = claims.get("family_name") or claims.get("last_name") or ""
        candidate = f"{given} {family}".strip()
        full_name = candidate or None
    return ClerkUser(
        clerk_id=clerk_id,
        email=email,
        full_name=full_name,
        raw_claims=claims,
    )


async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> ClerkUser:
    """FastAPI dependency: verify Bearer token, return ClerkUser. No DB writes."""
    token = _extract_bearer(authorization)
    claims = await _verify_clerk_token(token)
    return _build_clerk_user(claims)


async def get_current_user_provisioned(
    request: Request,
    user: ClerkUser = Depends(get_current_user),
) -> ClerkUser:
    """Same as `get_current_user`, but also ensures the user exists in both DBs.

    - Upserts a row in `users` (Postgres). Satisfies the FK on every owner_clerk_id.
    - MERGEs `(:User {clerk_id})` in Neo4j so per-user subgraphs can attach.

    Failures here surface as 500, not 401 — at this point the token already
    verified successfully; an upsert failure is a server-side problem.
    """
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None,
            pipeline.postgres.upsert_user,
            user.clerk_id,
            user.email,
            user.full_name,
        )
    except Exception as e:
        logger.exception("Failed to upsert user in Postgres: %s", e)
        raise HTTPException(status_code=500, detail="User provisioning failed")

    try:
        await loop.run_in_executor(
            None,
            pipeline.neo4j.execute_write,
            """
            MERGE (u:User {clerk_id: $clerk_id})
            ON CREATE SET u.created_at = datetime(), u.email = $email, u.full_name = $full_name
            ON MATCH  SET u.last_seen_at = datetime(),
                          u.email = coalesce($email, u.email),
                          u.full_name = coalesce($full_name, u.full_name)
            RETURN u.clerk_id AS clerk_id
            """,
            {
                "clerk_id": user.clerk_id,
                "email": user.email,
                "full_name": user.full_name,
            },
        )
    except Exception as e:
        logger.exception("Failed to merge :User node in Neo4j: %s", e)
        raise HTTPException(status_code=500, detail="User provisioning failed")

    return user
