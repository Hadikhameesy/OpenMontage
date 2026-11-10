from pathlib import Path
from threading import Event
from types import SimpleNamespace
import subprocess

import pytest

from cloud_worker_plugins.openmontage import execute


class FakeWorkerClient:
    def __init__(self, source: bytes = b"image-bytes"):
        self.source = source
        self.uploaded = None

    def input_artifacts(self, job):
        return [{
            "bucket_id": "openmontage-private",
            "object_path": "owner/job/source.png",
            "content_type": "image/png",
            "size_bytes": len(self.source),
        }]

    def download_artifact(self, artifact, destination):
        path = Path(destination)
        path.write_bytes(self.source)
        return path

    def upload_artifact(self, job, local_path, *, artifact_type, content_type):
        path = Path(local_path)
        self.uploaded = {
            "artifact_type": artifact_type,
            "content_type": content_type,
            "size_bytes": path.stat().st_size,
        }
        return self.uploaded


def test_free_executor_builds_and_uploads_mp4(monkeypatch, tmp_path):
    import cloud_worker_plugins.openmontage as renderer

    monkeypatch.setattr(renderer.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    def fake_ffmpeg(args, **kwargs):
        Path(args[-1]).write_bytes(b"mock-mp4-data" * 200)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_ffmpeg)
    client = FakeWorkerClient()
    progress = []

    result = execute(
        job={"id": "job-1", "payload": {"duration_seconds": 5}},
        project={"aspect_ratio": "9:16"},
        report_progress=lambda value, stage, message="": progress.append((value, stage)),
        stop_event=Event(),
        worker_client=client,
    )

    assert result["mode"] == "free_media_assembly"
    assert result["content_type"] == "video/mp4"
    assert result["aspect_ratio"] == "9:16"
    assert result["clips_used"] == 1
    assert client.uploaded["artifact_type"] == "output"
    assert client.uploaded["content_type"] == "video/mp4"
    assert progress[-1][1] == "finalizing"


def test_free_executor_requires_an_image_or_video(monkeypatch):
    import cloud_worker_plugins.openmontage as renderer

    monkeypatch.setattr(renderer.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    class EmptyWorker(FakeWorkerClient):
        def input_artifacts(self, job):
            return []

    with pytest.raises(ValueError, match="upload_media_required"):
        execute(
            job={"id": "job-2", "payload": {}},
            project={"aspect_ratio": "16:9"},
            report_progress=lambda *args: None,
            stop_event=Event(),
            worker_client=EmptyWorker(),
        )
