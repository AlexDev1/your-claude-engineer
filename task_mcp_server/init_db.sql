-- =============================================================================
-- Task MCP Server Database Schema
-- Enterprise-grade PostgreSQL 16 with pgvector for RAG
-- =============================================================================

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- Teams (команды)
CREATE TABLE IF NOT EXISTS teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(10) UNIQUE NOT NULL,          -- "ENG", "DEV"
    name VARCHAR(255) NOT NULL,               -- "Engineering"
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
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
    type VARCHAR(20) NOT NULL,                -- "backlog", "unstarted", "started", "completed", "canceled"
    position INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Issue counters (счётчики для identifier)
CREATE TABLE IF NOT EXISTS issue_counters (
    team_key VARCHAR(10) PRIMARY KEY REFERENCES teams(key) ON DELETE CASCADE,
    counter INTEGER DEFAULT 0
);

-- =============================================================================
-- ENTERPRISE INDEXES - Core Tables
-- =============================================================================

-- Basic FK indexes
CREATE INDEX IF NOT EXISTS idx_issues_team_id ON issues(team_id);
CREATE INDEX IF NOT EXISTS idx_issues_project_id ON issues(project_id);
CREATE INDEX IF NOT EXISTS idx_issues_state_id ON issues(state_id);
CREATE INDEX IF NOT EXISTS idx_issues_identifier ON issues(identifier);
CREATE INDEX IF NOT EXISTS idx_comments_issue_id ON comments(issue_id);
CREATE INDEX IF NOT EXISTS idx_projects_team_id ON projects(team_id);
CREATE INDEX IF NOT EXISTS idx_workflow_states_team_id ON workflow_states(team_id);

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_issues_team_created ON issues(team_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_issues_team_state_created ON issues(team_id, state_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_issues_project_state ON issues(project_id, state_id);
CREATE INDEX IF NOT EXISTS idx_issues_updated_at ON issues(updated_at DESC);

-- Functional indexes for case-insensitive search
CREATE INDEX IF NOT EXISTS idx_teams_name_lower ON teams(LOWER(name));
CREATE INDEX IF NOT EXISTS idx_projects_name_lower ON projects(LOWER(name));
CREATE INDEX IF NOT EXISTS idx_workflow_states_name_lower ON workflow_states(team_id, LOWER(name));

-- Covering indexes for comments
CREATE INDEX IF NOT EXISTS idx_comments_issue_created ON comments(issue_id, created_at);

-- =============================================================================
-- RAG TABLES - pgvector support
-- =============================================================================

-- Embedding model configuration
CREATE TABLE IF NOT EXISTS embedding_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,        -- "text-embedding-3-small"
    provider VARCHAR(50) NOT NULL,            -- "openai", "cohere", "local"
    dimensions INTEGER NOT NULL,              -- 1536 for OpenAI
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- RAG Documents - source documents for embedding
CREATE TABLE IF NOT EXISTS rag_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    source_type VARCHAR(20) NOT NULL,         -- "issue", "comment"
    source_id UUID NOT NULL,                  -- ID of the source entity
    parent_id UUID REFERENCES rag_documents(id) ON DELETE CASCADE,  -- For comments -> parent issue doc
    title VARCHAR(500),
    full_text TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'pending',     -- "pending", "processing", "completed", "error"
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(source_type, source_id)
);

-- RAG Chunks - document segments for embedding
CREATE TABLE IF NOT EXISTS rag_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,             -- Order within document
    content TEXT NOT NULL,
    start_char INTEGER,                       -- Character offset in source
    end_char INTEGER,
    token_count INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);

-- RAG Embeddings - vector storage
CREATE TABLE IF NOT EXISTS rag_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES rag_chunks(id) ON DELETE CASCADE,
    model_id UUID NOT NULL REFERENCES embedding_models(id) ON DELETE CASCADE,
    embedding vector(1536),                   -- OpenAI text-embedding-3-small dimension
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(chunk_id, model_id)
);

-- RAG Search Cache - frequently queried embeddings
CREATE TABLE IF NOT EXISTS rag_search_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_hash VARCHAR(64) NOT NULL,          -- SHA256 of query text
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    query_embedding vector(1536),
    results JSONB NOT NULL,                   -- Cached search results
    hit_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() + INTERVAL '1 hour',
    UNIQUE(query_hash, team_id)
);

-- RAG Embedding Jobs - batch processing tracker
CREATE TABLE IF NOT EXISTS rag_embedding_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    model_id UUID REFERENCES embedding_models(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'pending',     -- "pending", "processing", "completed", "failed"
    total_documents INTEGER DEFAULT 0,
    processed_documents INTEGER DEFAULT 0,
    failed_documents INTEGER DEFAULT 0,
    error_log JSONB DEFAULT '[]',
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- RAG INDEXES - Optimized for semantic search
-- =============================================================================

-- HNSW index for fast approximate nearest neighbor search
-- Parameters: m=16 (connections per layer), ef_construction=200 (build quality)
CREATE INDEX IF NOT EXISTS idx_rag_embeddings_hnsw
ON rag_embeddings USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);

-- Standard indexes for RAG tables
CREATE INDEX IF NOT EXISTS idx_rag_documents_team_id ON rag_documents(team_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_project_id ON rag_documents(project_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_source ON rag_documents(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_status ON rag_documents(status);
CREATE INDEX IF NOT EXISTS idx_rag_documents_parent_id ON rag_documents(parent_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_document_id ON rag_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_rag_embeddings_chunk_id ON rag_embeddings(chunk_id);
CREATE INDEX IF NOT EXISTS idx_rag_embeddings_model_id ON rag_embeddings(model_id);
CREATE INDEX IF NOT EXISTS idx_rag_search_cache_expires ON rag_search_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_rag_search_cache_query ON rag_search_cache(query_hash, team_id);
CREATE INDEX IF NOT EXISTS idx_rag_embedding_jobs_status ON rag_embedding_jobs(status);

-- =============================================================================
-- FUNCTIONS - Core
-- =============================================================================

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function to generate next issue identifier (FIXED: race condition with FOR UPDATE)
CREATE OR REPLACE FUNCTION get_next_issue_identifier(p_team_key VARCHAR(10))
RETURNS VARCHAR(20) AS $$
DECLARE
    v_counter INTEGER;
BEGIN
    -- Try to lock and get existing counter
    SELECT counter INTO v_counter
    FROM issue_counters
    WHERE team_key = p_team_key
    FOR UPDATE;

    IF v_counter IS NULL THEN
        -- No counter exists, insert new one with conflict handling
        INSERT INTO issue_counters (team_key, counter)
        VALUES (p_team_key, 1)
        ON CONFLICT (team_key) DO UPDATE
        SET counter = issue_counters.counter + 1
        RETURNING counter INTO v_counter;
    ELSE
        -- Counter exists, increment it
        UPDATE issue_counters
        SET counter = counter + 1
        WHERE team_key = p_team_key
        RETURNING counter INTO v_counter;
    END IF;

    RETURN p_team_key || '-' || v_counter;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- FUNCTIONS - RAG
-- =============================================================================

-- Chunk a document into overlapping segments
CREATE OR REPLACE FUNCTION chunk_document(
    p_document_id UUID,
    p_chunk_size INTEGER DEFAULT 768,
    p_overlap INTEGER DEFAULT 100
)
RETURNS INTEGER AS $$
DECLARE
    v_full_text TEXT;
    v_text_length INTEGER;
    v_start INTEGER := 0;
    v_chunk_index INTEGER := 0;
    v_chunk_content TEXT;
    v_end INTEGER;
BEGIN
    -- Get document text
    SELECT full_text INTO v_full_text
    FROM rag_documents
    WHERE id = p_document_id;

    IF v_full_text IS NULL THEN
        RETURN 0;
    END IF;

    v_text_length := LENGTH(v_full_text);

    -- Delete existing chunks
    DELETE FROM rag_chunks WHERE document_id = p_document_id;

    -- Create chunks with overlap
    WHILE v_start < v_text_length LOOP
        v_end := LEAST(v_start + p_chunk_size, v_text_length);
        v_chunk_content := SUBSTRING(v_full_text FROM v_start + 1 FOR v_end - v_start);

        INSERT INTO rag_chunks (document_id, chunk_index, content, start_char, end_char, token_count)
        VALUES (
            p_document_id,
            v_chunk_index,
            v_chunk_content,
            v_start,
            v_end,
            LENGTH(v_chunk_content) / 4  -- Rough token estimate
        );

        v_chunk_index := v_chunk_index + 1;
        v_start := v_start + p_chunk_size - p_overlap;
    END LOOP;

    RETURN v_chunk_index;
END;
$$ LANGUAGE plpgsql;

-- Search similar documents using vector similarity
CREATE OR REPLACE FUNCTION search_similar_documents(
    p_query_embedding vector(1536),
    p_team_id UUID,
    p_limit INTEGER DEFAULT 10,
    p_threshold FLOAT DEFAULT 0.5
)
RETURNS TABLE (
    document_id UUID,
    chunk_id UUID,
    source_type VARCHAR(20),
    source_id UUID,
    title VARCHAR(500),
    content TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id AS document_id,
        c.id AS chunk_id,
        d.source_type,
        d.source_id,
        d.title,
        c.content,
        1 - (e.embedding <=> p_query_embedding) AS similarity
    FROM rag_embeddings e
    JOIN rag_chunks c ON e.chunk_id = c.id
    JOIN rag_documents d ON c.document_id = d.id
    WHERE d.team_id = p_team_id
      AND d.status = 'completed'
      AND 1 - (e.embedding <=> p_query_embedding) >= p_threshold
    ORDER BY e.embedding <=> p_query_embedding
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- Get context around a chunk
CREATE OR REPLACE FUNCTION get_chunk_context(
    p_chunk_id UUID,
    p_context_radius INTEGER DEFAULT 2
)
RETURNS TABLE (
    chunk_id UUID,
    chunk_index INTEGER,
    content TEXT,
    is_target BOOLEAN
) AS $$
DECLARE
    v_document_id UUID;
    v_target_index INTEGER;
BEGIN
    -- Get document and index of target chunk
    SELECT document_id, chunk_index INTO v_document_id, v_target_index
    FROM rag_chunks
    WHERE id = p_chunk_id;

    RETURN QUERY
    SELECT
        c.id,
        c.chunk_index,
        c.content,
        (c.chunk_index = v_target_index) AS is_target
    FROM rag_chunks c
    WHERE c.document_id = v_document_id
      AND c.chunk_index BETWEEN v_target_index - p_context_radius
                            AND v_target_index + p_context_radius
    ORDER BY c.chunk_index;
END;
$$ LANGUAGE plpgsql;

-- Get embedding statistics for a team
CREATE OR REPLACE FUNCTION get_embedding_stats(p_team_id UUID)
RETURNS TABLE (
    total_documents BIGINT,
    completed_documents BIGINT,
    pending_documents BIGINT,
    error_documents BIGINT,
    total_chunks BIGINT,
    total_embeddings BIGINT,
    issues_indexed BIGINT,
    comments_indexed BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::BIGINT AS total_documents,
        COUNT(*) FILTER (WHERE d.status = 'completed')::BIGINT AS completed_documents,
        COUNT(*) FILTER (WHERE d.status = 'pending')::BIGINT AS pending_documents,
        COUNT(*) FILTER (WHERE d.status = 'error')::BIGINT AS error_documents,
        (SELECT COUNT(*)::BIGINT FROM rag_chunks c
         JOIN rag_documents rd ON c.document_id = rd.id
         WHERE rd.team_id = p_team_id) AS total_chunks,
        (SELECT COUNT(*)::BIGINT FROM rag_embeddings e
         JOIN rag_chunks c ON e.chunk_id = c.id
         JOIN rag_documents rd ON c.document_id = rd.id
         WHERE rd.team_id = p_team_id) AS total_embeddings,
        COUNT(*) FILTER (WHERE d.source_type = 'issue')::BIGINT AS issues_indexed,
        COUNT(*) FILTER (WHERE d.source_type = 'comment')::BIGINT AS comments_indexed
    FROM rag_documents d
    WHERE d.team_id = p_team_id;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGERS - updated_at
-- =============================================================================

DROP TRIGGER IF EXISTS update_teams_updated_at ON teams;
CREATE TRIGGER update_teams_updated_at
    BEFORE UPDATE ON teams
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

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

DROP TRIGGER IF EXISTS update_comments_updated_at ON comments;
CREATE TRIGGER update_comments_updated_at
    BEFORE UPDATE ON comments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_rag_documents_updated_at ON rag_documents;
CREATE TRIGGER update_rag_documents_updated_at
    BEFORE UPDATE ON rag_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- TRIGGERS - RAG Synchronization
-- =============================================================================

-- Create RAG document when issue is created
CREATE OR REPLACE FUNCTION trigger_create_rag_doc_on_issue()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO rag_documents (team_id, project_id, source_type, source_id, title, full_text, status)
    VALUES (
        NEW.team_id,
        NEW.project_id,
        'issue',
        NEW.id,
        NEW.title,
        NEW.title || E'\n\n' || COALESCE(NEW.description, ''),
        'pending'
    )
    ON CONFLICT (source_type, source_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_create_rag_doc_on_issue ON issues;
CREATE TRIGGER trg_create_rag_doc_on_issue
    AFTER INSERT ON issues
    FOR EACH ROW
    EXECUTE FUNCTION trigger_create_rag_doc_on_issue();

-- Update RAG document when issue is updated
CREATE OR REPLACE FUNCTION trigger_update_rag_doc_on_issue()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.title IS DISTINCT FROM OLD.title OR NEW.description IS DISTINCT FROM OLD.description THEN
        UPDATE rag_documents
        SET
            title = NEW.title,
            full_text = NEW.title || E'\n\n' || COALESCE(NEW.description, ''),
            status = 'pending',
            updated_at = NOW()
        WHERE source_type = 'issue' AND source_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_rag_doc_on_issue ON issues;
CREATE TRIGGER trg_update_rag_doc_on_issue
    AFTER UPDATE ON issues
    FOR EACH ROW
    EXECUTE FUNCTION trigger_update_rag_doc_on_issue();

-- Create RAG document when comment is created
CREATE OR REPLACE FUNCTION trigger_create_rag_doc_on_comment()
RETURNS TRIGGER AS $$
DECLARE
    v_team_id UUID;
    v_parent_doc_id UUID;
BEGIN
    -- Get team_id from the issue
    SELECT team_id INTO v_team_id FROM issues WHERE id = NEW.issue_id;

    -- Get parent RAG document for the issue
    SELECT id INTO v_parent_doc_id
    FROM rag_documents
    WHERE source_type = 'issue' AND source_id = NEW.issue_id;

    INSERT INTO rag_documents (team_id, source_type, source_id, parent_id, full_text, status)
    VALUES (
        v_team_id,
        'comment',
        NEW.id,
        v_parent_doc_id,
        NEW.body,
        'pending'
    )
    ON CONFLICT (source_type, source_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_create_rag_doc_on_comment ON comments;
CREATE TRIGGER trg_create_rag_doc_on_comment
    AFTER INSERT ON comments
    FOR EACH ROW
    EXECUTE FUNCTION trigger_create_rag_doc_on_comment();

-- Cleanup embeddings and chunks when document is deleted
CREATE OR REPLACE FUNCTION trigger_cleanup_on_doc_delete()
RETURNS TRIGGER AS $$
BEGIN
    -- Chunks and embeddings will be cascade deleted via FK
    -- This trigger is for any additional cleanup if needed
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cleanup_on_doc_delete ON rag_documents;
CREATE TRIGGER trg_cleanup_on_doc_delete
    BEFORE DELETE ON rag_documents
    FOR EACH ROW
    EXECUTE FUNCTION trigger_cleanup_on_doc_delete();

-- =============================================================================
-- VIEWS - RAG
-- =============================================================================

-- View for issue chunks with metadata
CREATE OR REPLACE VIEW issue_chunks_view AS
SELECT
    c.id AS chunk_id,
    c.chunk_index,
    c.content,
    c.token_count,
    d.id AS document_id,
    d.source_id AS issue_id,
    d.title AS issue_title,
    d.team_id,
    d.project_id,
    i.identifier AS issue_identifier,
    i.priority,
    ws.name AS state_name
FROM rag_chunks c
JOIN rag_documents d ON c.document_id = d.id
JOIN issues i ON d.source_id = i.id
LEFT JOIN workflow_states ws ON i.state_id = ws.id
WHERE d.source_type = 'issue';

-- =============================================================================
-- DEFAULT DATA
-- =============================================================================

-- Insert default embedding model
INSERT INTO embedding_models (name, provider, dimensions, is_default)
VALUES ('text-embedding-3-small', 'openai', 1536, TRUE)
ON CONFLICT (name) DO NOTHING;

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

-- =============================================================================
-- AUTH TABLES - API Key Authentication
-- =============================================================================

CREATE TABLE IF NOT EXISTS auth_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(8) NOT NULL,
    key_hash VARCHAR(64) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    last_used_ip INET,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

-- Auth indexes
CREATE INDEX IF NOT EXISTS idx_auth_api_keys_key_hash ON auth_api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_auth_api_keys_key_prefix ON auth_api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_auth_api_keys_user_id ON auth_api_keys(user_id);

-- Auth triggers
DROP TRIGGER IF EXISTS update_auth_users_updated_at ON auth_users;
CREATE TRIGGER update_auth_users_updated_at
    BEFORE UPDATE ON auth_users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- MIGRATION HELPERS (run manually after applying schema to existing DB)
-- =============================================================================

-- Sync existing issues to RAG documents
-- INSERT INTO rag_documents (team_id, project_id, source_type, source_id, title, full_text, status)
-- SELECT
--     team_id,
--     project_id,
--     'issue',
--     id,
--     title,
--     title || E'\n\n' || COALESCE(description, ''),
--     'pending'
-- FROM issues
-- ON CONFLICT (source_type, source_id) DO NOTHING;

-- Sync existing comments to RAG documents
-- INSERT INTO rag_documents (team_id, source_type, source_id, parent_id, full_text, status)
-- SELECT
--     i.team_id,
--     'comment',
--     c.id,
--     rd.id,
--     c.body,
--     'pending'
-- FROM comments c
-- JOIN issues i ON c.issue_id = i.id
-- LEFT JOIN rag_documents rd ON rd.source_id = i.id AND rd.source_type = 'issue'
-- ON CONFLICT (source_type, source_id) DO NOTHING;
