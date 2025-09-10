# Backend RLS Enforcement Guide

This backend must never bypass Postgres/Supabase Row Level Security (RLS). The database schema enforces org-based isolation with policies on core tables (users, organizations, memberships, projects, tasks, comments, attachments, project_github_repos).

Key rules:
- PUBLIC_INTERFACE
- Always propagate user identity to the database layer so RLS can evaluate policies:
  1) Prefer calling Supabase (PostgREST) with the user's JWT. Supabase injects request.jwt.claims for RLS.
  2) If using a direct Postgres connection, you must set the session GUC before any queries in a request:
     SELECT set_config('app.user_id', '<uuid>', false);
  This makes get_current_user_id() work outside Supabase REST.

- Do NOT use the Supabase service key or a superuser role for end-user queries. The service key bypasses RLS and is reserved for isolated privileged admin flows with their own policy checks.

- When using connection pools, ensure set_config is executed per-request on the connection you obtained from the pool before running any queries. Clear or overwrite it before returning the connection to the pool.

- Avoid raw queries that join across orgs without a where clause on org context. RLS will block cross-org access, but explicit scoping reduces risk and improves clarity.

- For bulk operations (e.g., reorder tasks), ensure the active organization context is established (via JWT or set_config).

- Webhooks/integrations:
  - If GitHub or Stripe webhooks need to write data, run them under a restricted technical role and set app.user_id to an appropriate service principal (or keep using RLS-compatible paths—e.g., org owner/admin semantics if applicable).

- Testing locally without Supabase Auth:
  - After authenticating in the backend and issuing your own JWT, either:
    * call Supabase with that JWT, or
    * set_config('app.user_id', <uuid>) on your Postgres session.
  - Never disable RLS to "make it work".

- Auditing reminder:
  - Log when queries run without an app.user_id in session unless using clearly annotated admin paths.

This guide is a living document; update it if db access patterns change.
