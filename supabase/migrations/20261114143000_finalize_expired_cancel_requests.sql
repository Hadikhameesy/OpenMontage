-- Finalize cancellation requests if the worker disappears before acknowledging them.
-- This prevents expired cancel_requested jobs from remaining stuck forever.
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

  -- A cancellation is terminal once its worker lease expires. Do not retry it.
  with expired_cancelled as (
    update public.jobs
       set status = 'cancelled',
           error_code = null,
           finished_at = now(),
           heartbeat_at = now(),
           lease_token = null,
           lease_expires_at = null,
           worker_id = null,
           stage = 'cancelled'
     where status = 'cancel_requested'
       and (lease_expires_at is null or lease_expires_at < now())
     returning id, owner_id
  ), event_rows as (
    select c.id, c.owner_id, coalesce(max(e.sequence), 0) + 1 as sequence
      from expired_cancelled c
      left join public.job_events e on e.job_id = c.id
     group by c.id, c.owner_id
  )
  insert into public.job_events (
    job_id, owner_id, sequence, event_type, stage, message, data
  )
  select id, owner_id, sequence, 'job.cancelled', 'cancelled',
         'Cancellation finalized after the worker lease expired',
         jsonb_build_object('reason', 'worker_lease_expired')
    from event_rows;

  -- Exhausted running jobs fail; cancelled jobs were handled separately above.
  update public.jobs
     set status = 'failed',
         error_code = 'worker_lease_expired',
         finished_at = now(),
         lease_token = null,
         lease_expires_at = null,
         worker_id = null,
         heartbeat_at = now()
   where status = 'running'
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
