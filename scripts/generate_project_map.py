#!/usr/bin/env python3
"""
Project Map Generator (ENG-33)
==============================

Generates .agent/PROJECT_MAP.md with:
- Directory structure with file counts
- Key files and their purposes
- Dependencies and versions
- Ports and URLs
- Recent 5 commits
- Import dependency graph

Run manually or via git post-commit hook:
    python scripts/generate_project_map.py [project_dir]
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


# Configuration
IGNORE_DIRS = {
    "node_modules",
    ".git",
    "dist",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "build",
    "coverage",
    ".next",
    ".nuxt",
}

IGNORE_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "*.pyc",
    "*.pyo",
    ".env",
}

# Key file patterns to highlight
KEY_FILE_PATTERNS = {
    "entry_points": [
        "main.py",
        "agent.py",
        "app.py",
        "server.py",
        "index.js",
        "index.ts",
        "index.tsx",
        "App.jsx",
        "App.tsx",
    ],
    "configs": [
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "tsconfig.json",
        "vite.config.js",
        "tailwind.config.js",
        ".env.example",
        "Makefile",
        "pytest.ini",
    ],
    "documentation": [
        "README.md",
        "CLAUDE.md",
        "LICENSE",
    ],
}


def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[str, int]:
    """Run a shell command and return output + exit code."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", 1
    except FileNotFoundError:
        return "", 1


def get_directory_tree(project_dir: Path, max_depth: int = 3) -> str:
    """Generate directory tree with file counts."""
    lines = []
    file_counts: dict[str, int] = {}

    def count_files(path: Path) -> int:
        """Count files in a directory."""
        count = 0
        try:
            for item in path.iterdir():
                if item.name in IGNORE_DIRS or item.name.startswith("."):
                    continue
                if item.is_file():
                    count += 1
                elif item.is_dir():
                    count += count_files(item)
        except PermissionError:
            pass
        return count

    def walk_dir(path: Path, prefix: str = "", depth: int = 0):
        """Walk directory and build tree."""
        if depth > max_depth:
            return

        try:
            items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return

        # Filter items
        dirs = []
        files = []
        for item in items:
            if item.name in IGNORE_DIRS:
                continue
            if item.name.startswith(".") and item.name not in (".agent", ".github"):
                continue
            if item.is_dir():
                dirs.append(item)
            elif item.is_file() and item.name not in IGNORE_FILES:
                files.append(item)

        # Process directories
        for i, dir_item in enumerate(dirs):
            is_last = i == len(dirs) - 1 and not files
            connector = "└── " if is_last else "├── "
            file_count = count_files(dir_item)
            file_counts[str(dir_item.relative_to(project_dir))] = file_count

            count_suffix = f" ({file_count} files)" if file_count > 0 else ""
            lines.append(f"{prefix}{connector}{dir_item.name}/{count_suffix}")

            extension = "    " if is_last else "│   "
            walk_dir(dir_item, prefix + extension, depth + 1)

        # Show file count summary for shallow dirs (depth 0)
        if depth == 0 and files:
            file_summary = f"├── [{len(files)} files in root]"
            lines.append(file_summary)

    lines.append(f"{project_dir.name}/")
    walk_dir(project_dir)

    return "\n".join(lines)


def get_key_files(project_dir: Path) -> dict[str, list[str]]:
    """Find key files in the project."""
    found: dict[str, list[str]] = {
        "entry_points": [],
        "configs": [],
        "documentation": [],
    }

    for category, patterns in KEY_FILE_PATTERNS.items():
        for pattern in patterns:
            # Search in root
            root_file = project_dir / pattern
            if root_file.exists():
                found[category].append(pattern)

            # Search in common subdirs
            for subdir in ["src", "dashboard", "dashboard/src", "agent", "agents"]:
                subdir_file = project_dir / subdir / pattern
                if subdir_file.exists():
                    found[category].append(f"{subdir}/{pattern}")

    return found


def parse_dependencies(project_dir: Path) -> dict[str, dict]:
    """Parse dependencies from package.json and requirements.txt."""
    deps = {"python": {}, "node": {}, "dev": {}}

    # Python dependencies
    req_file = project_dir / "requirements.txt"
    if req_file.exists():
        content = req_file.read_text()
        for line in content.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                # Parse package==version format
                if "==" in line:
                    name, version = line.split("==", 1)
                    deps["python"][name.strip()] = version.strip()
                elif ">=" in line:
                    name, version = line.split(">=", 1)
                    deps["python"][name.strip()] = f">={version.strip()}"

    # Node dependencies
    pkg_file = project_dir / "package.json"
    if not pkg_file.exists():
        pkg_file = project_dir / "dashboard" / "package.json"

    if pkg_file.exists():
        try:
            pkg_data = json.loads(pkg_file.read_text())
            deps["node"] = pkg_data.get("dependencies", {})
            deps["dev"] = pkg_data.get("devDependencies", {})
        except json.JSONDecodeError:
            pass

    return deps


def find_ports_and_urls(project_dir: Path) -> list[tuple[str, str]]:
    """Find port configurations and localhost URLs."""
    ports_found: list[tuple[str, str]] = []

    # Common patterns to search
    patterns = [
        (r"PORT\s*[=:]\s*[\"']?(\d{4,5})[\"']?", "Port config"),
        (r"localhost:(\d{4,5})", "localhost URL"),
        (r"127\.0\.0\.1:(\d{4,5})", "localhost URL"),
        (r":(\d{4,5})/", "URL path"),
    ]

    # Files to search
    search_files = [
        ".env.example",
        ".env",
        "vite.config.js",
        "vite.config.ts",
        "package.json",
        "docker-compose.yml",
        "docker-compose.yaml",
    ]

    seen_ports: set[str] = set()

    for filename in search_files:
        filepath = project_dir / filename
        if not filepath.exists():
            # Check in dashboard too
            filepath = project_dir / "dashboard" / filename
        if not filepath.exists():
            continue

        try:
            content = filepath.read_text()
            for pattern, desc in patterns:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    port = match.group(1)
                    if port not in seen_ports:
                        seen_ports.add(port)
                        ports_found.append((port, f"{filename}"))
        except (IOError, UnicodeDecodeError):
            pass

    # Also check MEMORY.md for documented ports
    memory_file = project_dir / ".agent" / "MEMORY.md"
    if memory_file.exists():
        try:
            content = memory_file.read_text()
            # Look for port documentation
            for match in re.finditer(r"(\d{4,5}):\s*([^\n]+)", content):
                port, desc = match.groups()
                if port not in seen_ports and len(port) >= 4:
                    seen_ports.add(port)
                    ports_found.append((port, desc.strip()))
        except IOError:
            pass

    return sorted(ports_found, key=lambda x: int(x[0]))


def get_recent_commits(project_dir: Path, count: int = 5) -> list[dict]:
    """Get recent git commits."""
    cmd = ["git", "log", f"-{count}", "--pretty=format:%h|%s|%ar|%an"]
    output, code = run_command(cmd, cwd=project_dir)

    if code != 0 or not output:
        return []

    commits = []
    for line in output.strip().split("\n"):
        if "|" in line:
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "time": parts[2],
                    "author": parts[3],
                })

    return commits


def analyze_imports(project_dir: Path) -> dict[str, list[str]]:
    """Analyze import dependencies to find hub files."""
    imports: dict[str, list[str]] = defaultdict(list)
    imported_by: dict[str, list[str]] = defaultdict(list)

    # Python imports
    for py_file in project_dir.glob("**/*.py"):
        if any(part in IGNORE_DIRS for part in py_file.parts):
            continue

        try:
            content = py_file.read_text()
            rel_path = str(py_file.relative_to(project_dir))

            # Find imports
            for match in re.finditer(r"^(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_]*)", content, re.MULTILINE):
                module = match.group(1)
                # Check if it's a local module
                local_module = project_dir / f"{module}.py"
                if local_module.exists():
                    imports[rel_path].append(f"{module}.py")
                    imported_by[f"{module}.py"].append(rel_path)
        except (IOError, UnicodeDecodeError):
            pass

    # JavaScript/TypeScript imports
    for ext in ["*.js", "*.jsx", "*.ts", "*.tsx"]:
        for js_file in project_dir.glob(f"**/{ext}"):
            if any(part in IGNORE_DIRS for part in js_file.parts):
                continue

            try:
                content = js_file.read_text()
                rel_path = str(js_file.relative_to(project_dir))

                # Find imports
                for match in re.finditer(r"(?:import|from)\s+['\"]\.?\.?/?([^'\"]+)['\"]", content):
                    imported = match.group(1)
                    if not imported.startswith("."):
                        continue  # Skip npm packages
                    imports[rel_path].append(imported)
            except (IOError, UnicodeDecodeError):
                pass

    return dict(imported_by)


def find_hub_files(imported_by: dict[str, list[str]], threshold: int = 3) -> list[tuple[str, int]]:
    """Find files that are imported by many other files (hub files)."""
    hubs = []
    for file, importers in imported_by.items():
        if len(importers) >= threshold:
            hubs.append((file, len(importers)))

    return sorted(hubs, key=lambda x: -x[1])


def generate_project_map(project_dir: Path) -> str:
    """Generate the complete project map markdown."""
    lines = [
        "# Project Map",
        "",
        f"*Auto-generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "> This file is automatically updated after each commit.",
        "> Coding Agent reads this at session start for project context.",
        "",
        "---",
        "",
    ]

    # 1. Directory Structure
    lines.append("## Directory Structure")
    lines.append("")
    lines.append("```")
    lines.append(get_directory_tree(project_dir))
    lines.append("```")
    lines.append("")

    # 2. Key Files
    lines.append("## Key Files")
    lines.append("")
    key_files = get_key_files(project_dir)

    if key_files["entry_points"]:
        lines.append("### Entry Points")
        for f in key_files["entry_points"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if key_files["configs"]:
        lines.append("### Configuration")
        for f in key_files["configs"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if key_files["documentation"]:
        lines.append("### Documentation")
        for f in key_files["documentation"]:
            lines.append(f"- `{f}`")
        lines.append("")

    # 3. Dependencies
    lines.append("## Dependencies")
    lines.append("")
    deps = parse_dependencies(project_dir)

    if deps["python"]:
        lines.append("### Python (requirements.txt)")
        lines.append("")
        # Show key dependencies only
        key_python_deps = ["claude-agent-sdk", "httpx", "pydantic", "uvicorn", "mcp"]
        for dep in key_python_deps:
            if dep in deps["python"]:
                lines.append(f"- {dep}=={deps['python'][dep]}")
        if len(deps["python"]) > len(key_python_deps):
            lines.append(f"- *... and {len(deps['python']) - len(key_python_deps)} more*")
        lines.append("")

    if deps["node"]:
        lines.append("### Node.js (package.json)")
        lines.append("")
        for dep, version in list(deps["node"].items())[:8]:
            lines.append(f"- {dep}: {version}")
        if len(deps["node"]) > 8:
            lines.append(f"- *... and {len(deps['node']) - 8} more*")
        lines.append("")

    # 4. Ports and URLs
    lines.append("## Ports and URLs")
    lines.append("")
    ports = find_ports_and_urls(project_dir)
    if ports:
        lines.append("| Port | Description |")
        lines.append("|------|-------------|")
        for port, desc in ports:
            lines.append(f"| {port} | {desc} |")
        lines.append("")
    else:
        lines.append("*No port configurations found*")
        lines.append("")

    # 5. Recent Commits
    lines.append("## Recent Commits")
    lines.append("")
    commits = get_recent_commits(project_dir)
    if commits:
        for commit in commits:
            lines.append(f"- `{commit['hash']}` {commit['message']} ({commit['time']})")
        lines.append("")
    else:
        lines.append("*No git history found*")
        lines.append("")

    # 6. Import Graph (Hub Files)
    lines.append("## Import Graph (Hub Files)")
    lines.append("")
    lines.append("> Files imported by 3+ other files. Changes here are high-risk.")
    lines.append("")

    imported_by = analyze_imports(project_dir)
    hubs = find_hub_files(imported_by)

    if hubs:
        lines.append("| File | Imported By |")
        lines.append("|------|-------------|")
        for file, count in hubs[:10]:  # Top 10 hubs
            lines.append(f"| `{file}` | {count} files |")
        lines.append("")
    else:
        lines.append("*No hub files detected (all files have <3 importers)*")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("*Generated by `scripts/generate_project_map.py`*")
    lines.append("")

    return "\n".join(lines)


def main():
    """Main entry point."""
    # Get project directory from args or current directory
    if len(sys.argv) > 1:
        project_dir = Path(sys.argv[1]).resolve()
    else:
        project_dir = Path.cwd()

    if not project_dir.is_dir():
        print(f"Ошибка: {project_dir} не является директорией")
        sys.exit(1)

    # Ensure .agent directory exists
    agent_dir = project_dir / ".agent"
    agent_dir.mkdir(exist_ok=True)

    # Generate the map
    print(f"Генерация карты проекта для: {project_dir}")
    map_content = generate_project_map(project_dir)

    # Write to .agent/PROJECT_MAP.md
    map_file = agent_dir / "PROJECT_MAP.md"
    map_file.write_text(map_content)

    print(f"Карта проекта записана в: {map_file}")
    print(f"Размер: {len(map_content)} байт")

    return 0


if __name__ == "__main__":
    sys.exit(main())
