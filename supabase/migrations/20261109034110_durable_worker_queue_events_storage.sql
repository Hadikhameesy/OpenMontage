-- Durable worker queue, leases, event history, and private artifacts.
alter table public.jobs add column if not exists worker_id text,
 add column if not exists lease_token uuid, add column if not exists lease_expires_at timestamptz,
 add column if not exists max_attempts integer not null default 3 check (max_attempts between 1 and 10),
 add column if not exists idempotency_key text, add column if not exists cancel_requested_at timestamptz;
create unique index if not exists jobs_owner_idempotency_idx on public.jobs(owner_id,idempotency_key) where idempotency_key is not null;
create index if not exists jobs_lease_idx on public.jobs(status,lease_expires_at) where status in ('running','cancel_requested');
create table if not exists public.job_events (
 id bigint generated always as identity primary key, job_id uuid not null references public.jobs(id) on delete cascade,
 owner_id uuid not null references auth.users(id) on delete cascade, sequence bigint not null,
 event_type text not null check (char_length(event_type) between 1 and 80), stage text,
 progress integer check (progress between 0 and 100), message text, data jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), unique(job_id,sequence)
);
create index if not exists job_events_owner_job_idx on public.job_events(owner_id,job_id,sequence);
create table if not exists public.job_artifacts (
 id uuid primary key default gen_random_uuid(), job_id uuid not null references public.jobs(id) on delete cascade,
 owner_id uuid not null references auth.users(id) on delete cascade, bucket_id text not null default 'openmontage-private',
 object_path text not null, artifact_type text not null default 'output', content_type text,
 size_bytes bigint check (size_bytes is null or size_bytes >= 0), created_at timestamptz not null default now(),
 unique(bucket_id,object_path)
);
create index if not exists job_artifacts_owner_job_idx on public.job_artifacts(owner_id,job_id,created_at desc);
alter table public.job_events enable row level security;
alter table public.job_artifacts enable row level security;
create policy "owners can read their job events" on public.job_events for select to authenticated using (owner_id=(select auth.uid()));
create policy "owners can read their job artifacts" on public.job_artifacts for select to authenticated using (owner_id=(select auth.uid()));
grant select on public.job_events,public.job_artifacts to authenticated;
drop policy if exists "job owners can request cancellation" on public.jobs;
create policy "job owners can request cancellation" on public.jobs for update to authenticated
 using (owner_id=(select auth.uid()) and status in ('queued','running'))
 with check (owner_id=(select auth.uid()) and ((status='cancelled' and cancel_requested_at is null) or (status='cancel_requested' and cancel_requested_at is not null)));
insert into storage.buckets(id,name,public,file_size_limit) values('openmontage-private','openmontage-private',false,1073741824)
on conflict(id) do update set public=false;
create policy "owners read own OpenMontage objects" on storage.objects for select to authenticated
 using(bucket_id='openmontage-private' and (storage.foldername(name))[1]=(select auth.uid())::text);
create policy "owners upload own OpenMontage objects" on storage.objects for insert to authenticated
 with check(bucket_id='openmontage-private' and (storage.foldername(name))[1]=(select auth.uid())::text);
create or replace function public.claim_openmontage_job(p_worker_id text,p_lease_seconds integer default 120)
returns setof public.jobs language plpgsql security definer set search_path=public,pg_temp as $$
declare v_job_id uuid;
begin
 if p_worker_id is null or length(trim(p_worker_id))=0 or length(p_worker_id)>120 then raise exception 'invalid worker id'; end if;
 if p_lease_seconds<30 or p_lease_seconds>900 then raise exception 'invalid lease duration'; end if;
 update public.jobs set status='failed',error_code='worker_lease_expired',finished_at=now(),lease_token=null,lease_expires_at=null,worker_id=null
 where status in ('running','cancel_requested') and lease_expires_at<now() and attempt>=max_attempts;
 with candidate as (
  select id from public.jobs where status='queued' or (status='running' and lease_expires_at<now() and attempt<max_attempts)
  order by created_at for update skip locked limit 1
 )
 update public.jobs j set status='running',worker_id=p_worker_id,lease_token=gen_random_uuid(),
  lease_expires_at=now()+make_interval(secs=>p_lease_seconds),heartbeat_at=now(),
  started_at=coalesce(started_at,now()),attempt=attempt+1,error_code=null
 from candidate c where j.id=c.id returning j.id into v_job_id;
 if v_job_id is null then return; end if;
 return query select * from public.jobs where id=v_job_id;
end; $$;
create or replace function public.heartbeat_openmontage_job(p_job_id uuid,p_lease_token uuid,p_lease_seconds integer default 120,p_progress integer default null,p_stage text default null,p_message text default null)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare v_owner uuid; v_seq bigint;
begin
 update public.jobs set heartbeat_at=now(),lease_expires_at=now()+make_interval(secs=>greatest(30,least(p_lease_seconds,900))),
  progress=case when p_progress is null then progress else greatest(0,least(99,p_progress)) end,stage=coalesce(p_stage,stage)
 where id=p_job_id and lease_token=p_lease_token and status='running' returning owner_id into v_owner;
 if v_owner is null then return false; end if;
 select coalesce(max(sequence),0)+1 into v_seq from public.job_events where job_id=p_job_id;
 insert into public.job_events(job_id,owner_id,sequence,event_type,stage,progress,message)
 values(p_job_id,v_owner,v_seq,'stage.progress',p_stage,p_progress,p_message);
 return true;
end; $$;
create or replace function public.finish_openmontage_job(p_job_id uuid,p_lease_token uuid,p_result jsonb default '{}'::jsonb)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare v_owner uuid; v_seq bigint;
begin
 update public.jobs set status='completed',progress=100,result=coalesce(p_result,'{}'::jsonb),finished_at=now(),heartbeat_at=now(),
  lease_token=null,lease_expires_at=null,worker_id=null,stage='completed'
 where id=p_job_id and lease_token=p_lease_token and status='running' returning owner_id into v_owner;
 if v_owner is null then return false; end if;
 select coalesce(max(sequence),0)+1 into v_seq from public.job_events where job_id=p_job_id;
 insert into public.job_events(job_id,owner_id,sequence,event_type,stage,progress,message)
 values(p_job_id,v_owner,v_seq,'job.completed','completed',100,'Job completed');
 return true;
end; $$;
create or replace function public.fail_openmontage_job(p_job_id uuid,p_lease_token uuid,p_error_code text,p_retryable boolean default true)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare v_owner uuid; v_seq bigint; v_status text;
begin
 update public.jobs set status=case when p_retryable and attempt<max_attempts then 'queued' else 'failed' end,
  error_code=left(coalesce(p_error_code,'worker_error'),100),
  finished_at=case when p_retryable and attempt<max_attempts then null else now() end,
  lease_token=null,lease_expires_at=null,worker_id=null,heartbeat_at=now()
 where id=p_job_id and lease_token=p_lease_token and status='running' returning owner_id,status into v_owner,v_status;
 if v_owner is null then return false; end if;
 select coalesce(max(sequence),0)+1 into v_seq from public.job_events where job_id=p_job_id;
 insert into public.job_events(job_id,owner_id,sequence,event_type,message,data)
 values(p_job_id,v_owner,v_seq,case when v_status='queued' then 'job.retrying' else 'job.failed' end,'Worker reported a failure',
  jsonb_build_object('error_code',left(coalesce(p_error_code,'worker_error'),100)));
 return true;
end; $$;
revoke all on function public.claim_openmontage_job(text,integer) from public,anon,authenticated;
revoke all on function public.heartbeat_openmontage_job(uuid,uuid,integer,integer,text,text) from public,anon,authenticated;
revoke all on function public.finish_openmontage_job(uuid,uuid,jsonb) from public,anon,authenticated;
revoke all on function public.fail_openmontage_job(uuid,uuid,text,boolean) from public,anon,authenticated;
grant execute on function public.claim_openmontage_job(text,integer) to service_role;
grant execute on function public.heartbeat_openmontage_job(uuid,uuid,integer,integer,text,text) to service_role;
grant execute on function public.finish_openmontage_job(uuid,uuid,jsonb) to service_role;
grant execute on function public.fail_openmontage_job(uuid,uuid,text,boolean) to service_role;