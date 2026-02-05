"""
Database Connection and Queries for Task MCP Server
====================================================

Async PostgreSQL connection using asyncpg.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Optional
from uuid import UUID

import asyncpg


def _get_database_url() -> str:
    """
    Build database URL with support for Docker secrets.

    Reads password from /run/secrets/db_password if available,
    otherwise falls back to environment variable.
    """
    base_url = os.environ.get(
        "DATABASE_URL", "postgresql://agent:password@localhost:5432/tasks"
    )

    # Try to read password from Docker secret
    secret_path = Path("/run/secrets/db_password")
    if secret_path.exists():
        password = secret_path.read_text().strip()
        # Replace password placeholder in URL
        # URL format: postgresql://user:password@host:port/db
        if "@" in base_url and "://" in base_url:
            # Extract parts
            protocol_user = base_url.split("@")[0]  # postgresql://user:password
            host_db = base_url.split("@")[1]  # host:port/db

            # Get user part
            protocol = protocol_user.split("://")[0]  # postgresql
            user_pass = protocol_user.split("://")[1]  # user:password
            user = user_pass.split(":")[0]  # user

            # Rebuild URL with secret password
            return f"{protocol}://{user}:{password}@{host_db}"

    return base_url


# Database URL with Docker secrets support
DATABASE_URL = _get_database_url()


class Database:
    """Async database connection pool manager."""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self, max_retries: int = 10, retry_delay: float = 2.0) -> None:
        """Create connection pool with enterprise-grade settings and retry logic."""
        import asyncio
        import socket
        import urllib.parse

        # Resolve hostname to IP to avoid DNS caching issues
        db_url = DATABASE_URL
        if "@postgres:" in db_url or "@postgres/" in db_url:
            try:
                ip = socket.gethostbyname("postgres")
                db_url = db_url.replace("@postgres:", f"@{ip}:").replace("@postgres/", f"@{ip}/")
            except socket.gaierror:
                pass  # Will retry with hostname

        # Parse connection parameters from URL
        parsed = urllib.parse.urlparse(db_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        user = parsed.username or "agent"
        password = parsed.password or ""
        database = parsed.path.lstrip("/") or "tasks"

        last_error = None
        for attempt in range(max_retries):
            try:
                self.pool = await asyncpg.create_pool(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=database,
                    min_size=5,
                    max_size=50,
                    command_timeout=60,
                    max_inactive_connection_lifetime=300,  # 5 min idle timeout
                    ssl=False,  # Disable SSL for internal Docker network
                )
                return
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    await asyncio.sleep(wait_time)

        raise RuntimeError(f"Failed to connect to database after {max_retries} attempts: {last_error}")

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Acquire connection from pool."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        async with self.pool.acquire() as conn:
            yield conn


# Global database instance
db = Database()


# =============================================================================
# Team Queries
# =============================================================================


async def get_teams() -> list[dict[str, Any]]:
    """Get all teams."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, key, name, created_at FROM teams ORDER BY name"
        )
        return [dict(row) for row in rows]


async def get_team_by_key_or_name(key_or_name: str) -> Optional[dict[str, Any]]:
    """Get team by key or name."""
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, key, name, created_at FROM teams
            WHERE key = $1 OR LOWER(name) = LOWER($1)
            """,
            key_or_name,
        )
        return dict(row) if row else None


async def create_team(key: str, name: str) -> dict[str, Any]:
    """Create a new team."""
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO teams (key, name)
            VALUES ($1, $2)
            RETURNING id, key, name, created_at
            """,
            key.upper(),
            name,
        )
        # Initialize counter
        await conn.execute(
            """
            INSERT INTO issue_counters (team_key, counter)
            VALUES ($1, 0)
            ON CONFLICT (team_key) DO NOTHING
            """,
            key.upper(),
        )
        # Create default workflow states
        team_id = row["id"]
        await conn.executemany(
            """
            INSERT INTO workflow_states (team_id, name, type, position)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (team_id, name) DO NOTHING
            """,
            [
                (team_id, "Backlog", "backlog", 0),
                (team_id, "Todo", "unstarted", 1),
                (team_id, "In Progress", "started", 2),
                (team_id, "Done", "completed", 3),
                (team_id, "Canceled", "canceled", 4),
            ],
        )
        return dict(row)


# =============================================================================
# Workflow State Queries
# =============================================================================


async def get_workflow_states(team_id: UUID) -> list[dict[str, Any]]:
    """Get workflow states for a team."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, team_id, name, type, position
            FROM workflow_states
            WHERE team_id = $1
            ORDER BY position
            """,
            team_id,
        )
        return [dict(row) for row in rows]


async def get_workflow_state_by_name(
    team_id: UUID, state_name: str
) -> Optional[dict[str, Any]]:
    """Get workflow state by name."""
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, team_id, name, type, position
            FROM workflow_states
            WHERE team_id = $1 AND LOWER(name) = LOWER($2)
            """,
            team_id,
            state_name,
        )
        return dict(row) if row else None


# =============================================================================
# Project Queries
# =============================================================================


async def get_projects(team_id: Optional[UUID] = None) -> list[dict[str, Any]]:
    """Get all projects, optionally filtered by team."""
    async with db.acquire() as conn:
        if team_id:
            rows = await conn.fetch(
                """
                SELECT p.id, p.name, p.slug, p.description, p.team_id,
                       p.created_at, p.updated_at, t.key as team_key
                FROM projects p
                JOIN teams t ON p.team_id = t.id
                WHERE p.team_id = $1
                ORDER BY p.name
                """,
                team_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT p.id, p.name, p.slug, p.description, p.team_id,
                       p.created_at, p.updated_at, t.key as team_key
                FROM projects p
                JOIN teams t ON p.team_id = t.id
                ORDER BY p.name
                """
            )
        return [dict(row) for row in rows]


async def get_project_by_slug_or_name(
    slug_or_name: str, team_id: Optional[UUID] = None
) -> Optional[dict[str, Any]]:
    """Get project by slug or name."""
    async with db.acquire() as conn:
        if team_id:
            row = await conn.fetchrow(
                """
                SELECT p.id, p.name, p.slug, p.description, p.team_id,
                       p.created_at, p.updated_at, t.key as team_key
                FROM projects p
                JOIN teams t ON p.team_id = t.id
                WHERE (p.slug = $1 OR LOWER(p.name) = LOWER($1)) AND p.team_id = $2
                """,
                slug_or_name,
                team_id,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT p.id, p.name, p.slug, p.description, p.team_id,
                       p.created_at, p.updated_at, t.key as team_key
                FROM projects p
                JOIN teams t ON p.team_id = t.id
                WHERE p.slug = $1 OR LOWER(p.name) = LOWER($1)
                """,
                slug_or_name,
            )
        return dict(row) if row else None


async def create_project(
    name: str, team_id: UUID, description: Optional[str] = None
) -> dict[str, Any]:
    """Create a new project."""
    # Generate slug from name
    slug = name.lower().replace(" ", "-").replace("_", "-")
    # Remove non-alphanumeric characters except hyphens
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO projects (name, slug, description, team_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id, name, slug, description, team_id, created_at, updated_at
            """,
            name,
            slug,
            description,
            team_id,
        )
        return dict(row)


# =============================================================================
# Issue Queries
# =============================================================================


async def get_issues(
    team_id: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    state_id: Optional[UUID] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Get issues with optional filters."""
    async with db.acquire() as conn:
        query = """
            SELECT i.id, i.identifier, i.title, i.description, i.priority,
                   i.state_id, ws.name as state_name, ws.type as state_type,
                   i.project_id, p.name as project_name,
                   i.team_id, t.key as team_key,
                   i.created_at, i.updated_at
            FROM issues i
            LEFT JOIN workflow_states ws ON i.state_id = ws.id
            LEFT JOIN projects p ON i.project_id = p.id
            JOIN teams t ON i.team_id = t.id
            WHERE 1=1
        """
        params = []
        param_idx = 1

        if team_id:
            query += f" AND i.team_id = ${param_idx}"
            params.append(team_id)
            param_idx += 1

        if project_id:
            query += f" AND i.project_id = ${param_idx}"
            params.append(project_id)
            param_idx += 1

        if state_id:
            query += f" AND i.state_id = ${param_idx}"
            params.append(state_id)
            param_idx += 1

        query += f" ORDER BY i.created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def get_issue_by_identifier_or_id(identifier_or_id: str) -> Optional[dict[str, Any]]:
    """Get issue by identifier (ENG-42) or UUID."""
    async with db.acquire() as conn:
        # Try as identifier first
        row = await conn.fetchrow(
            """
            SELECT i.id, i.identifier, i.title, i.description, i.priority,
                   i.state_id, ws.name as state_name, ws.type as state_type,
                   i.project_id, p.name as project_name,
                   i.team_id, t.key as team_key,
                   i.created_at, i.updated_at
            FROM issues i
            LEFT JOIN workflow_states ws ON i.state_id = ws.id
            LEFT JOIN projects p ON i.project_id = p.id
            JOIN teams t ON i.team_id = t.id
            WHERE i.identifier = $1
            """,
            identifier_or_id.upper(),
        )
        if row:
            return dict(row)

        # Try as UUID
        try:
            uuid_val = UUID(identifier_or_id)
            row = await conn.fetchrow(
                """
                SELECT i.id, i.identifier, i.title, i.description, i.priority,
                       i.state_id, ws.name as state_name, ws.type as state_type,
                       i.project_id, p.name as project_name,
                       i.team_id, t.key as team_key,
                       i.created_at, i.updated_at
                FROM issues i
                LEFT JOIN workflow_states ws ON i.state_id = ws.id
                LEFT JOIN projects p ON i.project_id = p.id
                JOIN teams t ON i.team_id = t.id
                WHERE i.id = $1
                """,
                uuid_val,
            )
            return dict(row) if row else None
        except ValueError:
            return None


async def create_issue(
    team_id: UUID,
    team_key: str,
    title: str,
    description: Optional[str] = None,
    project_id: Optional[UUID] = None,
    priority: str = "medium",
) -> dict[str, Any]:
    """Create a new issue with explicit transaction."""
    async with db.acquire() as conn:
        # Use explicit transaction for atomicity
        async with conn.transaction():
            # Get next identifier (uses FOR UPDATE internally)
            identifier = await conn.fetchval(
                "SELECT get_next_issue_identifier($1)", team_key
            )

            # Get default state (Todo)
            default_state = await conn.fetchrow(
                """
                SELECT id FROM workflow_states
                WHERE team_id = $1 AND name = 'Todo'
                """,
                team_id,
            )
            state_id = default_state["id"] if default_state else None

            row = await conn.fetchrow(
                """
                INSERT INTO issues (identifier, title, description, priority, state_id, project_id, team_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, identifier, title, description, priority, state_id, project_id, team_id, created_at, updated_at
                """,
                identifier,
                title,
                description,
                priority,
                state_id,
                project_id,
                team_id,
            )
            return dict(row)


async def update_issue(
    issue_id: UUID,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    project_id: Optional[UUID] = None,
    state_id: Optional[UUID] = None,
) -> Optional[dict[str, Any]]:
    """Update an issue."""
    async with db.acquire() as conn:
        # Build dynamic update query
        updates = []
        params = []
        param_idx = 1

        if title is not None:
            updates.append(f"title = ${param_idx}")
            params.append(title)
            param_idx += 1

        if description is not None:
            updates.append(f"description = ${param_idx}")
            params.append(description)
            param_idx += 1

        if priority is not None:
            updates.append(f"priority = ${param_idx}")
            params.append(priority)
            param_idx += 1

        if project_id is not None:
            updates.append(f"project_id = ${param_idx}")
            params.append(project_id)
            param_idx += 1

        if state_id is not None:
            updates.append(f"state_id = ${param_idx}")
            params.append(state_id)
            param_idx += 1

        if not updates:
            return await get_issue_by_identifier_or_id(str(issue_id))

        query = f"""
            UPDATE issues
            SET {", ".join(updates)}
            WHERE id = ${param_idx}
            RETURNING id, identifier, title, description, priority, state_id, project_id, team_id, created_at, updated_at
        """
        params.append(issue_id)

        row = await conn.fetchrow(query, *params)
        return dict(row) if row else None


async def transition_issue_state(
    issue_id: UUID, target_state_id: UUID
) -> Optional[dict[str, Any]]:
    """Transition issue to a new state."""
    return await update_issue(issue_id, state_id=target_state_id)


# =============================================================================
# Comment Queries
# =============================================================================


async def get_comments(issue_id: UUID) -> list[dict[str, Any]]:
    """Get comments for an issue."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, issue_id, body, created_at
            FROM comments
            WHERE issue_id = $1
            ORDER BY created_at ASC
            """,
            issue_id,
        )
        return [dict(row) for row in rows]


async def add_comment(issue_id: UUID, body: str) -> dict[str, Any]:
    """Add a comment to an issue."""
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO comments (issue_id, body)
            VALUES ($1, $2)
            RETURNING id, issue_id, body, created_at
            """,
            issue_id,
            body,
        )
        return dict(row)
