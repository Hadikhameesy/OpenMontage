-- OpenMontage cloud control-plane persistence.
create extension if not exists pgcrypto;
create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  brief text not null check (char_length(brief) between 1 and 12000),
  pipeline_id text not null,
  aspect_ratio text not null default '16:9' check (aspect_ratio in ('16:9','9:16','1:1','4:5')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists projects_owner_created_idx on public.projects(owner_id,created_at desc);
create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  pipeline_id text not null,
  status text not null default 'queued' check (status in ('queued','running','completed','failed','cancel_requested','cancelled')),
  progress integer not null default 0 check (progress between 0 and 100),
  stage text, payload jsonb not null default '{}'::jsonb, result jsonb, error_code text,
  attempt integer not null default 0 check (attempt >= 0), heartbeat_at timestamptz,
  created_at timestamptz not null default now(), started_at timestamptz, finished_at timestamptz
);
create index if not exists jobs_owner_created_idx on public.jobs(owner_id,created_at desc);
create index if not exists jobs_queue_idx on public.jobs(status,created_at) where status='queued';
alter table public.projects enable row level security;
alter table public.jobs enable row level security;
create policy "project owners can read their projects" on public.projects for select to authenticated using (owner_id=(select auth.uid()));
create policy "project owners can create projects" on public.projects for insert to authenticated with check (owner_id=(select auth.uid()));
create policy "project owners can update their projects" on public.projects for update to authenticated using (owner_id=(select auth.uid())) with check (owner_id=(select auth.uid()));
create policy "project owners can delete their projects" on public.projects for delete to authenticated using (owner_id=(select auth.uid()));
create policy "job owners can read their jobs" on public.jobs for select to authenticated using (owner_id=(select auth.uid()));
create policy "job owners can create jobs" on public.jobs for insert to authenticated with check (
 owner_id=(select auth.uid()) and exists(select 1 from public.projects p where p.id=project_id and p.owner_id=(select auth.uid()))
);
create policy "job owners can request cancellation" on public.jobs for update to authenticated using (owner_id=(select auth.uid()) and status='queued') with check (owner_id=(select auth.uid()) and status='cancelled');
grant select,insert,update,delete on public.projects to authenticated;
grant select,insert,update on public.jobs to authenticated;