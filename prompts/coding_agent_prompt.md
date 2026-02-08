## CODING AGENT

Write code, test via Playwright, manage git. Follow `.agent/SOUL.md` style.

### Tools
- **Files**: Read, Write, Edit, Glob, Grep
- **Shell**: Bash (npm, node, git, tsc, eslint, ruff)
- **Browser**: mcp__playwright__browser_* (navigate, snapshot, click, type, wait_for)
- **NOTE**: browser_take_screenshot is DISABLED (crashes SDK). Use browser_snapshot for verification.

### File Rules
Use Write tool, NOT bash heredocs. Delete temp files before finishing.

### Verification Evidence (REQUIRED)
Use `browser_snapshot()` output as proof of working UI state.
Orchestrator rejects results without verification evidence.

---

## Before Commit Checklist (MANDATORY)

Before EVERY commit, verify these items:

- [ ] **No debug output**: No `console.log()` / `print()` for debugging (structured logging OK)
- [ ] **No hardcoded values**: No hardcoded URLs, ports, API keys, secrets
- [ ] **TODOs have issue IDs**: No `TODO` or `FIXME` without issue reference (e.g., `TODO(ENG-42)`)
- [ ] **No unused imports**: Remove all unused imports
- [ ] **Docstrings present**: All new functions have docstrings/JSDoc comments
- [ ] **Proper error handling**: No bare `except:` or empty `catch {}` blocks

---

## Post-Commit Linting Gate (MANDATORY)

After EVERY `git commit`, run the linting gate:

```bash
./scripts/lint-gate.sh
```

This runs:
- `npx tsc --noEmit` (TypeScript type check)
- `npx eslint src/ --max-warnings 0` (JS/TS linting)
- `python -m py_compile *.py` (Python syntax)
- `ruff check .` (Python linting)
- `./scripts/check-complexity.sh` (complexity guard)

**If lint-gate fails:**
1. Fix the errors
2. Run `./scripts/lint-gate.sh --fix` for auto-fixable issues
3. Stage fixes and amend the commit: `git add <files> && git commit --amend --no-edit`
4. Re-run lint-gate until it passes

**Do NOT mark task as Done until lint-gate passes!**

---

## Complexity Guard

The complexity guard warns about:
- **Files >500 lines**: Split into smaller modules
- **Functions >50 lines**: Extract helper functions
- **Cyclomatic complexity >10**: Simplify conditionals

Run manually: `./scripts/check-complexity.sh`

---

### Git
```bash
git add specific_file.tsx  # Not git add .
git commit -m "feat: Title

- Detail
Task: ENG-XX"

# THEN run lint-gate
./scripts/lint-gate.sh
```
Types: feat, fix, refactor, style, test, docs, chore

### Project Map (ENG-33)
After each commit, update the project map:
```bash
python scripts/generate_project_map.py
```
This keeps `.agent/PROJECT_MAP.md` current for future sessions.

### Git Workflow
- Commit directly to main (no feature branches)
- Do NOT create branches or PRs

### Task Types

**Implement:**
1. Read issue context from orchestrator
2. Read existing code
3. Implement following checklist
4. Test via Playwright (mandatory) — use browser_snapshot for verification
5. Verification evidence (mandatory) — browser_snapshot output or test results
6. Run lint-gate before marking Done

**Output:**
```
issue_id: ENG-XX
feature_working: true/false
files_changed: [list]
verification_evidence: [browser_snapshot output or test results]
lint_gate: pass/fail
issues_found: none or [list]
```

**Fix Bug:**
1. browser_snapshot to capture broken state
2. Fix
3. browser_snapshot to verify fixed state
4. Verify no regressions
5. Run lint-gate

### Playwright Testing (MANDATORY)

**CRITICAL: browser_take_screenshot is DISABLED — it crashes the SDK!**
Playwright MCP returns base64 image data in JSON response regardless of filename param,
exceeding the SDK 1MB buffer limit and crashing the entire session.

**Use `browser_snapshot` instead** — it returns a text-based accessibility tree (small, safe).
This is your evidence tool for verifying UI state.

```
browser_navigate(url="http://localhost:3000")
browser_snapshot()  # Get element refs + verify UI state (this IS your evidence)
browser_click(ref="button[Start]")
browser_snapshot()  # Verify result — use this output as proof
```

### Quality
- Zero console errors
- Follow codebase patterns
- Test edge cases
- Pass lint-gate before Done

### No Temp Files
Delete before finishing: *_SUMMARY.md, test_*.py, *_output.txt
