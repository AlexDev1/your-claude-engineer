#!/usr/bin/env python3
"""
Autonomous Coding Agent Demo
============================

A minimal harness demonstrating long-running autonomous coding with Claude.
This script implements an orchestrator pattern where a main agent delegates to
specialized sub-agents (task, coding, telegram) for different domains.

The agent works in the current directory, picks tasks from the Task MCP Server
by priority, and executes them one at a time.

Example Usage:
    uv run python autonomous_agent_demo.py
    uv run python autonomous_agent_demo.py --team ENG --max-iterations 5
    uv run python autonomous_agent_demo.py --model opus
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent import run_autonomous_agent

# Load environment variables from .env file
load_dotenv()


# Available Claude 4.5 models
AVAILABLE_MODELS: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-5-20251101",
}

# Default orchestrator model (can be overridden by ORCHESTRATOR_MODEL env var or --model flag)
# Orchestrator just delegates, so haiku is sufficient and cost-effective
DEFAULT_MODEL: str = os.environ.get("ORCHESTRATOR_MODEL", "haiku").lower()
if DEFAULT_MODEL not in AVAILABLE_MODELS:
    DEFAULT_MODEL = "haiku"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Autonomous Coding Agent - Task-driven agent harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run in current directory, default team ENG
  uv run python autonomous_agent_demo.py

  # Specify team
  uv run python autonomous_agent_demo.py --team ENG

  # Use opus for orchestrator (more capable but costs more)
  uv run python autonomous_agent_demo.py --model opus

  # Limit iterations for testing
  uv run python autonomous_agent_demo.py --max-iterations 5

Environment Variables:
  ORCHESTRATOR_MODEL         Orchestrator model (default: haiku)
  TASK_MCP_URL               Task MCP server URL
  TELEGRAM_MCP_URL           Telegram MCP server URL
  MCP_API_KEY                API key for MCP servers
        """,
    )

    parser.add_argument(
        "--team",
        type=str,
        default="ENG",
        help="Team key for task management (default: ENG)",
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum number of agent iterations (default: unlimited)",
    )

    parser.add_argument(
        "--model",
        type=str,
        choices=list(AVAILABLE_MODELS.keys()),
        default=DEFAULT_MODEL,
        help=f"Model for orchestrator (sub-agents have fixed models: coding=sonnet, others=haiku) (default: {DEFAULT_MODEL})",
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, 1 for error, 130 for keyboard interrupt)
    """
    args: argparse.Namespace = parse_args()

    # Working directory is always cwd
    project_dir: Path = Path.cwd()

    # Resolve model short name to full model ID
    model_id: str = AVAILABLE_MODELS[args.model]

    # Run the agent
    try:
        asyncio.run(
            run_autonomous_agent(
                project_dir=project_dir,
                model=model_id,
                team=args.team,
                max_iterations=args.max_iterations,
            )
        )
        return 0
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        print("To resume, run the same command again")
        return 130  # Standard Unix exit code for SIGINT
    except Exception as e:
        error_type: str = type(e).__name__
        print(f"\nFatal error ({error_type}): {e}")
        print("\nCommon causes:")
        print("  1. Missing Claude authentication (run: claude login)")
        print("  2. MCP server connection issues (check TASK_MCP_URL, TELEGRAM_MCP_URL in .env)")
        print("\nFull error details:")
        raise


if __name__ == "__main__":
    sys.exit(main())
