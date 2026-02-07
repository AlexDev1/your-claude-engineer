"""Minimal HTTP server to display config dump for Playwright screenshot."""
import http.server
import json
import html
import socketserver
from config import get_config


PORT = 8765


class ConfigHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that serves config dump as HTML."""

    def do_GET(self):
        """Handle GET request with config dump page."""
        cfg = get_config()

        if self.path == "/api/config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(cfg.dump_json().encode())
            return

        dump_text = cfg.dump()
        json_text = cfg.dump_json()
        env_name = cfg.environment.value

        page_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>ENG-25: Centralized Config</title>
    <style>
        body {{
            font-family: monospace;
            background: #1a1a2e;
            color: #e0e0e0;
            padding: 20px;
            margin: 0;
        }}
        h1 {{
            color: #00d4ff;
            border-bottom: 2px solid #00d4ff;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #ff6b6b;
            margin-top: 30px;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: bold;
            margin-left: 10px;
        }}
        .badge-dev {{
            background: #2d5a3d;
            color: #4ade80;
        }}
        .badge-staging {{
            background: #5a4a2d;
            color: #fbbf24;
        }}
        .badge-prod {{
            background: #5a2d2d;
            color: #f87171;
        }}
        pre {{
            background: #16213e;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            border: 1px solid #333;
            line-height: 1.6;
        }}
        .section {{
            margin-bottom: 24px;
        }}
        .status {{
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 16px;
        }}
        .status-ok {{
            background: #1a3a2a;
            border: 1px solid #4ade80;
            color: #4ade80;
        }}
        .meta {{
            color: #888;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <h1>ENG-25: Centralized Config
        <span class="badge badge-{env_name}">{env_name.upper()}</span>
    </h1>

    <div class="status status-ok">
        Configuration loaded and validated successfully.
        Pydantic Settings is working.
    </div>

    <div class="section">
        <h2>Config Dump (Text)</h2>
        <pre>{html.escape(dump_text)}</pre>
    </div>

    <div class="section">
        <h2>Config Dump (JSON)</h2>
        <pre>{html.escape(json_text)}</pre>
    </div>

    <div class="section">
        <h2>Derived Properties</h2>
        <pre>orchestrator_model_id: {html.escape(cfg.orchestrator_model_id)}
is_production: {cfg.is_production}
is_development: {cfg.is_development}
telegram_configured: {cfg.telegram_configured}
mcp_auth_headers: {html.escape(str(bool(cfg.mcp_auth_headers)))}
github_reviewers_list: {html.escape(str(cfg.github_reviewers_list))}</pre>
    </div>

    <p class="meta">
        Served by test_config_server.py | Port {PORT}
    </p>
</body>
</html>"""

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(page_html.encode())

    def log_message(self, format, *args):
        """Suppress default request logging."""
        pass


if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), ConfigHandler) as httpd:
        print(f"Config server running on http://localhost:{PORT}")
        httpd.serve_forever()
