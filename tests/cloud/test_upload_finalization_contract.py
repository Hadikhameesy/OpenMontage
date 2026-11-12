"""Contract checks for the cloud upload-finalization gate.

These are source-level safeguards; live Storage/RLS behavior still requires an
integration test against an isolated Supabase test project.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/20261112143000_upload_completion_gate.sql"
API = ROOT / "supabase/functions/openmontage-api/index.ts"


def test_deferred_jobs_are_not_claimed_before_upload_completion():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "uploads_complete boolean not null default true" in sql
    assert "status = 'queued' and uploads_complete is true" in sql
    assert "finalize_openmontage_job_uploads" in sql


def test_upload_finalizer_is_owner_scoped_and_checks_real_storage_objects():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "auth.uid()" in sql
    assert "left join storage.objects" in sql
    assert "a.owner_id = v_owner" in sql
    assert "v_visual_count < 1" in sql
    assert "v_missing_count > 0" in sql
    assert "metadata->>'size'" in sql
    assert "v_input_count > 12" in sql


def test_artifact_registration_is_limited_to_the_private_owner_job_prefix():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "bucket_id = 'openmontage-private'" in sql
    assert "artifact_type = 'input'" in sql
    assert "owner_id = (select auth.uid())" in sql
    assert "object_path like" in sql


def test_api_supports_deferred_creation_and_explicit_finalization():
    api = API.read_text(encoding="utf-8")
    assert "deferQueue=b.defer_queue===true" in api
    assert "uploads_complete:!deferQueue" in api
    assert "/complete-uploads" in api
    assert 'sb.rpc("finalize_openmontage_job_uploads"' in api
