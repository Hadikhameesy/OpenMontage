-- Gate worker claims until a deferred upload set has been fully stored and verified.
-- Default true preserves existing clients; the updated Studio opts into defer_queue.
alter table public.jobs
  add column if not exists uploads_complete boolean not null default true;

create index if not exists jobs_ready_queue_idx
  on public.jobs(created_at)
  where status='queued' and uploads_complete is true;

-- Prevent authenticated users from registering arbitrary buckets or paths that
-- the service-role worker would otherwise fetch with elevated privileges.
drop policy if exists "owners can register their own job artifacts" on public.job_artifacts;
create policy "owners can register their own job artifacts" on public.job_artifacts
for insert to authenticated
with check (
  owner_id = (select auth.uid())
  and bucket_id = 'openmontage-private'
  and artifact_type = 'input'
  and size_bytes between 1 and 268435456
  and array_length(string_to_array(object_path, '/'), 1) = 3
  and object_path like ((select auth.uid())::text || '/' || job_id::text || '/%')
  and exists (
    select 1 from public.jobs j
    where j.id = job_id and j.owner_id = (select auth.uid())
  )
);

-- This narrow RPC verifies that every registered input object exists, that at
-- least one visual input exists, and only then releases the job to the worker.
create or replace function public.finalize_openmontage_job_uploads(p_job_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public, storage, pg_temp
as $$
declare
  v_owner uuid := auth.uid();
  v_status text;
  v_complete boolean;
  v_input_count integer;
  v_visual_count integer;
  v_missing_count integer;
  v_seq bigint;
begin
  if v_owner is null then
    return false;
  end if;

  select status, uploads_complete
    into v_status, v_complete
    from public.jobs
   where id = p_job_id and owner_id = v_owner
   for update;

  if not found or v_status <> 'queued' then
    return false;
  end if;

  if v_complete then
    return true;
  end if;

  select
    count(*) filter (where a.artifact_type = 'input'),
    count(*) filter (
      where a.artifact_type = 'input'
        and a.content_type ~* '^(image|video)/'
    ),
    count(*) filter (where a.artifact_type = 'input' and o.name is null)
    into v_input_count, v_visual_count, v_missing_count
    from public.job_artifacts a
    left join storage.objects o
      on o.bucket_id = a.bucket_id and o.name = a.object_path
   where a.job_id = p_job_id
     and a.owner_id = v_owner
     and a.bucket_id = 'openmontage-private';

  if v_input_count < 1
     or v_input_count > 12
     or v_visual_count < 1
     or v_missing_count > 0 then
    return false;
  end if;

  update public.jobs
     set uploads_complete = true
   where id = p_job_id
     and owner_id = v_owner
     and status = 'queued'
     and uploads_complete is false;

  if not found then
    return false;
  end if;

  select coalesce(max(sequence), 0) + 1
    into v_seq
    from public.job_events
   where job_id = p_job_id;

  insert into public.job_events (
    job_id, owner_id, sequence, event_type, stage, progress, message
  ) values (
    p_job_id, v_owner, v_seq, 'job.uploads_ready', 'queued', 0,
    'All input uploads verified; job released to the worker'
  );

  return true;
end;
$$;

revoke all on function public.finalize_openmontage_job_uploads(uuid) from public, anon;
grant execute on function public.finalize_openmontage_job_uploads(uuid) to authenticated;

-- Legacy queued jobs remain claimable because uploads_complete defaults true.
-- Deferred jobs are invisible to the worker until the finalization RPC succeeds.
create or replace function public.claim_openmontage_job(
  p_worker_id text,
  p_lease_seconds integer default 120
)
returns setof public.jobs
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_job_id uuid;
begin
  if p_worker_id is null or length(trim(p_worker_id)) = 0 or length(p_worker_id) > 120 then
    raise exception 'invalid worker id';
  end if;
  if p_lease_seconds < 30 or p_lease_seconds > 900 then
    raise exception 'invalid lease duration';
  end if;

  update public.jobs
     set status = 'failed',
         error_code = 'worker_lease_expired',
         finished_at = now(),
         lease_token = null,
         lease_expires_at = null,
         worker_id = null
   where status in ('running', 'cancel_requested')
     and lease_expires_at < now()
     and attempt >= max_attempts;

  with candidate as (
    select id
      from public.jobs
     where (status = 'queued' and uploads_complete is true)
        or (status = 'running' and lease_expires_at < now() and attempt < max_attempts)
     order by created_at
     for update skip locked
     limit 1
  )
  update public.jobs j
     set status = 'running',
         worker_id = p_worker_id,
         lease_token = gen_random_uuid(),
         lease_expires_at = now() + make_interval(secs => p_lease_seconds),
         heartbeat_at = now(),
         started_at = coalesce(started_at, now()),
         attempt = attempt + 1,
         error_code = null
    from candidate c
   where j.id = c.id
   returning j.id into v_job_id;

  if v_job_id is null then
    return;
  end if;

  return query select * from public.jobs where id = v_job_id;
end;
$$;

revoke all on function public.claim_openmontage_job(text, integer) from public, anon, authenticated;
grant execute on function public.claim_openmontage_job(text, integer) to service_role;
