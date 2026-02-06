"""
OAuth Login Page
================

HTML login page for the OAuth 2.0 Authorization Code flow.
Users authenticate with their existing API key to authorize OAuth clients.

Routes:
    GET  /oauth/login?session_id=... — Show login form
    POST /oauth/login               — Validate API key, issue authorization code
"""

import hashlib
import json
import secrets
import time

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from database import validate_api_key

# Authorization code TTL (5 minutes)
AUTHORIZATION_CODE_TTL = 300

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authorize — Task MCP Server</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a;
            color: #e5e5e5;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .container {{
            background: #171717;
            border: 1px solid #262626;
            border-radius: 12px;
            padding: 40px;
            max-width: 420px;
            width: 90%;
        }}
        .logo {{
            text-align: center;
            margin-bottom: 24px;
            font-size: 24px;
            font-weight: 700;
            color: #fff;
        }}
        .logo span {{ color: #3b82f6; }}
        .subtitle {{
            text-align: center;
            color: #a3a3a3;
            font-size: 14px;
            margin-bottom: 32px;
            line-height: 1.5;
        }}
        .client-name {{
            color: #e5e5e5;
            font-weight: 500;
        }}
        label {{
            display: block;
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 8px;
            color: #d4d4d4;
        }}
        input[type="password"] {{
            width: 100%;
            padding: 10px 14px;
            background: #0a0a0a;
            border: 1px solid #404040;
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
            font-family: 'SF Mono', 'Fira Code', monospace;
            outline: none;
            transition: border-color 0.2s;
        }}
        input[type="password"]:focus {{
            border-color: #3b82f6;
        }}
        input[type="password"]::placeholder {{
            color: #525252;
        }}
        .btn {{
            width: 100%;
            padding: 12px;
            margin-top: 20px;
            background: #3b82f6;
            color: #fff;
            border: none;
            border-radius: 8px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .btn:hover {{ background: #2563eb; }}
        .btn:active {{ background: #1d4ed8; }}
        .error {{
            background: #7f1d1d;
            border: 1px solid #991b1b;
            color: #fca5a5;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 20px;
        }}
        .footer {{
            text-align: center;
            margin-top: 24px;
            font-size: 12px;
            color: #525252;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">Axon<span>Code</span> MCP</div>
        <div class="subtitle">
            {client_info}
        </div>
        {error_html}
        <form method="POST" action="{form_action}">
            <input type="hidden" name="session_id" value="{session_id}">
            <label for="api_key">API Key</label>
            <input type="password" id="api_key" name="api_key"
                   placeholder="mcp_..." autocomplete="off" autofocus required>
            <button type="submit" class="btn">Authorize</button>
        </form>
        <div class="footer">Enter your MCP API key to authorize this application.</div>
    </div>
</body>
</html>"""


async def login_page(request: Request) -> Response:
    """GET /oauth/login — Show login form."""
    session_id = request.query_params.get("session_id", "")

    if not session_id:
        return HTMLResponse(
            content="<h1>400 Bad Request</h1><p>Missing session_id parameter.</p>",
            status_code=400,
        )

    # Get the OAuth provider from app state
    oauth_provider = request.app.state.oauth_provider
    pending = oauth_provider.get_pending_authorization(session_id)

    if not pending:
        return HTMLResponse(
            content="<h1>400 Bad Request</h1><p>Invalid or expired session.</p>",
            status_code=400,
        )

    client = pending["client"]
    client_info = (
        f'Application <span class="client-name">{client.client_name or client.client_id}</span> '
        f"is requesting access to your MCP server."
    )

    # Use root_path to build correct form action behind reverse proxy
    root_path = request.scope.get("root_path", "")
    form_action = f"{root_path}/oauth/login"

    html = LOGIN_HTML.format(
        session_id=session_id,
        client_info=client_info,
        error_html="",
        form_action=form_action,
    )
    return HTMLResponse(content=html)


async def login_submit(request: Request) -> Response:
    """POST /oauth/login — Validate API key, issue authorization code."""
    form = await request.form()
    session_id = form.get("session_id", "")
    api_key = form.get("api_key", "")

    if not session_id:
        return HTMLResponse(
            content="<h1>400 Bad Request</h1><p>Missing session_id.</p>",
            status_code=400,
        )

    oauth_provider = request.app.state.oauth_provider
    pending = oauth_provider.get_pending_authorization(session_id)

    if not pending:
        return HTMLResponse(
            content="<h1>400 Bad Request</h1><p>Invalid or expired session.</p>",
            status_code=400,
        )

    # Validate API key
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    client_ip = request.headers.get("x-real-ip", request.client.host if request.client else None)
    user_info = await validate_api_key(key_hash, client_ip)

    if not user_info:
        client = pending["client"]
        client_info = (
            f'Application <span class="client-name">{client.client_name or client.client_id}</span> '
            f"is requesting access to your MCP server."
        )
        root_path = request.scope.get("root_path", "")
        form_action = f"{root_path}/oauth/login"
        html = LOGIN_HTML.format(
            session_id=session_id,
            client_info=client_info,
            error_html='<div class="error">Invalid API key. Please check and try again.</div>',
            form_action=form_action,
        )
        return HTMLResponse(content=html)

    # API key is valid — generate authorization code
    client = pending["client"]
    params = pending["params"]

    code = secrets.token_urlsafe(48)
    expires_at = time.time() + AUTHORIZATION_CODE_TTL

    scopes = params.scopes if params.scopes else []

    # Store authorization code in database
    from database import db

    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO oauth_authorization_codes
                (code, client_id, redirect_uri, redirect_uri_provided_explicitly,
                 code_challenge, scopes, expires_at, resource)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            code,
            client.client_id,
            str(params.redirect_uri),
            params.redirect_uri_provided_explicitly,
            params.code_challenge,
            json.dumps(scopes),
            expires_at,
            params.resource,
        )

    # Remove pending authorization
    oauth_provider.remove_pending_authorization(session_id)

    # Build redirect URL back to the client
    redirect_uri = str(params.redirect_uri)
    separator = "&" if "?" in redirect_uri else "?"
    redirect_url = f"{redirect_uri}{separator}code={code}"
    if params.state:
        redirect_url += f"&state={params.state}"

    return RedirectResponse(url=redirect_url, status_code=302)
