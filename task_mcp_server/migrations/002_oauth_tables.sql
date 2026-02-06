-- =============================================================================
-- Migration 002: OAuth 2.0 Tables
-- =============================================================================
--
-- Adds OAuth 2.0 support for Claude.ai web connector compatibility.
-- Supports Authorization Code + PKCE with Dynamic Client Registration.
--
-- Apply with:
--   docker exec -i mcp-postgres psql -U agent -d tasks < migrations/002_oauth_tables.sql
--
-- =============================================================================

-- OAuth clients (Dynamic Client Registration - RFC 7591)
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id VARCHAR(255) PRIMARY KEY,
    client_secret VARCHAR(255),
    client_id_issued_at INTEGER,
    client_secret_expires_at INTEGER,
    redirect_uris JSONB NOT NULL DEFAULT '[]',
    grant_types JSONB NOT NULL DEFAULT '["authorization_code", "refresh_token"]',
    response_types JSONB NOT NULL DEFAULT '["code"]',
    token_endpoint_auth_method VARCHAR(50) DEFAULT 'none',
    client_name VARCHAR(255),
    client_uri TEXT,
    logo_uri TEXT,
    scope TEXT,
    contacts JSONB,
    tos_uri TEXT,
    policy_uri TEXT,
    software_id VARCHAR(255),
    software_version VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Authorization codes (short-lived, ~5 min TTL)
CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
    code VARCHAR(255) PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL,
    redirect_uri_provided_explicitly BOOLEAN DEFAULT TRUE,
    code_challenge VARCHAR(255) NOT NULL,
    scopes JSONB NOT NULL DEFAULT '[]',
    expires_at DOUBLE PRECISION NOT NULL,
    resource TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Access tokens
CREATE TABLE IF NOT EXISTS oauth_access_tokens (
    token VARCHAR(255) PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    scopes JSONB NOT NULL DEFAULT '[]',
    expires_at INTEGER,
    resource TEXT,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Refresh tokens
CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
    token VARCHAR(255) PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    scopes JSONB NOT NULL DEFAULT '[]',
    expires_at INTEGER,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_oauth_auth_codes_client_id ON oauth_authorization_codes(client_id);
CREATE INDEX IF NOT EXISTS idx_oauth_auth_codes_expires_at ON oauth_authorization_codes(expires_at);
CREATE INDEX IF NOT EXISTS idx_oauth_access_tokens_client_id ON oauth_access_tokens(client_id);
CREATE INDEX IF NOT EXISTS idx_oauth_access_tokens_expires_at ON oauth_access_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_oauth_access_tokens_revoked ON oauth_access_tokens(revoked) WHERE revoked = FALSE;
CREATE INDEX IF NOT EXISTS idx_oauth_refresh_tokens_client_id ON oauth_refresh_tokens(client_id);
CREATE INDEX IF NOT EXISTS idx_oauth_refresh_tokens_revoked ON oauth_refresh_tokens(revoked) WHERE revoked = FALSE;
