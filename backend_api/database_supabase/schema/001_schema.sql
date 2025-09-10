-- CollabTask core schema: users, organizations, memberships, projects, tasks

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
    created_at timestamptz not null default now()
);

-- Helpful indexes
create index if not exists idx_memberships_user on public.memberships(user_id);
create index if not exists idx_memberships_org on public.memberships(org_id);
create index if not exists idx_projects_org on public.projects(org_id);
create index if not exists idx_tasks_org on public.tasks(org_id);
create index if not exists idx_tasks_project on public.tasks(project_id);

-- Note: RLS policies are defined in a separate file to allow environment-specific bindings.
