#!/usr/bin/env python3
"""
Self-Diagnostics Tool
=====================

Callable diagnostics tool for the Coding Agent to check the health
of the development environment.

Checks:
- Port availability (common dev ports)
- node_modules corruption
- npm cache health
- Git state (uncommitted changes, detached HEAD, merge conflicts)

Returns structured results with actionable recommendations.

Usage:
    # CLI
    python self_diagnostics.py
    python self_diagnostics.py --json

    # Programmatic
    from self_diagnostics import run_diagnostics
    results = run_diagnostics()
"""

import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Status(str, Enum):
    """Status indicators for diagnostic checks."""
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class DiagnosticResult:
    """Result of a single diagnostic check."""
    name: str
    status: Status
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DiagnosticsReport:
    """Complete diagnostics report."""
    summary: dict[str, int]
    checks: list[DiagnosticResult]
    overall_status: Status

    def to_dict(self) -> dict:
        """Convert report to dictionary."""
        return {
            "summary": self.summary,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "details": c.details,
                    "recommendations": c.recommendations,
                }
                for c in self.checks
            ],
            "overall_status": self.overall_status.value,
        }


# Common development ports to check
DEV_PORTS = {
    3000: "React/Vite dev server (alternative)",
    5000: "Flask/Python dev server",
    5173: "Vite dev server (dashboard)",
    8003: "FastAPI analytics server",
    8080: "Common HTTP alternative",
    8085: "Analytics API server",
}


def run_command(cmd: list[str], timeout: int = 30) -> tuple[bool, str, str]:
    """Run a command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)


def check_port(port: int) -> tuple[bool, str | None]:
    """
    Check if a port is available (not in use).

    Returns:
        (is_available, process_info_if_in_use)
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex(("localhost", port))
        if result == 0:
            # Port is in use, try to find what's using it
            success, stdout, _ = run_command(["lsof", "-i", f":{port}", "-t"])
            if success and stdout:
                pid = stdout.split("\n")[0]
                # Get process name
                success2, name, _ = run_command(["ps", "-p", pid, "-o", "comm="])
                if success2:
                    return False, f"PID {pid} ({name})"
                return False, f"PID {pid}"
            return False, "unknown process"
        return True, None
    except Exception:
        return True, None
    finally:
        sock.close()


def check_ports() -> DiagnosticResult:
    """Check availability of common development ports."""
    available = []
    in_use = []
    details = {}

    for port, description in DEV_PORTS.items():
        is_available, process_info = check_port(port)
        if is_available:
            available.append(port)
            details[str(port)] = {"status": "available", "description": description}
        else:
            in_use.append(port)
            details[str(port)] = {
                "status": "in_use",
                "description": description,
                "process": process_info,
            }

    recommendations = []

    if in_use:
        status = Status.WARNING
        message = f"{len(in_use)} port(s) in use: {', '.join(map(str, in_use))}"
        for port in in_use:
            recommendations.append(
                f"Kill process on port {port}: lsof -ti:{port} | xargs kill -9"
            )
    else:
        status = Status.OK
        message = f"All {len(available)} checked ports are available"

    return DiagnosticResult(
        name="Port Availability",
        status=status,
        message=message,
        details=details,
        recommendations=recommendations,
    )


def check_node_modules() -> DiagnosticResult:
    """Check node_modules for corruption indicators."""
    dashboard_dir = Path("/home/dev/work/AxonCode/your-claude-engineer/dashboard")
    node_modules = dashboard_dir / "node_modules"
    package_json = dashboard_dir / "package.json"
    package_lock = dashboard_dir / "package-lock.json"

    details = {}
    recommendations = []
    issues = []

    # Check if dashboard exists
    if not dashboard_dir.exists():
        return DiagnosticResult(
            name="node_modules Health",
            status=Status.WARNING,
            message="Dashboard directory not found",
            details={"dashboard_path": str(dashboard_dir)},
            recommendations=["Ensure dashboard directory exists"],
        )

    # Check package.json
    if not package_json.exists():
        return DiagnosticResult(
            name="node_modules Health",
            status=Status.ERROR,
            message="package.json not found in dashboard",
            details={"dashboard_path": str(dashboard_dir)},
            recommendations=["Initialize npm project: cd dashboard && npm init"],
        )

    details["package_json_exists"] = True
    details["package_lock_exists"] = package_lock.exists()

    # Check if node_modules exists
    if not node_modules.exists():
        return DiagnosticResult(
            name="node_modules Health",
            status=Status.WARNING,
            message="node_modules not found - dependencies not installed",
            details=details,
            recommendations=["Install dependencies: cd dashboard && npm install"],
        )

    # Check for broken symlinks
    broken_symlinks = []
    try:
        for item in node_modules.rglob("*"):
            if item.is_symlink() and not item.exists():
                broken_symlinks.append(str(item.relative_to(node_modules)))
                if len(broken_symlinks) >= 10:
                    break
    except Exception as e:
        details["symlink_check_error"] = str(e)

    if broken_symlinks:
        issues.append("broken symlinks")
        details["broken_symlinks"] = broken_symlinks[:10]
        details["broken_symlinks_count"] = len(broken_symlinks)
        recommendations.append("Fix broken symlinks: cd dashboard && rm -rf node_modules && npm install")

    # Check for .package-lock.json integrity
    if package_lock.exists():
        success, stdout, stderr = run_command(
            ["npm", "ls", "--json"],
            timeout=60,
        )
        # cd to dashboard for npm ls
        old_cwd = os.getcwd()
        try:
            os.chdir(dashboard_dir)
            success, stdout, stderr = run_command(["npm", "ls", "--json"], timeout=60)
            if not success:
                # Parse the JSON output to find issues
                try:
                    npm_ls = json.loads(stdout) if stdout else {}
                    problems = npm_ls.get("problems", [])
                    if problems:
                        issues.append("missing packages")
                        details["missing_packages"] = problems[:5]
                        recommendations.append(
                            "Fix missing packages: cd dashboard && npm install"
                        )
                except json.JSONDecodeError:
                    if "ELOCKVERIFY" in stderr or "ENOENT" in stderr:
                        issues.append("lock file mismatch")
                        recommendations.append(
                            "Regenerate lock file: cd dashboard && rm package-lock.json && npm install"
                        )
        finally:
            os.chdir(old_cwd)

    # Check node_modules size
    try:
        size_bytes = sum(
            f.stat().st_size for f in node_modules.rglob("*") if f.is_file()
        )
        size_mb = size_bytes / (1024 * 1024)
        details["size_mb"] = round(size_mb, 2)

        if size_mb > 1000:
            issues.append("unusually large")
            recommendations.append(
                "node_modules is very large (>1GB). Consider: npm dedupe"
            )
    except Exception as e:
        details["size_check_error"] = str(e)

    # Determine status
    if issues:
        status = Status.WARNING if "broken" not in str(issues) else Status.ERROR
        message = f"node_modules issues: {', '.join(issues)}"
    else:
        status = Status.OK
        message = "node_modules appears healthy"

    return DiagnosticResult(
        name="node_modules Health",
        status=status,
        message=message,
        details=details,
        recommendations=recommendations,
    )


def check_npm_cache() -> DiagnosticResult:
    """Check npm cache health and size."""
    details = {}
    recommendations = []

    # Check if npm is available
    npm_path = shutil.which("npm")
    if not npm_path:
        return DiagnosticResult(
            name="npm Cache",
            status=Status.ERROR,
            message="npm not found in PATH",
            recommendations=["Install Node.js and npm"],
        )

    # Get cache location
    success, cache_path, _ = run_command(["npm", "config", "get", "cache"])
    if success and cache_path:
        details["cache_path"] = cache_path

        cache_dir = Path(cache_path)
        if cache_dir.exists():
            # Get cache size
            try:
                size_bytes = sum(
                    f.stat().st_size for f in cache_dir.rglob("*") if f.is_file()
                )
                size_mb = size_bytes / (1024 * 1024)
                details["size_mb"] = round(size_mb, 2)

                if size_mb > 5000:
                    recommendations.append(
                        f"Cache is large ({size_mb:.0f}MB). Consider: npm cache clean --force"
                    )
            except Exception as e:
                details["size_check_error"] = str(e)

    # Verify cache integrity
    success, stdout, stderr = run_command(["npm", "cache", "verify"], timeout=120)

    if success:
        # Parse verify output
        details["verify_output"] = stdout[:500] if stdout else "OK"

        # Check for corruption indicators
        if "corrupted" in stdout.lower() or "error" in stdout.lower():
            return DiagnosticResult(
                name="npm Cache",
                status=Status.WARNING,
                message="npm cache may have issues",
                details=details,
                recommendations=["Clean npm cache: npm cache clean --force"],
            )

        return DiagnosticResult(
            name="npm Cache",
            status=Status.OK,
            message="npm cache is healthy",
            details=details,
            recommendations=recommendations,
        )
    else:
        details["verify_error"] = stderr[:200] if stderr else "unknown error"
        return DiagnosticResult(
            name="npm Cache",
            status=Status.WARNING,
            message="npm cache verify failed",
            details=details,
            recommendations=["Clean npm cache: npm cache clean --force"],
        )


def check_git_state() -> DiagnosticResult:
    """Check git repository state for potential issues."""
    details = {}
    recommendations = []
    issues = []

    # Check if we're in a git repo
    success, _, _ = run_command(["git", "rev-parse", "--is-inside-work-tree"])
    if not success:
        return DiagnosticResult(
            name="Git State",
            status=Status.ERROR,
            message="Not inside a git repository",
            recommendations=["Initialize git: git init"],
        )

    # Check for detached HEAD
    success, head_ref, _ = run_command(["git", "symbolic-ref", "HEAD"])
    if not success:
        issues.append("detached HEAD")
        # Get the current commit
        _, commit, _ = run_command(["git", "rev-parse", "--short", "HEAD"])
        details["detached_head"] = True
        details["current_commit"] = commit
        recommendations.append("Attach to a branch: git checkout <branch-name>")
    else:
        details["current_branch"] = head_ref.replace("refs/heads/", "")

    # Check for uncommitted changes
    success, status_output, _ = run_command(["git", "status", "--porcelain"])
    if status_output:
        lines = status_output.strip().split("\n")
        details["uncommitted_changes"] = len(lines)

        # Categorize changes
        modified = [l for l in lines if l.startswith(" M") or l.startswith("M ")]
        added = [l for l in lines if l.startswith("A ") or l.startswith("??")]
        deleted = [l for l in lines if l.startswith(" D") or l.startswith("D ")]

        details["modified_files"] = len(modified)
        details["untracked_files"] = len([l for l in lines if l.startswith("??")])
        details["deleted_files"] = len(deleted)

        if len(lines) > 20:
            issues.append("many uncommitted changes")
            recommendations.append(
                "Consider committing or stashing changes: git stash or git commit"
            )
        else:
            issues.append("uncommitted changes")

    # Check for merge conflicts
    success, conflicts, _ = run_command(
        ["git", "diff", "--name-only", "--diff-filter=U"]
    )
    if conflicts:
        conflict_files = conflicts.strip().split("\n")
        issues.append("merge conflicts")
        details["conflict_files"] = conflict_files
        recommendations.append(
            f"Resolve merge conflicts in: {', '.join(conflict_files[:5])}"
        )

    # Check for stashed changes
    success, stash_list, _ = run_command(["git", "stash", "list"])
    if stash_list:
        stash_count = len(stash_list.strip().split("\n"))
        details["stashed_changes"] = stash_count
        if stash_count > 5:
            recommendations.append(
                f"You have {stash_count} stashed changes. Consider: git stash drop"
            )

    # Check if behind remote
    success, _, _ = run_command(["git", "fetch", "--dry-run"])
    success, behind, _ = run_command(
        ["git", "rev-list", "--count", "HEAD..@{upstream}"]
    )
    if success and behind and behind != "0":
        details["commits_behind"] = int(behind)
        issues.append(f"behind remote by {behind} commits")
        recommendations.append("Pull latest changes: git pull")

    # Check ahead of remote
    success, ahead, _ = run_command(
        ["git", "rev-list", "--count", "@{upstream}..HEAD"]
    )
    if success and ahead and ahead != "0":
        details["commits_ahead"] = int(ahead)
        # This is just informational, not an issue

    # Determine status
    if "merge conflicts" in issues:
        status = Status.ERROR
    elif issues:
        status = Status.WARNING
    else:
        status = Status.OK

    if issues:
        message = f"Git state issues: {', '.join(issues)}"
    else:
        message = "Git state is clean"

    return DiagnosticResult(
        name="Git State",
        status=status,
        message=message,
        details=details,
        recommendations=recommendations,
    )


def run_diagnostics() -> DiagnosticsReport:
    """
    Run all diagnostic checks and return a structured report.

    This is the main entry point for programmatic usage.

    Returns:
        DiagnosticsReport with all check results and recommendations.
    """
    checks = [
        check_ports(),
        check_node_modules(),
        check_npm_cache(),
        check_git_state(),
    ]

    # Calculate summary
    summary = {
        "ok": sum(1 for c in checks if c.status == Status.OK),
        "warning": sum(1 for c in checks if c.status == Status.WARNING),
        "error": sum(1 for c in checks if c.status == Status.ERROR),
        "total": len(checks),
    }

    # Determine overall status
    if summary["error"] > 0:
        overall_status = Status.ERROR
    elif summary["warning"] > 0:
        overall_status = Status.WARNING
    else:
        overall_status = Status.OK

    return DiagnosticsReport(
        summary=summary,
        checks=checks,
        overall_status=overall_status,
    )


def print_report(report: DiagnosticsReport) -> None:
    """Print the diagnostics report in human-readable format."""
    print("=" * 70)
    print("  SELF-DIAGNOSTICS REPORT")
    print("=" * 70)
    print()

    # Status symbols
    status_symbols = {
        Status.OK: "\033[92m[OK]\033[0m",      # Green
        Status.WARNING: "\033[93m[WARN]\033[0m",  # Yellow
        Status.ERROR: "\033[91m[ERROR]\033[0m",   # Red
    }

    for check in report.checks:
        symbol = status_symbols[check.status]
        print(f"{symbol} {check.name}")
        print(f"    {check.message}")

        if check.details:
            for key, value in check.details.items():
                if isinstance(value, list):
                    print(f"    - {key}: {len(value)} items")
                elif isinstance(value, dict):
                    print(f"    - {key}: {json.dumps(value, default=str)[:60]}...")
                else:
                    print(f"    - {key}: {value}")

        if check.recommendations:
            print("    Recommendations:")
            for rec in check.recommendations:
                print(f"      -> {rec}")
        print()

    # Summary
    print("-" * 70)
    print(f"  Summary: {report.summary['ok']} OK, "
          f"{report.summary['warning']} warnings, "
          f"{report.summary['error']} errors")
    print(f"  Overall Status: {status_symbols[report.overall_status]}")
    print("-" * 70)

    # All recommendations
    all_recs = []
    for check in report.checks:
        all_recs.extend(check.recommendations)

    if all_recs:
        print("\n  All Recommendations:")
        for i, rec in enumerate(all_recs, 1):
            print(f"    {i}. {rec}")
    else:
        print("\n  No issues found. Environment is healthy.")


def main() -> int:
    """CLI entry point for self-diagnostics."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Self-diagnostics tool for development environment health checks"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    parser.add_argument(
        "--check",
        choices=["ports", "node_modules", "npm_cache", "git"],
        help="Run only a specific check",
    )

    args = parser.parse_args()

    # Run diagnostics
    if args.check:
        check_map = {
            "ports": check_ports,
            "node_modules": check_node_modules,
            "npm_cache": check_npm_cache,
            "git": check_git_state,
        }
        result = check_map[args.check]()

        if args.json:
            print(json.dumps({
                "name": result.name,
                "status": result.status.value,
                "message": result.message,
                "details": result.details,
                "recommendations": result.recommendations,
            }, indent=2))
        else:
            print(f"{result.status.value}: {result.name}")
            print(f"  {result.message}")
            for rec in result.recommendations:
                print(f"  -> {rec}")

        return 0 if result.status == Status.OK else 1

    report = run_diagnostics()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report)

    # Return exit code based on overall status
    if report.overall_status == Status.ERROR:
        return 2
    elif report.overall_status == Status.WARNING:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
