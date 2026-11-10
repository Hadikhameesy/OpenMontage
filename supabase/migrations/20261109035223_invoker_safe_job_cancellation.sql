-- Replace the cancellation SECURITY DEFINER RPC with an invoker-safe function.
drop policy if exists "job owners can request cancellation" on public.jobs;
revoke update on public.jobs from authenticated;
grant update (status, cancel_requested_at, finished_at) on public.jobs to authenticated;
create policy "owners cancel queued jobs" on public.jobs
for update to authenticated using (owner_id=(select auth.uid()) and status='queued')
with check (owner_id=(select auth.uid()) and status='cancelled' and cancel_requested_at is null);
create policy "owners request running job cancellation" on public.jobs
for update to authenticated using (owner_id=(select auth.uid()) and status='running')
with check (owner_id=(select auth.uid()) and status='cancel_requested' and cancel_requested_at is not null);
create or replace function public.request_openmontage_job_cancel(p_job_id uuid)
returns setof public.jobs language plpgsql set search_path=public,pg_temp as $$
begin
 update public.jobs set
  status=case when status='queued' then 'cancelled' else 'cancel_requested' end,
  cancel_requested_at=case when status='running' then now() else cancel_requested_at end,
  finished_at=case when status='queued' then now() else finished_at end
 where id=p_job_id and owner_id=(select auth.uid()) and status in ('queued','running');
 return query select * from public.jobs where id=p_job_id and owner_id=(select auth.uid());
end; $$;
revoke all on function public.request_openmontage_job_cancel(uuid) from public,anon;
grant execute on function public.request_openmontage_job_cancel(uuid) to authenticated;