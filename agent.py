"""
Agent Session Logic
===================

Core agent interaction functions for running autonomous coding sessions.
Integrates with session_state for phase tracking and crash recovery (ENG-66).
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
from prompts import (
    get_continuation_task_with_memory,
    get_execute_task_with_memory,
)
from session_state import (
    ErrorType,
    GracefulDegradation,
    SessionPhase,
    SessionRecovery,
    SessionState,
    SessionStateManager,
    clear_session_state,
    get_session_recovery,
    get_session_state_manager,
    load_session_state,
    save_session_state,
    set_default_project_dir,
    transition_phase,
)


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
    Run the autonomous agent loop with session state tracking and crash recovery.

    Features (ENG-66):
    - Session phase tracking with persistence to .agent/session_state.json
    - Crash recovery from persisted state on startup
    - Phase-level retry with smart restart logic
    - Graceful degradation for MCP/Playwright failures
    - Exponential backoff on rate limits

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

    # Set default project dir for standalone session state functions (ENG-66)
    set_default_project_dir(project_dir)

    # Initialize session state manager and check for crash recovery (ENG-66)
    state_manager = get_session_state_manager(project_dir)
    recovery = get_session_recovery(project_dir)

    # Check for interrupted session on startup
    recovery_needed, saved_state = await recovery.check_recovery()
    resume_phase: SessionPhase | None = None

    if recovery_needed and saved_state:
        print("\n" + "-" * 70)
        print("  CRASH RECOVERY: Resuming from interrupted session")
        print(f"  Issue: {saved_state.issue_id}")
        print(f"  Last phase: {saved_state.phase.phase_name}")
        if saved_state.uncommitted_changes:
            print("  Status: Uncommitted changes detected")
        if saved_state.degraded_services:
            print(f"  Degraded services: {', '.join(saved_state.degraded_services)}")
        print("-" * 70 + "\n")

        # Determine resume point
        resume_phase = state_manager.get_resume_phase(saved_state)
        print(f"Resuming at phase: {resume_phase.phase_name}")

        # Restore state
        state_manager._current_state = saved_state

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

        # First iteration uses execute_task, subsequent iterations use continuation_task
        # Continuation prompt checks META issue for previous session context before proceeding
        # Both prompts now include .agent/MEMORY.md content for persistent memory
        if iteration == 1:
            prompt: str = get_execute_task_with_memory(team, project_dir)
            print("(Loading agent memory from .agent/MEMORY.md)")

            # If recovering, add context about resume phase (ENG-66)
            if resume_phase:
                prompt += f"\n\n[RECOVERY MODE: Resuming from phase '{resume_phase.phase_name}']"
                if saved_state and saved_state.uncommitted_changes:
                    prompt += "\n[Note: Uncommitted changes detected - check git status]"
                resume_phase = None  # Clear after first use
        else:
            prompt = get_continuation_task_with_memory(team, project_dir)
            print("(Using continuation prompt - will check previous session context)")
            print("(Loading agent memory from .agent/MEMORY.md)")

        # Run session with error recovery (ENG-66)
        result: SessionResult = SessionResult(status=SESSION_ERROR, response="uninitialized")
        error_type_detected: ErrorType | None = None

        try:
            async with client:
                result = await run_agent_session(client, prompt, project_dir)

            # Success - clear session state (ENG-66)
            if result.status == SESSION_COMPLETE:
                state_manager.clear_state()

        except ConnectionError as e:
            print(f"\nNetwork error during agent session: {e}")
            print("Check your internet connection and try again.")
            traceback.print_exc()
            error_type_detected = recovery.classify_error(e)
            state_manager.record_error(e, error_type_detected)
            result = SessionResult(status=SESSION_ERROR, response=str(e))

        except TimeoutError as e:
            print(f"\nTimeout during agent session: {e}")
            error_type_detected = ErrorType.MCP_TIMEOUT
            state_manager.record_error(e, error_type_detected)
            result = SessionResult(status=SESSION_ERROR, response=str(e))

        except Exception as e:
            error_type_name: str = type(e).__name__
            print(f"\nUnexpected error in session context ({error_type_name}): {e}")
            traceback.print_exc()
            error_type_detected = recovery.classify_error(e)
            state_manager.record_error(e, error_type_detected)
            result = SessionResult(status=SESSION_ERROR, response=str(e))

        # Handle status
        if result.status == SESSION_COMPLETE:
            print("\n" + "=" * 70)
            print("  ALL TASKS DONE")
            print("=" * 70)
            print("\nNo remaining tasks in Todo.")
            state_manager.clear_state()
            break

        elif result.status == SESSION_CONTINUE:
            print(f"\nAgent will auto-continue in {AUTO_CONTINUE_DELAY_SECONDS}s...")

        elif result.status == SESSION_ERROR:
            print("\nSession encountered an error")

            # Calculate backoff delay based on error type (ENG-66)
            if error_type_detected:
                current_phase = (
                    state_manager.current_state.phase
                    if state_manager.current_state
                    else SessionPhase.ORIENT
                )
                attempt = state_manager.get_phase_attempt(current_phase).attempt
                delay = GracefulDegradation.get_backoff_delay(
                    attempt, error_type_detected
                )

                # Check for graceful degradation
                if not state_manager.get_phase_attempt(current_phase).can_retry:
                    if GracefulDegradation.should_skip_service(
                        error_type_detected, current_phase
                    ):
                        msg = GracefulDegradation.get_degradation_message(
                            error_type_detected, current_phase
                        )
                        print(f"Graceful degradation: {msg}")
                        state_manager.mark_degraded(current_phase.phase_name)
                        # Continue to next iteration
                        delay = AUTO_CONTINUE_DELAY_SECONDS
                    else:
                        # Save changes if git error during commit
                        if (
                            error_type_detected == ErrorType.GIT_ERROR
                            and current_phase == SessionPhase.COMMIT
                        ):
                            print("Attempting to save uncommitted changes...")
                            diff_file = await recovery.save_git_diff_to_file()
                            if diff_file:
                                print(f"Changes saved to: {diff_file}")
                            else:
                                await recovery.stash_changes()

                print(f"Will retry with backoff delay of {delay:.1f}s...")
                await asyncio.sleep(delay)
                continue
            else:
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
