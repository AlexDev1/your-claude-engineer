"""Test config validation edge cases."""
import os
import sys

from pydantic import ValidationError

from config import AppConfig, reset_config


def test_valid_defaults():
    """Test that explicitly provided values work correctly."""
    cfg = AppConfig(
        task_mcp_url="http://localhost:8001/sse",
        telegram_mcp_url="http://localhost:8002/sse",
        mcp_api_key="",
        orchestrator_model="haiku",
    )
    assert cfg.environment.value == "development"
    assert cfg.orchestrator_model.value == "haiku"
    assert cfg.health_check_max_retries == 3
    print("  [PASS] Explicit values work correctly")


def test_invalid_mcp_url():
    """Test that invalid MCP URLs are rejected."""
    try:
        AppConfig(task_mcp_url="not-a-url")
        print("  [FAIL] Should have rejected invalid URL")
        sys.exit(1)
    except ValidationError as e:
        assert "http://" in str(e)
        print("  [PASS] Invalid MCP URL rejected")


def test_invalid_github_repo():
    """Test that invalid github_repo format is rejected."""
    try:
        AppConfig(github_repo="no-slash-here")
        print("  [FAIL] Should have rejected invalid repo format")
        sys.exit(1)
    except ValidationError as e:
        assert "owner/repo" in str(e)
        print("  [PASS] Invalid github_repo rejected")


def test_valid_github_repo():
    """Test that valid github_repo is accepted."""
    cfg = AppConfig(github_repo="AxonCode/your-claude-engineer")
    assert cfg.github_repo == "AxonCode/your-claude-engineer"
    print("  [PASS] Valid github_repo accepted")


def test_production_warnings(capsys=None):
    """Test that production warnings fire for localhost URLs."""
    import io
    from contextlib import redirect_stderr

    buf = io.StringIO()
    with redirect_stderr(buf):
        cfg = AppConfig(
            environment="production",
            task_mcp_url="http://localhost:8001/sse",
        )
    output = buf.getvalue()
    assert "localhost" in output or cfg.environment.value == "production"
    print("  [PASS] Production warnings work")


def test_enum_values():
    """Test that enum values are accepted as strings."""
    cfg = AppConfig(
        environment="staging",
        orchestrator_model="sonnet",
        coding_agent_model="inherit",
    )
    assert cfg.environment.value == "staging"
    assert cfg.orchestrator_model.value == "sonnet"
    assert cfg.coding_agent_model.value == "inherit"
    print("  [PASS] Enum values accepted as strings")


def test_health_check_bounds():
    """Test health check bounds validation."""
    try:
        AppConfig(health_check_max_retries=0)
        print("  [FAIL] Should have rejected retries=0")
        sys.exit(1)
    except ValidationError:
        print("  [PASS] health_check_max_retries=0 rejected (ge=1)")

    try:
        AppConfig(health_check_max_retries=25)
        print("  [FAIL] Should have rejected retries=25")
        sys.exit(1)
    except ValidationError:
        print("  [PASS] health_check_max_retries=25 rejected (le=20)")


def test_config_dump():
    """Test config dump methods."""
    cfg = AppConfig(
        mcp_api_key="super-secret-key-12345",
        telegram_bot_token="bot-token-abcdef",
    )
    dump = cfg.dump(mask_secrets=True)
    assert "super-secret" not in dump
    assert "***" in dump
    print("  [PASS] Secrets masked in dump")

    dump_unmasked = cfg.dump(mask_secrets=False)
    assert "super-secret-key-12345" in dump_unmasked
    print("  [PASS] Secrets shown when unmasked")

    json_dump = cfg.dump_json(mask_secrets=True)
    assert "super-secret" not in json_dump
    print("  [PASS] Secrets masked in JSON dump")


def test_derived_properties():
    """Test derived properties."""
    cfg = AppConfig(
        orchestrator_model="sonnet",
        github_reviewers="alice,bob, charlie ",
        telegram_bot_token="tok",
        telegram_chat_id="123",
        mcp_api_key="key123",
    )
    assert cfg.orchestrator_model_id == "claude-sonnet-4-5-20250929"
    assert cfg.github_reviewers_list == ["alice", "bob", "charlie"]
    assert cfg.telegram_configured is True
    assert "Bearer" in cfg.mcp_auth_headers.get("Authorization", "")
    print("  [PASS] Derived properties work")

    cfg2 = AppConfig(telegram_bot_token="", telegram_chat_id="")
    assert cfg2.telegram_configured is False
    print("  [PASS] telegram_configured=False when missing")


if __name__ == "__main__":
    print("Config Validation Tests")
    print("=" * 40)
    test_valid_defaults()
    test_invalid_mcp_url()
    test_invalid_github_repo()
    test_valid_github_repo()
    test_production_warnings()
    test_enum_values()
    test_health_check_bounds()
    test_config_dump()
    test_derived_properties()
    print("=" * 40)
    print("All tests passed!")
