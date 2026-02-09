"""
Централизованная конфигурация (ENG-25)
========================================

Конфигурация на основе Pydantic Settings с валидацией, профилями окружения
и дампом конфига для отладки. Заменяет разбросанные вызовы os.environ.get().

Все переменные окружения определены, провалидированы и задокументированы здесь.
Другие модули должны импортировать из этого модуля вместо прямого чтения os.environ.

Usage:
    from config import get_config

    cfg = get_config()
    print(cfg.task_mcp_url)
    print(cfg.environment)
    cfg.dump()

Environment Profiles:
    Set ENVIRONMENT=development|staging|production to select a profile.
    Each profile provides different defaults (e.g., log levels, URLs).
"""

from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Final

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Environment profiles
# ---------------------------------------------------------------------------

class Environment(str, Enum):
    """Supported environment profiles."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


# ---------------------------------------------------------------------------
# Model options (matches agents/definitions.py)
# ---------------------------------------------------------------------------

class ModelOption(str, Enum):
    """Valid Claude model short names."""

    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


class AgentModelOption(str, Enum):
    """Valid model options for sub-agents (includes inherit)."""

    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"
    INHERIT = "inherit"


# ---------------------------------------------------------------------------
# Available Claude 4.5 model IDs (maps short name -> full ID)
# ---------------------------------------------------------------------------

AVAILABLE_MODELS: Final[dict[str, str]] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-5-20251101",
}


# ---------------------------------------------------------------------------
# Configuration class
# ---------------------------------------------------------------------------

class AppConfig(BaseSettings):
    """
    Centralized application configuration.

    All environment variables are declared here with types, defaults,
    and validation. Pydantic Settings reads from the process environment
    and from the .env file automatically.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Do not fail if .env is missing -- bare env vars are fine
        env_ignore_empty=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Environment profile
    # ------------------------------------------------------------------
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Active environment profile (development, staging, production)",
    )

    # ------------------------------------------------------------------
    # MCP Server URLs
    # ------------------------------------------------------------------
    task_mcp_url: str = Field(
        default="http://localhost:8001/sse",
        description="URL of the Task MCP Server SSE endpoint",
    )
    telegram_mcp_url: str = Field(
        default="http://localhost:8002/sse",
        description="URL of the Telegram MCP Server SSE endpoint",
    )
    mcp_api_key: str = Field(
        default="",
        description="Bearer token for MCP server authentication",
    )

    # ------------------------------------------------------------------
    # Agent model configuration
    # ------------------------------------------------------------------
    orchestrator_model: ModelOption = Field(
        default=ModelOption.HAIKU,
        description="Claude model for orchestrator agent",
    )
    task_agent_model: AgentModelOption = Field(
        default=AgentModelOption.HAIKU,
        description="Claude model for task agent",
    )
    coding_agent_model: AgentModelOption = Field(
        default=AgentModelOption.SONNET,
        description="Claude model for coding agent",
    )
    telegram_agent_model: AgentModelOption = Field(
        default=AgentModelOption.HAIKU,
        description="Claude model for telegram agent",
    )

    # ------------------------------------------------------------------
    # Project output
    # ------------------------------------------------------------------
    generations_base_path: Path = Field(
        default=Path("./generations"),
        description="Base directory for generated project output",
    )

    # ------------------------------------------------------------------
    # Health check (ENG-58)
    # ------------------------------------------------------------------
    health_check_max_retries: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Max health check retry attempts before failing",
    )
    health_check_retry_delay_seconds: int = Field(
        default=30,
        ge=1,
        le=600,
        description="Delay between health check retries (seconds)",
    )

    # ------------------------------------------------------------------
    # Heartbeat monitoring
    # ------------------------------------------------------------------
    heartbeat_interval_minutes: int = Field(
        default=5,
        ge=1,
        le=1440,
        description="Heartbeat check interval in minutes",
    )
    stale_threshold_hours: float = Field(
        default=2.0,
        ge=0.1,
        le=168.0,
        description="Hours without update to consider a task stale",
    )
    heartbeat_team: str = Field(
        default="",
        description="Team key to monitor (empty = all teams)",
    )

    # ------------------------------------------------------------------
    # Telegram bot
    # ------------------------------------------------------------------
    telegram_bot_token: str = Field(
        default="",
        description="Telegram Bot token from @BotFather",
    )
    telegram_chat_id: str = Field(
        default="",
        description="Telegram Chat ID for notifications",
    )

    # ------------------------------------------------------------------
    # Telegram rich reports (ENG-31)
    # ------------------------------------------------------------------
    daily_digest_hour: int = Field(
        default=18,
        ge=0,
        le=23,
        description="Hour to send daily digest (0-23)",
    )
    weekly_summary_day: int = Field(
        default=4,
        ge=0,
        le=6,
        description="Day to send weekly summary (0=Monday, 6=Sunday)",
    )

    # ------------------------------------------------------------------
    # GitHub integration
    # ------------------------------------------------------------------
    github_token: str = Field(
        default="",
        description="GitHub Personal Access Token",
    )
    github_repo: str = Field(
        default="",
        description="GitHub repository in owner/repo format",
    )
    github_base_branch: str = Field(
        default="main",
        description="Default base branch for pull requests",
    )
    github_reviewers: str = Field(
        default="",
        description="Comma-separated GitHub usernames for PR review",
    )
    github_issues_sync: bool = Field(
        default=False,
        description="Enable bidirectional GitHub Issues sync",
    )

    # ------------------------------------------------------------------
    # Context manager (ENG-29)
    # ------------------------------------------------------------------
    max_context_tokens: int = Field(
        default=180_000,
        ge=10_000,
        le=1_000_000,
        description="Maximum context window token budget",
    )

    # ------------------------------------------------------------------
    # Backup / analytics (scripts/backup.py, analytics_server)
    # ------------------------------------------------------------------
    analytics_api_url: str = Field(
        default="http://localhost:8003",
        description="URL of the analytics API server",
    )
    backup_retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Number of days to retain backups",
    )

    # =====================================================================
    # Validators
    # =====================================================================

    @field_validator("task_mcp_url", "telegram_mcp_url")
    @classmethod
    def _validate_mcp_url(cls, v: str) -> str:
        """Ensure MCP URLs look like valid HTTP(S) endpoints."""
        if v and not v.startswith(("http://", "https://")):
            raise ValueError(
                f"MCP URL must start with http:// or https://, got: {v!r}"
            )
        return v

    @field_validator("github_repo")
    @classmethod
    def _validate_github_repo(cls, v: str) -> str:
        """Ensure github_repo is in owner/repo format when provided."""
        if v and "/" not in v:
            raise ValueError(
                f"GITHUB_REPO must be in 'owner/repo' format, got: {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _warn_production_defaults(self) -> "AppConfig":
        """Log warnings if production profile uses insecure defaults."""
        if self.environment == Environment.PRODUCTION:
            if not self.mcp_api_key:
                _print_warning("MCP_API_KEY is empty in production")
            if self.task_mcp_url.startswith("http://localhost"):
                _print_warning("TASK_MCP_URL points to localhost in production")
            if self.telegram_mcp_url.startswith("http://localhost"):
                _print_warning("TELEGRAM_MCP_URL points to localhost in production")
        return self

    # =====================================================================
    # Derived properties
    # =====================================================================

    @property
    def orchestrator_model_id(self) -> str:
        """Full model ID for the orchestrator."""
        return AVAILABLE_MODELS[self.orchestrator_model.value]

    @property
    def is_production(self) -> bool:
        """True if running in production environment."""
        return self.environment == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        """True if running in development environment."""
        return self.environment == Environment.DEVELOPMENT

    @property
    def github_reviewers_list(self) -> list[str]:
        """Parse comma-separated reviewers into a list."""
        if not self.github_reviewers:
            return []
        return [r.strip() for r in self.github_reviewers.split(",") if r.strip()]

    @property
    def telegram_configured(self) -> bool:
        """True if Telegram bot token and chat ID are both set."""
        return bool(self.telegram_bot_token) and bool(self.telegram_chat_id)

    @property
    def mcp_auth_headers(self) -> dict[str, str]:
        """Authorization headers for MCP server requests."""
        if self.mcp_api_key:
            return {"Authorization": f"Bearer {self.mcp_api_key}"}
        return {}

    # =====================================================================
    # Config dump for debugging
    # =====================================================================

    def dump(self, *, mask_secrets: bool = True) -> str:
        """
        Dump configuration as a human-readable string for debugging.

        Args:
            mask_secrets: If True, mask sensitive values like tokens and keys.

        Returns:
            Multi-line formatted configuration dump.
        """
        secret_fields = {
            "mcp_api_key",
            "telegram_bot_token",
            "github_token",
        }
        lines = [
            "=" * 60,
            "  Configuration Dump",
            "=" * 60,
            f"  Environment: {self.environment.value}",
            "",
        ]

        data = self.model_dump(mode="json")
        # Group fields by section using field order
        for key, value in data.items():
            display_value = value
            if mask_secrets and key in secret_fields:
                display_value = _mask_secret(str(value))
            lines.append(f"  {key}: {display_value}")

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)

    def dump_json(self, *, mask_secrets: bool = True) -> str:
        """
        Dump configuration as JSON string for programmatic consumption.

        Args:
            mask_secrets: If True, mask sensitive values.

        Returns:
            JSON-formatted configuration string.
        """
        secret_fields = {
            "mcp_api_key",
            "telegram_bot_token",
            "github_token",
        }
        data = self.model_dump(mode="json")
        if mask_secrets:
            for key in secret_fields:
                if key in data and data[key]:
                    data[key] = _mask_secret(str(data[key]))
        return json.dumps(data, indent=2, default=str)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_secret(value: str) -> str:
    """Mask a secret value, showing only last 4 characters."""
    if not value:
        return "(not set)"
    if len(value) <= 4:
        return "***"
    return "***" + value[-4:]


def _print_warning(msg: str) -> None:
    """Print a configuration warning to stderr."""
    print(f"[config WARNING] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_config_instance: AppConfig | None = None


def get_config() -> AppConfig:
    """
    Get the global configuration singleton.

    The configuration is loaded once from environment variables and .env file.
    Subsequent calls return the cached instance.

    Returns:
        Validated AppConfig instance.
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = AppConfig()
    return _config_instance


def reset_config() -> None:
    """
    Reset the configuration singleton (useful for testing).

    The next call to get_config() will reload from environment.
    """
    global _config_instance
    _config_instance = None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """
    CLI entry point: dump current configuration.

    Usage:
        python config.py
        python config.py --json
        python config.py --validate
    """
    import argparse

    parser = argparse.ArgumentParser(description="Dump and validate configuration")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output configuration as JSON",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate configuration and exit",
    )
    parser.add_argument(
        "--show-secrets",
        action="store_true",
        help="Show secret values without masking",
    )
    args = parser.parse_args()

    try:
        cfg = get_config()
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    if args.validate:
        print("Configuration is valid.")
        print(f"  Environment: {cfg.environment.value}")
        print(f"  Task MCP URL: {cfg.task_mcp_url}")
        print(f"  Telegram MCP URL: {cfg.telegram_mcp_url}")
        return 0

    mask = not args.show_secrets

    if args.json:
        print(cfg.dump_json(mask_secrets=mask))
    else:
        print(cfg.dump(mask_secrets=mask))

    return 0


if __name__ == "__main__":
    sys.exit(main())
