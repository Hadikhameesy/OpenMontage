-- Restrict user job mutations to a narrow cancellation RPC.
drop policy if exists "job owners can request cancellation" on public.jobs;
revoke update on public.jobs from authenticated;
create or replace function public.request_openmontage_job_cancel(p_job_id uuid)
returns setof public.jobs language plpgsql security definer set search_path=public,pg_temp as $$
declare v_owner uuid; v_status text; v_seq bigint;
begin
 update public.jobs set
  status=case when status='queued' then 'cancelled' else 'cancel_requested' end,
  cancel_requested_at=case when status='running' then now() else cancel_requested_at end,
  finished_at=case when status='queued' then now() else finished_at end
 where id=p_job_id and owner_id=(select auth.uid()) and status in ('queued','running')
 returning owner_id,status into v_owner,v_status;
 if v_owner is null then return; end if;
 select coalesce(max(sequence),0)+1 into v_seq from public.job_events where job_id=p_job_id;
 insert into public.job_events(job_id,owner_id,sequence,event_type,message)
 values(p_job_id,v_owner,v_seq,case when v_status='cancelled' then 'job.cancelled' else 'job.cancel_requested' end,
  case when v_status='cancelled' then 'Queued job cancelled' else 'Cancellation requested' end);
 return query select * from public.jobs where id=p_job_id;
end; $$;
revoke all on function public.request_openmontage_job_cancel(uuid) from public,anon;
grant execute on function public.request_openmontage_job_cancel(uuid) to authenticated;