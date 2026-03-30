-- Chat messages for AI-powered paper Q&A
CREATE TABLE IF NOT EXISTS chat_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id        UUID REFERENCES raw_papers(id),
    user_id         UUID REFERENCES decoded_users(id),
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    model           TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
    prompt_tokens   INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    cost_usd        REAL DEFAULT 0.0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_paper ON chat_messages(paper_id);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at);
