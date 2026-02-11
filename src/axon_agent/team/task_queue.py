"""Task queue abstraction over Task MCP Server."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger("axon_agent.team.task_queue")

# Priority ordering for task sorting
PRIORITY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "low": 3}


class TaskQueue:
    """Wraps Task MCP Server for team coordination.

    Connects via SSE to the MCP server and uses tool calls to manage tasks.
    """

    def __init__(self, team: str, mcp_url: str, api_key: str = "") -> None:
        self.team = team
        self.mcp_url = mcp_url
        self.api_key = api_key
        self._session: ClientSession | None = None
        self._streams: Any = None

    async def connect(self) -> None:
        """Establish SSE connection to Task MCP Server."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._streams = sse_client(self.mcp_url, headers=headers)
        read_stream, write_stream = await self._streams.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()
        logger.info("Connected to Task MCP at %s", self.mcp_url)

    async def disconnect(self) -> None:
        """Close the SSE connection."""
        if self._session:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._streams:
            await self._streams.__aexit__(None, None, None)
            self._streams = None

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool and return parsed result."""
        if not self._session:
            raise RuntimeError("Not connected to Task MCP")
        result = await self._session.call_tool(name, arguments)
        # MCP tool results come as content blocks
        if result.content:
            for block in result.content:
                if hasattr(block, "text"):
                    try:
                        return json.loads(block.text)
                    except json.JSONDecodeError:
                        return block.text
        return None

    async def get_todo_tasks(self, project: str = "") -> list[dict]:
        """Get Todo tasks sorted by priority."""
        args: dict[str, Any] = {"team": self.team, "state": "Todo"}
        if project:
            args["project"] = project

        result = await self._call_tool("Task_ListIssues", args)
        if not isinstance(result, list):
            return []

        # Sort by priority
        return sorted(result, key=lambda t: PRIORITY_ORDER.get(t.get("priority", "low"), 3))

    async def claim_task(self, issue_id: str, worker_id: int) -> bool:
        """Atomically claim a task for a worker."""
        try:
            # Verify still Todo
            issue = await self._call_tool("Task_GetIssue", {"issue_id": issue_id})
            if not issue or issue.get("state") != "Todo":
                return False

            # Mark claim
            await self._call_tool("Task_AddComment", {
                "issue": issue_id,
                "body": f"__CLAIM__worker-{worker_id}__",
            })

            # Transition to In Progress
            await self._call_tool("Task_TransitionIssueState", {
                "issue_id": issue_id,
                "target_state": "In Progress",
            })

            logger.info("Worker %d claimed %s", worker_id, issue_id)
            return True
        except Exception as e:
            logger.warning("Failed to claim %s: %s", issue_id, e)
            return False

    async def complete_task(self, issue_id: str, worker_id: int) -> bool:
        """Mark a task as Done."""
        try:
            await self._call_tool("Task_AddComment", {
                "issue": issue_id,
                "body": f"Completed by worker-{worker_id}",
            })
            await self._call_tool("Task_TransitionIssueState", {
                "issue_id": issue_id,
                "target_state": "Done",
            })
            return True
        except Exception as e:
            logger.warning("Failed to complete %s: %s", issue_id, e)
            return False

    async def fail_task(self, issue_id: str, worker_id: int, error: str) -> bool:
        """Mark a task as failed — add comment and revert to Todo."""
        try:
            await self._call_tool("Task_AddComment", {
                "issue": issue_id,
                "body": f"Failed by worker-{worker_id}: {error}",
            })
            await self._call_tool("Task_TransitionIssueState", {
                "issue_id": issue_id,
                "target_state": "Todo",
            })
            return True
        except Exception as e:
            logger.warning("Failed to mark %s as failed: %s", issue_id, e)
            return False

    async def add_comment(self, issue_id: str, body: str) -> None:
        """Add a comment to a task."""
        await self._call_tool("Task_AddComment", {"issue": issue_id, "body": body})
