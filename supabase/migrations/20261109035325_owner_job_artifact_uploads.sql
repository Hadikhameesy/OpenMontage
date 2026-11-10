-- Allow owners to register input artifacts only for their own jobs.
create policy "owners can register their own job artifacts" on public.job_artifacts
for insert to authenticated
with check (
 owner_id = (select auth.uid())
 and exists (
  select 1 from public.jobs j
  where j.id = job_id and j.owner_id = (select auth.uid())
 )
);
grant insert on public.job_artifacts to authenticated;