Execute next task for team: {team}
Working directory: {cwd}

## Flow

### 1. Get Task
task agent: "List Todo issues for {team}, return highest priority (urgent>high>medium>low)"

If no Todo: telegram ":tada: All tasks complete!" then output `ALL_TASKS_DONE:` and stop.

### 1.5 Evaluate Task Size (ENG-27)

Check if task is Large based on:
- **Keywords**: "create service", "build dashboard", "implement pipeline", "full", "complete", "entire", "web app", "API server", "new project"
- **Scope**: Multiple components, 5+ files expected, 300+ lines estimated

**If Large Task → Decompose:**
1. Analyze task description, break into 3-7 logical subtasks
2. Create each subtask via task agent (Task_CreateIssue):
   - Title: "[Parent Title]: [Subtask description]"
   - Priority: Same as parent
   - Description: Specific scope for this subtask
3. Add comment to original task:
   ```
   Epic: This task has been decomposed into subtasks:
   - [subtask-id-1]: [title]
   - [subtask-id-2]: [title]
   ...
   Will mark Done when all subtasks complete.
   ```
4. Continue with first subtask as current task

**Decomposition Example:**
```
Original: "Build Web Dashboard" (ENG-50)
Subtasks created:
- ENG-51: "Build Web Dashboard: REST API endpoints"
- ENG-52: "Build Web Dashboard: React project setup"
- ENG-53: "Build Web Dashboard: Projects list page"
- ENG-54: "Build Web Dashboard: Kanban board component"
- ENG-55: "Build Web Dashboard: Docker integration"
```

**If Small/Medium Task:** Continue to Step 2 (no decomposition needed).

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
