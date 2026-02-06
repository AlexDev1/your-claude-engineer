"""
HTTP Token Verifier for Telegram MCP Server
=============================================

Validates bearer tokens by making an HTTP request to the Task MCP Server's
/auth/validate endpoint. This avoids duplicating authentication logic and
keeps Telegram MCP as a pure Resource Server.
"""

import httpx

from mcp.server.auth.provider import AccessToken


class HttpTokenVerifier:
    """
    Validates tokens via HTTP request to Task MCP /auth/validate.

    Works with both OAuth access tokens and legacy API keys,
    since Task MCP's auth endpoint handles both.
    """

    def __init__(self, validate_url: str):
        self.validate_url = validate_url

    async def verify_token(self, token: str) -> AccessToken | None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(
                    self.validate_url,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.RequestError:
                return None

            if resp.status_code == 200:
                return AccessToken(
                    token=token,
                    client_id=resp.headers.get("X-Auth-User", "unknown"),
                    scopes=[],
                )
            return None
