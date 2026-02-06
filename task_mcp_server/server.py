"""
Task MCP Server
===============

FastMCP server providing task management functionality.
Replaces Linear with a self-hosted PostgreSQL-backed solution.

Run with:
    uvicorn server:app --host 0.0.0.0 --port 8000

Or for development:
    python server.py
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
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

from database import (
    db,
    get_teams,
    get_team_by_key_or_name,
    create_team,
    get_workflow_states,
    get_workflow_state_by_name,
    get_projects,
    get_project_by_slug_or_name,
    create_project,
    get_issues,
    get_issue_by_identifier_or_id,
    create_issue,
    update_issue,
    get_comments,
    add_comment,
)
from models import (
    UserInfo,
    Team,
    ProjectCreate,
    IssueCreate,
    IssueUpdate,
    IssueListFilter,
    StateTransition,
    CommentCreate,
)


# =============================================================================
# Server Setup
# =============================================================================


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

# Import security settings
from mcp.server.transport_security import TransportSecuritySettings

transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=ALLOWED_HOSTS,
)

# Create FastMCP server
mcp = FastMCP("Task MCP Server", transport_security=transport_security)


# =============================================================================
# MCP Tools (10 tools)
# =============================================================================


@mcp.tool()
async def Task_WhoAmI() -> dict[str, Any]:
    """
    Get profile information and list of teams.

    Returns user profile with available teams for task management.
    """
    teams_data = await get_teams()
    teams = [
        Team(
            id=t["id"],
            key=t["key"],
            name=t["name"],
            created_at=t["created_at"],
        )
        for t in teams_data
    ]

    user_info = UserInfo(
        name=os.environ.get("AGENT_NAME", "Task Agent"),
        email=os.environ.get("AGENT_EMAIL", "agent@local"),
        teams=teams,
    )

    return {
        "name": user_info.name,
        "email": user_info.email,
        "teams": [
            {"id": str(t.id), "key": t.key, "name": t.name}
            for t in user_info.teams
        ],
    }


@mcp.tool()
async def Task_ListTeams() -> dict[str, Any]:
    """
    List all available teams.

    Returns a list of teams with their keys and names.
    """
    teams_data = await get_teams()
    return {
        "teams": [
            {
                "id": str(t["id"]),
                "key": t["key"],
                "name": t["name"],
                "created_at": t["created_at"].isoformat(),
            }
            for t in teams_data
        ]
    }


@mcp.tool()
async def Task_CreateProject(
    name: str,
    team: str,
    description: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create a new project.

    Args:
        name: Project name
        team: Team key (e.g., "ENG") or team name
        description: Optional project description

    Returns:
        Created project details including slug
    """
    # Find team
    team_data = await get_team_by_key_or_name(team)
    if not team_data:
        return {"error": f"Team '{team}' not found"}

    project = await create_project(
        name=name,
        team_id=team_data["id"],
        description=description,
    )

    return {
        "id": str(project["id"]),
        "name": project["name"],
        "slug": project["slug"],
        "description": project["description"],
        "team_id": str(project["team_id"]),
        "team_key": team_data["key"],
        "created_at": project["created_at"].isoformat(),
    }


@mcp.tool()
async def Task_CreateIssue(
    team: str,
    title: str,
    description: Optional[str] = None,
    project: Optional[str] = None,
    priority: str = "medium",
) -> dict[str, Any]:
    """
    Create a new issue/task.

    Args:
        team: Team key (e.g., "ENG") or team name
        title: Issue title
        description: Optional detailed description with test steps
        project: Optional project slug or name
        priority: Priority level (urgent, high, medium, low)

    Returns:
        Created issue with identifier (e.g., ENG-42)
    """
    # Find team
    team_data = await get_team_by_key_or_name(team)
    if not team_data:
        return {"error": f"Team '{team}' not found"}

    # Find project if specified
    project_id = None
    if project:
        project_data = await get_project_by_slug_or_name(project, team_data["id"])
        if project_data:
            project_id = project_data["id"]

    issue = await create_issue(
        team_id=team_data["id"],
        team_key=team_data["key"],
        title=title,
        description=description,
        project_id=project_id,
        priority=priority,
    )

    return {
        "id": str(issue["id"]),
        "identifier": issue["identifier"],
        "title": issue["title"],
        "description": issue["description"],
        "priority": issue["priority"],
        "state": "Todo",
        "project_id": str(issue["project_id"]) if issue["project_id"] else None,
        "team_id": str(issue["team_id"]),
        "team_key": team_data["key"],
        "created_at": issue["created_at"].isoformat(),
    }


@mcp.tool()
async def Task_ListIssues(
    team: Optional[str] = None,
    project: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    List issues with optional filters.

    Args:
        team: Filter by team key or name
        project: Filter by project slug or name
        state: Filter by state name (Todo, In Progress, Done)
        limit: Maximum number of issues to return (max 100)
        offset: Number of issues to skip

    Returns:
        List of issues matching filters
    """
    team_id = None
    project_id = None
    state_id = None

    if team:
        team_data = await get_team_by_key_or_name(team)
        if team_data:
            team_id = team_data["id"]

            if project:
                project_data = await get_project_by_slug_or_name(project, team_id)
                if project_data:
                    project_id = project_data["id"]

            if state:
                state_data = await get_workflow_state_by_name(team_id, state)
                if state_data:
                    state_id = state_data["id"]

    issues = await get_issues(
        team_id=team_id,
        project_id=project_id,
        state_id=state_id,
        limit=min(limit, 100),
        offset=max(offset, 0),
    )

    return {
        "issues": [
            {
                "id": str(i["id"]),
                "identifier": i["identifier"],
                "title": i["title"],
                "description": i["description"],
                "priority": i["priority"],
                "state": i["state_name"],
                "state_type": i["state_type"],
                "project": i["project_name"],
                "team_key": i["team_key"],
                "created_at": i["created_at"].isoformat(),
                "updated_at": i["updated_at"].isoformat(),
            }
            for i in issues
        ],
        "count": len(issues),
    }


@mcp.tool()
async def Task_GetIssue(issue_id: str) -> dict[str, Any]:
    """
    Get issue details by identifier or UUID.

    Args:
        issue_id: Issue identifier (e.g., ENG-42) or UUID

    Returns:
        Full issue details including comments
    """
    issue = await get_issue_by_identifier_or_id(issue_id)
    if not issue:
        return {"error": f"Issue '{issue_id}' not found"}

    # Get comments
    comments = await get_comments(issue["id"])

    return {
        "id": str(issue["id"]),
        "identifier": issue["identifier"],
        "title": issue["title"],
        "description": issue["description"],
        "priority": issue["priority"],
        "state": issue["state_name"],
        "state_type": issue["state_type"],
        "project": issue["project_name"],
        "project_id": str(issue["project_id"]) if issue["project_id"] else None,
        "team_key": issue["team_key"],
        "team_id": str(issue["team_id"]),
        "created_at": issue["created_at"].isoformat(),
        "updated_at": issue["updated_at"].isoformat(),
        "comments": [
            {
                "id": str(c["id"]),
                "body": c["body"],
                "created_at": c["created_at"].isoformat(),
            }
            for c in comments
        ],
    }


@mcp.tool()
async def Task_UpdateIssue(
    issue_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    project: Optional[str] = None,
) -> dict[str, Any]:
    """
    Update issue fields.

    Args:
        issue_id: Issue identifier (e.g., ENG-42) or UUID
        title: New title (optional)
        description: New description (optional)
        priority: New priority (optional)
        project: New project slug or name (optional)

    Returns:
        Updated issue details
    """
    issue = await get_issue_by_identifier_or_id(issue_id)
    if not issue:
        return {"error": f"Issue '{issue_id}' not found"}

    # Find project if specified
    project_id = None
    if project:
        project_data = await get_project_by_slug_or_name(project, issue["team_id"])
        if project_data:
            project_id = project_data["id"]

    updated = await update_issue(
        issue_id=issue["id"],
        title=title,
        description=description,
        priority=priority,
        project_id=project_id,
    )

    if not updated:
        return {"error": "Failed to update issue"}

    return await Task_GetIssue(str(updated["id"]))


@mcp.tool()
async def Task_TransitionIssueState(
    issue_id: str,
    target_state: str,
) -> dict[str, Any]:
    """
    Transition issue to a new workflow state.

    Args:
        issue_id: Issue identifier (e.g., ENG-42) or UUID
        target_state: Target state name (Backlog, Todo, In Progress, Done, Canceled)

    Returns:
        Updated issue details
    """
    issue = await get_issue_by_identifier_or_id(issue_id)
    if not issue:
        return {"error": f"Issue '{issue_id}' not found"}

    # Find target state
    state = await get_workflow_state_by_name(issue["team_id"], target_state)
    if not state:
        return {"error": f"State '{target_state}' not found"}

    updated = await update_issue(issue_id=issue["id"], state_id=state["id"])
    if not updated:
        return {"error": "Failed to transition issue state"}

    return await Task_GetIssue(str(updated["id"]))


@mcp.tool()
async def Task_AddComment(
    issue: str,
    body: str,
) -> dict[str, Any]:
    """
    Add a comment to an issue.

    Args:
        issue: Issue identifier (e.g., ENG-42) or UUID
        body: Comment text (supports markdown)

    Returns:
        Created comment details
    """
    issue_data = await get_issue_by_identifier_or_id(issue)
    if not issue_data:
        return {"error": f"Issue '{issue}' not found"}

    comment = await add_comment(issue_data["id"], body)

    return {
        "id": str(comment["id"]),
        "issue_id": str(comment["issue_id"]),
        "issue_identifier": issue_data["identifier"],
        "body": comment["body"],
        "created_at": comment["created_at"].isoformat(),
    }


@mcp.tool()
async def Task_ListWorkflowStates(team: str) -> dict[str, Any]:
    """
    List available workflow states for a team.

    Args:
        team: Team key (e.g., "ENG") or team name

    Returns:
        List of workflow states with their types
    """
    team_data = await get_team_by_key_or_name(team)
    if not team_data:
        return {"error": f"Team '{team}' not found"}

    states = await get_workflow_states(team_data["id"])

    return {
        "team_key": team_data["key"],
        "states": [
            {
                "id": str(s["id"]),
                "name": s["name"],
                "type": s["type"],
                "position": s["position"],
            }
            for s in states
        ],
    }


# =============================================================================
# Health Check Endpoint
# =============================================================================


async def health_check(request):
    """
    Health check endpoint for container orchestration.

    Verifies database connectivity and returns health status.
    Used by Docker healthcheck and load balancers.
    """
    try:
        # Check database connectivity
        async with db.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return JSONResponse({
            "status": "healthy",
            "service": "task-mcp-server",
            "database": "connected",
        })
    except Exception as e:
        return JSONResponse(
            {
                "status": "unhealthy",
                "service": "task-mcp-server",
                "database": "disconnected",
                "error": str(e),
            },
            status_code=503,
        )


# =============================================================================
# ASGI Application
# =============================================================================


@asynccontextmanager
async def app_lifespan(app):
    """ASGI lifespan for database connection."""
    await db.connect()
    yield
    await db.disconnect()


# Create ASGI app for uvicorn with lifespan
_mcp_app = mcp.sse_app()
app = Starlette(
    routes=_mcp_app.routes + [Route("/health", health_check, methods=["GET"])],
    lifespan=app_lifespan,
)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
