# Free cloud rendering worker

GitHub Actions checks the Supabase queue every five minutes and processes at
most one job per run. This is scheduled best-effort execution, not a continuously
running worker; queued jobs may wait until the next run.

## One-time setup

1. Open repository Settings → Secrets and variables → Actions.
2. Add a repository secret named `SUPABASE_SERVICE_ROLE_KEY` using the
   service-role key from Supabase Project Settings → API. Never put it in Git
   or browser configuration.
3. Enable GitHub Actions for the repository.
4. Open Actions → OpenMontage free cloud worker → Run workflow once for a test.

The trusted adapter assembles uploaded images/videos and an optional audio track
into MP4 using FFmpeg on a GitHub-hosted CPU runner. It does not generate new
AI video from text and does not call paid providers. Upload at least one image
or video. Supported aspect ratios are 16:9, 9:16, 1:1, and 4:5; default duration
is 30 seconds, maximum 60 seconds.

Scheduled runs can be delayed and are subject to GitHub Actions quotas. For
continuous low-latency rendering, deploy the same Docker worker on an always-on
host, which may not be free.
