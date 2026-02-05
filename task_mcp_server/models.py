"""
Pydantic Models for Task MCP Server
===================================

Data models for tasks, projects, teams, and related entities.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class Team(BaseModel):
    """Team model."""

    id: UUID
    key: str = Field(..., max_length=10)
    name: str = Field(..., max_length=255)
    created_at: datetime


class TeamCreate(BaseModel):
    """Create team request."""

    key: str = Field(..., max_length=10)
    name: str = Field(..., max_length=255)


class WorkflowState(BaseModel):
    """Workflow state model."""

    id: UUID
    team_id: UUID
    name: str = Field(..., max_length=50)
    type: str = Field(..., max_length=20)  # "unstarted", "started", "completed", "backlog", "canceled"
    position: int = 0


class Project(BaseModel):
    """Project model."""

    id: UUID
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255)
    description: Optional[str] = None
    team_id: UUID
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    """Create project request."""

    name: str = Field(..., max_length=255)
    team: str = Field(..., description="Team key or name")
    description: Optional[str] = None


class Issue(BaseModel):
    """Issue model."""

    id: UUID
    identifier: str = Field(..., max_length=20)
    title: str = Field(..., max_length=500)
    description: Optional[str] = None
    priority: str = Field(default="medium", max_length=20)
    state_id: Optional[UUID] = None
    state_name: Optional[str] = None
    state_type: Optional[str] = None
    project_id: Optional[UUID] = None
    project_name: Optional[str] = None
    team_id: UUID
    team_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class IssueCreate(BaseModel):
    """Create issue request."""

    team: str = Field(..., description="Team key or name")
    title: str = Field(..., max_length=500)
    description: Optional[str] = None
    project: Optional[str] = Field(None, description="Project slug or name")
    priority: str = Field(default="medium", pattern="^(urgent|high|medium|low)$")


class IssueUpdate(BaseModel):
    """Update issue request."""

    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    priority: Optional[str] = Field(None, pattern="^(urgent|high|medium|low)$")
    project: Optional[str] = Field(None, description="Project slug or name")


class Comment(BaseModel):
    """Comment model."""

    id: UUID
    issue_id: UUID
    body: str
    created_at: datetime


class CommentCreate(BaseModel):
    """Create comment request."""

    issue: str = Field(..., description="Issue identifier (e.g., ENG-42) or UUID")
    body: str


class UserInfo(BaseModel):
    """User/profile information."""

    name: str = "Task Agent"
    email: str = "agent@local"
    teams: list[Team] = []


class IssueListFilter(BaseModel):
    """Filter for listing issues."""

    team: Optional[str] = Field(None, description="Team key or name")
    project: Optional[str] = Field(None, description="Project slug or name")
    state: Optional[str] = Field(None, description="State name (Todo, In Progress, Done)")
    limit: int = Field(default=50, le=100)
    offset: int = Field(default=0, ge=0)


class StateTransition(BaseModel):
    """State transition request."""

    issue_id: str = Field(..., description="Issue identifier (e.g., ENG-42) or UUID")
    target_state: str = Field(..., description="Target state name (Todo, In Progress, Done)")
