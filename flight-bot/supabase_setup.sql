-- Run this in your Supabase SQL Editor
-- Dashboard → SQL Editor → New Query → paste and run

-- Sessions table: stores file collections per user
CREATE TABLE IF NOT EXISTS sessions (
  id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id     BIGINT      NOT NULL,
  chat_id     BIGINT      NOT NULL,
  files       JSONB       DEFAULT '[]'::jsonb,
  status      TEXT        DEFAULT 'collecting',
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookup by user + status
CREATE INDEX IF NOT EXISTS idx_sessions_user_status
  ON sessions (user_id, status);

-- Auto-cleanup: delete sessions older than 7 days
-- (Optional - set up a Supabase cron job or pg_cron for this)
-- DELETE FROM sessions WHERE created_at < NOW() - INTERVAL '7 days';

-- Verify table was created
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'sessions'
ORDER BY ordinal_position;
