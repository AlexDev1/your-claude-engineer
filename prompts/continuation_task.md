Execute next task for team: {team}
Working directory: {cwd}

## CONTINUATION MODE

### 0. Load Previous Context
task agent: Get META issue comments, find latest "Session Summary"
Return: what was done, failures, files, next step, context

Use to: resume work, skip analyzed files, avoid failed approaches.

### 0.1 Check for Interrupted Session (ENG-29)
Check .agent/MEMORY.md for "Context Limit Shutdown" entry.
If found:
- Note the interrupted issue ID and step
- Resume from that exact step, don't restart from zero
- The previous work is still valid, just continue

## Flow

### 1. Get Task
task agent: List Todo and In Progress for {team}
- If In Progress: resume it (check if context-limit interrupted)
- Else: highest priority Todo

If no Todo/In Progress: telegram ":tada: All complete!" then `ALL_TASKS_DONE:` and stop.

### 1.5 Check for Epic (ENG-27)

After getting task, check if it's an Epic (decomposed task):
- Look for comment starting with "Epic: This task has been decomposed"
- If found, extract subtask IDs from the comment

**If Task is Epic:**
1. List all subtask IDs from Epic comment
2. Check status of each subtask via task agent
3. Find first subtask that is NOT Done
4. If all subtasks Done:
   - Mark Epic as Done
   - telegram: ":white_check_mark: Epic completed: [title]"
   - Return to Step 1 for next task
5. If incomplete subtask found:
   - Report Epic progress: "Epic [id]: 3/5 subtasks done"
   - Continue with incomplete subtask as current task

**If Task is NOT Epic:**
- Check if Large task (see evaluate_task.md Step 1.5)
- If Large and not yet decomposed: decompose it
- Otherwise: continue normally

### 2. Start
task agent: Transition to In Progress (if needed)
telegram: ":construction: Starting: [title]" or ":repeat: Resuming: [title]"

### 3. Implement
coding agent with FULL context + previous context:
- ID, Title, Description, Test Steps
- Previous Context (if resuming)
- Interrupted step (if context-limit recovery)

**If COMPACT MODE active (70%+ context):**
- Use only: ID + Title + 1-line description
- Skip META issue history lookup
- Pass minimal context to coding agent

### 4. Commit
coding agent: Commit with task ID

<<<<<<< HEAD
### 5. Done
task agent: Mark Done with files/screenshots
=======
### Step 4b: Code Review Gate
Before committing, run an automated code review.

**Auto-approve check** (skip reviewer if ALL true):
- Only .md or documentation files changed
- OR only config files changed (package.json, .env.example, tsconfig.json, .gitignore)
- OR diff is less than 20 lines of actual code changes

**If auto-approve does NOT apply:**

1. Delegate to `coding` agent:
   "Run `git diff` and return the full output. Also run `git diff --stat` for a summary."

2. Delegate to `reviewer` agent with the diff:
   "Review this diff for security issues, code quality, and best practices:
   [paste the diff output from coding agent]

   Check for: hardcoded secrets, SQL injection, unused imports, missing error handling,
   debug print statements, TODO without issue ID, missing type hints/docstrings."

3. **If verdict is APPROVE**: Proceed to Step 5 (commit)

4. **If verdict is REQUEST_CHANGES**:
   - Pass the reviewer's issues to `coding` agent:
     "Fix these code review issues:
     [paste reviewer's issues list with file, line, and suggestion]
     Then run `git diff` again and return the updated diff."
   - Send the updated diff to `reviewer` agent for a second review
   - If APPROVE on second review: Proceed to Step 5
   - If still REQUEST_CHANGES after 2 review cycles: Proceed to Step 5 anyway,
     but include the unresolved findings in the issue comment (Step 6)

### Step 5: Commit
Delegate to `coding` agent:
"Commit changes for [issue title]. Include task ID in commit message."
>>>>>>> agent/ENG-66

### 6. Notify
telegram: ":white_check_mark: Completed: [title]"

### 7. Memory
coding agent: Update .agent/MEMORY.md
task agent: Session summary to META issue

## Context Limit Recovery (ENG-29)

If session was interrupted by context limit:
1. Check MEMORY.md for "Context Limit Shutdown" note
2. Find the interrupted_at step
3. Resume from that step (don't re-do completed work)
4. The issue is likely still In Progress

Example MEMORY.md entry:
```
### Context Limit Shutdown (2024-01-15T10:30:00)
- Issue: ENG-29
- Interrupted at: step_implement
- Resume from step: implement
```

## Rules
- Check previous context first
- Check for context-limit interruption
- No Done without screenshots
- One issue per session
- Memory flush before ending
- In COMPACT MODE: minimal context only
