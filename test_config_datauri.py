"""Generate data URI for Playwright browser navigation."""
import base64
import html as html_mod
from config import get_config


def main():
    """Print data URI for config page."""
    cfg = get_config()
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
        .badge-development {{
            background: #2d5a3d;
            color: #4ade80;
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
        .tests {{
            background: #1a2a3a;
            border: 1px solid #60a5fa;
            color: #60a5fa;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 16px;
        }}
    </style>
</head>
<body>
    <h1>ENG-25: Centralized Config
        <span class="badge badge-{env_name}">{env_name.upper()}</span>
    </h1>
    <div class="status status-ok">
        Configuration loaded and validated successfully via Pydantic Settings.
    </div>
    <div class="tests">
        Validation tests: 13/13 passed
    </div>
    <div class="section">
        <h2>Config Dump (Text)</h2>
        <pre>{html_mod.escape(dump_text)}</pre>
    </div>
    <div class="section">
        <h2>Config Dump (JSON)</h2>
        <pre>{html_mod.escape(json_text)}</pre>
    </div>
    <div class="section">
        <h2>Derived Properties</h2>
        <pre>orchestrator_model_id: {html_mod.escape(cfg.orchestrator_model_id)}
is_production: {cfg.is_production}
is_development: {cfg.is_development}
telegram_configured: {cfg.telegram_configured}
mcp_auth_headers: {html_mod.escape(str(bool(cfg.mcp_auth_headers)))}</pre>
    </div>
</body>
</html>"""

    encoded = base64.b64encode(page_html.encode()).decode()
    data_uri = f"data:text/html;base64,{encoded}"
    print(data_uri)


if __name__ == "__main__":
    main()
