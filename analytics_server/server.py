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
"""

import os
import json
from datetime import datetime, timedelta
from typing import Any, Optional
from collections import defaultdict

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
