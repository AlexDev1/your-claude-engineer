#!/usr/bin/env python3
"""
MCP Servers Integration Tests
=============================

Integration tests for Task MCP Server and Telegram MCP Server.

Prerequisites:
    docker compose up -d

Run with:
    uv run python test_mcp_servers.py
"""

import asyncio
import json
import sys
import uuid
from typing import Any

import httpx

# Server URLs
TASK_MCP_URL = "http://localhost:8001"
TELEGRAM_MCP_URL = "http://localhost:8002"

# Test results
passed: int = 0
failed: int = 0


def log_result(test_name: str, success: bool, details: str = "") -> None:
    """Log test result."""
    global passed, failed
    if success:
        passed += 1
        status = "PASS"
    else:
        failed += 1
        status = "FAIL"

    print(f"  {status}: {test_name}")
    if details and not success:
        print(f"         {details}")


class MCPClient:
    """Simple MCP client for testing with SSE transport."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def connect(self) -> bool:
        """Test SSE endpoint connectivity."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                async with client.stream("GET", f"{self.base_url}/sse") as response:
                    if response.status_code != 200:
                        return False

                    async for line in response.aiter_lines():
                        if line.startswith("data: ") and "session_id=" in line:
                            return True

            return False
        except Exception as e:
            print(f"      DEBUG: connect() exception: {e}")
            return False

    async def _read_response(self, lines_iter, request_id: str, timeout: float = 10.0) -> dict | None:
        """Read JSON-RPC response from SSE stream."""
        import asyncio
        event_type = None
        try:
            start = asyncio.get_event_loop().time()
            async for line in lines_iter:
                if asyncio.get_event_loop().time() - start > timeout:
                    return {"error": "Timeout waiting for response"}

                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: ") and event_type == "message":
                    try:
                        data = json.loads(line[6:])
                        if data.get("id") == request_id:
                            return data
                    except json.JSONDecodeError:
                        pass
                elif not line:
                    # Empty line - continue
                    pass
                else:
                    event_type = None
        except asyncio.CancelledError:
            pass
        return None

    async def _init_session(self, post_client, session_url: str, lines_iter) -> bool:
        """Initialize MCP session."""
        init_id = str(uuid.uuid4())

        await post_client.post(
            session_url,
            json={
                "jsonrpc": "2.0",
                "id": init_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            },
        )

        response = await self._read_response(lines_iter, init_id, timeout=5.0)
        if not response or "error" in response:
            return False

        # Send initialized notification
        await post_client.post(
            session_url,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
        )

        return True

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] = None) -> dict[str, Any] | None:
        """Call an MCP tool and get response via SSE."""
        request_id = str(uuid.uuid4())

        try:
            sse_client = httpx.AsyncClient(timeout=30.0)
            post_client = httpx.AsyncClient(timeout=30.0)

            try:
                async with sse_client.stream("GET", f"{self.base_url}/sse") as sse_response:
                    if sse_response.status_code != 200:
                        return None

                    lines_iter = sse_response.aiter_lines()

                    # Get session endpoint
                    session_url = None
                    async for line in lines_iter:
                        if line.startswith("data: ") and "session_id=" in line:
                            endpoint = line[6:]
                            session_url = f"{self.base_url}{endpoint}"
                            break

                    if not session_url:
                        return None

                    # Initialize session
                    if not await self._init_session(post_client, session_url, lines_iter):
                        return {"error": "Session initialization failed"}

                    # Send tool call request
                    post_response = await post_client.post(
                        session_url,
                        json={
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "tools/call",
                            "params": {
                                "name": tool_name,
                                "arguments": arguments or {},
                            },
                        },
                    )

                    if post_response.status_code != 202:
                        return {"error": f"POST returned {post_response.status_code}"}

                    # Read response
                    response = await self._read_response(lines_iter, request_id)
                    if not response:
                        return {"error": "No response received"}

                    if "error" in response:
                        return {"error": response["error"]}

                    result = response.get("result", {})
                    content = result.get("content", [])

                    if content and content[0].get("type") == "text":
                        text = content[0].get("text", "{}")
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError:
                            return {"text": text}

                    return result

            finally:
                await sse_client.aclose()
                await post_client.aclose()
        except Exception as e:
            return {"error": str(e)}

    async def list_tools(self) -> list[str]:
        """List available tools via SSE."""
        request_id = str(uuid.uuid4())

        try:
            sse_client = httpx.AsyncClient(timeout=30.0)
            post_client = httpx.AsyncClient(timeout=30.0)

            try:
                async with sse_client.stream("GET", f"{self.base_url}/sse") as sse_response:
                    if sse_response.status_code != 200:
                        return []

                    lines_iter = sse_response.aiter_lines()

                    # Get session endpoint
                    session_url = None
                    async for line in lines_iter:
                        if line.startswith("data: ") and "session_id=" in line:
                            endpoint = line[6:]
                            session_url = f"{self.base_url}{endpoint}"
                            break

                    if not session_url:
                        return []

                    # Initialize session
                    if not await self._init_session(post_client, session_url, lines_iter):
                        return []

                    # Send tools/list request
                    post_response = await post_client.post(
                        session_url,
                        json={
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "tools/list",
                        },
                    )

                    if post_response.status_code != 202:
                        return []

                    # Read response
                    response = await self._read_response(lines_iter, request_id)
                    if not response or "error" in response:
                        return []

                    tools = response.get("result", {}).get("tools", [])
                    return [t.get("name") for t in tools]

            finally:
                await sse_client.aclose()
                await post_client.aclose()
        except Exception:
            return []

    async def close(self) -> None:
        """Close the client (no-op since we create fresh clients per call)."""
        pass


# =============================================================================
# Task MCP Server Tests
# =============================================================================


async def test_task_mcp_health() -> bool:
    """Test Task MCP Server health endpoint."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{TASK_MCP_URL}/health", timeout=5.0)
            data = response.json()
            success = (
                response.status_code == 200
                and data.get("status") == "healthy"
                and data.get("database") == "connected"
            )
            log_result("Task MCP health", success, f"Response: {data}")
            return success
        except Exception as e:
            log_result("Task MCP health", False, str(e))
            return False


async def test_task_mcp_connection() -> tuple[bool, MCPClient | None]:
    """Test Task MCP Server SSE connection."""
    client = MCPClient(TASK_MCP_URL)
    success = await client.connect()
    log_result("Task MCP SSE connection", success)
    if success:
        return True, client
    await client.close()
    return False, None


async def test_task_mcp_tools(client: MCPClient) -> bool:
    """Test Task MCP tools listing."""
    tools = await client.list_tools()
    expected = ["Task_WhoAmI", "Task_ListTeams", "Task_CreateIssue", "Task_GetIssue"]
    found = [t for t in expected if t in tools]
    success = len(found) >= 3
    log_result("Task MCP tools list", success, f"Found {len(tools)} tools: {tools[:6]}...")
    return success


async def test_task_mcp_whoami(client: MCPClient) -> bool:
    """Test Task_WhoAmI tool."""
    result = await client.call_tool("Task_WhoAmI")
    if result and "name" in result and "email" in result:
        log_result("Task MCP WhoAmI", True, f"Agent: {result.get('name')}")
        return True
    log_result("Task MCP WhoAmI", False, f"Result: {result}")
    return False


async def test_task_mcp_list_teams(client: MCPClient) -> bool:
    """Test Task_ListTeams tool."""
    result = await client.call_tool("Task_ListTeams")
    if result and "teams" in result:
        teams = result.get("teams", [])
        has_eng = any(t.get("key") == "ENG" for t in teams)
        success = len(teams) >= 1 and has_eng
        log_result("Task MCP ListTeams", success, f"Teams: {[t.get('key') for t in teams]}")
        return success
    log_result("Task MCP ListTeams", False, f"Result: {result}")
    return False


async def test_task_mcp_create_issue(client: MCPClient) -> tuple[bool, str | None]:
    """Test Task_CreateIssue tool."""
    result = await client.call_tool(
        "Task_CreateIssue",
        {
            "team": "ENG",
            "title": "Integration Test Issue",
            "description": "Created by integration test",
            "priority": "low",
        },
    )

    if result and "identifier" in result:
        identifier = result.get("identifier")
        log_result("Task MCP CreateIssue", True, f"Created: {identifier}")
        return True, identifier
    log_result("Task MCP CreateIssue", False, f"Result: {result}")
    return False, None


async def test_task_mcp_get_issue(client: MCPClient, identifier: str) -> bool:
    """Test Task_GetIssue tool."""
    result = await client.call_tool("Task_GetIssue", {"issue_id": identifier})

    if result and result.get("identifier") == identifier:
        log_result("Task MCP GetIssue", True, f"Retrieved: {identifier}")
        return True
    log_result("Task MCP GetIssue", False, f"Result: {result}")
    return False


async def test_task_mcp_transition(client: MCPClient, identifier: str) -> bool:
    """Test Task_TransitionIssueState tool."""
    result = await client.call_tool(
        "Task_TransitionIssueState",
        {"issue_id": identifier, "target_state": "In Progress"},
    )

    if result and result.get("state") == "In Progress":
        log_result("Task MCP Transition", True, f"{identifier}: Todo -> In Progress")
        return True
    log_result("Task MCP Transition", False, f"Result: {result}")
    return False


async def test_task_mcp_add_comment(client: MCPClient, identifier: str) -> bool:
    """Test Task_AddComment tool."""
    result = await client.call_tool(
        "Task_AddComment",
        {"issue": identifier, "body": "Integration test comment"},
    )

    if result and "id" in result:
        log_result("Task MCP AddComment", True, f"Comment added to {identifier}")
        return True
    log_result("Task MCP AddComment", False, f"Result: {result}")
    return False


# =============================================================================
# Telegram MCP Server Tests
# =============================================================================


async def test_telegram_mcp_health() -> bool:
    """Test Telegram MCP Server health endpoint."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{TELEGRAM_MCP_URL}/health", timeout=5.0)
            data = response.json()
            success = (
                response.status_code == 200
                and data.get("status") == "healthy"
                and data.get("bot_configured") is True
            )
            log_result(
                "Telegram MCP health",
                success,
                f"Bot: @{data.get('bot_username', 'unknown')}"
            )
            return success
        except Exception as e:
            log_result("Telegram MCP health", False, str(e))
            return False


async def test_telegram_mcp_connection() -> tuple[bool, MCPClient | None]:
    """Test Telegram MCP Server SSE connection."""
    client = MCPClient(TELEGRAM_MCP_URL)
    success = await client.connect()
    log_result("Telegram MCP SSE connection", success)
    if success:
        return True, client
    await client.close()
    return False, None


async def test_telegram_mcp_tools(client: MCPClient) -> bool:
    """Test Telegram MCP tools listing."""
    tools = await client.list_tools()
    expected = ["Telegram_WhoAmI", "Telegram_SendMessage"]
    found = [t for t in expected if t in tools]
    success = len(found) >= 2
    log_result("Telegram MCP tools list", success, f"Found: {tools}")
    return success


async def test_telegram_mcp_whoami(client: MCPClient) -> bool:
    """Test Telegram_WhoAmI tool."""
    result = await client.call_tool("Telegram_WhoAmI")
    if result and "bot_username" in result:
        log_result("Telegram MCP WhoAmI", True, f"Bot: @{result.get('bot_username')}")
        return True
    log_result("Telegram MCP WhoAmI", False, f"Result: {result}")
    return False


async def test_telegram_mcp_send_message(client: MCPClient) -> bool:
    """Test Telegram_SendMessage tool."""
    result = await client.call_tool(
        "Telegram_SendMessage",
        {"message": "Integration test from test_mcp_servers.py"},
    )

    if result and result.get("sent"):
        log_result("Telegram MCP SendMessage", True, f"Message ID: {result.get('message_id')}")
        return True
    log_result("Telegram MCP SendMessage", False, f"Result: {result}")
    return False


# =============================================================================
# Main
# =============================================================================


async def run_tests() -> int:
    """Run all integration tests."""
    global passed, failed

    print("=" * 70)
    print("  MCP SERVERS INTEGRATION TESTS")
    print("=" * 70)

    # Task MCP Server Tests
    print("\n--- Task MCP Server Tests ---\n")

    await test_task_mcp_health()

    connected, task_client = await test_task_mcp_connection()
    if connected and task_client:
        await test_task_mcp_tools(task_client)
        await test_task_mcp_whoami(task_client)
        await test_task_mcp_list_teams(task_client)

        created, identifier = await test_task_mcp_create_issue(task_client)
        if created and identifier:
            await test_task_mcp_get_issue(task_client, identifier)
            await test_task_mcp_transition(task_client, identifier)
            await test_task_mcp_add_comment(task_client, identifier)

        await task_client.close()

    # Telegram MCP Server Tests
    print("\n--- Telegram MCP Server Tests ---\n")

    await test_telegram_mcp_health()

    connected, telegram_client = await test_telegram_mcp_connection()
    if connected and telegram_client:
        await test_telegram_mcp_tools(telegram_client)
        await test_telegram_mcp_whoami(telegram_client)
        await test_telegram_mcp_send_message(telegram_client)
        await telegram_client.close()

    # Summary
    print("\n" + "-" * 70)
    print(f"  Results: {passed} passed, {failed} failed")
    print("-" * 70)

    if failed == 0:
        print("\n  ALL TESTS PASSED")
        return 0
    else:
        print(f"\n  {failed} TEST(S) FAILED")
        return 1


def main() -> int:
    """Entry point."""
    return asyncio.run(run_tests())


if __name__ == "__main__":
    sys.exit(main())
