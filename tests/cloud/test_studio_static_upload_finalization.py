from pathlib import Path


def test_static_studio_defers_jobs_until_all_uploads_are_finalized():
    source = (Path(__file__).parents[2] / "studio" / "app.js").read_text(encoding="utf-8")
    create_job = source.index('body:JSON.stringify({defer_queue:true,options:{duration_seconds:30}})')
    upload_loop = source.index('for(const file of files)', create_job)
    finalize = source.index('complete-uploads', upload_loop)
    success_message = source.index('const queueNote=', finalize)

    assert create_job < upload_loop < finalize < success_message
    assert 'method:"POST"' in source[finalize - 90:finalize + 100]
    assert 'files.some(f=>f.type.startsWith("image/")||f.type.startsWith("video/"))' in source
    assert 'f.size>268435456' in source
