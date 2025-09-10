# CollabTask Backend API - Database Schema and RLS

This backend uses PostgreSQL (asyncpg). On startup, the app creates minimal core tables if they do not exist: users, organizations, memberships. We additionally provide SQL migration drafts for projects and tasks, and Row Level Security (RLS) compatible with application-issued JWTs.

Files:
- database_supabase/schema/001_schema.sql: Tables (users, organizations, memberships, projects, tasks) and indexes.
- database_supabase/schema/002_rls.sql: RLS policies enabling org-level isolation.

Assumptions:
- JWT access tokens carry claim user_id and optionally active_org_id.
- RLS helper function auth.uid() reads user_id from JWT claims via request.jwt.claims.

Notes:
- If using Supabase, ensure request.jwt.claims is populated by the proxy. If not using Supabase, you can disable RLS or adapt to your gateway.
- The FastAPI app also creates minimal auth tables on startup for local development via src/api/db.py:init_db_schema(), covering users, organizations, memberships only.

Environment variables (see README.md):
- POSTGRES_URL or POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB/POSTGRES_HOST/POSTGRES_PORT
- JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRES_MINUTES
