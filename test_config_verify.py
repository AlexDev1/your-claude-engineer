"""Verify config module loads and dumps correctly."""
from config import get_config

cfg = get_config()
print(cfg.dump())
print()
print("JSON output:")
print(cfg.dump_json())
print()
print("Validation passed.")
print(f"  Environment: {cfg.environment.value}")
print(f"  Task MCP URL: {cfg.task_mcp_url}")
print(f"  Telegram MCP URL: {cfg.telegram_mcp_url}")
print(f"  Orchestrator model ID: {cfg.orchestrator_model_id}")
print(f"  Is production: {cfg.is_production}")
print(f"  Is development: {cfg.is_development}")
print(f"  Telegram configured: {cfg.telegram_configured}")
print(f"  MCP auth headers present: {bool(cfg.mcp_auth_headers)}")
