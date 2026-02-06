-- =============================================================================
-- Migration 001: Auth Tables for API Key Authentication
-- =============================================================================
-- Apply to running DB:
--   docker exec -i mcp-postgres psql -U agent -d tasks < migrations/001_auth_tables.sql
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_auth_api_keys_key_hash ON auth_api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_auth_api_keys_key_prefix ON auth_api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_auth_api_keys_user_id ON auth_api_keys(user_id);

-- Trigger for updated_at on auth_users
DROP TRIGGER IF EXISTS update_auth_users_updated_at ON auth_users;
CREATE TRIGGER update_auth_users_updated_at
    BEFORE UPDATE ON auth_users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
