"""
CLI interface for Axon Agent.

Replaces autonomous_agent_demo.py as the main entry point.
Uses Click for command-line parsing with subcommands.

Usage:
    axon-agent run --team ENG
    axon-agent team --team ENG --workers 3
    axon-agent health
    axon-agent config
    axon-agent dashboard --port 8003
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from axon_agent import __version__

# ---------------------------------------------------------------------------
# Load .env early so all config reads pick up the values
# ---------------------------------------------------------------------------
load_dotenv()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _resolve_model(model_name: str) -> str:
    """Resolve a short model alias to a full Claude model ID.

    Imports AVAILABLE_MODELS from config at call time to avoid circular
    imports during module collection.
    """
    from axon_agent.config import AVAILABLE_MODELS

    if model_name in AVAILABLE_MODELS:
        return AVAILABLE_MODELS[model_name]
    # If the caller passed a full model ID already, use it as-is
    return model_name


def _default_model() -> str:
    """Return the default orchestrator model alias.

    Reads ``ORCHESTRATOR_MODEL`` env var and falls back to ``"haiku"``.
    """
    from axon_agent.config import AVAILABLE_MODELS

    raw = os.environ.get("ORCHESTRATOR_MODEL", "haiku").lower()
    if raw not in AVAILABLE_MODELS:
        return "haiku"
    return raw


def _model_choices() -> list[str]:
    """Return the list of valid model short names."""
    from axon_agent.config import AVAILABLE_MODELS

    return list(AVAILABLE_MODELS.keys())


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------

@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, "-V", "--version", prog_name="axon-agent")
def cli() -> None:
    """Axon Agent -- autonomous AI coding agent on Claude Agent SDK."""


# ---------------------------------------------------------------------------
# axon-agent run
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--team",
    default="ENG",
    show_default=True,
    help="Team key for task management.",
)
@click.option(
    "--model",
    default=None,
    help="Orchestrator model (haiku / sonnet / opus). "
    "Sub-agents use fixed models. [default from $ORCHESTRATOR_MODEL or haiku]",
)
@click.option(
    "--max-iterations",
    type=int,
    default=None,
    help="Max agent iterations (default: unlimited).",
)
@click.option(
    "--skip-preflight",
    is_flag=True,
    default=False,
    help="Skip pre-flight checks.",
)
@click.option(
    "--no-dashboard",
    is_flag=True,
    default=False,
    help="Disable the built-in dashboard.",
)
@click.option(
    "--dashboard-port",
    type=int,
    default=8003,
    show_default=True,
    help="Dashboard HTTP port.",
)
def run(
    team: str,
    model: str | None,
    max_iterations: int | None,
    skip_preflight: bool,
    no_dashboard: bool,
    dashboard_port: int,
) -> None:
    """Run the agent in solo mode (current default behaviour)."""
    from axon_agent.core.runner import run_autonomous_agent
    from axon_agent.monitoring.preflight import run_preflight_checks

    # --- preflight ---------------------------------------------------------
    if not skip_preflight:
        passed: bool = run_preflight_checks()
        if not passed:
            click.echo(
                "\nPreflight checks failed. Use --skip-preflight to bypass.",
                err=True,
            )
            raise SystemExit(2)
        click.echo()  # blank line before agent output

    # --- resolve model -----------------------------------------------------
    model_alias = model or _default_model()
    model_id = _resolve_model(model_alias)

    # --- dashboard ---------------------------------------------------------
    if not no_dashboard:
        from axon_agent.dashboard import start_dashboard

        start_dashboard(port=dashboard_port)
        click.echo(f"Dashboard: http://localhost:{dashboard_port}")

    # --- run ---------------------------------------------------------------
    project_dir = Path.cwd()
    click.echo(f"Starting autonomous agent  team={team}  model={model_alias}  dir={project_dir}")
    click.echo()

    try:
        asyncio.run(
            run_autonomous_agent(
                project_dir=project_dir,
                model=model_id,
                team=team,
                max_iterations=max_iterations,
            )
        )
    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user.")
        click.echo("Re-run the same command to resume.")
        raise SystemExit(130)


# ---------------------------------------------------------------------------
# axon-agent team
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--team", default="ENG", show_default=True, help="Team key.")
@click.option(
    "--workers",
    type=int,
    default=3,
    show_default=True,
    help="Number of parallel workers.",
)
@click.option(
    "--model",
    default=None,
    help="Orchestrator model (haiku / sonnet / opus).",
)
@click.option(
    "--max-tasks",
    type=int,
    default=None,
    help="Maximum number of tasks to process.",
)
@click.option(
    "--no-dashboard",
    is_flag=True,
    default=False,
    help="Disable the built-in dashboard.",
)
@click.option(
    "--dashboard-port",
    type=int,
    default=8003,
    show_default=True,
    help="Dashboard HTTP port.",
)
def team(
    team: str,
    workers: int,
    model: str | None,
    max_tasks: int | None,
    no_dashboard: bool,
    dashboard_port: int,
) -> None:
    """Run in team mode with parallel workers."""
    from axon_agent.config import get_config
    from axon_agent.team.coordinator import TeamCoordinator

    model_alias = model or _default_model()
    model_id = _resolve_model(model_alias)

    click.echo(
        f"Team mode: starting coordinator with {workers} workers  "
        f"team={team}  model={model_alias}"
    )

    if not no_dashboard:
        from axon_agent.dashboard import start_dashboard

        start_dashboard(port=dashboard_port)
        click.echo(f"Dashboard: http://localhost:{dashboard_port}")

    config = get_config()
    coordinator = TeamCoordinator(
        config=config,
        team=team,
        workers=workers,
        model=model_id,
        max_tasks=max_tasks,
    )

    try:
        asyncio.run(coordinator.run())
    except KeyboardInterrupt:
        click.echo("\n\nTeam coordinator interrupted.")
        raise SystemExit(130)


# ---------------------------------------------------------------------------
# axon-agent health
# ---------------------------------------------------------------------------

@cli.command()
def health() -> None:
    """Check MCP server health."""
    asyncio.run(_health_check())


async def _health_check() -> None:
    """Probe each MCP endpoint and report status."""
    import httpx

    task_url = os.environ.get("TASK_MCP_URL", "http://localhost:8001/sse")
    telegram_url = os.environ.get("TELEGRAM_MCP_URL", "http://localhost:8002/sse")

    endpoints: list[tuple[str, str]] = [
        ("Task MCP", task_url),
        ("Telegram MCP", telegram_url),
    ]

    all_ok = True

    async with httpx.AsyncClient(timeout=10.0) as client:
        for name, url in endpoints:
            # Derive a health URL: strip /sse suffix and append /health,
            # falling back to the base URL itself.
            base = url.rsplit("/sse", 1)[0] if url.endswith("/sse") else url
            health_url = f"{base}/health"

            try:
                resp = await client.get(health_url)
                if resp.status_code < 400:
                    click.echo(f"  OK   {name}  ({health_url})  status={resp.status_code}")
                else:
                    click.echo(
                        f"  WARN {name}  ({health_url})  status={resp.status_code}"
                    )
                    all_ok = False
            except httpx.ConnectError:
                click.echo(f"  FAIL {name}  ({health_url})  connection refused")
                all_ok = False
            except httpx.TimeoutException:
                click.echo(f"  FAIL {name}  ({health_url})  timeout")
                all_ok = False
            except Exception as exc:
                click.echo(f"  FAIL {name}  ({health_url})  {exc}")
                all_ok = False

    if not all_ok:
        raise SystemExit(1)

    click.echo("\nAll MCP servers healthy.")


# ---------------------------------------------------------------------------
# axon-agent config
# ---------------------------------------------------------------------------

@cli.command("config")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
@click.option(
    "--show-secrets",
    is_flag=True,
    default=False,
    help="Unmask secret values.",
)
def config_cmd(as_json: bool, show_secrets: bool) -> None:
    """Dump current configuration."""
    from axon_agent.config import AVAILABLE_MODELS

    task_url = os.environ.get("TASK_MCP_URL", "")
    telegram_url = os.environ.get("TELEGRAM_MCP_URL", "")
    api_key = os.environ.get("MCP_API_KEY", "")
    orchestrator_model = _default_model()

    masked_key = api_key if show_secrets else (_mask(api_key) if api_key else "(not set)")

    data = {
        "version": __version__,
        "orchestrator_model": orchestrator_model,
        "available_models": AVAILABLE_MODELS,
        "task_mcp_url": task_url or "(not set)",
        "telegram_mcp_url": telegram_url or "(not set)",
        "mcp_api_key": masked_key,
        "project_dir": str(Path.cwd()),
    }

    if as_json:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        click.echo("Axon Agent Configuration")
        click.echo("=" * 40)
        for key, value in data.items():
            if isinstance(value, dict):
                click.echo(f"  {key}:")
                for k, v in value.items():
                    click.echo(f"    {k}: {v}")
            else:
                click.echo(f"  {key}: {value}")


def _mask(secret: str) -> str:
    """Mask a secret, showing only the first 4 and last 4 characters."""
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}{'*' * (len(secret) - 8)}{secret[-4:]}"


# ---------------------------------------------------------------------------
# axon-agent dashboard
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--port",
    type=int,
    default=8003,
    show_default=True,
    help="Dashboard HTTP port.",
)
def dashboard(port: int) -> None:
    """Start the dashboard only (no agent)."""
    from axon_agent.dashboard import start_dashboard

    click.echo(f"Starting dashboard on http://localhost:{port}")
    click.echo("Press Ctrl+C to stop.")

    thread = start_dashboard(port=port)

    try:
        # Block the main thread so the daemon thread stays alive
        thread.join()
    except KeyboardInterrupt:
        click.echo("\nDashboard stopped.")


# ---------------------------------------------------------------------------
# axon-agent worker  (hidden -- used internally by team coordinator)
# ---------------------------------------------------------------------------

@cli.command(hidden=True)
@click.option("--worker-id", required=True, help="Worker identifier.")
@click.option("--team", default="ENG", help="Team key.")
@click.option("--project-dir", type=click.Path(exists=True), default=None, help="Working directory.")
@click.option("--model", default=None, help="Model for this worker.")
def worker(
    worker_id: str,
    team: str,
    project_dir: str | None,
    model: str | None,
) -> None:
    """Internal: run a single worker (used by team coordinator)."""
    from axon_agent.core.runner import run_autonomous_agent

    model_alias = model or _default_model()
    model_id = _resolve_model(model_alias)
    work_dir = Path(project_dir) if project_dir else Path.cwd()

    click.echo(f"Worker {worker_id} starting  team={team}  model={model_alias}  dir={work_dir}")

    try:
        asyncio.run(
            run_autonomous_agent(
                project_dir=work_dir,
                model=model_id,
                team=team,
                max_iterations=None,
            )
        )
    except KeyboardInterrupt:
        click.echo(f"\nWorker {worker_id} interrupted.")
        raise SystemExit(130)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Package entry point (called by ``axon-agent`` console script and ``__main__``)."""
    cli()
