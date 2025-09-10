-- Row Level Security policies (draft). Adjust to your authn provider.
-- This version assumes application-level JWT with claim `user_id` and optional `active_org_id`.

-- Enable RLS
alter table public.users enable row level security;
alter table public.organizations enable row level security;
alter table public.memberships enable row level security;
alter table public.projects enable row level security;
alter table public.tasks enable row level security;

-- Helper function to get current user id from JWT
create or replace function auth.uid()
returns uuid
language sql stable
as $$
  select nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'user_id', '')::uuid;
$$;

-- Users: a user can see themself; admins may refine later
drop policy if exists "users_self_select" on public.users;
create policy "users_self_select"
on public.users
for select
using (id = auth.uid());

drop policy if exists "users_self_update" on public.users;
create policy "users_self_update"
on public.users
for update
using (id = auth.uid());

-- Organizations: visible to members
drop policy if exists "orgs_member_select" on public.organizations;
create policy "orgs_member_select"
on public.organizations
for select
using (
  exists(select 1 from public.memberships m where m.org_id = organizations.id and m.user_id = auth.uid())
);

-- Memberships: visible to the member and org members (for listing)
drop policy if exists "memberships_member_select" on public.memberships;
create policy "memberships_member_select"
on public.memberships
for select
using (
  user_id = auth.uid() or
  exists(select 1 from public.memberships m where m.org_id = memberships.org_id and m.user_id = auth.uid())
);

-- Projects: members can select/insert/update/delete within their org
drop policy if exists "projects_member_select" on public.projects;
create policy "projects_member_select"
on public.projects
for select
using (
  exists(select 1 from public.memberships m where m.org_id = projects.org_id and m.user_id = auth.uid())
);

drop policy if exists "projects_member_crud" on public.projects;
create policy "projects_member_crud"
on public.projects
for all
using (
  exists(select 1 from public.memberships m where m.org_id = projects.org_id and m.user_id = auth.uid())
)
with check (
  exists(select 1 from public.memberships m where m.org_id = projects.org_id and m.user_id = auth.uid())
);

-- Tasks: members can select/insert/update/delete within their org
drop policy if exists "tasks_member_select" on public.tasks;
create policy "tasks_member_select"
on public.tasks
for select
using (
  exists(select 1 from public.memberships m where m.org_id = tasks.org_id and m.user_id = auth.uid())
);

drop policy if exists "tasks_member_crud" on public.tasks;
create policy "tasks_member_crud"
on public.tasks
for all
using (
  exists(select 1 from public.memberships m where m.org_id = tasks.org_id and m.user_id = auth.uid())
)
with check (
  exists(select 1 from public.memberships m where m.org_id = tasks.org_id and m.user_id = auth.uid())
);
