"""Test script for ENG-53 Telegram commands: /skip and /priority."""
from analytics_server.server import app

# List all telegram routes
routes = [r.path for r in app.routes]
telegram_routes = [r for r in routes if 'telegram' in r]
print("Telegram routes:")
for r in telegram_routes:
    print(f"  {r}")
