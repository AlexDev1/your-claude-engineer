Execute next task for team: {team}
Working directory: {cwd}

## Flow

### 1. Get Task
task agent: "List Todo issues for {team}, return highest priority (urgent>high>medium>low)"

If no Todo: telegram ":tada: All tasks complete!" then output `ALL_TASKS_DONE:` and stop.

### 2. Start
task agent: Transition to In Progress
telegram: ":construction: Starting: [title] ([id])"

### 3. Implement
coding agent with FULL context:
- ID, Title, Description, Test Steps
- Requirements: read code, implement, Playwright test, screenshot

**If COMPACT MODE active (70%+ context):**
- Use only: ID + Title + 1-line description
- Skip detailed requirements
- Pass minimal context to coding agent

### 4. Commit
coding agent: Commit with task ID

### 5. Done
task agent: Mark Done with files/screenshots/results

### 6. Notify
telegram: ":white_check_mark: Completed: [title]"

### 7. Memory
coding agent: Update .agent/MEMORY.md
task agent: Add session summary to META issue

## Rules
- No Done without screenshots
- Pass FULL context to coding agent (unless COMPACT MODE)
- One issue per session
- Memory flush before ending
- If 85%+ context used: output `CONTEXT_LIMIT_REACHED:` for graceful shutdown
