Execute next task for team: {team}
Working directory: {cwd}

## CONTINUATION MODE

### 0. Load Previous Context
task agent: Get META issue comments, find latest "Session Summary"
Return: what was done, failures, files, next step, context

Use to: resume work, skip analyzed files, avoid failed approaches.

## Flow

### 1. Get Task
task agent: List Todo and In Progress for {team}
- If In Progress: resume it
- Else: highest priority Todo

If no Todo/In Progress: telegram ":tada: All complete!" then `ALL_TASKS_DONE:` and stop.

### 2. Start
task agent: Transition to In Progress (if needed)
telegram: ":construction: Starting: [title]" or ":repeat: Resuming: [title]"

### 3. Implement
coding agent with FULL context + previous context:
- ID, Title, Description, Test Steps
- Previous Context (if resuming)

### 4. Commit
coding agent: Commit with task ID

### 5. Done
task agent: Mark Done with files/screenshots

### 6. Notify
telegram: ":white_check_mark: Completed: [title]"

### 7. Memory
coding agent: Update .agent/MEMORY.md
task agent: Session summary to META issue

## Rules
- Check previous context first
- No Done without screenshots
- One issue per session
- Memory flush before ending
