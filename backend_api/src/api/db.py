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
                created_at timestamptz not null default now(),
                -- New column to support ordering within a project/status lane
                order_index integer
            );
            create index if not exists idx_tasks_org on tasks(org_id);
            create index if not exists idx_tasks_project on tasks(project_id);
            -- Helpful composite indexes for ordering use cases
            create index if not exists idx_tasks_project_status_order on tasks(project_id, status, order_index);
            create index if not exists idx_tasks_org_project_order on tasks(org_id, project_id, order_index);

            -- Comments table for tasks
            create table if not exists comments (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null references organizations(id) on delete cascade,
                task_id uuid not null references tasks(id) on delete cascade,
                author_id uuid references users(id) on delete set null,
                content text not null,
                created_at timestamptz not null default now()
            );
            create index if not exists idx_comments_org on comments(org_id);
            create index if not exists idx_comments_task on comments(task_id);

            -- Files/Attachments table for local development
            create table if not exists attachments (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null references organizations(id) on delete cascade,
                project_id uuid references projects(id) on delete cascade,
                task_id uuid references tasks(id) on delete cascade,
                uploader_id uuid references users(id) on delete set null,
                filename text not null,
                content_type text,
                size_bytes bigint,
                storage_path text not null,
                created_at timestamptz not null default now()
            );
            create index if not exists idx_attachments_org on attachments(org_id);
            create index if not exists idx_attachments_project on attachments(project_id);
            create index if not exists idx_attachments_task on attachments(task_id);
            create index if not exists idx_attachments_created on attachments(created_at);

            -- Audit log table
            create table if not exists audit_log (
                id uuid primary key default gen_random_uuid(),
                occurred_at timestamptz not null default now(),
                user_id uuid,
                org_id uuid,
                project_id uuid,
                entity_type text not null,
                entity_id uuid,
                action text not null,
                request_path text,
                method text,
                details jsonb
            );
            create index if not exists idx_audit_log_org on audit_log(org_id);
            create index if not exists idx_audit_log_project on audit_log(project_id);
            create index if not exists idx_audit_log_entity on audit_log(entity_type, entity_id);
            create index if not exists idx_audit_log_time on audit_log(occurred_at);

            -- Trigger function and triggers to log direct SQL changes on tasks
            create or replace function public.log_task_changes()
            returns trigger
            language plpgsql
            as $$
            declare
                v_action text;
                v_entity_id uuid;
                v_org_id uuid;
                v_project_id uuid;
                v_details jsonb;
            begin
                if (TG_OP = 'INSERT') then
                    v_action := 'create';
                    v_entity_id := NEW.id;
                    v_org_id := NEW.org_id;
                    v_project_id := NEW.project_id;
                    v_details := jsonb_build_object('new', to_jsonb(NEW));
                elsif (TG_OP = 'UPDATE') then
                    v_action := 'update';
                    v_entity_id := NEW.id;
                    v_org_id := NEW.org_id;
                    v_project_id := NEW.project_id;
                    v_details := jsonb_build_object('old', to_jsonb(OLD), 'new', to_jsonb(NEW));
                elsif (TG_OP = 'DELETE') then
                    v_action := 'delete';
                    v_entity_id := OLD.id;
                    v_org_id := OLD.org_id;
                    v_project_id := OLD.project_id;
                    v_details := jsonb_build_object('old', to_jsonb(OLD));
                end if;

                insert into public.audit_log (user_id, org_id, project_id, entity_type, entity_id, action, request_path, method, details)
                values (null, v_org_id, v_project_id, 'task', v_entity_id, v_action, null, null, v_details);

                return null;
            end;
            $$;

            drop trigger if exists trg_tasks_audit_insert on tasks;
            drop trigger if exists trg_tasks_audit_update on tasks;
            drop trigger if exists trg_tasks_audit_delete on tasks;

            create trigger trg_tasks_audit_insert
            after insert on tasks
            for each row execute function public.log_task_changes();

            create trigger trg_tasks_audit_update
            after update on tasks
            for each row execute function public.log_task_changes();

            create trigger trg_tasks_audit_delete
            after delete on tasks
            for each row execute function public.log_task_changes();
            """
        )
