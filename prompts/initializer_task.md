Initialize a new project in: {project_dir}

This is the FIRST session. The project has not been set up yet.

## INITIALIZATION SEQUENCE

### Step 1: Set Up Project in Task Server
Delegate to `task` agent:
"Read app_spec.txt to understand what we're building. Then:
1. Create a project with appropriate name
2. Create issues for ALL features from app_spec.txt (with test steps in description)
3. Create a META issue '[META] Project Progress Tracker' for session handoffs
4. Add initial comment to META issue with project summary and session 1 status
5. Save state to .task_project.json
6. Return: project_id, total_issues created, meta_issue_id"

### Step 2: Initialize Git
Delegate to `coding` agent:
"Initialize git repository:
1. Create README.md with project overview (use Write tool)
2. Create init.sh script to start dev server (use Write tool)
3. Create .gitignore (use Write tool)
4. Run: git init
5. Run: git add README.md init.sh .gitignore .task_project.json
6. Run: git commit -m 'chore: Initial project setup'
7. Report: commit_hash"

### Step 3: Send Notification
Delegate to `telegram` agent:
"Send message: :rocket: Project initialized: [project name]"

### Step 4: Start First Feature (if time permits)
Get the highest-priority issue details from task agent, then delegate to `coding` agent:
"Implement this task:
- ID: [from task agent]
- Title: [from task agent]
- Description: [from task agent]
- Test Steps: [from task agent]

Requirements:
1. Implement the feature
2. Test via Playwright (mandatory)
3. Take screenshot evidence
4. Report: files_changed, screenshot_path, test_results"

### Step 5: Commit Progress
If coding was done, delegate to `coding` agent to commit.
Then delegate to `task` agent to add session summary comment to META issue.

## OUTPUT FILES TO CREATE
- .task_project.json (project state)
- init.sh (dev server startup)
- README.md (project overview)
- .gitignore

Remember: You are the orchestrator. Delegate tasks to specialized agents, don't do the work yourself.
