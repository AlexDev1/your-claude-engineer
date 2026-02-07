"""
Analytics API Server
====================

FastAPI server providing analytics endpoints for agent performance metrics.
Fetches data from Task MCP server and computes KPIs.

Endpoints:
- GET /api/analytics/velocity - Task velocity over time
- GET /api/analytics/efficiency - Success rate, avg completion time
- GET /api/analytics/bottlenecks - Stuck tasks, retry rates
- GET /api/analytics/export - Export data as CSV/PDF
- GET /api/analytics/summary - Overview dashboard data

Issue CRUD Endpoints:
- GET /api/issues - List all issues
- GET /api/issues/{id} - Get single issue
- POST /api/issues - Create new issue
- PUT /api/issues/{id} - Update issue
- DELETE /api/issues/{id} - Delete issue
- POST /api/issues/{id}/comments - Add comment
- POST /api/issues/bulk - Bulk operations
"""

import os
import json
from datetime import datetime, timedelta
from typing import Any, Optional, List
from collections import defaultdict
from enum import Enum
import uuid
import copy

import httpx
from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import io
import csv

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Agent Analytics API",
    description="KPI dashboard and performance analytics for autonomous coding agents",
    version="1.0.0",
)

# CORS configuration for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
TASK_MCP_URL = os.environ.get("TASK_MCP_URL", "http://localhost:8001/sse")
MCP_API_KEY = os.environ.get("MCP_API_KEY", "")

# Derive API base URL from MCP SSE URL
TASK_API_BASE = TASK_MCP_URL.replace("/sse", "")


# =============================================================================
# Data Models
# =============================================================================


class VelocityData(BaseModel):
    """Velocity metrics response."""
    daily: list[dict[str, Any]]
    weekly_avg: float
    trend: str  # "up", "down", "stable"
    total_completed: int


class EfficiencyData(BaseModel):
    """Efficiency metrics response."""
    success_rate: float  # percentage
    avg_completion_time_hours: float
    tasks_done: int
    tasks_cancelled: int
    tasks_in_progress: int
    tasks_todo: int


class BottleneckData(BaseModel):
    """Bottleneck detection response."""
    stuck_tasks: list[dict[str, Any]]
    avg_retry_rate: float
    time_distribution: dict[str, float]  # state -> avg hours
    recommendations: list[str]
    longest_stuck: Optional[dict[str, Any]]


class SummaryData(BaseModel):
    """Summary dashboard data."""
    velocity: VelocityData
    efficiency: EfficiencyData
    bottlenecks: BottleneckData
    priority_distribution: dict[str, int]
    activity_heatmap: list[dict[str, Any]]


class IssueState(str, Enum):
    """Valid issue states."""
    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    DONE = "Done"
    CANCELLED = "Cancelled"


class IssuePriority(str, Enum):
    """Valid issue priorities."""
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class IssueType(str, Enum):
    """Issue type templates."""
    BUG = "Bug"
    FEATURE = "Feature"
    TASK = "Task"
    EPIC = "Epic"


class Comment(BaseModel):
    """Issue comment."""
    id: str
    author: str = "Agent"
    content: str
    created_at: str


class CreateIssueRequest(BaseModel):
    """Request model for creating an issue."""
    title: str
    description: Optional[str] = ""
    priority: IssuePriority = IssuePriority.MEDIUM
    issue_type: Optional[IssueType] = IssueType.TASK
    team: str = "ENG"
    project: Optional[str] = None
    parent_id: Optional[str] = None
    dependencies: Optional[List[str]] = []


class UpdateIssueRequest(BaseModel):
    """Request model for updating an issue."""
    title: Optional[str] = None
    description: Optional[str] = None
    state: Optional[IssueState] = None
    priority: Optional[IssuePriority] = None
    parent_id: Optional[str] = None
    dependencies: Optional[List[str]] = None


class BulkOperationRequest(BaseModel):
    """Request model for bulk operations."""
    issue_ids: List[str]
    operation: str  # "change_state", "change_priority", "assign_project", "delete"
    value: Optional[str] = None


class IssueResponse(BaseModel):
    """Full issue response."""
    identifier: str
    title: str
    description: str
    state: str
    priority: str
    issue_type: str
    team: str
    project: Optional[str]
    parent_id: Optional[str]
    dependencies: List[str]
    comments: List[Comment]
    created_at: str
    updated_at: str
    completed_at: Optional[str]


# In-memory storage for issues (for development/demo)
# In production, this would connect to a real database or task management system
ISSUES_STORE: dict[str, dict] = {}
ISSUE_COUNTER = 50  # Start after existing mock issues
UNDO_STACK: list[dict] = []  # For undo operations


# =============================================================================
# MCP API Client
# =============================================================================


async def fetch_issues(team: str = "ENG", states: Optional[list[str]] = None) -> list[dict]:
    """Fetch issues from Task MCP server."""
    headers = {}
    if MCP_API_KEY:
        headers["Authorization"] = f"Bearer {MCP_API_KEY}"

    params = {"team": team}
    if states:
        params["states"] = ",".join(states)

    try:
        async with httpx.AsyncClient() as client:
            # Try the issues endpoint
            url = f"{TASK_API_BASE}/issues"
            response = await client.get(url, headers=headers, params=params, timeout=30.0)

            if response.status_code == 200:
                data = response.json()
                return data.get("issues", data) if isinstance(data, dict) else data
            elif response.status_code == 404:
                # Endpoint not found, return mock data for development
                return generate_mock_issues()
            else:
                print(f"Failed to fetch issues: {response.status_code}")
                return generate_mock_issues()
    except Exception as e:
        print(f"Error fetching issues: {e}")
        return generate_mock_issues()


def generate_mock_issues() -> list[dict]:
    """Generate mock issue data for development/demo."""
    now = datetime.now()
    mock_issues = []

    priorities = ["urgent", "high", "medium", "low"]
    states = ["Done", "Done", "Done", "In Progress", "In Progress", "Todo", "Cancelled"]

    for i in range(1, 35):
        created = now - timedelta(days=i % 30, hours=i * 2 % 24)
        state = states[i % len(states)]

        completed = None
        if state == "Done":
            completed = created + timedelta(hours=(i % 8) + 1)
        elif state == "Cancelled":
            completed = created + timedelta(hours=(i % 4) + 0.5)

        mock_issues.append({
            "identifier": f"ENG-{i}",
            "title": f"Task {i}: {'Feature' if i % 3 == 0 else 'Bug fix' if i % 3 == 1 else 'Refactor'}",
            "state": state,
            "priority": priorities[i % len(priorities)],
            "created_at": created.isoformat(),
            "updated_at": (completed or now).isoformat(),
            "completed_at": completed.isoformat() if completed else None,
            "time_in_state_hours": ((now - created).total_seconds() / 3600) if state == "In Progress" else None,
        })

    return mock_issues


def calculate_velocity(issues: list[dict], days: int = 14) -> VelocityData:
    """Calculate velocity metrics from issues."""
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    # Group completed tasks by day
    daily_counts = defaultdict(int)

    for issue in issues:
        if issue.get("state") == "Done" and issue.get("completed_at"):
            try:
                completed = datetime.fromisoformat(issue["completed_at"].replace("Z", "+00:00"))
                if completed.tzinfo:
                    completed = completed.replace(tzinfo=None)
                if completed >= cutoff:
                    day_key = completed.strftime("%Y-%m-%d")
                    daily_counts[day_key] += 1
            except (ValueError, TypeError):
                pass

    # Fill in missing days
    daily_data = []
    for i in range(days):
        day = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        daily_data.append({
            "date": day,
            "count": daily_counts.get(day, 0)
        })

    # Calculate weekly average
    total = sum(d["count"] for d in daily_data)
    weekly_avg = (total / days) * 7 if days > 0 else 0

    # Calculate trend (compare last 7 days vs previous 7 days)
    if days >= 14:
        recent = sum(d["count"] for d in daily_data[-7:])
        previous = sum(d["count"] for d in daily_data[-14:-7])
        if recent > previous * 1.1:
            trend = "up"
        elif recent < previous * 0.9:
            trend = "down"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return VelocityData(
        daily=daily_data,
        weekly_avg=round(weekly_avg, 1),
        trend=trend,
        total_completed=total,
    )


def calculate_efficiency(issues: list[dict]) -> EfficiencyData:
    """Calculate efficiency metrics from issues."""
    done = [i for i in issues if i.get("state") == "Done"]
    cancelled = [i for i in issues if i.get("state") == "Cancelled"]
    in_progress = [i for i in issues if i.get("state") == "In Progress"]
    todo = [i for i in issues if i.get("state") == "Todo"]

    total_terminal = len(done) + len(cancelled)
    success_rate = (len(done) / total_terminal * 100) if total_terminal > 0 else 100.0

    # Calculate average completion time
    completion_times = []
    for issue in done:
        if issue.get("created_at") and issue.get("completed_at"):
            try:
                created = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
                completed = datetime.fromisoformat(issue["completed_at"].replace("Z", "+00:00"))
                if created.tzinfo:
                    created = created.replace(tzinfo=None)
                if completed.tzinfo:
                    completed = completed.replace(tzinfo=None)
                hours = (completed - created).total_seconds() / 3600
                completion_times.append(hours)
            except (ValueError, TypeError):
                pass

    avg_time = sum(completion_times) / len(completion_times) if completion_times else 0

    return EfficiencyData(
        success_rate=round(success_rate, 1),
        avg_completion_time_hours=round(avg_time, 2),
        tasks_done=len(done),
        tasks_cancelled=len(cancelled),
        tasks_in_progress=len(in_progress),
        tasks_todo=len(todo),
    )


def detect_bottlenecks(issues: list[dict]) -> BottleneckData:
    """Detect bottlenecks and generate recommendations."""
    now = datetime.now()

    # Find stuck tasks (in progress for too long)
    stuck_tasks = []
    for issue in issues:
        if issue.get("state") == "In Progress":
            hours = issue.get("time_in_state_hours")
            if hours is None and issue.get("updated_at"):
                try:
                    updated = datetime.fromisoformat(issue["updated_at"].replace("Z", "+00:00"))
                    if updated.tzinfo:
                        updated = updated.replace(tzinfo=None)
                    hours = (now - updated).total_seconds() / 3600
                except (ValueError, TypeError):
                    hours = 0

            if hours and hours > 2:  # More than 2 hours in progress
                stuck_tasks.append({
                    "identifier": issue.get("identifier"),
                    "title": issue.get("title"),
                    "hours_stuck": round(hours, 1),
                    "priority": issue.get("priority"),
                })

    stuck_tasks.sort(key=lambda x: x.get("hours_stuck", 0), reverse=True)
    longest_stuck = stuck_tasks[0] if stuck_tasks else None

    # Calculate time distribution by state
    time_distribution = {
        "Todo": 0,
        "In Progress": 0,
        "Done": 0,
    }

    state_counts = defaultdict(list)
    for issue in issues:
        if issue.get("created_at") and issue.get("completed_at"):
            try:
                created = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
                completed = datetime.fromisoformat(issue["completed_at"].replace("Z", "+00:00"))
                if created.tzinfo:
                    created = created.replace(tzinfo=None)
                if completed.tzinfo:
                    completed = completed.replace(tzinfo=None)
                hours = (completed - created).total_seconds() / 3600
                state_counts[issue.get("state", "Unknown")].append(hours)
            except (ValueError, TypeError):
                pass

    for state, times in state_counts.items():
        if times:
            time_distribution[state] = round(sum(times) / len(times), 2)

    # Generate recommendations
    recommendations = []
    if len(stuck_tasks) > 3:
        recommendations.append(
            f"High number of stuck tasks ({len(stuck_tasks)}). Consider reviewing blockers."
        )
    if longest_stuck and longest_stuck.get("hours_stuck", 0) > 8:
        recommendations.append(
            f"Task {longest_stuck['identifier']} stuck for {longest_stuck['hours_stuck']}h. Prioritize resolution."
        )
    if time_distribution.get("In Progress", 0) > 4:
        recommendations.append(
            "Average time in 'In Progress' is high. Break down tasks into smaller units."
        )
    if not recommendations:
        recommendations.append("No significant bottlenecks detected. Performance is healthy.")

    return BottleneckData(
        stuck_tasks=stuck_tasks[:10],  # Top 10 stuck tasks
        avg_retry_rate=1.2,  # Mock - would need retry tracking
        time_distribution=time_distribution,
        recommendations=recommendations,
        longest_stuck=longest_stuck,
    )


def calculate_priority_distribution(issues: list[dict]) -> dict[str, int]:
    """Calculate distribution of tasks by priority."""
    distribution = defaultdict(int)
    for issue in issues:
        priority = issue.get("priority", "none")
        distribution[priority] += 1
    return dict(distribution)


def calculate_activity_heatmap(issues: list[dict]) -> list[dict]:
    """Calculate activity heatmap by day/hour."""
    # Count completions by day of week and hour
    heatmap_data = defaultdict(lambda: defaultdict(int))

    for issue in issues:
        if issue.get("completed_at"):
            try:
                completed = datetime.fromisoformat(issue["completed_at"].replace("Z", "+00:00"))
                if completed.tzinfo:
                    completed = completed.replace(tzinfo=None)
                day = completed.strftime("%A")
                hour = completed.hour
                heatmap_data[day][hour] += 1
            except (ValueError, TypeError):
                pass

    # Convert to list format for frontend
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    result = []
    for day in days:
        for hour in range(24):
            result.append({
                "day": day,
                "hour": hour,
                "count": heatmap_data[day][hour],
            })

    return result


# =============================================================================
# API Endpoints
# =============================================================================


@app.get("/api/analytics/velocity")
async def get_velocity(
    days: int = Query(14, ge=1, le=90, description="Number of days to analyze"),
    team: str = Query("ENG", description="Team to filter by"),
) -> VelocityData:
    """Get velocity metrics for the specified period."""
    issues = await fetch_issues(team)
    return calculate_velocity(issues, days)


@app.get("/api/analytics/efficiency")
async def get_efficiency(
    team: str = Query("ENG", description="Team to filter by"),
) -> EfficiencyData:
    """Get efficiency metrics (success rate, completion time)."""
    issues = await fetch_issues(team)
    return calculate_efficiency(issues)


@app.get("/api/analytics/bottlenecks")
async def get_bottlenecks(
    team: str = Query("ENG", description="Team to filter by"),
) -> BottleneckData:
    """Get bottleneck detection and recommendations."""
    issues = await fetch_issues(team)
    return detect_bottlenecks(issues)


@app.get("/api/analytics/summary")
async def get_summary(
    days: int = Query(14, ge=1, le=90, description="Number of days for velocity"),
    team: str = Query("ENG", description="Team to filter by"),
) -> SummaryData:
    """Get complete analytics summary for dashboard."""
    issues = await fetch_issues(team)

    return SummaryData(
        velocity=calculate_velocity(issues, days),
        efficiency=calculate_efficiency(issues),
        bottlenecks=detect_bottlenecks(issues),
        priority_distribution=calculate_priority_distribution(issues),
        activity_heatmap=calculate_activity_heatmap(issues),
    )


@app.get("/api/analytics/export")
async def export_data(
    format: str = Query("csv", regex="^(csv|json)$", description="Export format"),
    period: str = Query("week", regex="^(day|week|month)$", description="Time period"),
    team: str = Query("ENG", description="Team to filter by"),
):
    """Export analytics data as CSV or JSON."""
    issues = await fetch_issues(team)

    # Filter by period
    now = datetime.now()
    if period == "day":
        cutoff = now - timedelta(days=1)
    elif period == "week":
        cutoff = now - timedelta(days=7)
    else:
        cutoff = now - timedelta(days=30)

    filtered = []
    for issue in issues:
        if issue.get("created_at"):
            try:
                created = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
                if created.tzinfo:
                    created = created.replace(tzinfo=None)
                if created >= cutoff:
                    filtered.append(issue)
            except (ValueError, TypeError):
                pass

    if format == "json":
        return {
            "period": period,
            "team": team,
            "exported_at": now.isoformat(),
            "issues": filtered,
            "summary": {
                "total": len(filtered),
                "done": len([i for i in filtered if i.get("state") == "Done"]),
                "in_progress": len([i for i in filtered if i.get("state") == "In Progress"]),
                "todo": len([i for i in filtered if i.get("state") == "Todo"]),
            },
        }

    # CSV export
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["identifier", "title", "state", "priority", "created_at", "completed_at"],
    )
    writer.writeheader()
    for issue in filtered:
        writer.writerow({
            "identifier": issue.get("identifier", ""),
            "title": issue.get("title", ""),
            "state": issue.get("state", ""),
            "priority": issue.get("priority", ""),
            "created_at": issue.get("created_at", ""),
            "completed_at": issue.get("completed_at", ""),
        })

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=analytics_{period}_{team}.csv"},
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "analytics-api", "timestamp": datetime.now().isoformat()}


# =============================================================================
# Context Budget Endpoints
# =============================================================================


# In-memory context stats (updated by agent sessions)
CONTEXT_STATS = {
    "max_tokens": 200000,
    "total_used": 0,
    "remaining": 200000,
    "usage_percent": 0.0,
    "is_warning": False,
    "breakdown": {
        "system_prompt": 0,
        "files": 0,
        "history": 0,
        "memory": 0,
        "issue": 0,
    },
    "files_loaded": 0,
    "history_messages": 0,
}

# Prompt token stats (calculated from prompts directory)
PROMPT_STATS = None


def estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token)."""
    return len(text) // 4 if text else 0


def calculate_prompt_stats() -> dict:
    """Calculate token stats for all prompts."""
    global PROMPT_STATS
    if PROMPT_STATS is not None:
        return PROMPT_STATS

    import os
    prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

    stats = {}
    total = 0

    if os.path.exists(prompts_dir):
        for filename in os.listdir(prompts_dir):
            if filename.endswith(".md"):
                filepath = os.path.join(prompts_dir, filename)
                with open(filepath, "r") as f:
                    content = f.read()
                    tokens = estimate_tokens(content)
                    stats[filename.replace(".md", "")] = {
                        "chars": len(content),
                        "tokens": tokens,
                    }
                    total += tokens

    stats["_total"] = {"tokens": total}

    # Add savings info (original was ~9896 tokens)
    original_total = 9896
    stats["_savings"] = {
        "before": original_total,
        "after": total,
        "percent": round((original_total - total) / original_total * 100, 1) if original_total > 0 else 0,
    }

    PROMPT_STATS = stats
    return stats


@app.get("/api/context/stats")
async def get_context_stats() -> dict:
    """Get current context budget statistics.

    Returns real-time context usage if agent session is active,
    otherwise returns last known stats or demo data.
    """
    # Try to get live stats from context manager
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from context_manager import get_context_manager
        ctx = get_context_manager()
        stats = ctx.get_stats()
        # Update global stats
        CONTEXT_STATS.update(stats)
        return stats
    except Exception:
        pass

    # Return stored stats or generate demo
    if CONTEXT_STATS["total_used"] == 0:
        # Return demo data when no live session
        prompts = calculate_prompt_stats()
        prompt_tokens = prompts.get("_total", {}).get("tokens", 2283)

        return {
            "max_tokens": 200000,
            "total_used": prompt_tokens + 45000,  # Demo: prompts + estimated file/history
            "remaining": 200000 - (prompt_tokens + 45000),
            "usage_percent": (prompt_tokens + 45000) / 200000 * 100,
            "is_warning": False,
            "breakdown": {
                "system_prompt": prompt_tokens,
                "files": 30000,
                "history": 12000,
                "memory": 1500,
                "issue": 1500,
            },
            "files_loaded": 8,
            "history_messages": 5,
        }

    return CONTEXT_STATS


@app.post("/api/context/stats")
async def update_context_stats(stats: dict) -> dict:
    """Update context stats from agent session.

    This endpoint is called by the agent to report current context usage.
    """
    global CONTEXT_STATS
    allowed_keys = ["max_tokens", "total_used", "remaining", "usage_percent",
                    "is_warning", "breakdown", "files_loaded", "history_messages"]

    for key in allowed_keys:
        if key in stats:
            CONTEXT_STATS[key] = stats[key]

    return {"updated": True, "stats": CONTEXT_STATS}


@app.get("/api/context/prompts")
async def get_prompt_stats() -> dict:
    """Get token statistics for all prompt files.

    Returns character and token counts for each prompt,
    plus total and savings compared to pre-optimization.
    """
    return calculate_prompt_stats()


# =============================================================================
# Issue CRUD Endpoints
# =============================================================================


def initialize_issues_store():
    """Initialize the in-memory store with mock issues."""
    global ISSUES_STORE
    if ISSUES_STORE:
        return

    mock_issues = generate_mock_issues()
    for issue in mock_issues:
        issue_id = issue["identifier"]
        ISSUES_STORE[issue_id] = {
            **issue,
            "description": f"Description for {issue['title']}",
            "issue_type": "Task" if "Refactor" in issue["title"] else "Feature" if "Feature" in issue["title"] else "Bug",
            "team": "ENG",
            "project": "Agent Dashboard",
            "parent_id": None,
            "dependencies": [],
            "comments": [],
        }


@app.on_event("startup")
async def startup_event():
    """Initialize data on startup."""
    initialize_issues_store()


@app.get("/api/issues")
async def list_issues(
    team: str = Query("ENG", description="Team to filter by"),
    state: Optional[str] = Query(None, description="Filter by state"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
) -> dict:
    """List all issues with optional filters."""
    initialize_issues_store()

    issues = list(ISSUES_STORE.values())

    # Apply filters
    if state:
        issues = [i for i in issues if i.get("state") == state]
    if priority:
        issues = [i for i in issues if i.get("priority") == priority]
    if team:
        issues = [i for i in issues if i.get("team", "ENG") == team]

    # Sort by priority and created_at
    priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
    issues.sort(key=lambda x: (
        priority_order.get(x.get("priority", "none"), 4),
        x.get("created_at", "")
    ))

    return {"issues": issues, "total": len(issues)}


@app.get("/api/issues/{issue_id}")
async def get_issue(issue_id: str) -> dict:
    """Get a single issue by ID."""
    initialize_issues_store()

    if issue_id not in ISSUES_STORE:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")

    return ISSUES_STORE[issue_id]


@app.post("/api/issues")
async def create_issue(request: CreateIssueRequest) -> dict:
    """Create a new issue."""
    global ISSUE_COUNTER
    initialize_issues_store()

    ISSUE_COUNTER += 1
    issue_id = f"{request.team}-{ISSUE_COUNTER}"
    now = datetime.now().isoformat()

    issue = {
        "identifier": issue_id,
        "title": request.title,
        "description": request.description or "",
        "state": "Todo",
        "priority": request.priority.value if request.priority else "medium",
        "issue_type": request.issue_type.value if request.issue_type else "Task",
        "team": request.team,
        "project": request.project,
        "parent_id": request.parent_id,
        "dependencies": request.dependencies or [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }

    ISSUES_STORE[issue_id] = issue

    # Add to undo stack
    UNDO_STACK.append({
        "action": "create",
        "issue_id": issue_id,
        "timestamp": now,
    })

    return issue


@app.put("/api/issues/{issue_id}")
async def update_issue(issue_id: str, request: UpdateIssueRequest) -> dict:
    """Update an existing issue."""
    initialize_issues_store()

    if issue_id not in ISSUES_STORE:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")

    issue = ISSUES_STORE[issue_id]
    old_state = copy.deepcopy(issue)
    now = datetime.now().isoformat()

    # Validate state transition
    if request.state:
        valid_transitions = {
            "Todo": ["In Progress", "Cancelled"],
            "In Progress": ["Todo", "Done", "Cancelled"],
            "Done": ["In Progress"],
            "Cancelled": ["Todo"],
        }
        current_state = issue.get("state", "Todo")
        new_state = request.state.value

        if new_state != current_state and new_state not in valid_transitions.get(current_state, []):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Invalid state transition: {current_state} -> {new_state}"
            )

        issue["state"] = new_state
        if new_state == "Done":
            issue["completed_at"] = now
        elif new_state != "Done" and issue.get("completed_at"):
            issue["completed_at"] = None

    # Update other fields
    if request.title is not None:
        issue["title"] = request.title
    if request.description is not None:
        issue["description"] = request.description
    if request.priority is not None:
        issue["priority"] = request.priority.value
    if request.parent_id is not None:
        issue["parent_id"] = request.parent_id
    if request.dependencies is not None:
        issue["dependencies"] = request.dependencies

    issue["updated_at"] = now

    # Add to undo stack
    UNDO_STACK.append({
        "action": "update",
        "issue_id": issue_id,
        "old_state": old_state,
        "timestamp": now,
    })

    return issue


@app.delete("/api/issues/{issue_id}")
async def delete_issue(issue_id: str) -> dict:
    """Delete an issue."""
    initialize_issues_store()

    if issue_id not in ISSUES_STORE:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")

    deleted_issue = ISSUES_STORE.pop(issue_id)

    # Add to undo stack
    UNDO_STACK.append({
        "action": "delete",
        "issue_id": issue_id,
        "issue_data": deleted_issue,
        "timestamp": datetime.now().isoformat(),
    })

    return {"deleted": True, "identifier": issue_id}


@app.post("/api/issues/{issue_id}/comments")
async def add_comment(issue_id: str, content: str = Query(..., description="Comment content")) -> dict:
    """Add a comment to an issue."""
    initialize_issues_store()

    if issue_id not in ISSUES_STORE:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")

    comment = {
        "id": str(uuid.uuid4())[:8],
        "author": "Agent",
        "content": content,
        "created_at": datetime.now().isoformat(),
    }

    ISSUES_STORE[issue_id]["comments"].append(comment)
    ISSUES_STORE[issue_id]["updated_at"] = datetime.now().isoformat()

    return comment


@app.post("/api/issues/bulk")
async def bulk_operation(request: BulkOperationRequest) -> dict:
    """Perform bulk operations on multiple issues."""
    initialize_issues_store()

    results = {"success": [], "failed": []}
    old_states = []

    for issue_id in request.issue_ids:
        if issue_id not in ISSUES_STORE:
            results["failed"].append({"id": issue_id, "error": "Not found"})
            continue

        try:
            issue = ISSUES_STORE[issue_id]
            old_states.append({"issue_id": issue_id, "state": copy.deepcopy(issue)})

            if request.operation == "change_state":
                issue["state"] = request.value
                if request.value == "Done":
                    issue["completed_at"] = datetime.now().isoformat()
                issue["updated_at"] = datetime.now().isoformat()
                results["success"].append(issue_id)

            elif request.operation == "change_priority":
                issue["priority"] = request.value
                issue["updated_at"] = datetime.now().isoformat()
                results["success"].append(issue_id)

            elif request.operation == "assign_project":
                issue["project"] = request.value
                issue["updated_at"] = datetime.now().isoformat()
                results["success"].append(issue_id)

            elif request.operation == "delete":
                deleted = ISSUES_STORE.pop(issue_id)
                old_states[-1]["deleted"] = deleted
                results["success"].append(issue_id)

            else:
                results["failed"].append({"id": issue_id, "error": f"Unknown operation: {request.operation}"})

        except Exception as e:
            results["failed"].append({"id": issue_id, "error": str(e)})

    # Add to undo stack
    UNDO_STACK.append({
        "action": "bulk",
        "operation": request.operation,
        "old_states": old_states,
        "timestamp": datetime.now().isoformat(),
    })

    return results


@app.post("/api/issues/undo")
async def undo_last_operation() -> dict:
    """Undo the last operation."""
    if not UNDO_STACK:
        return {"success": False, "message": "Nothing to undo"}

    last_action = UNDO_STACK.pop()

    if last_action["action"] == "create":
        # Undo create by deleting
        issue_id = last_action["issue_id"]
        if issue_id in ISSUES_STORE:
            del ISSUES_STORE[issue_id]
        return {"success": True, "action": "Undid issue creation", "issue_id": issue_id}

    elif last_action["action"] == "update":
        # Undo update by restoring old state
        issue_id = last_action["issue_id"]
        ISSUES_STORE[issue_id] = last_action["old_state"]
        return {"success": True, "action": "Undid issue update", "issue_id": issue_id}

    elif last_action["action"] == "delete":
        # Undo delete by restoring
        issue_id = last_action["issue_id"]
        ISSUES_STORE[issue_id] = last_action["issue_data"]
        return {"success": True, "action": "Restored deleted issue", "issue_id": issue_id}

    elif last_action["action"] == "bulk":
        # Undo bulk operation
        for item in last_action["old_states"]:
            issue_id = item["issue_id"]
            if "deleted" in item:
                ISSUES_STORE[issue_id] = item["deleted"]
            else:
                ISSUES_STORE[issue_id] = item["state"]
        return {"success": True, "action": f"Undid bulk {last_action['operation']}", "count": len(last_action["old_states"])}

    return {"success": False, "message": "Unknown action type"}


# =============================================================================
# Data Import/Export Endpoints (ENG-48)
# =============================================================================


class ExportFormat(str, Enum):
    """Export format options."""
    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ImportConflictResolution(str, Enum):
    """Conflict resolution strategies for import."""
    SKIP = "skip"
    UPDATE = "update"
    DUPLICATE = "duplicate"


class ImportPreviewRequest(BaseModel):
    """Request for import preview."""
    data: str  # JSON or CSV string
    format: str = "json"
    source: str = "generic"  # "generic", "linear", "github"


class ImportExecuteRequest(BaseModel):
    """Request to execute import."""
    data: str
    format: str = "json"
    source: str = "generic"
    conflict_resolution: ImportConflictResolution = ImportConflictResolution.SKIP
    dry_run: bool = False


class LinearImportRequest(BaseModel):
    """Request for Linear import."""
    data: str  # Linear export JSON string
    conflict_resolution: ImportConflictResolution = ImportConflictResolution.SKIP
    dry_run: bool = False


class GitHubImportRequest(BaseModel):
    """Request for GitHub import."""
    owner: str
    repo: str
    labels: Optional[List[str]] = None
    state: str = "open"  # "open", "closed", "all"
    import_comments: bool = True
    conflict_resolution: ImportConflictResolution = ImportConflictResolution.SKIP


class BackupInfo(BaseModel):
    """Backup metadata."""
    filename: str
    created_at: str
    size_bytes: int
    issue_count: int


@app.get("/api/export/json")
async def export_json(
    team: str = Query("ENG", description="Team to filter by"),
    include_comments: bool = Query(True, description="Include comments"),
) -> dict:
    """Export all issues as JSON with full fidelity."""
    initialize_issues_store()

    issues = [i for i in ISSUES_STORE.values() if i.get("team", "ENG") == team]

    export_data = {
        "version": "1.0.0",
        "exported_at": datetime.now().isoformat(),
        "team": team,
        "projects": list(set(i.get("project") for i in issues if i.get("project"))),
        "issue_count": len(issues),
        "issues": issues if include_comments else [
            {k: v for k, v in i.items() if k != "comments"} for i in issues
        ],
    }

    return export_data


@app.get("/api/export/csv")
async def export_csv(
    team: str = Query("ENG", description="Team to filter by"),
) -> Response:
    """Export issues as CSV (simplified format)."""
    initialize_issues_store()

    issues = [i for i in ISSUES_STORE.values() if i.get("team", "ENG") == team]

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["id", "title", "state", "priority", "created_at"],
    )
    writer.writeheader()

    for issue in issues:
        writer.writerow({
            "id": issue.get("identifier", ""),
            "title": issue.get("title", ""),
            "state": issue.get("state", ""),
            "priority": issue.get("priority", ""),
            "created_at": issue.get("created_at", ""),
        })

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=issues_{team}_{datetime.now().strftime('%Y%m%d')}.csv"
        },
    )


@app.get("/api/export/markdown")
async def export_markdown(
    team: str = Query("ENG", description="Team to filter by"),
) -> dict:
    """Export issues as Markdown files (returns list of file contents)."""
    initialize_issues_store()

    issues = [i for i in ISSUES_STORE.values() if i.get("team", "ENG") == team]

    markdown_files = []

    for issue in issues:
        md_content = f"""# {issue.get('identifier', 'Unknown')}: {issue.get('title', 'Untitled')}

**State:** {issue.get('state', 'Unknown')}
**Priority:** {issue.get('priority', 'none')}
**Type:** {issue.get('issue_type', 'Task')}
**Created:** {issue.get('created_at', 'Unknown')}
**Updated:** {issue.get('updated_at', 'Unknown')}

## Description

{issue.get('description', 'No description provided.')}

## Comments

"""
        comments = issue.get('comments', [])
        if comments:
            for comment in comments:
                md_content += f"### {comment.get('author', 'Unknown')} - {comment.get('created_at', '')}\n\n"
                md_content += f"{comment.get('content', '')}\n\n"
        else:
            md_content += "_No comments yet._\n"

        markdown_files.append({
            "filename": f"{issue.get('identifier', 'unknown')}.md",
            "content": md_content,
        })

    return {
        "exported_at": datetime.now().isoformat(),
        "team": team,
        "file_count": len(markdown_files),
        "files": markdown_files,
    }


@app.post("/api/import/preview")
async def import_preview(request: ImportPreviewRequest) -> dict:
    """Preview import data before executing."""
    initialize_issues_store()

    try:
        if request.format == "json":
            data = json.loads(request.data)
            issues = data.get("issues", data) if isinstance(data, dict) else data
        elif request.format == "csv":
            reader = csv.DictReader(io.StringIO(request.data))
            issues = []
            for row in reader:
                issues.append({
                    "identifier": row.get("id", ""),
                    "title": row.get("title", ""),
                    "state": row.get("state", "Todo"),
                    "priority": row.get("priority", "medium"),
                    "created_at": row.get("created_at", datetime.now().isoformat()),
                })
        else:
            return {"error": f"Unsupported format: {request.format}"}

        # Check for conflicts
        existing_ids = set(ISSUES_STORE.keys())
        new_issues = []
        conflicts = []

        for issue in issues:
            issue_id = issue.get("identifier", "")
            if issue_id in existing_ids:
                conflicts.append({
                    "id": issue_id,
                    "existing_title": ISSUES_STORE[issue_id].get("title", ""),
                    "new_title": issue.get("title", ""),
                })
            else:
                new_issues.append(issue)

        return {
            "success": True,
            "total_items": len(issues),
            "new_items": len(new_issues),
            "conflicts": len(conflicts),
            "conflict_details": conflicts[:10],  # Limit for preview
            "preview": issues[:5],  # First 5 for preview
        }

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/import/execute")
async def import_execute(request: ImportExecuteRequest) -> dict:
    """Execute the import with conflict resolution."""
    global ISSUE_COUNTER
    initialize_issues_store()

    try:
        if request.format == "json":
            data = json.loads(request.data)
            issues = data.get("issues", data) if isinstance(data, dict) else data
        elif request.format == "csv":
            reader = csv.DictReader(io.StringIO(request.data))
            issues = []
            for row in reader:
                issues.append({
                    "identifier": row.get("id", ""),
                    "title": row.get("title", ""),
                    "description": row.get("description", ""),
                    "state": row.get("state", "Todo"),
                    "priority": row.get("priority", "medium"),
                    "issue_type": "Task",
                    "team": "ENG",
                    "project": None,
                    "parent_id": None,
                    "dependencies": [],
                    "comments": [],
                    "created_at": row.get("created_at", datetime.now().isoformat()),
                    "updated_at": datetime.now().isoformat(),
                    "completed_at": None,
                })
        else:
            return {"error": f"Unsupported format: {request.format}"}

        results = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

        for issue in issues:
            issue_id = issue.get("identifier", "")

            try:
                if issue_id in ISSUES_STORE:
                    if request.conflict_resolution == ImportConflictResolution.SKIP:
                        results["skipped"] += 1
                    elif request.conflict_resolution == ImportConflictResolution.UPDATE:
                        if not request.dry_run:
                            ISSUES_STORE[issue_id].update({
                                "title": issue.get("title", ISSUES_STORE[issue_id]["title"]),
                                "description": issue.get("description", ISSUES_STORE[issue_id].get("description", "")),
                                "state": issue.get("state", ISSUES_STORE[issue_id]["state"]),
                                "priority": issue.get("priority", ISSUES_STORE[issue_id]["priority"]),
                                "updated_at": datetime.now().isoformat(),
                            })
                        results["updated"] += 1
                    elif request.conflict_resolution == ImportConflictResolution.DUPLICATE:
                        ISSUE_COUNTER += 1
                        new_id = f"ENG-{ISSUE_COUNTER}"
                        if not request.dry_run:
                            issue["identifier"] = new_id
                            issue["updated_at"] = datetime.now().isoformat()
                            issue.setdefault("comments", [])
                            issue.setdefault("dependencies", [])
                            ISSUES_STORE[new_id] = issue
                        results["created"] += 1
                else:
                    if not issue_id:
                        ISSUE_COUNTER += 1
                        issue_id = f"ENG-{ISSUE_COUNTER}"
                        issue["identifier"] = issue_id

                    if not request.dry_run:
                        issue.setdefault("team", "ENG")
                        issue.setdefault("project", None)
                        issue.setdefault("parent_id", None)
                        issue.setdefault("dependencies", [])
                        issue.setdefault("comments", [])
                        issue.setdefault("updated_at", datetime.now().isoformat())
                        issue.setdefault("completed_at", None)
                        ISSUES_STORE[issue_id] = issue
                    results["created"] += 1

            except Exception as e:
                results["errors"].append({"id": issue_id, "error": str(e)})

        return {
            "success": True,
            "dry_run": request.dry_run,
            "results": results,
            "total_issues_after": len(ISSUES_STORE),
        }

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/import/linear")
async def import_linear(request: LinearImportRequest) -> dict:
    """Import from Linear export JSON."""
    global ISSUE_COUNTER
    initialize_issues_store()

    try:
        data = json.loads(request.data)

        # Linear exports issues in a specific format
        linear_issues = data.get("issues", [])
        if not linear_issues and isinstance(data, list):
            linear_issues = data

        # Linear state mapping
        state_map = {
            "backlog": "Todo",
            "unstarted": "Todo",
            "started": "In Progress",
            "in_progress": "In Progress",
            "completed": "Done",
            "done": "Done",
            "canceled": "Cancelled",
            "cancelled": "Cancelled",
        }

        # Linear priority mapping (Linear uses 0-4 urgency)
        priority_map = {
            0: "none",
            1: "urgent",
            2: "high",
            3: "medium",
            4: "low",
        }

        results = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

        for linear_issue in linear_issues:
            try:
                # Map Linear fields to our format
                linear_id = linear_issue.get("identifier") or linear_issue.get("id", "")

                # Create issue ID (preserve Linear ID in metadata)
                ISSUE_COUNTER += 1
                issue_id = f"ENG-{ISSUE_COUNTER}"

                # Map state
                linear_state = (linear_issue.get("state", {}).get("name", "") or
                               linear_issue.get("state", "") or "").lower()
                mapped_state = state_map.get(linear_state, "Todo")

                # Map priority
                linear_priority = linear_issue.get("priority", 3)
                if isinstance(linear_priority, dict):
                    linear_priority = linear_priority.get("value", 3)
                mapped_priority = priority_map.get(linear_priority, "medium")

                # Map labels to priority if priority not set
                labels = linear_issue.get("labels", [])
                for label in labels:
                    label_name = label.get("name", "").lower() if isinstance(label, dict) else label.lower()
                    if label_name in ["urgent", "critical"]:
                        mapped_priority = "urgent"
                    elif label_name in ["high", "important"]:
                        mapped_priority = "high"
                    elif label_name in ["low", "minor"]:
                        mapped_priority = "low"

                issue = {
                    "identifier": issue_id,
                    "title": linear_issue.get("title", "Untitled"),
                    "description": linear_issue.get("description", ""),
                    "state": mapped_state,
                    "priority": mapped_priority,
                    "issue_type": "Task",
                    "team": "ENG",
                    "project": linear_issue.get("project", {}).get("name") if isinstance(linear_issue.get("project"), dict) else None,
                    "parent_id": None,
                    "dependencies": [],
                    "comments": [],
                    "created_at": linear_issue.get("createdAt", datetime.now().isoformat()),
                    "updated_at": linear_issue.get("updatedAt", datetime.now().isoformat()),
                    "completed_at": linear_issue.get("completedAt"),
                    "metadata": {
                        "linear_id": linear_id,
                        "linear_url": linear_issue.get("url", ""),
                        "imported_from": "linear",
                        "imported_at": datetime.now().isoformat(),
                    },
                }

                # Import comments
                linear_comments = linear_issue.get("comments", [])
                for lc in linear_comments:
                    issue["comments"].append({
                        "id": str(uuid.uuid4())[:8],
                        "author": lc.get("user", {}).get("name", "Linear User") if isinstance(lc.get("user"), dict) else "Linear User",
                        "content": lc.get("body", ""),
                        "created_at": lc.get("createdAt", datetime.now().isoformat()),
                    })

                if not request.dry_run:
                    ISSUES_STORE[issue_id] = issue
                results["created"] += 1

            except Exception as e:
                results["errors"].append({"linear_id": linear_id, "error": str(e)})

        return {
            "success": True,
            "dry_run": request.dry_run,
            "source": "linear",
            "results": results,
            "total_issues_after": len(ISSUES_STORE),
        }

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid Linear JSON: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/import/github")
async def import_github(request: GitHubImportRequest) -> dict:
    """Import issues from GitHub repository."""
    global ISSUE_COUNTER
    initialize_issues_store()

    github_token = os.environ.get("GITHUB_TOKEN", "")

    if not github_token:
        return {"success": False, "error": "GITHUB_TOKEN not configured"}

    try:
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        # Build API URL
        url = f"https://api.github.com/repos/{request.owner}/{request.repo}/issues"
        params = {"state": request.state, "per_page": 100}
        if request.labels:
            params["labels"] = ",".join(request.labels)

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=30.0)

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"GitHub API error: {response.status_code} - {response.text}",
                }

            github_issues = response.json()

        # GitHub priority mapping (from labels)
        priority_keywords = {
            "urgent": "urgent",
            "critical": "urgent",
            "high": "high",
            "important": "high",
            "medium": "medium",
            "low": "low",
            "minor": "low",
        }

        results = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

        for gh_issue in github_issues:
            # Skip pull requests
            if "pull_request" in gh_issue:
                continue

            try:
                gh_id = gh_issue.get("number", "")
                gh_title = gh_issue.get("title", "Untitled")

                # Check for existing import
                existing = None
                for eid, eissue in ISSUES_STORE.items():
                    meta = eissue.get("metadata", {})
                    if meta.get("github_number") == gh_id and meta.get("github_repo") == f"{request.owner}/{request.repo}":
                        existing = eid
                        break

                if existing:
                    if request.conflict_resolution == ImportConflictResolution.SKIP:
                        results["skipped"] += 1
                        continue
                    elif request.conflict_resolution == ImportConflictResolution.UPDATE:
                        # Update existing
                        ISSUES_STORE[existing]["title"] = gh_title
                        ISSUES_STORE[existing]["description"] = gh_issue.get("body", "") or ""
                        ISSUES_STORE[existing]["updated_at"] = datetime.now().isoformat()
                        results["updated"] += 1
                        continue

                # Determine priority from labels
                priority = "medium"
                gh_labels = gh_issue.get("labels", [])
                for label in gh_labels:
                    label_name = label.get("name", "").lower() if isinstance(label, dict) else label.lower()
                    for keyword, prio in priority_keywords.items():
                        if keyword in label_name:
                            priority = prio
                            break

                # Map state
                state = "Done" if gh_issue.get("state") == "closed" else "Todo"

                ISSUE_COUNTER += 1
                issue_id = f"ENG-{ISSUE_COUNTER}"

                issue = {
                    "identifier": issue_id,
                    "title": gh_title,
                    "description": gh_issue.get("body", "") or "",
                    "state": state,
                    "priority": priority,
                    "issue_type": "Bug" if any("bug" in (l.get("name", "") if isinstance(l, dict) else l).lower() for l in gh_labels) else "Task",
                    "team": "ENG",
                    "project": f"{request.owner}/{request.repo}",
                    "parent_id": None,
                    "dependencies": [],
                    "comments": [],
                    "created_at": gh_issue.get("created_at", datetime.now().isoformat()),
                    "updated_at": gh_issue.get("updated_at", datetime.now().isoformat()),
                    "completed_at": gh_issue.get("closed_at"),
                    "metadata": {
                        "github_number": gh_id,
                        "github_repo": f"{request.owner}/{request.repo}",
                        "github_url": gh_issue.get("html_url", ""),
                        "imported_from": "github",
                        "imported_at": datetime.now().isoformat(),
                    },
                }

                # Import comments if requested
                if request.import_comments:
                    comments_url = gh_issue.get("comments_url", "")
                    if comments_url:
                        async with httpx.AsyncClient() as client:
                            comments_response = await client.get(comments_url, headers=headers, timeout=30.0)
                            if comments_response.status_code == 200:
                                gh_comments = comments_response.json()
                                for gc in gh_comments:
                                    issue["comments"].append({
                                        "id": str(uuid.uuid4())[:8],
                                        "author": gc.get("user", {}).get("login", "GitHub User"),
                                        "content": gc.get("body", ""),
                                        "created_at": gc.get("created_at", datetime.now().isoformat()),
                                    })

                ISSUES_STORE[issue_id] = issue
                results["created"] += 1

            except Exception as e:
                results["errors"].append({"github_number": gh_id, "error": str(e)})

        return {
            "success": True,
            "source": "github",
            "repo": f"{request.owner}/{request.repo}",
            "results": results,
            "total_issues_after": len(ISSUES_STORE),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Backup Endpoints
# =============================================================================

BACKUPS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backups")


@app.get("/api/backups")
async def list_backups() -> dict:
    """List available backups."""
    if not os.path.exists(BACKUPS_DIR):
        return {"backups": [], "total": 0}

    backups = []
    for filename in os.listdir(BACKUPS_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(BACKUPS_DIR, filename)
            stat = os.stat(filepath)

            # Parse issue count from backup
            try:
                with open(filepath, "r") as f:
                    backup_data = json.load(f)
                    issue_count = backup_data.get("issue_count", 0)
            except Exception:
                issue_count = 0

            backups.append({
                "filename": filename,
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size_bytes": stat.st_size,
                "issue_count": issue_count,
            })

    # Sort by creation date, newest first
    backups.sort(key=lambda x: x["created_at"], reverse=True)

    return {"backups": backups, "total": len(backups)}


@app.post("/api/backups/create")
async def create_backup() -> dict:
    """Create a new backup."""
    initialize_issues_store()

    os.makedirs(BACKUPS_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.json"
    filepath = os.path.join(BACKUPS_DIR, filename)

    backup_data = {
        "version": "1.0.0",
        "created_at": datetime.now().isoformat(),
        "issue_count": len(ISSUES_STORE),
        "issues": list(ISSUES_STORE.values()),
    }

    with open(filepath, "w") as f:
        json.dump(backup_data, f, indent=2, default=str)

    stat = os.stat(filepath)

    return {
        "success": True,
        "backup": {
            "filename": filename,
            "created_at": backup_data["created_at"],
            "size_bytes": stat.st_size,
            "issue_count": backup_data["issue_count"],
        },
    }


@app.post("/api/backups/restore/{filename}")
async def restore_backup(filename: str) -> dict:
    """Restore from a backup."""
    global ISSUES_STORE, ISSUE_COUNTER

    filepath = os.path.join(BACKUPS_DIR, filename)

    if not os.path.exists(filepath):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Backup {filename} not found")

    try:
        with open(filepath, "r") as f:
            backup_data = json.load(f)

        issues = backup_data.get("issues", [])

        # Clear and restore
        ISSUES_STORE.clear()
        max_id = 50

        for issue in issues:
            issue_id = issue.get("identifier", "")
            ISSUES_STORE[issue_id] = issue

            # Track max ID
            try:
                num = int(issue_id.split("-")[1])
                max_id = max(max_id, num)
            except (ValueError, IndexError):
                pass

        ISSUE_COUNTER = max_id

        return {
            "success": True,
            "restored_issues": len(issues),
            "backup_date": backup_data.get("created_at", "Unknown"),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.delete("/api/backups/{filename}")
async def delete_backup(filename: str) -> dict:
    """Delete a backup file."""
    filepath = os.path.join(BACKUPS_DIR, filename)

    if not os.path.exists(filepath):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Backup {filename} not found")

    os.remove(filepath)

    return {"success": True, "deleted": filename}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
