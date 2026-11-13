from pathlib import Path


def test_studio_defers_jobs_until_all_uploads_are_finalized():
    source = (Path(__file__).parents[2] / "cloud" / "web" / "app.js").read_text(encoding="utf-8")
    create_job = source.index('body:JSON.stringify({defer_queue:true,options:{duration_seconds:30}})')
    upload_loop = source.index('for(const file of files)', create_job)
    finalize = source.index('complete-uploads', upload_loop)
    success_message = source.index('const queueNote=', finalize)

    assert create_job < upload_loop < finalize < success_message
    assert 'method:"POST"' in source[finalize - 90:finalize + 100]


def test_deployed_studio_bundle_uses_the_same_upload_gate():
    bundle = (Path(__file__).parents[2] / "supabase" / "functions" / "openmontage-studio" / "index.ts").read_text(encoding="utf-8")
    create_job = bundle.index('defer_queue:true')
    upload_loop = bundle.index('for(const file of files)', create_job)
    finalize = bundle.index('complete-uploads', upload_loop)
    success_message = bundle.index('const queueNote=', finalize)

    assert create_job < upload_loop < finalize < success_message
    assert 'method:"POST"' in bundle[finalize - 90:finalize + 100]
    assert '"/api/v1/jobs/"+j.id+"/artifacts"' in bundle
    assert 'a.artifact_type==="output"&&a.signedUrl' in bundle
