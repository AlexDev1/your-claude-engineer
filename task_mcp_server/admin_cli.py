"""
Admin CLI for Task MCP Server Authentication
=============================================

Manage users and API keys for MCP server authentication.

Usage:
    docker exec -it mcp-task python admin_cli.py create-user agent
    docker exec -it mcp-task python admin_cli.py create-key agent --name "Production Key"
    docker exec -it mcp-task python admin_cli.py list-users
    docker exec -it mcp-task python admin_cli.py list-keys
    docker exec -it mcp-task python admin_cli.py revoke-key mcp_abcd
    docker exec -it mcp-task python admin_cli.py verify-key mcp_...
"""

import argparse
import asyncio
import hashlib
import secrets
import sys
from datetime import datetime, timezone

from database import db


def generate_api_key() -> str:
    """Generate a secure API key: mcp_ + 40 random hex characters."""
    return "mcp_" + secrets.token_hex(20)


async def cmd_create_user(args):
    """Create a new user."""
    await db.connect()
    try:
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO auth_users (username, email)
                VALUES ($1, $2)
                RETURNING id, username, email, created_at
                """,
                args.username,
                args.email,
            )
            print(f"User created:")
            print(f"  ID:       {row['id']}")
            print(f"  Username: {row['username']}")
            print(f"  Email:    {row['email'] or '(none)'}")
            print(f"  Created:  {row['created_at']}")
    except Exception as e:
        if "unique" in str(e).lower():
            print(f"Error: User '{args.username}' already exists.", file=sys.stderr)
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await db.disconnect()


async def cmd_create_key(args):
    """Create a new API key for a user."""
    await db.connect()
    try:
        async with db.acquire() as conn:
            # Find user
            user = await conn.fetchrow(
                "SELECT id, username FROM auth_users WHERE username = $1",
                args.username,
            )
            if not user:
                print(f"Error: User '{args.username}' not found.", file=sys.stderr)
                sys.exit(1)

            # Generate key
            raw_key = generate_api_key()
            key_prefix = raw_key[:8]
            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

            # Calculate expiration
            expires_at = None
            if args.expires_days:
                from datetime import timedelta

                expires_at = datetime.now(timezone.utc) + timedelta(days=args.expires_days)

            # Insert key
            row = await conn.fetchrow(
                """
                INSERT INTO auth_api_keys (user_id, name, key_prefix, key_hash, expires_at)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, created_at
                """,
                user["id"],
                args.name,
                key_prefix,
                key_hash,
                expires_at,
            )

            print(f"API key created for user '{user['username']}':")
            print(f"  Key ID:   {row['id']}")
            print(f"  Name:     {args.name}")
            print(f"  Prefix:   {key_prefix}")
            print(f"  Expires:  {expires_at or 'never'}")
            print()
            print(f"  API Key:  {raw_key}")
            print()
            print("  WARNING: This key will only be shown ONCE. Store it securely!")
    finally:
        await db.disconnect()


async def cmd_list_users(args):
    """List all users."""
    await db.connect()
    try:
        async with db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT u.id, u.username, u.email, u.is_active, u.created_at,
                       COUNT(k.id) AS key_count
                FROM auth_users u
                LEFT JOIN auth_api_keys k ON k.user_id = u.id AND k.is_active = TRUE AND k.revoked_at IS NULL
                GROUP BY u.id
                ORDER BY u.created_at
                """
            )
            if not rows:
                print("No users found.")
                return

            print(f"{'Username':<20} {'Email':<30} {'Active':<8} {'Keys':<6} {'Created'}")
            print("-" * 95)
            for row in rows:
                print(
                    f"{row['username']:<20} "
                    f"{(row['email'] or '-'):<30} "
                    f"{'yes' if row['is_active'] else 'no':<8} "
                    f"{row['key_count']:<6} "
                    f"{row['created_at'].strftime('%Y-%m-%d %H:%M')}"
                )
    finally:
        await db.disconnect()


async def cmd_list_keys(args):
    """List API keys, optionally filtered by username."""
    await db.connect()
    try:
        async with db.acquire() as conn:
            if args.username:
                rows = await conn.fetch(
                    """
                    SELECT k.id, k.name, k.key_prefix, k.is_active, k.expires_at,
                           k.last_used_at, k.last_used_ip, k.created_at, k.revoked_at,
                           u.username
                    FROM auth_api_keys k
                    JOIN auth_users u ON k.user_id = u.id
                    WHERE u.username = $1
                    ORDER BY k.created_at
                    """,
                    args.username,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT k.id, k.name, k.key_prefix, k.is_active, k.expires_at,
                           k.last_used_at, k.last_used_ip, k.created_at, k.revoked_at,
                           u.username
                    FROM auth_api_keys k
                    JOIN auth_users u ON k.user_id = u.id
                    ORDER BY k.created_at
                    """
                )

            if not rows:
                print("No API keys found.")
                return

            print(f"{'Prefix':<10} {'User':<15} {'Name':<20} {'Status':<10} {'Last Used':<20} {'Expires'}")
            print("-" * 100)
            for row in rows:
                if row["revoked_at"]:
                    status = "revoked"
                elif not row["is_active"]:
                    status = "inactive"
                elif row["expires_at"] and datetime.now(timezone.utc) > row["expires_at"]:
                    status = "expired"
                else:
                    status = "active"

                last_used = row["last_used_at"].strftime("%Y-%m-%d %H:%M") if row["last_used_at"] else "never"
                expires = row["expires_at"].strftime("%Y-%m-%d %H:%M") if row["expires_at"] else "never"

                print(
                    f"{row['key_prefix']:<10} "
                    f"{row['username']:<15} "
                    f"{row['name']:<20} "
                    f"{status:<10} "
                    f"{last_used:<20} "
                    f"{expires}"
                )
    finally:
        await db.disconnect()


async def cmd_revoke_key(args):
    """Revoke an API key by prefix."""
    await db.connect()
    try:
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE auth_api_keys
                SET is_active = FALSE, revoked_at = NOW()
                WHERE key_prefix = $1 AND revoked_at IS NULL
                RETURNING id, name, key_prefix
                """,
                args.key_prefix,
            )
            if not row:
                print(f"Error: No active key with prefix '{args.key_prefix}' found.", file=sys.stderr)
                sys.exit(1)

            print(f"Key revoked:")
            print(f"  ID:     {row['id']}")
            print(f"  Name:   {row['name']}")
            print(f"  Prefix: {row['key_prefix']}")
    finally:
        await db.disconnect()


async def cmd_verify_key(args):
    """Verify an API key (for debugging)."""
    await db.connect()
    try:
        key_hash = hashlib.sha256(args.key.encode()).hexdigest()
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT k.id, k.name, k.key_prefix, k.is_active, k.expires_at,
                       k.revoked_at, k.last_used_at, u.username, u.is_active AS user_active
                FROM auth_api_keys k
                JOIN auth_users u ON k.user_id = u.id
                WHERE k.key_hash = $1
                """,
                key_hash,
            )

            if not row:
                print("INVALID: Key not found in database.")
                sys.exit(1)

            print(f"Key found:")
            print(f"  Prefix:    {row['key_prefix']}")
            print(f"  Name:      {row['name']}")
            print(f"  User:      {row['username']}")
            print(f"  Key active:  {row['is_active']}")
            print(f"  User active: {row['user_active']}")
            print(f"  Revoked:   {row['revoked_at'] or 'no'}")
            print(f"  Expires:   {row['expires_at'] or 'never'}")
            print(f"  Last used: {row['last_used_at'] or 'never'}")

            # Check validity
            is_valid = True
            reasons = []
            if not row["is_active"]:
                is_valid = False
                reasons.append("key is inactive")
            if not row["user_active"]:
                is_valid = False
                reasons.append("user is inactive")
            if row["revoked_at"]:
                is_valid = False
                reasons.append("key is revoked")
            if row["expires_at"] and datetime.now(timezone.utc) > row["expires_at"]:
                is_valid = False
                reasons.append("key is expired")

            print()
            if is_valid:
                print("VALID: Key would be accepted.")
            else:
                print(f"INVALID: {', '.join(reasons)}")
                sys.exit(1)
    finally:
        await db.disconnect()


def main():
    parser = argparse.ArgumentParser(
        description="Admin CLI for Task MCP Server Authentication"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-user
    p_create_user = subparsers.add_parser("create-user", help="Create a new user")
    p_create_user.add_argument("username", help="Username")
    p_create_user.add_argument("--email", default=None, help="User email")

    # create-key
    p_create_key = subparsers.add_parser("create-key", help="Create API key for user")
    p_create_key.add_argument("username", help="Username")
    p_create_key.add_argument("--name", required=True, help="Key name/description")
    p_create_key.add_argument("--expires-days", type=int, default=None, help="Key expiration in days")

    # list-users
    subparsers.add_parser("list-users", help="List all users")

    # list-keys
    p_list_keys = subparsers.add_parser("list-keys", help="List API keys")
    p_list_keys.add_argument("--username", default=None, help="Filter by username")

    # revoke-key
    p_revoke = subparsers.add_parser("revoke-key", help="Revoke an API key")
    p_revoke.add_argument("key_prefix", help="Key prefix (first 8 chars, e.g. mcp_abcd)")

    # verify-key
    p_verify = subparsers.add_parser("verify-key", help="Verify an API key")
    p_verify.add_argument("key", help="Full API key to verify")

    args = parser.parse_args()

    commands = {
        "create-user": cmd_create_user,
        "create-key": cmd_create_key,
        "list-users": cmd_list_users,
        "list-keys": cmd_list_keys,
        "revoke-key": cmd_revoke_key,
        "verify-key": cmd_verify_key,
    }

    asyncio.run(commands[args.command](args))


if __name__ == "__main__":
    main()
