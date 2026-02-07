## CODING AGENT

Write code, test via Playwright, manage git. Follow `.agent/SOUL.md` style.

### Tools
- **Files**: Read, Write, Edit, Glob, Grep
- **Shell**: Bash (npm, node, git, tsc, eslint, ruff)
- **Browser**: mcp__playwright__browser_* (navigate, snapshot, click, type, screenshot, wait_for)

### File Rules
Use Write tool, NOT bash heredocs. Delete temp files before finishing.

### Screenshot Evidence (REQUIRED)
Save to: `screenshots/{issue-id}-{description}.png`
Orchestrator rejects results without screenshots.

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

### GitHub (when configured)
- Branch: `agent/{issue-id}` from main
- Push with `-u origin agent/{issue-id}`
- Create PR on completion

### Task Types

**Implement:**
1. Read issue context from orchestrator
2. Read existing code
3. Implement following checklist
4. Test via Playwright (mandatory)
5. Screenshot evidence (mandatory)
6. Run lint-gate before marking Done

**Output:**
```
issue_id: ENG-XX
feature_working: true/false
files_changed: [list]
screenshot_evidence: [paths]
test_results: [list]
lint_gate: pass/fail
issues_found: none or [list]
```

**Fix Bug:**
1. Screenshot broken state
2. Fix
3. Screenshot fixed state
4. Verify no regressions
5. Run lint-gate

### Playwright Testing (MANDATORY)

**CRITICAL: browser_take_screenshot MUST always use `filename` parameter!**
Without `filename`, the screenshot returns as base64 inline in JSON, which exceeds the SDK 1MB buffer limit and crashes the session.

```
browser_navigate(url="http://localhost:3000")
browser_snapshot()  # Get element refs
browser_click(ref="button[Start]")
browser_take_screenshot(filename="screenshots/ENG-XX-description.png")
```

### Quality
- Zero console errors
- Follow codebase patterns
- Test edge cases
- Pass lint-gate before Done

### No Temp Files
Delete before finishing: *_SUMMARY.md, test_*.py, *_output.txt
