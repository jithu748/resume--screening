# Authentication and tenant-isolation foundation

The application includes a SQLite-backed local authentication foundation and a PostgreSQL adapter for production. Authentication is intentionally not enabled on the live deployment by this change.

## Configuration

Development defaults preserve the anonymous workflow:

```text
APP_ENV=development
AUTH_REQUIRED=false
AUTH_DB_PATH=data/auth.sqlite3
CORS_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
```

Production must fail closed unless all of the following are configured:

```text
APP_ENV=production
AUTH_REQUIRED=true
DATABASE_URL=<PostgreSQL URL supplied through the deployment secret manager>
CORS_ALLOWED_ORIGINS=https://your-frontend.example
```

Production uses `DATABASE_URL`, the parameterized `psycopg` adapter, and the PostgreSQL migration. The application refuses production startup unless `AUTH_REQUIRED=true` is explicit, the URL is PostgreSQL, the driver is installed, and CORS origins are explicitly configured. Never place credentials in source control or logs.

## Account and agency flow

`POST /api/auth/register` creates a new agency and makes the registering user its owner. Registration cannot accept an agency ID or arbitrary role. Existing agencies are joined only through an invitation created by an owner or admin.

Supported roles are `owner`, `admin`, `recruiter`, and `viewer`. Admins may invite recruiters/viewers; only owners may invite admins.

Authentication uses opaque random cookies. Only SHA-256 token hashes are persisted. Passwords use salted `hashlib.scrypt` hashes. Authenticated state-changing requests require the CSRF token cookie/header pair and an allowed `Origin`.

## Frontend migration

The existing anonymous frontend continues to work only when `AUTH_REQUIRED=false`. The frontend now includes:

1. Registration/login/logout controls and current-user status.
2. `credentials: "include"` on authenticated requests.
3. An `X-CSRF-Token` header copied from the non-HttpOnly `resume_csrf` cookie for state-changing requests.
4. Handling for `401`, `403`, and expired sessions.

CSV exports now contain only `rank`, `file`, `score`, `matched_skills`, and `missing_skills`; full resume text is not exported by default.

## Local-only development demo mode

The authentication controls may be hidden for a local demonstration only by
setting `LOCAL_DEMO_MODE=true`. This mode is accepted only when
`APP_ENV=development` and `AUTH_REQUIRED=false`. It also requires explicit
HTTP loopback origins in `CORS_ALLOWED_ORIGINS`; wildcard origins are not
allowed. The application rejects non-loopback clients while this mode is
active.

Start the demo with Uvicorn bound to loopback:

```powershell
$env:APP_ENV="development"
$env:AUTH_REQUIRED="false"
$env:LOCAL_DEMO_MODE="true"
$env:CORS_ALLOWED_ORIGINS="http://127.0.0.1:8081"
.\.venv\Scripts\python.exe -m uvicorn data.src.webapp:app --host 127.0.0.1 --port 8081
```

This mode is not suitable for public or production deployment. Upload,
content, path, cleanup, and origin validation remain active. Anonymous demo
sessions are intentionally unowned and temporary; authenticated production
workflows continue to require user and agency ownership.

## Migration

The migration is applied automatically at first authenticated use. SQLite uses [001_auth_and_tenant.sql](data/migrations/001_auth_and_tenant.sql); PostgreSQL uses [001_auth_and_tenant_postgres.sql](data/migrations/001_auth_and_tenant_postgres.sql). Both create agencies, users, memberships, authentication sessions, resume sessions/files, screening-result metadata, and agency invitations. Migration execution is recorded in `schema_migrations`.

For production, install the pinned `psycopg[binary]` dependency, provision an empty or reviewed PostgreSQL database, set the environment variables above, and start the application once to apply the migration. Existing SQLite data is not copied automatically; perform a reviewed export/import if migration of local accounts is required. Do not enable `AUTH_REQUIRED` on the live application until deployment configuration and a real PostgreSQL migration have been verified.

## Legacy `/run` limitation

The legacy `POST /run` endpoint remains available for frontend compatibility.
It remains subject to the configured authentication requirement and uses the
same upload validation as the newer upload endpoints. It processes uploads
within one request and removes its temporary directory afterward.

It does not create a durable ownership-recorded resume session. Persistent
agency-owned workflows should use `/api/upload`, `/api/session_status`,
`/api/score`, `/view/{session_id}/{filename}`, and
`/api/download_results`.
