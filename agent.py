"""
Agent Session Logic
===================

Core agent interaction functions for running autonomous coding sessions.
"""

import asyncio
import traceback
from pathlib import Path
from typing import Literal, NamedTuple

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from client import create_client
from progress import print_session_header
from prompts import get_execute_task


# Configuration
AUTO_CONTINUE_DELAY_SECONDS: int = 3


# Type-safe literal union - no runtime overhead
SessionStatus = Literal["continue", "error", "complete"]

# Constants for code clarity
SESSION_CONTINUE: SessionStatus = "continue"
SESSION_ERROR: SessionStatus = "error"
SESSION_COMPLETE: SessionStatus = "complete"

# Completion signal that orchestrator outputs when all tasks are done
COMPLETION_SIGNAL = "ALL_TASKS_DONE:"


class SessionResult(NamedTuple):
    """Result of running an agent session.

    Attributes:
        status: Session outcome:
            - "continue": Normal completion, agent can continue with more work
            - "error": Exception occurred, will retry with fresh session
            - "complete": All tasks done, orchestrator signaled ALL_TASKS_DONE
        response: Response text from the agent, or error message if status is "error"
    """

    status: SessionStatus
    response: str


async def run_agent_session(
    client: ClaudeSDKClient,
    message: str,
    project_dir: Path,
) -> SessionResult:
    """
    Run a single agent session using Claude Agent SDK.

    Args:
        client: Claude SDK client
        message: The prompt to send
        project_dir: Project directory path

    Returns:
        SessionResult with status and response text:
        - status=CONTINUE: Normal completion, agent can continue
        - status=ERROR: Exception occurred, will retry with fresh session
        - status=COMPLETE: All tasks done, ALL_TASKS_DONE signal detected
    """
    print("Sending prompt to Claude Agent SDK...\n")

    try:
        # Send the query
        await client.query(message)

        # Collect response text and show tool use
        response_text: str = ""
        async for msg in client.receive_response():
            # Handle AssistantMessage (text and tool use)
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
                        print(block.text, end="", flush=True)
                    elif isinstance(block, ToolUseBlock):
                        print(f"\n[Tool: {block.name}]", flush=True)
                        input_str: str = str(block.input)
                        if len(input_str) > 200:
                            print(f"   Input: {input_str[:200]}...", flush=True)
                        else:
                            print(f"   Input: {input_str}", flush=True)

            # Handle UserMessage (tool results)
            elif isinstance(msg, UserMessage):
                for block in msg.content:
                    if isinstance(block, ToolResultBlock):
                        result_content = block.content
                        is_error: bool = bool(block.is_error) if block.is_error else False

                        # Check if command was blocked by security hook
                        if "blocked" in str(result_content).lower():
                            print(f"   [BLOCKED] {result_content}", flush=True)
                        elif is_error:
                            # Show errors (truncated)
                            error_str: str = str(result_content)[:500]
                            print(f"   [Error] {error_str}", flush=True)
                        else:
                            # Tool succeeded - just show brief confirmation
                            print("   [Done]", flush=True)

        print("\n" + "-" * 70 + "\n")

        # Check for completion signal from orchestrator
        if COMPLETION_SIGNAL in response_text:
            return SessionResult(status=SESSION_COMPLETE, response=response_text)

        return SessionResult(status=SESSION_CONTINUE, response=response_text)

    except ConnectionError as e:
        print(f"\nNetwork error during agent session: {e}")
        print("Check your internet connection and try again.")
        traceback.print_exc()
        return SessionResult(status=SESSION_ERROR, response=str(e))

    except TimeoutError as e:
        print(f"\nTimeout during agent session: {e}")
        print("The API request timed out. Will retry with fresh session.")
        traceback.print_exc()
        return SessionResult(status=SESSION_ERROR, response=str(e))

    except Exception as e:
        error_type: str = type(e).__name__
        error_msg: str = str(e)

        print(f"\nError during agent session ({error_type}): {error_msg}")
        print("\nFull traceback:")
        traceback.print_exc()

        # Provide actionable guidance based on error type
        error_lower = error_msg.lower()
        if "auth" in error_lower or "token" in error_lower:
            print("\nThis appears to be an authentication error.")
            print("Check your CLAUDE_CODE_OAUTH_TOKEN environment variable.")
        elif "rate" in error_lower or "limit" in error_lower:
            print("\nThis appears to be a rate limit error.")
            print("The agent will retry after a delay.")
        elif "task" in error_lower:
            print("\nThis appears to be a Task MCP Server error.")
            print("Check your TASK_MCP_URL and ensure the server is running.")
        elif "telegram" in error_lower:
            print("\nThis appears to be a Telegram MCP Server error.")
            print("Check your TELEGRAM_MCP_URL and ensure the server is running.")
        elif "mcp" in error_lower:
            print("\nThis appears to be an MCP server error.")
            print("Check your MCP server URLs and ensure they are accessible.")
        else:
            # Unexpected error type - make this visible
            print(f"\nUnexpected error type: {error_type}")
            print("This may indicate a bug or an unhandled edge case.")
            print("The agent will retry, but please report this if it persists.")

        return SessionResult(status=SESSION_ERROR, response=error_msg)


async def run_autonomous_agent(
    project_dir: Path,
    model: str,
    team: str,
    max_iterations: int | None = None,
) -> None:
    """
    Run the autonomous agent loop.

    Args:
        project_dir: Working directory for the project
        model: Claude model to use
        team: Team key for task management (e.g., "ENG")
        max_iterations: Maximum number of iterations (None for unlimited)

    Raises:
        ValueError: If max_iterations is not positive
    """
    if max_iterations is not None and max_iterations < 1:
        raise ValueError(f"max_iterations must be positive, got {max_iterations}")

    print("\n" + "=" * 70)
    print("  AUTONOMOUS CODING AGENT")
    print("=" * 70)
    print(f"\nWorking directory: {project_dir}")
    print(f"Team: {team}")
    print(f"Model: {model}")
    if max_iterations:
        print(f"Max iterations: {max_iterations}")
    else:
        print("Max iterations: Unlimited (will run until all tasks done)")
    print()

    iteration: int = 0

    while True:
        iteration += 1

        # Check max iterations
        if max_iterations and iteration > max_iterations:
            print(f"\nReached max iterations ({max_iterations})")
            print("To continue, run the script again without --max-iterations")
            break

        # Print session header
        print_session_header(iteration)

        # Fresh client each iteration to avoid context window exhaustion
        client: ClaudeSDKClient = create_client(project_dir, model)

        # Same prompt every iteration: get next task and execute it
        prompt: str = get_execute_task(team)

        # Run session
        result: SessionResult = SessionResult(status=SESSION_ERROR, response="uninitialized")
        try:
            async with client:
                result = await run_agent_session(client, prompt, project_dir)
        except ConnectionError as e:
            print(f"\nFailed to connect to Claude SDK: {e}")
            print("Check your authentication and network connection.")
            traceback.print_exc()
            result = SessionResult(status=SESSION_ERROR, response=str(e))
        except Exception as e:
            error_type: str = type(e).__name__
            print(f"\nUnexpected error in session context ({error_type}): {e}")
            traceback.print_exc()
            result = SessionResult(status=SESSION_ERROR, response=str(e))

        # Handle status
        if result.status == SESSION_COMPLETE:
            print("\n" + "=" * 70)
            print("  ALL TASKS DONE")
            print("=" * 70)
            print("\nNo remaining tasks in Todo.")
            break
        elif result.status == SESSION_CONTINUE:
            print(f"\nAgent will auto-continue in {AUTO_CONTINUE_DELAY_SECONDS}s...")
        elif result.status == SESSION_ERROR:
            print("\nSession encountered an error")
            print("Will retry with a fresh session...")

        # Always wait before next iteration
        await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

        # Small delay between sessions
        if max_iterations is None or iteration < max_iterations:
            print("\nPreparing next session...\n")
            await asyncio.sleep(1)

    # Final summary
    print("\n" + "=" * 70)
    print("  SESSION COMPLETE")
    print("=" * 70)
    print(f"\nWorking directory: {project_dir}")
    print("\nDone!")
