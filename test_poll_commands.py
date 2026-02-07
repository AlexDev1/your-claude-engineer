"""Test script for ENG-54 Telegram Poll Commands."""
import sys
sys.path.insert(0, "/home/dev/work/AxonCode/your-claude-engineer")

from analytics_server.server import app

# List telegram routes
routes = [r.path for r in app.routes if hasattr(r, 'path')]
telegram_routes = [r for r in routes if 'telegram' in r]

print("Telegram routes found:")
for r in sorted(telegram_routes):
    print(f"  {r}")

# Check for new endpoints
poll_commands = "/api/telegram/poll-commands" in routes
offset = "/api/telegram/offset" in routes
reset_offset = "/api/telegram/reset-offset" in routes

print(f"\nENG-54 Endpoints:")
print(f"  poll-commands: {'YES' if poll_commands else 'NO'}")
print(f"  offset: {'YES' if offset else 'NO'}")
print(f"  reset-offset: {'YES' if reset_offset else 'NO'}")
