"""
Telegram MCP Server
===================

FastMCP server for sending notifications via Telegram Bot API.
Replaces Slack notifications with Telegram messages.

Run with:
    uvicorn server:app --host 0.0.0.0 --port 8000

Or for development:
    python server.py

Environment variables / Docker secrets:
    TELEGRAM_BOT_TOKEN: Bot token from @BotFather
    TELEGRAM_CHAT_ID: Default chat ID for notifications
"""

import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse
from starlette.routing import Route


# =============================================================================
# Docker Secrets Support
# =============================================================================


def read_secret(name: str, env_fallback: str = None) -> str:
    """
    Read secret from Docker secrets or environment variable.

    Docker secrets are mounted at /run/secrets/<name>.
    Falls back to environment variable if secret file doesn't exist.

    Args:
        name: Secret name (filename in /run/secrets/)
        env_fallback: Environment variable name for fallback

    Returns:
        Secret value or empty string if not found
    """
    secret_path = Path(f"/run/secrets/{name}")
    if secret_path.exists():
        return secret_path.read_text().strip()
    if env_fallback:
        return os.environ.get(env_fallback, "")
    return ""

# =============================================================================
# Configuration
# =============================================================================

# Read from Docker secrets with env fallback
TELEGRAM_BOT_TOKEN = read_secret("telegram_bot_token", "TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = read_secret("telegram_chat_id", "TELEGRAM_CHAT_ID")
TELEGRAM_API_BASE = "https://api.telegram.org/bot"

# Emoji conversion map (Slack → Telegram/Unicode)
EMOJI_MAP = {
    ":white_check_mark:": "\u2705",  # ✅
    ":construction:": "\U0001F6A7",  # 🚧
    ":warning:": "\u26A0\uFE0F",  # ⚠️
    ":memo:": "\U0001F4DD",  # 📝
    ":rocket:": "\U0001F680",  # 🚀
    ":tada:": "\U0001F389",  # 🎉
    ":bug:": "\U0001F41B",  # 🐛
    ":fire:": "\U0001F525",  # 🔥
    ":sparkles:": "\u2728",  # ✨
    ":gear:": "\u2699\uFE0F",  # ⚙️
    ":package:": "\U0001F4E6",  # 📦
    ":wrench:": "\U0001F527",  # 🔧
    ":hammer:": "\U0001F528",  # 🔨
    ":bulb:": "\U0001F4A1",  # 💡
    ":link:": "\U0001F517",  # 🔗
    ":x:": "\u274C",  # ❌
    ":heavy_check_mark:": "\u2714\uFE0F",  # ✔️
    ":arrow_right:": "\u27A1\uFE0F",  # ➡️
    ":star:": "\u2B50",  # ⭐
    ":zap:": "\u26A1",  # ⚡
    ":hourglass:": "\u231B",  # ⌛
    ":clock:": "\U0001F550",  # 🕐
    ":eyes:": "\U0001F440",  # 👀
    ":thumbsup:": "\U0001F44D",  # 👍
    ":thumbsdown:": "\U0001F44E",  # 👎
}


def convert_slack_emoji(text: str) -> str:
    """Convert Slack-style emoji codes to Unicode emoji."""
    for slack_code, unicode_emoji in EMOJI_MAP.items():
        text = text.replace(slack_code, unicode_emoji)
    return text


def convert_slack_formatting(text: str) -> str:
    """
    Convert Slack formatting to Telegram MarkdownV2.

    Slack: *bold*, _italic_, ~strikethrough~, `code`
    Telegram MarkdownV2: *bold*, _italic_, ~strikethrough~, `code`

    Note: Telegram MarkdownV2 requires escaping special characters.
    """
    # Most Slack formatting is compatible with Telegram MarkdownV2
    # Just need to escape special characters outside of formatting
    return text


def escape_markdown_v2(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.

    Characters that need escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
    But we want to preserve formatting, so we're selective.
    """
    # For simplicity, we'll use HTML parsing mode instead
    # which is more forgiving
    return text


# =============================================================================
# Telegram API Client
# =============================================================================


async def telegram_request(
    method: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Make a request to Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}

    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/{method}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=data, timeout=30.0)
            return response.json()
        except httpx.RequestError as e:
            return {"ok": False, "error": str(e)}


async def get_bot_info() -> dict[str, Any]:
    """Get information about the bot."""
    return await telegram_request("getMe", {})


async def send_message(
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    disable_notification: bool = False,
) -> dict[str, Any]:
    """Send a message to a chat."""
    # Convert Slack emoji to Unicode
    text = convert_slack_emoji(text)

    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_notification": disable_notification,
    }

    return await telegram_request("sendMessage", data)


async def get_updates(offset: int = 0, limit: int = 100) -> dict[str, Any]:
    """Get recent updates (messages) to the bot."""
    return await telegram_request(
        "getUpdates",
        {"offset": offset, "limit": limit},
    )


# =============================================================================
# Transport Security Settings
# =============================================================================

# Get allowed hosts from environment (comma-separated)
_allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
_extra_hosts = [h.strip() for h in _allowed_hosts_env.split(",") if h.strip()]

# Default allowed hosts for production behind reverse proxy
ALLOWED_HOSTS = [
    "localhost",
    "localhost:*",
    "127.0.0.1",
    "127.0.0.1:*",
    "0.0.0.0:*",
] + _extra_hosts

from mcp.server.transport_security import TransportSecuritySettings

transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=ALLOWED_HOSTS,
)

# =============================================================================
# MCP Server Setup
# =============================================================================

mcp = FastMCP("Telegram MCP Server", transport_security=transport_security)


# =============================================================================
# MCP Tools (3 tools)
# =============================================================================


@mcp.tool()
async def Telegram_WhoAmI() -> dict[str, Any]:
    """
    Get information about the Telegram bot.

    Returns bot username, name, and configuration status.
    """
    if not TELEGRAM_BOT_TOKEN:
        return {
            "configured": False,
            "error": "TELEGRAM_BOT_TOKEN environment variable not set",
        }

    result = await get_bot_info()

    if not result.get("ok"):
        return {
            "configured": False,
            "error": result.get("error", result.get("description", "Unknown error")),
        }

    bot = result.get("result", {})
    return {
        "configured": True,
        "bot_id": bot.get("id"),
        "bot_username": bot.get("username"),
        "bot_name": bot.get("first_name"),
        "can_join_groups": bot.get("can_join_groups", False),
        "can_read_all_group_messages": bot.get("can_read_all_group_messages", False),
        "default_chat_id": TELEGRAM_CHAT_ID or "(not set)",
    }


@mcp.tool()
async def Telegram_SendMessage(
    message: str,
    chat_id: Optional[str] = None,
    disable_notification: bool = False,
) -> dict[str, Any]:
    """
    Send a message via Telegram.

    Automatically converts Slack-style emoji codes (e.g., :rocket:) to Unicode emoji.

    Args:
        message: Message text to send. Supports HTML formatting and Slack emoji codes.
        chat_id: Target chat ID. Uses TELEGRAM_CHAT_ID env var if not specified.
        disable_notification: If True, sends message silently.

    Returns:
        Message delivery status and message ID.

    Example messages:
        ":rocket: Project initialized: My App"
        ":white_check_mark: Completed: Timer Display feature"
        ":warning: Blocked: Missing API credentials"
    """
    target_chat_id = chat_id or TELEGRAM_CHAT_ID

    if not target_chat_id:
        return {
            "sent": False,
            "error": "No chat_id specified and TELEGRAM_CHAT_ID not configured",
        }

    result = await send_message(
        chat_id=target_chat_id,
        text=message,
        disable_notification=disable_notification,
    )

    if not result.get("ok"):
        return {
            "sent": False,
            "error": result.get("error", result.get("description", "Unknown error")),
            "chat_id": target_chat_id,
        }

    msg = result.get("result", {})
    return {
        "sent": True,
        "message_id": msg.get("message_id"),
        "chat_id": str(msg.get("chat", {}).get("id")),
        "chat_type": msg.get("chat", {}).get("type"),
        "date": msg.get("date"),
    }


@mcp.tool()
async def Telegram_ListChats() -> dict[str, Any]:
    """
    List recent chats that have interacted with the bot.

    Note: Telegram Bot API doesn't provide a direct way to list all chats.
    This returns chats from recent updates (messages sent to the bot).

    For the bot to receive messages, users must first send /start to the bot.

    Returns:
        List of unique chats from recent updates.
    """
    result = await get_updates()

    if not result.get("ok"):
        return {
            "chats": [],
            "error": result.get("error", result.get("description", "Unknown error")),
        }

    updates = result.get("result", [])
    chats: dict[int, dict[str, Any]] = {}

    for update in updates:
        message = update.get("message") or update.get("edited_message")
        if message and "chat" in message:
            chat = message["chat"]
            chat_id = chat["id"]
            if chat_id not in chats:
                chats[chat_id] = {
                    "id": str(chat_id),
                    "type": chat.get("type"),
                    "title": chat.get("title"),  # For groups
                    "username": chat.get("username"),  # For private chats
                    "first_name": chat.get("first_name"),
                    "last_name": chat.get("last_name"),
                }

    return {
        "chats": list(chats.values()),
        "count": len(chats),
        "note": "Only shows chats that have recently messaged the bot",
    }


# =============================================================================
# Health Check Endpoint
# =============================================================================


async def health_check(request):
    """
    Health check endpoint for container orchestration.

    Verifies Telegram bot token is configured and returns health status.
    Used by Docker healthcheck and load balancers.
    """
    if not TELEGRAM_BOT_TOKEN:
        return JSONResponse(
            {
                "status": "unhealthy",
                "service": "telegram-mcp-server",
                "error": "TELEGRAM_BOT_TOKEN not configured",
            },
            status_code=503,
        )

    # Optionally verify bot token is valid
    try:
        result = await get_bot_info()
        if result.get("ok"):
            return JSONResponse({
                "status": "healthy",
                "service": "telegram-mcp-server",
                "bot_configured": True,
                "bot_username": result.get("result", {}).get("username"),
            })
        else:
            return JSONResponse(
                {
                    "status": "unhealthy",
                    "service": "telegram-mcp-server",
                    "error": result.get("description", "Invalid bot token"),
                },
                status_code=503,
            )
    except Exception as e:
        return JSONResponse(
            {
                "status": "unhealthy",
                "service": "telegram-mcp-server",
                "error": str(e),
            },
            status_code=503,
        )


# =============================================================================
# ASGI Application
# =============================================================================

app = mcp.sse_app()

# Add health check route
app.routes.append(Route("/health", health_check, methods=["GET"]))


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
