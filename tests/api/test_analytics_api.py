"""
Analytics API Tests
====================

Tests for the analytics server endpoints.
Coverage: velocity, efficiency, bottlenecks, summary, export.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
import json

# Import the server module for testing
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from analytics_server.server import (
    app,
    calculate_velocity,
    calculate_efficiency,
    detect_bottlenecks,
    calculate_priority_distribution,
    calculate_activity_heatmap,
    VelocityData,
    EfficiencyData,
    BottleneckData,
)

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sample_issues():
    """Generate sample issues for testing."""
    now = datetime.now()
    return [
        {
            "identifier": "ENG-1",
            "title": "Task 1",
            "state": "Done",
            "priority": "high",
            "created_at": (now - timedelta(days=3)).isoformat(),
            "updated_at": now.isoformat(),
            "completed_at": (now - timedelta(days=1)).isoformat(),
        },
        {
            "identifier": "ENG-2",
            "title": "Task 2",
            "state": "Done",
            "priority": "medium",
            "created_at": (now - timedelta(days=5)).isoformat(),
            "updated_at": now.isoformat(),
            "completed_at": (now - timedelta(days=2)).isoformat(),
        },
        {
            "identifier": "ENG-3",
            "title": "Task 3",
            "state": "In Progress",
            "priority": "high",
            "created_at": (now - timedelta(days=2)).isoformat(),
            "updated_at": (now - timedelta(hours=10)).isoformat(),
            "completed_at": None,
            "time_in_state_hours": 10,
        },
        {
            "identifier": "ENG-4",
            "title": "Task 4",
            "state": "Todo",
            "priority": "low",
            "created_at": (now - timedelta(days=1)).isoformat(),
            "updated_at": now.isoformat(),
            "completed_at": None,
        },
        {
            "identifier": "ENG-5",
            "title": "Task 5",
            "state": "Cancelled",
            "priority": "medium",
            "created_at": (now - timedelta(days=4)).isoformat(),
            "updated_at": (now - timedelta(days=3)).isoformat(),
            "completed_at": (now - timedelta(days=3)).isoformat(),
        },
    ]


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client):
        """Health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "analytics-api"
        assert "timestamp" in data


class TestVelocityCalculation:
    """Tests for velocity calculation logic."""

    def test_calculate_velocity_with_completed_tasks(self, sample_issues):
        """Velocity calculation counts completed tasks correctly."""
        result = calculate_velocity(sample_issues, days=14)

        assert isinstance(result, VelocityData)
        assert result.total_completed >= 0
        assert result.weekly_avg >= 0
        assert result.trend in ["up", "down", "stable"]
        assert len(result.daily) == 14

    def test_calculate_velocity_empty_issues(self):
        """Velocity calculation handles empty issue list."""
        result = calculate_velocity([], days=7)

        assert result.total_completed == 0
        assert result.weekly_avg == 0
        assert result.trend == "stable"

    def test_calculate_velocity_all_in_progress(self):
        """Velocity is zero when no tasks completed."""
        issues = [
            {"identifier": "ENG-1", "state": "In Progress", "completed_at": None}
        ]
        result = calculate_velocity(issues, days=7)

        assert result.total_completed == 0


class TestEfficiencyCalculation:
    """Tests for efficiency metrics calculation."""

    def test_calculate_efficiency_success_rate(self, sample_issues):
        """Efficiency calculation computes success rate correctly."""
        result = calculate_efficiency(sample_issues)

        assert isinstance(result, EfficiencyData)
        # 2 done, 1 cancelled = 66.7% success rate
        assert 60 <= result.success_rate <= 70
        assert result.tasks_done == 2
        assert result.tasks_cancelled == 1
        assert result.tasks_in_progress == 1
        assert result.tasks_todo == 1

    def test_calculate_efficiency_completion_time(self, sample_issues):
        """Efficiency calculation computes average completion time."""
        result = calculate_efficiency(sample_issues)

        # Should have some completion time for done tasks
        assert result.avg_completion_time_hours >= 0

    def test_calculate_efficiency_all_done(self):
        """100% success rate when all tasks done."""
        now = datetime.now()
        issues = [
            {
                "identifier": "ENG-1",
                "state": "Done",
                "created_at": (now - timedelta(hours=2)).isoformat(),
                "completed_at": now.isoformat(),
            }
        ]
        result = calculate_efficiency(issues)

        assert result.success_rate == 100.0
        assert result.tasks_done == 1
        assert result.tasks_cancelled == 0


class TestBottleneckDetection:
    """Tests for bottleneck detection logic."""

    def test_detect_stuck_tasks(self, sample_issues):
        """Bottleneck detection identifies stuck tasks."""
        result = detect_bottlenecks(sample_issues)

        assert isinstance(result, BottleneckData)
        # ENG-3 is in progress for 10 hours, should be detected as stuck
        assert len(result.stuck_tasks) >= 1
        assert any(t["identifier"] == "ENG-3" for t in result.stuck_tasks)

    def test_detect_bottlenecks_recommendations(self, sample_issues):
        """Bottleneck detection provides recommendations."""
        result = detect_bottlenecks(sample_issues)

        assert len(result.recommendations) >= 1

    def test_detect_bottlenecks_no_stuck_tasks(self):
        """No stuck tasks when all complete or new."""
        now = datetime.now()
        issues = [
            {
                "identifier": "ENG-1",
                "state": "Done",
                "updated_at": now.isoformat(),
                "completed_at": now.isoformat(),
            }
        ]
        result = detect_bottlenecks(issues)

        assert len(result.stuck_tasks) == 0


class TestPriorityDistribution:
    """Tests for priority distribution calculation."""

    def test_calculate_priority_distribution(self, sample_issues):
        """Priority distribution counts tasks by priority."""
        result = calculate_priority_distribution(sample_issues)

        assert result["high"] == 2
        assert result["medium"] == 2
        assert result["low"] == 1

    def test_priority_distribution_empty(self):
        """Empty issues returns empty distribution."""
        result = calculate_priority_distribution([])
        assert len(result) == 0


class TestActivityHeatmap:
    """Tests for activity heatmap calculation."""

    def test_calculate_activity_heatmap(self, sample_issues):
        """Activity heatmap contains all days and hours."""
        result = calculate_activity_heatmap(sample_issues)

        # Should have 7 days * 24 hours = 168 entries
        assert len(result) == 168

        # Each entry should have day, hour, count
        for entry in result:
            assert "day" in entry
            assert "hour" in entry
            assert "count" in entry
            assert 0 <= entry["hour"] < 24

    def test_activity_heatmap_empty(self):
        """Empty issues returns zero-filled heatmap."""
        result = calculate_activity_heatmap([])

        assert len(result) == 168
        assert all(entry["count"] == 0 for entry in result)


class TestVelocityEndpoint:
    """Tests for /api/analytics/velocity endpoint."""

    def test_velocity_endpoint_default(self, client):
        """Velocity endpoint returns valid data."""
        response = client.get("/api/analytics/velocity")

        assert response.status_code == 200
        data = response.json()
        assert "daily" in data
        assert "weekly_avg" in data
        assert "trend" in data
        assert "total_completed" in data

    def test_velocity_endpoint_custom_days(self, client):
        """Velocity endpoint respects days parameter."""
        response = client.get("/api/analytics/velocity?days=7")

        assert response.status_code == 200
        data = response.json()
        assert len(data["daily"]) == 7

    def test_velocity_endpoint_invalid_days(self, client):
        """Velocity endpoint validates days range."""
        response = client.get("/api/analytics/velocity?days=0")
        assert response.status_code == 422  # Validation error

        response = client.get("/api/analytics/velocity?days=100")
        assert response.status_code == 422  # Exceeds max


class TestEfficiencyEndpoint:
    """Tests for /api/analytics/efficiency endpoint."""

    def test_efficiency_endpoint(self, client):
        """Efficiency endpoint returns valid data."""
        response = client.get("/api/analytics/efficiency")

        assert response.status_code == 200
        data = response.json()
        assert "success_rate" in data
        assert "avg_completion_time_hours" in data
        assert "tasks_done" in data
        assert "tasks_cancelled" in data
        assert "tasks_in_progress" in data
        assert "tasks_todo" in data


class TestBottlenecksEndpoint:
    """Tests for /api/analytics/bottlenecks endpoint."""

    def test_bottlenecks_endpoint(self, client):
        """Bottlenecks endpoint returns valid data."""
        response = client.get("/api/analytics/bottlenecks")

        assert response.status_code == 200
        data = response.json()
        assert "stuck_tasks" in data
        assert "avg_retry_rate" in data
        assert "time_distribution" in data
        assert "recommendations" in data


class TestSummaryEndpoint:
    """Tests for /api/analytics/summary endpoint."""

    def test_summary_endpoint(self, client):
        """Summary endpoint returns complete dashboard data."""
        response = client.get("/api/analytics/summary")

        assert response.status_code == 200
        data = response.json()
        assert "velocity" in data
        assert "efficiency" in data
        assert "bottlenecks" in data
        assert "priority_distribution" in data
        assert "activity_heatmap" in data


class TestExportEndpoint:
    """Tests for /api/analytics/export endpoint."""

    def test_export_json(self, client):
        """Export endpoint returns JSON format."""
        response = client.get("/api/analytics/export?format=json")

        assert response.status_code == 200
        data = response.json()
        assert "period" in data
        assert "team" in data
        assert "issues" in data
        assert "summary" in data

    def test_export_csv(self, client):
        """Export endpoint returns CSV format."""
        response = client.get("/api/analytics/export?format=csv")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers.get("content-disposition", "")

    def test_export_period_filter(self, client):
        """Export endpoint respects period parameter."""
        for period in ["day", "week", "month"]:
            response = client.get(f"/api/analytics/export?format=json&period={period}")
            assert response.status_code == 200
            data = response.json()
            assert data["period"] == period


class TestContextEndpoints:
    """Tests for context budget endpoints."""

    def test_get_context_stats(self, client):
        """Context stats endpoint returns valid data."""
        response = client.get("/api/context/stats")

        assert response.status_code == 200
        data = response.json()
        assert "max_tokens" in data
        assert "total_used" in data
        assert "remaining" in data
        assert "usage_percent" in data
        assert "breakdown" in data

    def test_update_context_stats(self, client):
        """Context stats can be updated."""
        new_stats = {
            "total_used": 50000,
            "remaining": 150000,
        }
        response = client.post("/api/context/stats", json=new_stats)

        assert response.status_code == 200
        data = response.json()
        assert data["updated"] is True

    def test_get_prompt_stats(self, client):
        """Prompt stats endpoint returns token information."""
        response = client.get("/api/context/prompts")

        assert response.status_code == 200
        # Response structure depends on prompts directory existence
