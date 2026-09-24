-- People who filled the download form on the landing page.
CREATE TABLE IF NOT EXISTS leads (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  name          TEXT    NOT NULL,
  phone         TEXT    NOT NULL,
  email         TEXT,
  purpose       TEXT,
  os            TEXT,
  ip_hash       TEXT,
  user_agent    TEXT,
  downloads     INTEGER NOT NULL DEFAULT 0,
  last_download TEXT
);
CREATE INDEX IF NOT EXISTS leads_ip_time ON leads (ip_hash, created_at);
CREATE INDEX IF NOT EXISTS leads_phone ON leads (phone);
