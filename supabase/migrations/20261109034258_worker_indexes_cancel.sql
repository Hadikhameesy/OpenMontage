-- Worker indexes and cooperative cancellation acknowledgement.
create index if not exists jobs_project_created_idx on public.jobs(project_id,created_at desc);
create index if not exists job_artifacts_job_created_idx on public.job_artifacts(job_id,created_at desc);
create or replace function public.cancel_openmontage_job(p_job_id uuid,p_lease_token uuid)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare v_owner uuid; v_seq bigint;
begin
 update public.jobs set status='cancelled',finished_at=now(),lease_token=null,lease_expires_at=null,worker_id=null,heartbeat_at=now()
 where id=p_job_id and lease_token=p_lease_token and status='cancel_requested' returning owner_id into v_owner;
 if v_owner is null then return false; end if;
 select coalesce(max(sequence),0)+1 into v_seq from public.job_events where job_id=p_job_id;
 insert into public.job_events(job_id,owner_id,sequence,event_type,message)
 values(p_job_id,v_owner,v_seq,'job.cancelled','Job cancelled by user');
 return true;
end; $$;
revoke all on function public.cancel_openmontage_job(uuid,uuid) from public,anon,authenticated;
grant execute on function public.cancel_openmontage_job(uuid,uuid) to service_role;