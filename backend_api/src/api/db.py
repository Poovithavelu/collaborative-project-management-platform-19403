import asyncpg
from typing import Optional
from .config import get_settings

_pool: Optional[asyncpg.pool.Pool] = None


# PUBLIC_INTERFACE
async def get_pool() -> asyncpg.pool.Pool:
    """Get or create a global asyncpg connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        dsn = settings.build_database_dsn()
        _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
    return _pool


# PUBLIC_INTERFACE
async def init_db_schema() -> None:
    """Initialize minimal schema for authentication and core domain if not exists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            -- Enable needed extension for UUID if not present; Supabase has gen_random_uuid
            create extension if not exists pgcrypto;

            create table if not exists users (
                id uuid primary key default gen_random_uuid(),
                email text unique not null,
                password_hash text not null,
                full_name text,
                created_at timestamptz not null default now(),
                active_org_id uuid
            );

            create table if not exists organizations (
                id uuid primary key default gen_random_uuid(),
                name text not null,
                created_at timestamptz not null default now(),
                owner_user_id uuid references users(id) on delete cascade
            );

            create table if not exists memberships (
                id uuid primary key default gen_random_uuid(),
                user_id uuid not null references users(id) on delete cascade,
                org_id uuid not null references organizations(id) on delete cascade,
                role text not null default 'member',
                created_at timestamptz not null default now(),
                unique(user_id, org_id)
            );

            create table if not exists projects (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null references organizations(id) on delete cascade,
                name text not null,
                description text,
                created_by uuid references users(id) on delete set null,
                created_at timestamptz not null default now()
            );

            create index if not exists idx_projects_org on projects(org_id);

            create table if not exists tasks (
                id uuid primary key default gen_random_uuid(),
                project_id uuid not null references projects(id) on delete cascade,
                title text not null,
                description text,
                assignee_id uuid references users(id) on delete set null,
                status text not null default 'todo',
                priority text not null default 'medium',
                created_by uuid references users(id) on delete set null,
                created_at timestamptz not null default now()
            );

            create index if not exists idx_tasks_project on tasks(project_id);

            create table if not exists comments (
                id uuid primary key default gen_random_uuid(),
                task_id uuid not null references tasks(id) on delete cascade,
                body text not null,
                created_by uuid references users(id) on delete set null,
                created_at timestamptz not null default now()
            );

            create index if not exists idx_comments_task on comments(task_id);

            create table if not exists files (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null references organizations(id) on delete cascade,
                filename text not null,
                content_type text,
                size_bytes integer not null,
                data bytea not null,
                uploaded_by uuid references users(id) on delete set null,
                created_at timestamptz not null default now()
            );

            create table if not exists subscriptions (
                org_id uuid primary key references organizations(id) on delete cascade,
                stripe_customer_id text,
                status text,
                price_id text,
                updated_at timestamptz not null default now()
            );

            create table if not exists github_repos (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null references organizations(id) on delete cascade,
                repo_full_name text not null,
                installation_id bigint,
                created_at timestamptz not null default now(),
                unique(org_id, repo_full_name)
            );
            """
        )
