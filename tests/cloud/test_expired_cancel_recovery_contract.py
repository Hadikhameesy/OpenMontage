from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/20261114143000_finalize_expired_cancel_requests.sql"


def test_expired_cancel_requests_become_terminal_cancelled_jobs():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "status = 'cancel_requested'" in sql
    assert "lease_expires_at is null or lease_expires_at < now()" in sql
    assert "set status = 'cancelled'" in sql
    assert "'job.cancelled'" in sql
    assert "'worker_lease_expired'" in sql


def test_cancelled_jobs_are_not_retried_or_marked_failed():
    sql = MIGRATION.read_text(encoding="utf-8")
    failed_section = sql.split("-- Exhausted running jobs fail", 1)[1].split("with candidate as", 1)[0]
    assert "where status = 'running'" in failed_section
    assert "status in ('running','cancel_requested')" not in failed_section
    assert "status = 'cancel_requested'" not in failed_section


def test_worker_claim_still_respects_upload_finalization_gate():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "status = 'queued' and uploads_complete is true" in sql
    assert "status = 'running' and lease_expires_at < now() and attempt < max_attempts" in sql
