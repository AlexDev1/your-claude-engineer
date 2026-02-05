-- Task MCP Server Database Schema
-- PostgreSQL 15+

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Teams (команды)
CREATE TABLE IF NOT EXISTS teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(10) UNIQUE NOT NULL,          -- "ENG", "DEV"
    name VARCHAR(255) NOT NULL,               -- "Engineering"
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Projects (проекты)
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Workflow states (статусы задач)
CREATE TABLE IF NOT EXISTS workflow_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,                -- "Todo", "In Progress", "Done"
    type VARCHAR(20) NOT NULL,                -- "unstarted", "started", "completed"
    position INTEGER DEFAULT 0,
    UNIQUE(team_id, name)
);

-- Issues (задачи)
CREATE TABLE IF NOT EXISTS issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    identifier VARCHAR(20) UNIQUE NOT NULL,   -- "ENG-42"
    title VARCHAR(500) NOT NULL,
    description TEXT,
    priority VARCHAR(20) DEFAULT 'medium',    -- "urgent", "high", "medium", "low"
    state_id UUID REFERENCES workflow_states(id),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Comments (комментарии к задачам)
CREATE TABLE IF NOT EXISTS comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID REFERENCES issues(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Issue counters (счётчики для identifier)
CREATE TABLE IF NOT EXISTS issue_counters (
    team_key VARCHAR(10) PRIMARY KEY REFERENCES teams(key) ON DELETE CASCADE,
    counter INTEGER DEFAULT 0
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_issues_team_id ON issues(team_id);
CREATE INDEX IF NOT EXISTS idx_issues_project_id ON issues(project_id);
CREATE INDEX IF NOT EXISTS idx_issues_state_id ON issues(state_id);
CREATE INDEX IF NOT EXISTS idx_issues_identifier ON issues(identifier);
CREATE INDEX IF NOT EXISTS idx_comments_issue_id ON comments(issue_id);
CREATE INDEX IF NOT EXISTS idx_projects_team_id ON projects(team_id);
CREATE INDEX IF NOT EXISTS idx_workflow_states_team_id ON workflow_states(team_id);

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
DROP TRIGGER IF EXISTS update_issues_updated_at ON issues;
CREATE TRIGGER update_issues_updated_at
    BEFORE UPDATE ON issues
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_projects_updated_at ON projects;
CREATE TRIGGER update_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to generate next issue identifier
CREATE OR REPLACE FUNCTION get_next_issue_identifier(p_team_key VARCHAR(10))
RETURNS VARCHAR(20) AS $$
DECLARE
    v_counter INTEGER;
BEGIN
    -- Increment counter and get new value
    UPDATE issue_counters
    SET counter = counter + 1
    WHERE team_key = p_team_key
    RETURNING counter INTO v_counter;

    -- If no row existed, insert new one
    IF v_counter IS NULL THEN
        INSERT INTO issue_counters (team_key, counter)
        VALUES (p_team_key, 1)
        ON CONFLICT (team_key) DO UPDATE SET counter = issue_counters.counter + 1
        RETURNING counter INTO v_counter;
    END IF;

    RETURN p_team_key || '-' || v_counter;
END;
$$ LANGUAGE plpgsql;

-- Insert default team and workflow states
INSERT INTO teams (key, name) VALUES ('ENG', 'Engineering')
ON CONFLICT (key) DO NOTHING;

-- Insert default workflow states for the team
DO $$
DECLARE
    v_team_id UUID;
BEGIN
    SELECT id INTO v_team_id FROM teams WHERE key = 'ENG';

    INSERT INTO workflow_states (team_id, name, type, position) VALUES
        (v_team_id, 'Backlog', 'backlog', 0),
        (v_team_id, 'Todo', 'unstarted', 1),
        (v_team_id, 'In Progress', 'started', 2),
        (v_team_id, 'Done', 'completed', 3),
        (v_team_id, 'Canceled', 'canceled', 4)
    ON CONFLICT (team_id, name) DO NOTHING;

    -- Initialize counter for team
    INSERT INTO issue_counters (team_key, counter) VALUES ('ENG', 0)
    ON CONFLICT (team_key) DO NOTHING;
END $$;
