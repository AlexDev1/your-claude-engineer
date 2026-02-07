"""
Task MCP Server - Analytics Extension
======================================

FastAPI server providing analytics MCP tools for project statistics
and session timeline reports.

MCP Tools:
- Task_GetProjectStats: Get comprehensive project statistics
- Task_GetSessionReport: Get session timeline from META issue

Run:
    python -m task_mcp_server.server

Or with uvicorn:
    uvicorn task_mcp_server.server:app --host 0.0.0.0 --port 8001
"""

import os
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import (
    get_project_stats,
    get_stale_issues,
    get_session_timeline,
    set_issues_store,
    get_issues_store,
    STALE_THRESHOLD_HOURS,
)


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Task MCP Server - Analytics",
    description="Analytics MCP tools for project statistics and session reports",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Request/Response Models
# =============================================================================


class ProjectStatsRequest(BaseModel):
    """Request model for Task_GetProjectStats."""

    team: str = Field(
        default="ENG",
        description="Team identifier (e.g., 'ENG', 'DESIGN')"
    )
    project: Optional[str] = Field(
        default=None,
        description="Optional project filter"
    )


class ProjectStatsResponse(BaseModel):
    """Response model for Task_GetProjectStats."""

    counts_by_state: dict = Field(
        description="Task counts by state (todo, in_progress, done, cancelled)"
    )
    counts_by_priority: dict = Field(
        description="Task counts by priority (urgent, high, medium, low, none)"
    )
    time_metrics: dict = Field(
        description="Time metrics (avg_completion_time_hours, avg_in_progress_time_hours)"
    )
    comment_metrics: dict = Field(
        description="Comment metrics (avg_comments_per_task, total_comments)"
    )
    stale_tasks: dict = Field(
        description="Stale task information (count, threshold_hours, issues list)"
    )
    metadata: dict = Field(
        description="Query metadata (total_tasks, team, project, calculated_at)"
    )


class SessionReportRequest(BaseModel):
    """Request model for Task_GetSessionReport."""

    meta_issue_id: str = Field(
        description="Identifier of the META issue (e.g., 'ENG-META', 'ENG-0')"
    )


class SessionReportResponse(BaseModel):
    """Response model for Task_GetSessionReport."""

    meta_issue_id: str = Field(
        description="The META issue identifier"
    )
    total_sessions: int = Field(
        description="Total number of sessions parsed"
    )
    total_tasks_completed: int = Field(
        description="Total tasks completed across all sessions"
    )
    last_session_at: Optional[str] = Field(
        description="Timestamp of the last session"
    )
    sessions: list = Field(
        description="List of session entries with summaries and task references"
    )


class StaleIssuesResponse(BaseModel):
    """Response model for stale issues endpoint."""

    stale_count: int
    threshold_hours: float
    team: str
    issues: list


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    timestamp: str
    stale_threshold_hours: float


# =============================================================================
# MCP Tool Endpoints
# =============================================================================


@app.post("/tools/Task_GetProjectStats", response_model=ProjectStatsResponse)
async def task_get_project_stats(request: ProjectStatsRequest) -> ProjectStatsResponse:
    """
    MCP Tool: Task_GetProjectStats

    Get comprehensive project statistics including:
    - Count of tasks by each state (Todo, In Progress, Done, Cancelled)
    - Count of tasks by priority (urgent, high, medium, low, none)
    - Average time from creation to Done (in hours)
    - Average time in "In Progress" state (in hours)
    - Average number of comments per task
    - List of stale tasks (In Progress longer than threshold)

    Args:
        team: Team identifier (required)
        project: Optional project filter

    Returns:
        Comprehensive project statistics as JSON
    """
    stats = get_project_stats(team=request.team, project=request.project)
    return ProjectStatsResponse(**stats.to_dict())


@app.post("/tools/Task_GetSessionReport", response_model=SessionReportResponse)
async def task_get_session_report(request: SessionReportRequest) -> SessionReportResponse:
    """
    MCP Tool: Task_GetSessionReport

    Collects all comments from META issue and parses session summaries.
    Returns a timeline showing: session N -> what was done, how many tasks closed.

    Session comment patterns recognized:
    - "Session N: <summary>"
    - "Session #N: <summary>"
    - "#N <summary>"
    - Task references: ENG-123, TASK-456, etc.

    Args:
        meta_issue_id: Identifier of the META issue

    Returns:
        Session timeline with parsed entries
    """
    timeline = get_session_timeline(meta_issue_id=request.meta_issue_id)
    return SessionReportResponse(**timeline.to_dict())


# =============================================================================
# REST API Endpoints (for direct access)
# =============================================================================


@app.get("/api/stats")
async def get_stats_api(
    team: str = Query("ENG", description="Team identifier"),
    project: Optional[str] = Query(None, description="Optional project filter"),
) -> dict:
    """
    REST API: Get project statistics.

    Same as Task_GetProjectStats but accessible via GET request.
    """
    stats = get_project_stats(team=team, project=project)
    return stats.to_dict()


@app.get("/api/sessions/{meta_issue_id}")
async def get_sessions_api(meta_issue_id: str) -> dict:
    """
    REST API: Get session timeline.

    Same as Task_GetSessionReport but accessible via GET request.
    """
    timeline = get_session_timeline(meta_issue_id=meta_issue_id)
    return timeline.to_dict()


@app.get("/stale-issues", response_model=StaleIssuesResponse)
async def get_stale_issues_endpoint(
    team: str = Query("ENG", description="Team identifier"),
    threshold_hours: Optional[float] = Query(None, description="Override stale threshold"),
) -> StaleIssuesResponse:
    """
    Get tasks that have been in "In Progress" longer than the threshold.

    This endpoint is used by the heartbeat daemon for monitoring.
    """
    result = get_stale_issues(team=team, threshold_hours=threshold_hours)
    return StaleIssuesResponse(**result)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="task-mcp-analytics",
        timestamp=datetime.now().isoformat(),
        stale_threshold_hours=STALE_THRESHOLD_HOURS,
    )


# =============================================================================
# Integration with Analytics Server
# =============================================================================


def integrate_with_analytics_server(issues_store: dict) -> None:
    """
    Integrate with the analytics server's in-memory store.

    Call this function from analytics_server to share the issues store.
    """
    set_issues_store(issues_store)


# =============================================================================
# SSE Endpoint (for MCP protocol)
# =============================================================================


@app.get("/sse")
async def sse_endpoint():
    """
    SSE endpoint for MCP protocol.

    This is a placeholder - the actual MCP SSE implementation would
    use a proper SSE library or the MCP SDK.
    """
    return {
        "message": "SSE endpoint for MCP protocol",
        "tools": [
            {
                "name": "Task_GetProjectStats",
                "description": "Get comprehensive project statistics",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "team": {
                            "type": "string",
                            "description": "Team identifier",
                            "default": "ENG",
                        },
                        "project": {
                            "type": "string",
                            "description": "Optional project filter",
                        },
                    },
                    "required": ["team"],
                },
            },
            {
                "name": "Task_GetSessionReport",
                "description": "Get session timeline from META issue",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "meta_issue_id": {
                            "type": "string",
                            "description": "Identifier of the META issue",
                        },
                    },
                    "required": ["meta_issue_id"],
                },
            },
        ],
    }


# =============================================================================
# Main Entry Point
# =============================================================================


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("TASK_MCP_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
