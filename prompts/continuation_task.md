Execute next task for team: {team}
Working directory: {cwd}
Project filter: {project}

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
task agent: List Todo and In Progress for {team} with project={project}, limit=10
- If In Progress: resume it (check if context-limit interrupted)
- Else: highest priority Todo
**IMPORTANT: Always use project={project} and limit=10 in Task_ListIssues.**

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

### 4b. Code Review Gate (ENG-42)
See orchestrator_prompt.md "Review Gate" section for full rules.
- Auto-approve: docs-only, config-only, or <20 lines
- Otherwise: reviewer agent checks diff, max 2 review cycles

### 5. Done
task agent: Mark Done with files/screenshots

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
- **NEVER create projects** (Task_CreateProject is FORBIDDEN). Work only in project={project}
- All new tasks (subtasks from decomposition) MUST use project={project}
