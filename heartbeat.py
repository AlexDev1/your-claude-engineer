#!/usr/bin/env python3
"""
Heartbeat Daemon (Local Development Version)
=============================================

Proactive monitoring daemon that periodically:
1. Checks /health endpoints of Task and Telegram MCP servers
2. Detects stuck "In Progress" tasks via Task_GetStaleIssues
3. Sends Telegram alerts when problems are detected

This is the local development version that uses the same MCP server URLs
as the main agent configuration.

Run:
    python heartbeat.py

Or with custom settings:
    HEARTBEAT_INTERVAL_MINUTES=1 STALE_THRESHOLD_HOURS=0.5 python heartbeat.py

Configuration via environment variables (from .env):
    TASK_MCP_URL - Task MCP server URL
    TELEGRAM_MCP_URL - Telegram MCP server URL
    MCP_API_KEY - API key for MCP servers
    HEARTBEAT_INTERVAL_MINUTES - Check interval (default: 5)
    STALE_THRESHOLD_HOURS - Hours to consider task stale (default: 2)
    HEARTBEAT_TEAM - Team to monitor (optional)
    TELEGRAM_BOT_TOKEN - Telegram bot token
    TELEGRAM_CHAT_ID - Telegram chat ID
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

# Load .env file
load_dotenv()

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("heartbeat")


# =============================================================================
# Configuration
# =============================================================================


class Config:
    """Heartbeat configuration from environment."""

    def __init__(self):
        # Get MCP URLs from .env and derive health endpoints
        task_mcp_url = os.environ.get("TASK_MCP_URL", "http://localhost:8001/sse")
        telegram_mcp_url = os.environ.get("TELEGRAM_MCP_URL", "http://localhost:8002/sse")

        # Derive health URLs from SSE URLs
        self.task_mcp_health_url = self._derive_health_url(task_mcp_url)
        self.telegram_mcp_health_url = self._derive_health_url(telegram_mcp_url)

        # Derive stale issues URL
        self.task_stale_url = self._derive_stale_url(task_mcp_url)

        # API key for authenticated endpoints
        self.mcp_api_key = os.environ.get("MCP_API_KEY", "")

        # Heartbeat settings
        self.interval_minutes = int(
            os.environ.get("HEARTBEAT_INTERVAL_MINUTES", "5")
        )
        self.stale_threshold_hours = float(
            os.environ.get("STALE_THRESHOLD_HOURS", "2")
        )
        self.team = os.environ.get("HEARTBEAT_TEAM", "")

        # Telegram settings
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    def _derive_health_url(self, sse_url: str) -> str:
        """Derive health URL from SSE URL."""
        # https://mcp.axoncode.pro/task/sse -> https://mcp.axoncode.pro/task/health
        return sse_url.replace("/sse", "/health")

    def _derive_stale_url(self, sse_url: str) -> str:
        """Derive stale issues URL from SSE URL."""
        # https://mcp.axoncode.pro/task/sse -> https://mcp.axoncode.pro/task/stale-issues
        return sse_url.replace("/sse", "/stale-issues")

    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN not configured")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID not configured")
        return errors


config = Config()


# =============================================================================
# Health Check
# =============================================================================


async def check_health(
    url: str, name: str, client: httpx.AsyncClient
) -> dict[str, Any]:
    """
    Check health of an MCP server.

    Returns:
        dict with 'healthy', 'status_code', 'response', 'error' keys
    """
    headers = {}
    if config.mcp_api_key:
        headers["Authorization"] = f"Bearer {config.mcp_api_key}"

    try:
        response = await client.get(url, headers=headers, timeout=10.0)
        data = response.json() if response.status_code == 200 else None

        return {
            "name": name,
            "url": url,
            "healthy": response.status_code == 200,
            "status_code": response.status_code,
            "response": data,
            "error": None,
        }
    except httpx.TimeoutException:
        return {
            "name": name,
            "url": url,
            "healthy": False,
            "status_code": None,
            "response": None,
            "error": "Timeout (10s)",
        }
    except httpx.ConnectError as e:
        return {
            "name": name,
            "url": url,
            "healthy": False,
            "status_code": None,
            "response": None,
            "error": f"Connection failed: {e}",
        }
    except Exception as e:
        return {
            "name": name,
            "url": url,
            "healthy": False,
            "status_code": None,
            "response": None,
            "error": str(e),
        }


# =============================================================================
# Stale Issues Check
# =============================================================================


async def get_stale_issues(client: httpx.AsyncClient) -> dict[str, Any]:
    """Get stale issues via REST endpoint."""
    headers = {}
    if config.mcp_api_key:
        headers["Authorization"] = f"Bearer {config.mcp_api_key}"

    try:
        params = {"threshold_hours": config.stale_threshold_hours}
        if config.team:
            params["team"] = config.team

        response = await client.get(
            config.task_stale_url,
            headers=headers,
            params=params,
            timeout=30.0,
        )

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            logger.warning("Stale issues endpoint not found, skipping check")
            return {"stale_count": 0, "issues": []}
        else:
            return {
                "error": f"HTTP {response.status_code}",
                "stale_count": 0,
                "issues": [],
            }
    except Exception as e:
        logger.error(f"Failed to get stale issues: {e}")
        return {"error": str(e), "stale_count": 0, "issues": []}


# =============================================================================
# Telegram Notifications
# =============================================================================


async def send_telegram_alert(
    message: str,
    client: httpx.AsyncClient,
    parse_mode: str = "HTML",
) -> bool:
    """Send alert message to Telegram."""
    if not config.telegram_bot_token or not config.telegram_chat_id:
        logger.warning("Telegram not configured, skipping alert")
        return False

    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": config.telegram_chat_id,
        "text": message,
        "parse_mode": parse_mode,
    }

    try:
        response = await client.post(url, json=payload, timeout=30.0)
        if response.status_code == 200:
            logger.info("Telegram alert sent successfully")
            return True
        else:
            logger.error(
                f"Telegram API error: {response.status_code} - {response.text}"
            )
            return False
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False


def format_health_alert(results: list[dict[str, Any]]) -> str:
    """Format health check results as Telegram message."""
    unhealthy = [r for r in results if not r["healthy"]]
    if not unhealthy:
        return ""

    lines = ["<b>MCP Server Health Alert</b>", ""]

    for r in unhealthy:
        lines.append(f"<b>{r['name']}</b>: UNHEALTHY")
        if r["status_code"]:
            lines.append(f"  Status: {r['status_code']}")
        if r["error"]:
            lines.append(f"  Error: {r['error']}")
        lines.append("")

    lines.append(f"<i>Checked at {datetime.now().strftime('%H:%M:%S')}</i>")
    return "\n".join(lines)


def format_stale_issues_alert(data: dict[str, Any]) -> str:
    """Format stale issues as Telegram message."""
    if data.get("stale_count", 0) == 0:
        return ""

    issues = data.get("issues", [])
    lines = [
        "<b>Stale Tasks Alert</b>",
        f"Found {len(issues)} task(s) stuck in 'In Progress':",
        "",
    ]

    for issue in issues[:5]:  # Limit to 5 issues
        identifier = issue.get("identifier", "?")
        title = issue.get("title", "Unknown")[:50]
        hours = issue.get("hours_stale", 0)
        lines.append(f"<b>{identifier}</b>: {title}")
        lines.append(f"  Stale for {hours:.1f} hours")
        lines.append("")

    if len(issues) > 5:
        lines.append(f"<i>... and {len(issues) - 5} more</i>")
        lines.append("")

    lines.append(f"<i>Threshold: {config.stale_threshold_hours}h</i>")
    return "\n".join(lines)


# =============================================================================
# Main Heartbeat Loop
# =============================================================================


async def run_heartbeat_check() -> None:
    """Run a single heartbeat check cycle."""
    logger.info("Running heartbeat check...")

    async with httpx.AsyncClient() as client:
        # 1. Check MCP server health
        health_results = await asyncio.gather(
            check_health(config.task_mcp_health_url, "Task MCP", client),
            check_health(config.telegram_mcp_health_url, "Telegram MCP", client),
        )

        # Log health status
        for r in health_results:
            status = "OK" if r["healthy"] else "FAIL"
            logger.info(f"  {r['name']}: {status}")
            if r["error"]:
                logger.warning(f"    Error: {r['error']}")

        # Send alert if any unhealthy
        health_alert = format_health_alert(health_results)
        if health_alert:
            await send_telegram_alert(health_alert, client)

        # 2. Check for stale issues (only if Task MCP is healthy)
        task_healthy = health_results[0]["healthy"]
        if task_healthy:
            stale_data = await get_stale_issues(client)
            stale_count = stale_data.get("stale_count", 0)
            logger.info(f"  Stale issues: {stale_count}")

            stale_alert = format_stale_issues_alert(stale_data)
            if stale_alert:
                await send_telegram_alert(stale_alert, client)
        else:
            logger.warning("  Skipping stale issues check (Task MCP unhealthy)")

    logger.info("Heartbeat check complete")


async def main() -> None:
    """Main entry point - run heartbeat loop."""
    logger.info("=" * 60)
    logger.info("Heartbeat Daemon Starting (Local Development)")
    logger.info("=" * 60)
    logger.info(f"Task MCP Health URL: {config.task_mcp_health_url}")
    logger.info(f"Telegram MCP Health URL: {config.telegram_mcp_health_url}")
    logger.info(f"Stale Issues URL: {config.task_stale_url}")
    logger.info(f"Check interval: {config.interval_minutes} minutes")
    logger.info(f"Stale threshold: {config.stale_threshold_hours} hours")
    if config.team:
        logger.info(f"Team filter: {config.team}")
    logger.info(f"Telegram configured: {bool(config.telegram_bot_token)}")
    logger.info(f"API key configured: {bool(config.mcp_api_key)}")
    logger.info("=" * 60)

    # Validate configuration
    errors = config.validate()
    if errors:
        for error in errors:
            logger.warning(f"Config warning: {error}")

    # Run initial check
    await run_heartbeat_check()

    # Main loop
    interval_seconds = config.interval_minutes * 60
    while True:
        logger.info(f"Next check in {config.interval_minutes} minutes...")
        await asyncio.sleep(interval_seconds)
        await run_heartbeat_check()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Heartbeat daemon stopped by user")
    except Exception as e:
        logger.error(f"Heartbeat daemon crashed: {e}")
        sys.exit(1)
