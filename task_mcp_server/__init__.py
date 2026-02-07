"""
Task MCP Server - Analytics Extension
======================================

This module provides analytics functionality for the Task MCP Server:
- Project statistics (task counts by state/priority, completion times)
- Session timeline reports from META issue comments
- Stale issue detection

MCP Tools:
- Task_GetProjectStats - Get comprehensive project analytics
- Task_GetSessionReport - Get session timeline from META issue

Environment Variables:
- STALE_THRESHOLD_HOURS - Hours without activity to consider task stale (default: 2)
"""

from .database import (
    get_project_stats,
    get_stale_issues,
    get_session_timeline,
)
from .server import app

__all__ = [
    "app",
    "get_project_stats",
    "get_stale_issues",
    "get_session_timeline",
]
