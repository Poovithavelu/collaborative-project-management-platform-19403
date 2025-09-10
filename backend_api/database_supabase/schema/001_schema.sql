-- CollabTask core schema: users, organizations, memberships, projects, tasks, audit_log

-- Extensions (if not already enabled in Supabase; harmless if present)
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- Users table (app-managed, not Supabase Auth)
create table if not exists public.users (
    id uuid primary key default gen_random_uuid(),
    email text unique not null,
    password_hash text not null,
    full_name text,
    created_at timestamptz not null default now(),
    active_org_id uuid
);

-- Organizations
create table if not exists public.organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_at timestamptz not null default now(),
    owner_user_id uuid references public.users(id) on delete cascade
);

-- Memberships
create table if not exists public.memberships (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    org_id uuid not null references public.organizations(id) on delete cascade,
    role text not null default 'member',
    created_at timestamptz not null default now(),
    unique (user_id, org_id)
);

-- Projects
create table if not exists public.projects (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    name text not null,
    description text,
    created_by uuid references public.users(id) on delete set null,
    created_at timestamptz not null default now()
);

-- Tasks
create table if not exists public.tasks (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    project_id uuid references public.projects(id) on delete cascade,
    title text not null,
    description text,
    status text not null default 'todo',
    assignee_id uuid references public.users(id) on delete set null,
    created_by uuid references public.users(id) on delete set null,
    created_at timestamptz not null default now(),
    -- New: order index for drag/drop and lane ordering
    order_index integer
);

-- Audit log: captures mutative actions either from API middleware or DB triggers.
create table if not exists public.audit_log (
    id uuid primary key default gen_random_uuid(),
    occurred_at timestamptz not null default now(),
    user_id uuid,               -- may be null for system/trigger actions
    org_id uuid,                -- organizational context if applicable
    project_id uuid,            -- project context if applicable
    entity_type text not null,  -- e.g., 'task','project','comment','auth','system'
    entity_id uuid,             -- id of the affected entity if known
    action text not null,       -- e.g., 'create','update','delete','reorder','login'
    request_path text,          -- API path when available
    method text,                -- HTTP method when applicable
    details jsonb               -- extra info (changed fields, before/after, subset)
);

-- Helpful indexes
create index if not exists idx_memberships_user on public.memberships(user_id);
create index if not exists idx_memberships_org on public.memberships(org_id);
create index if not exists idx_projects_org on public.projects(org_id);
create index if not exists idx_tasks_org on public.tasks(org_id);
create index if not exists idx_tasks_project on public.tasks(project_id);
-- Composite indexes to support Kanban and drag reordering
create index if not exists idx_tasks_project_status_order on public.tasks(project_id, status, order_index);
create index if not exists idx_tasks_org_project_order on public.tasks(org_id, project_id, order_index);

-- Audit log helpful indexes
create index if not exists idx_audit_log_org on public.audit_log(org_id);
create index if not exists idx_audit_log_project on public.audit_log(project_id);
create index if not exists idx_audit_log_entity on public.audit_log(entity_type, entity_id);
create index if not exists idx_audit_log_time on public.audit_log(occurred_at);

-- DB trigger function and triggers for tasks table to log direct SQL changes
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
        v_details := jsonb_build_object(
            'new', to_jsonb(NEW)
        );
    elsif (TG_OP = 'UPDATE') then
        v_action := 'update';
        v_entity_id := NEW.id;
        v_org_id := NEW.org_id;
        v_project_id := NEW.project_id;
        v_details := jsonb_build_object(
            'old', to_jsonb(OLD),
            'new', to_jsonb(NEW)
        );
    elsif (TG_OP = 'DELETE') then
        v_action := 'delete';
        v_entity_id := OLD.id;
        v_org_id := OLD.org_id;
        v_project_id := OLD.project_id;
        v_details := jsonb_build_object(
            'old', to_jsonb(OLD)
        );
    end if;

    insert into public.audit_log (user_id, org_id, project_id, entity_type, entity_id, action, request_path, method, details)
    values (null, v_org_id, v_project_id, 'task', v_entity_id, v_action, null, null, v_details);

    return null;
end;
$$;

drop trigger if exists trg_tasks_audit_insert on public.tasks;
drop trigger if exists trg_tasks_audit_update on public.tasks;
drop trigger if exists trg_tasks_audit_delete on public.tasks;

create trigger trg_tasks_audit_insert
after insert on public.tasks
for each row execute function public.log_task_changes();

create trigger trg_tasks_audit_update
after update on public.tasks
for each row execute function public.log_task_changes();

create trigger trg_tasks_audit_delete
after delete on public.tasks
for each row execute function public.log_task_changes();

-- Note: RLS policies are defined in a separate file to allow environment-specific bindings.
