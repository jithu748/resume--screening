CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS agencies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS agency_memberships (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agency_id TEXT NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'recruiter', 'viewer')),
    created_at REAL NOT NULL,
    PRIMARY KEY (user_id, agency_id)
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agency_id TEXT NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    csrf_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_seen REAL NOT NULL,
    idle_expires_at REAL NOT NULL,
    absolute_expires_at REAL NOT NULL,
    revoked_at REAL
);

CREATE TABLE IF NOT EXISTS resume_sessions (
    session_id TEXT PRIMARY KEY,
    owner_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    agency_id TEXT REFERENCES agencies(id) ON DELETE SET NULL,
    directory TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    ended_at REAL
);

CREATE TABLE IF NOT EXISTS resume_files (
    session_id TEXT NOT NULL REFERENCES resume_sessions(session_id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (session_id, filename)
);

CREATE TABLE IF NOT EXISTS screening_results (
    session_id TEXT PRIMARY KEY REFERENCES resume_sessions(session_id) ON DELETE CASCADE,
    result_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS agency_invitations (
    token_hash TEXT PRIMARY KEY,
    agency_id TEXT NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'recruiter', 'viewer')),
    created_by_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    accepted_at REAL
);

CREATE INDEX IF NOT EXISTS idx_memberships_agency ON agency_memberships(agency_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_resume_sessions_owner ON resume_sessions(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_resume_sessions_agency ON resume_sessions(agency_id);
