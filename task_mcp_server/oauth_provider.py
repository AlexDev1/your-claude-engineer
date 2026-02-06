"""
PostgreSQL-backed OAuth 2.0 Authorization Server Provider
==========================================================

Implements OAuthAuthorizationServerProvider for MCP SDK.
Supports Authorization Code + PKCE with Dynamic Client Registration.

Backward-compatible: load_access_token() checks both OAuth tokens and API keys.
"""

import hashlib
import json
import logging
import os
import secrets
import time

logger = logging.getLogger(__name__)

from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AccessToken,
    RefreshToken,
    OAuthAuthorizationServerProvider,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from database import db, validate_api_key


# Token lifetimes
ACCESS_TOKEN_TTL = 3600  # 1 hour
REFRESH_TOKEN_TTL = 86400 * 30  # 30 days
AUTHORIZATION_CODE_TTL = 300  # 5 minutes


class PostgresOAuthProvider:
    """
    OAuth 2.0 provider backed by PostgreSQL.

    Implements all OAuthAuthorizationServerProvider methods.
    The load_access_token() method provides backward compatibility
    by checking both OAuth tokens and API keys.
    """

    def __init__(self):
        # In-memory store for pending authorizations (session_id -> {client, params})
        # These are short-lived (5 min) and don't need persistence
        self._pending_authorizations: dict[str, dict] = {}

    # =========================================================================
    # Client Registration (RFC 7591)
    # =========================================================================

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM oauth_clients WHERE client_id = $1",
                client_id,
            )
            if not row:
                return None

            return OAuthClientInformationFull(
                client_id=row["client_id"],
                client_secret=row["client_secret"],
                client_id_issued_at=row["client_id_issued_at"],
                client_secret_expires_at=row["client_secret_expires_at"],
                redirect_uris=json.loads(row["redirect_uris"]) if isinstance(row["redirect_uris"], str) else row["redirect_uris"],
                grant_types=json.loads(row["grant_types"]) if isinstance(row["grant_types"], str) else row["grant_types"],
                response_types=json.loads(row["response_types"]) if isinstance(row["response_types"], str) else row["response_types"],
                token_endpoint_auth_method=row["token_endpoint_auth_method"],
                client_name=row["client_name"],
                client_uri=row["client_uri"],
                logo_uri=row["logo_uri"],
                scope=row["scope"],
                contacts=json.loads(row["contacts"]) if isinstance(row.get("contacts"), str) else row.get("contacts"),
                tos_uri=row["tos_uri"],
                policy_uri=row["policy_uri"],
                software_id=row["software_id"],
                software_version=row["software_version"],
            )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        async with db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO oauth_clients (
                    client_id, client_secret, client_id_issued_at,
                    client_secret_expires_at, redirect_uris, grant_types,
                    response_types, token_endpoint_auth_method,
                    client_name, client_uri, logo_uri, scope,
                    contacts, tos_uri, policy_uri,
                    software_id, software_version
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                    $13, $14, $15, $16, $17
                )
                """,
                client_info.client_id,
                client_info.client_secret,
                client_info.client_id_issued_at,
                client_info.client_secret_expires_at,
                json.dumps([str(u) for u in client_info.redirect_uris]),
                json.dumps(client_info.grant_types),
                json.dumps(client_info.response_types),
                client_info.token_endpoint_auth_method,
                client_info.client_name,
                str(client_info.client_uri) if client_info.client_uri else None,
                str(client_info.logo_uri) if client_info.logo_uri else None,
                client_info.scope,
                json.dumps(client_info.contacts) if client_info.contacts else None,
                str(client_info.tos_uri) if client_info.tos_uri else None,
                str(client_info.policy_uri) if client_info.policy_uri else None,
                client_info.software_id,
                client_info.software_version,
            )

    # =========================================================================
    # Authorization
    # =========================================================================

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """
        Start authorization flow. Returns URL for the login page.

        Generates a session_id, stores pending authorization, and redirects
        to the login page where the user enters their API key.
        """
        session_id = secrets.token_urlsafe(32)

        self._pending_authorizations[session_id] = {
            "client": client,
            "params": params,
            "created_at": time.time(),
        }

        # Clean up expired pending authorizations
        now = time.time()
        expired = [
            sid for sid, data in self._pending_authorizations.items()
            if now - data["created_at"] > AUTHORIZATION_CODE_TTL
        ]
        for sid in expired:
            del self._pending_authorizations[sid]

        # Build login URL using root_path from environment
        # root_path is set by uvicorn --root-path /task
        root_path = os.environ.get("OAUTH_LOGIN_PATH", "/oauth/login")
        issuer_url = os.environ.get("OAUTH_ISSUER_URL", "")

        if issuer_url:
            login_url = f"{issuer_url}{root_path}?session_id={session_id}"
        else:
            login_url = f"{root_path}?session_id={session_id}"

        return login_url

    def get_pending_authorization(self, session_id: str) -> dict | None:
        """Get pending authorization by session_id (used by login page)."""
        data = self._pending_authorizations.get(session_id)
        if not data:
            return None
        if time.time() - data["created_at"] > AUTHORIZATION_CODE_TTL:
            del self._pending_authorizations[session_id]
            return None
        return data

    def remove_pending_authorization(self, session_id: str) -> None:
        """Remove pending authorization after use."""
        self._pending_authorizations.pop(session_id, None)

    # =========================================================================
    # Authorization Code
    # =========================================================================

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM oauth_authorization_codes
                WHERE code = $1 AND client_id = $2
                """,
                authorization_code,
                client.client_id,
            )
            if not row:
                return None

            if time.time() > row["expires_at"]:
                # Expired, clean up
                await conn.execute(
                    "DELETE FROM oauth_authorization_codes WHERE code = $1",
                    authorization_code,
                )
                return None

            scopes = json.loads(row["scopes"]) if isinstance(row["scopes"], str) else row["scopes"]

            return AuthorizationCode(
                code=row["code"],
                client_id=row["client_id"],
                redirect_uri=row["redirect_uri"],
                redirect_uri_provided_explicitly=row["redirect_uri_provided_explicitly"],
                code_challenge=row["code_challenge"],
                scopes=scopes,
                expires_at=row["expires_at"],
                resource=row["resource"],
            )

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        access_token = secrets.token_urlsafe(48)
        refresh_token = secrets.token_urlsafe(48)
        now = int(time.time())

        async with db.acquire() as conn:
            async with conn.transaction():
                # Delete used authorization code
                await conn.execute(
                    "DELETE FROM oauth_authorization_codes WHERE code = $1",
                    authorization_code.code,
                )

                # Store access token
                await conn.execute(
                    """
                    INSERT INTO oauth_access_tokens (token, client_id, scopes, expires_at, resource)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    access_token,
                    client.client_id,
                    json.dumps(authorization_code.scopes),
                    now + ACCESS_TOKEN_TTL,
                    authorization_code.resource,
                )

                # Store refresh token
                await conn.execute(
                    """
                    INSERT INTO oauth_refresh_tokens (token, client_id, scopes, expires_at)
                    VALUES ($1, $2, $3, $4)
                    """,
                    refresh_token,
                    client.client_id,
                    json.dumps(authorization_code.scopes),
                    now + REFRESH_TOKEN_TTL,
                )

        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
            refresh_token=refresh_token,
        )

    # =========================================================================
    # Refresh Token
    # =========================================================================

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM oauth_refresh_tokens
                WHERE token = $1 AND client_id = $2 AND revoked = FALSE
                """,
                refresh_token,
                client.client_id,
            )
            if not row:
                return None

            if row["expires_at"] and int(time.time()) > row["expires_at"]:
                return None

            scopes = json.loads(row["scopes"]) if isinstance(row["scopes"], str) else row["scopes"]

            return RefreshToken(
                token=row["token"],
                client_id=row["client_id"],
                scopes=scopes,
                expires_at=row["expires_at"],
            )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        new_access_token = secrets.token_urlsafe(48)
        new_refresh_token = secrets.token_urlsafe(48)
        now = int(time.time())

        # Use requested scopes or fall back to original scopes
        token_scopes = scopes if scopes else refresh_token.scopes

        async with db.acquire() as conn:
            async with conn.transaction():
                # Revoke old refresh token
                await conn.execute(
                    "UPDATE oauth_refresh_tokens SET revoked = TRUE WHERE token = $1",
                    refresh_token.token,
                )

                # Store new access token
                await conn.execute(
                    """
                    INSERT INTO oauth_access_tokens (token, client_id, scopes, expires_at)
                    VALUES ($1, $2, $3, $4)
                    """,
                    new_access_token,
                    client.client_id,
                    json.dumps(token_scopes),
                    now + ACCESS_TOKEN_TTL,
                )

                # Store new refresh token
                await conn.execute(
                    """
                    INSERT INTO oauth_refresh_tokens (token, client_id, scopes, expires_at)
                    VALUES ($1, $2, $3, $4)
                    """,
                    new_refresh_token,
                    client.client_id,
                    json.dumps(token_scopes),
                    now + REFRESH_TOKEN_TTL,
                )

        return OAuthToken(
            access_token=new_access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            scope=" ".join(token_scopes) if token_scopes else None,
            refresh_token=new_refresh_token,
        )

    # =========================================================================
    # Token Validation (backward-compatible with API keys)
    # =========================================================================

    async def load_access_token(self, token: str) -> AccessToken | None:
        """
        Validate a token. Checks OAuth access tokens first, then API keys.

        This is the KEY method for backward compatibility:
        1. Check oauth_access_tokens table
        2. If not found, hash with SHA-256 and check auth_api_keys
        3. Return AccessToken in both cases
        """
        logger.info("load_access_token called, token prefix: %s...", token[:20] if len(token) > 20 else token)

        # 1. Check OAuth access tokens
        try:
            async with db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM oauth_access_tokens
                    WHERE token = $1 AND revoked = FALSE
                    """,
                    token,
                )
        except Exception as e:
            logger.error("OAuth token query failed: %s", e)
            row = None

        if row:
            if row["expires_at"] and int(time.time()) > row["expires_at"]:
                logger.info("OAuth token expired")
                return None
            scopes = json.loads(row["scopes"]) if isinstance(row["scopes"], str) else row["scopes"]
            logger.info("OAuth token valid, client_id=%s", row["client_id"])
            return AccessToken(
                token=token,
                client_id=row["client_id"],
                scopes=scopes,
                expires_at=row["expires_at"],
                resource=row["resource"],
            )

        # 2. Check API keys (backward compatibility)
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        logger.info("No OAuth token found, checking API key hash: %s...", key_hash[:16])
        user_info = await validate_api_key(key_hash)

        if user_info:
            logger.info("API key valid, username=%s", user_info["username"])
            return AccessToken(
                token=token,
                client_id=user_info["username"],
                scopes=[],
            )

        logger.warning("Token not found in OAuth tokens or API keys")
        return None

    # =========================================================================
    # Revocation
    # =========================================================================

    async def revoke_token(
        self,
        token: AccessToken | RefreshToken,
    ) -> None:
        async with db.acquire() as conn:
            if isinstance(token, AccessToken):
                await conn.execute(
                    "UPDATE oauth_access_tokens SET revoked = TRUE WHERE token = $1",
                    token.token,
                )
            elif isinstance(token, RefreshToken):
                await conn.execute(
                    "UPDATE oauth_refresh_tokens SET revoked = TRUE WHERE token = $1",
                    token.token,
                )
