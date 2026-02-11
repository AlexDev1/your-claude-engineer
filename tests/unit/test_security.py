#!/usr/bin/env python3
"""
Security Hook Tests
===================

Tests for the bash command security validation logic.
Run with: pytest tests/unit/test_security.py -v
"""

import asyncio
import pytest
from typing import cast

from claude_agent_sdk import PreToolUseHookInput

from axon_agent.security.hooks import (
    ValidationResult,
    bash_security_hook,
    extract_commands,
    validate_chmod_command,
    validate_init_script,
)


def run_hook(command: str) -> dict:
    """Run the security hook on a command."""
    input_data = cast(
        PreToolUseHookInput,
        {
            "session_id": "test-session",
            "transcript_path": "/tmp/test-transcript",
            "cwd": "/tmp",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        },
    )
    return asyncio.run(bash_security_hook(input_data))


class TestExtractCommands:
    """Tests for command extraction logic."""

    @pytest.mark.parametrize("cmd,expected", [
        ("ls -la", ["ls"]),
        ("npm install && npm run build", ["npm", "npm"]),
        ("cat file.txt | grep pattern", ["cat", "grep"]),
        ("/usr/bin/node script.js", ["node"]),
        ("VAR=value ls", ["ls"]),
        ("git status || git init", ["git", "git"]),
    ])
    def test_extract_commands(self, cmd: str, expected: list[str]):
        """Command extraction works correctly."""
        result = extract_commands(cmd)
        assert result == expected


class TestChmodValidation:
    """Tests for chmod command validation."""

    @pytest.mark.parametrize("cmd,should_allow,description", [
        # Allowed cases
        ("chmod +x init.sh", True, "basic +x"),
        ("chmod +x script.sh", True, "+x on any script"),
        ("chmod u+x init.sh", True, "user +x"),
        ("chmod a+x init.sh", True, "all +x"),
        ("chmod ug+x init.sh", True, "user+group +x"),
        ("chmod +x file1.sh file2.sh", True, "multiple files"),
        # Blocked cases
        ("chmod 777 init.sh", False, "numeric mode"),
        ("chmod 755 init.sh", False, "numeric mode 755"),
        ("chmod +w init.sh", False, "write permission"),
        ("chmod +r init.sh", False, "read permission"),
        ("chmod -x init.sh", False, "remove execute"),
        ("chmod -R +x dir/", False, "recursive flag"),
        ("chmod --recursive +x dir/", False, "long recursive flag"),
        ("chmod +x", False, "missing file"),
    ])
    def test_chmod_validation(self, cmd: str, should_allow: bool, description: str):
        """Chmod validation works correctly."""
        result = validate_chmod_command(cmd)
        assert result.allowed == should_allow, f"Failed for {description}: {result.reason}"


class TestInitScriptValidation:
    """Tests for init.sh script execution validation."""

    @pytest.mark.parametrize("cmd,should_allow,description", [
        # Allowed cases
        ("./init.sh", True, "basic ./init.sh"),
        ("./init.sh arg1 arg2", True, "with arguments"),
        ("/path/to/init.sh", True, "absolute path"),
        ("../dir/init.sh", True, "relative path with init.sh"),
        # Blocked cases
        ("./setup.sh", False, "different script name"),
        ("./init.py", False, "python script"),
        ("bash init.sh", False, "bash invocation"),
        ("sh init.sh", False, "sh invocation"),
        ("./malicious.sh", False, "malicious script"),
        ("./init.sh; rm -rf /", False, "semicolons attached to token by shlex"),
    ])
    def test_init_script_validation(self, cmd: str, should_allow: bool, description: str):
        """Init script validation works correctly."""
        result = validate_init_script(cmd)
        assert result.allowed == should_allow, f"Failed for {description}: {result.reason}"


class TestBlockedCommands:
    """Tests for commands that should be blocked."""

    @pytest.mark.parametrize("cmd", [
        # Not in allowlist - dangerous system commands
        "shutdown now",
        "reboot",
        "dd if=/dev/zero of=/dev/sda",
        # rm on dangerous paths
        "rm -rf /",
        "rm -rf /Users",
        "rm -rf /etc",
        # Not in allowlist
        "wget https://example.com",
        "kill 12345",
        "killall node",
        # pkill with non-dev processes
        "pkill bash",
        "pkill chrome",
        "pkill python",
        # Shell injection attempts
        "$(echo pkill) node",
        'eval "pkill node"',
        # chmod with disallowed modes
        "chmod 777 file.sh",
        "chmod 755 file.sh",
        "chmod +w file.sh",
        "chmod -R +x dir/",
        # Non-init.sh scripts
        "./setup.sh",
        "./malicious.sh",
        # Command chaining with dangerous rm
        "./init.sh; rm -rf /",
    ])
    def test_blocked_commands(self, cmd: str):
        """Dangerous commands are blocked."""
        result = run_hook(cmd)
        assert result.get("decision") == "block", f"Expected block for: {cmd}"


class TestAllowedCommands:
    """Tests for commands that should be allowed."""

    @pytest.mark.parametrize("cmd", [
        # File inspection
        "ls -la",
        "cat README.md",
        "head -100 file.txt",
        "tail -20 log.txt",
        "wc -l file.txt",
        "grep -r pattern src/",
        # File operations
        "cp file1.txt file2.txt",
        "mkdir newdir",
        "mkdir -p path/to/dir",
        "touch file.txt",
        "rm temp.txt",
        "rm -rf node_modules",
        # Directory
        "pwd",
        # Text output
        "echo hello",
        "echo 'test message'",
        # HTTP/Network
        "curl https://example.com",
        "curl -X POST https://api.example.com",
        # Python
        "python app.py",
        "python3 script.py",
        # Node.js development
        "npm install",
        "npm run build",
        "node server.js",
        # Version control
        "git status",
        "git commit -m 'test'",
        "git add . && git commit -m 'msg'",
        # Process management
        "ps aux",
        "lsof -i :3000",
        "sleep 2",
        # Allowed pkill patterns
        "pkill node",
        "pkill npm",
        "pkill -f node",
        "pkill -f 'node server.js'",
        "pkill vite",
        # Chained commands
        "npm install && npm run build",
        "ls | grep test",
        # Full paths
        "/usr/local/bin/node app.js",
        # chmod +x
        "chmod +x init.sh",
        "chmod +x script.sh",
        "chmod u+x init.sh",
        "chmod a+x init.sh",
        # init.sh execution
        "./init.sh",
        "./init.sh --production",
        "/path/to/init.sh",
        # Combined chmod and init.sh
        "chmod +x init.sh && ./init.sh",
    ])
    def test_allowed_commands(self, cmd: str):
        """Safe commands are allowed."""
        result = run_hook(cmd)
        assert result.get("decision") != "block", f"Unexpected block for: {cmd}, reason: {result.get('reason')}"
