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
    """Initialize minimal schema for authentication if not exists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
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
            -- Minimal projects table for local development
            create table if not exists projects (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null references organizations(id) on delete cascade,
                name text not null,
                description text,
                created_by uuid references users(id) on delete set null,
                created_at timestamptz not null default now()
            );
            create index if not exists idx_projects_org on projects(org_id);

            -- Minimal tasks table for local development
            create table if not exists tasks (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null references organizations(id) on delete cascade,
                project_id uuid references projects(id) on delete cascade,
                title text not null,
                description text,
                status text not null default 'todo',
                assignee_id uuid references users(id) on delete set null,
                created_by uuid references users(id) on delete set null,
                created_at timestamptz not null default now()
            );
            create index if not exists idx_tasks_org on tasks(org_id);
            create index if not exists idx_tasks_project on tasks(project_id);
            """
        )
