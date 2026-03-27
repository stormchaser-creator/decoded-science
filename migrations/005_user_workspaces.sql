-- Migration 005: Decoded user accounts + persistent workspaces
-- Run: psql -d encoded_human -f migrations/005_user_workspaces.sql

BEGIN;

-- Decoded-specific user accounts (separate from EHP users)
CREATE TABLE IF NOT EXISTS decoded_users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL,
    name            TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'researcher'
                        CHECK (role IN ('researcher', 'admin')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT decoded_users_email_unique UNIQUE (email)
);

-- Saved searches (query + filters bookmarked by user)
CREATE TABLE IF NOT EXISTS saved_searches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES decoded_users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    query           TEXT NOT NULL,
    filters         JSONB NOT NULL DEFAULT '{}',
    result_count    INTEGER,
    last_run_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_saved_searches_user ON saved_searches (user_id);

-- Collections (named sets of papers)
CREATE TABLE IF NOT EXISTS decoded_collections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES decoded_users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT,
    is_public       BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_collections_user ON decoded_collections (user_id);

-- Papers in a collection
CREATE TABLE IF NOT EXISTS collection_papers (
    collection_id   UUID NOT NULL REFERENCES decoded_collections(id) ON DELETE CASCADE,
    paper_id        UUID NOT NULL REFERENCES raw_papers(id) ON DELETE CASCADE,
    notes           TEXT,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (collection_id, paper_id)
);

-- Watchlists (entity/concept alerts — notify when new papers match)
CREATE TABLE IF NOT EXISTS watchlists (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES decoded_users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    watch_type      TEXT NOT NULL CHECK (watch_type IN ('entity', 'query', 'author')),
    watch_value     TEXT NOT NULL,
    last_checked_at TIMESTAMPTZ,
    new_count       INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists (user_id);

-- Workspaces (named research contexts with layout/filter state)
CREATE TABLE IF NOT EXISTS decoded_workspaces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES decoded_users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT,
    state           JSONB NOT NULL DEFAULT '{}',  -- pinned panels, active filters, etc.
    is_default      BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspaces_user ON decoded_workspaces (user_id);

-- Auto-update updated_at triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS decoded_users_updated_at ON decoded_users;
CREATE TRIGGER decoded_users_updated_at
    BEFORE UPDATE ON decoded_users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS saved_searches_updated_at ON saved_searches;
CREATE TRIGGER saved_searches_updated_at
    BEFORE UPDATE ON saved_searches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS decoded_collections_updated_at ON decoded_collections;
CREATE TRIGGER decoded_collections_updated_at
    BEFORE UPDATE ON decoded_collections
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS decoded_workspaces_updated_at ON decoded_workspaces;
CREATE TRIGGER decoded_workspaces_updated_at
    BEFORE UPDATE ON decoded_workspaces
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
