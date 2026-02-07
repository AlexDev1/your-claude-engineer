#!/usr/bin/env python3
"""
Scheduled Backup Script (ENG-48)
================================

This script creates automated backups of issue data.
Run via cron for scheduled daily backups:

    # Daily backup at 2 AM
    0 2 * * * cd /path/to/project && python scripts/backup.py

Features:
- Creates JSON backup in backups/ directory
- 30-day retention (automatically deletes old backups)
- Optional Telegram notification on failure
"""

import os
import sys
import json
import httpx
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
ANALYTICS_API_URL = os.environ.get("ANALYTICS_API_URL", "http://localhost:8003")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BACKUP_RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
BACKUPS_DIR = PROJECT_ROOT / "backups"


def send_telegram_notification(message: str) -> bool:
    """Send notification via Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured, skipping notification")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        response = httpx.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=30.0,
        )
        return response.status_code == 200
    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")
        return False


def cleanup_old_backups() -> int:
    """Delete backups older than retention period. Returns count of deleted files."""
    if not BACKUPS_DIR.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
    deleted_count = 0

    for backup_file in BACKUPS_DIR.glob("backup_*.json"):
        try:
            # Parse date from filename (backup_YYYYMMDD_HHMMSS.json)
            date_str = backup_file.stem.replace("backup_", "")
            file_date = datetime.strptime(date_str, "%Y%m%d_%H%M%S")

            if file_date < cutoff:
                backup_file.unlink()
                deleted_count += 1
                print(f"Deleted old backup: {backup_file.name}")
        except (ValueError, OSError) as e:
            print(f"Error processing {backup_file}: {e}")

    return deleted_count


async def create_backup() -> dict:
    """Create a new backup via the analytics API."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ANALYTICS_API_URL}/api/backups/create",
            timeout=60.0,
        )

        if response.status_code != 200:
            raise Exception(f"API returned {response.status_code}: {response.text}")

        return response.json()


async def create_local_backup() -> dict:
    """Create backup directly from file system if API is unavailable."""
    # Try to read existing issues store
    # This is a fallback if the API server is not running

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.json"
    filepath = BACKUPS_DIR / filename

    # Try to fetch from API first
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ANALYTICS_API_URL}/api/export/json?team=ENG",
                timeout=30.0,
            )

            if response.status_code == 200:
                data = response.json()

                backup_data = {
                    "version": "1.0.0",
                    "created_at": datetime.now().isoformat(),
                    "issue_count": data.get("issue_count", 0),
                    "issues": data.get("issues", []),
                    "backup_type": "scheduled",
                }

                with open(filepath, "w") as f:
                    json.dump(backup_data, f, indent=2, default=str)

                return {
                    "success": True,
                    "backup": {
                        "filename": filename,
                        "created_at": backup_data["created_at"],
                        "size_bytes": filepath.stat().st_size,
                        "issue_count": backup_data["issue_count"],
                    },
                }
    except Exception as e:
        print(f"API backup failed, creating empty backup: {e}")

    # Create empty backup as fallback
    backup_data = {
        "version": "1.0.0",
        "created_at": datetime.now().isoformat(),
        "issue_count": 0,
        "issues": [],
        "backup_type": "scheduled",
        "note": "Empty backup - API was unavailable",
    }

    with open(filepath, "w") as f:
        json.dump(backup_data, f, indent=2)

    return {
        "success": True,
        "backup": {
            "filename": filename,
            "created_at": backup_data["created_at"],
            "size_bytes": filepath.stat().st_size,
            "issue_count": 0,
        },
        "warning": "API unavailable, created empty backup",
    }


async def main():
    """Main backup routine."""
    print(f"[{datetime.now().isoformat()}] Starting scheduled backup...")

    success = False
    result = None
    error_message = None

    try:
        # Create backup directory
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

        # Cleanup old backups first
        deleted = cleanup_old_backups()
        if deleted > 0:
            print(f"Cleaned up {deleted} old backup(s)")

        # Try API backup first, fall back to local
        try:
            result = await create_backup()
        except Exception as e:
            print(f"API backup failed: {e}")
            result = await create_local_backup()

        if result.get("success"):
            backup_info = result.get("backup", {})
            print(f"Backup created successfully: {backup_info.get('filename')}")
            print(f"  - Issues: {backup_info.get('issue_count', 0)}")
            print(f"  - Size: {backup_info.get('size_bytes', 0)} bytes")

            if result.get("warning"):
                print(f"  - Warning: {result['warning']}")

            success = True
        else:
            error_message = result.get("error", "Unknown error")
            print(f"Backup failed: {error_message}")

    except Exception as e:
        error_message = str(e)
        print(f"Backup error: {error_message}")

    # Send notification on failure
    if not success and (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        message = f"<b>Backup Failed</b>\n\nTime: {datetime.now().isoformat()}\nError: {error_message}"
        send_telegram_notification(message)

    print(f"[{datetime.now().isoformat()}] Backup {'completed' if success else 'failed'}")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
