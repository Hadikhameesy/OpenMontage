from pathlib import Path
from types import SimpleNamespace

from cloud.worker import SupabaseWorkerClient


class FakeHTTP:
    def __init__(self):
        self.posts = []

    def post(self, url, *, data, headers, timeout):
        self.posts.append({"url": url, "headers": headers, "timeout": timeout})
        return SimpleNamespace(status_code=200)


def test_output_upload_uses_a_fresh_private_object_path_for_each_retry(tmp_path):
    client = SupabaseWorkerClient.__new__(SupabaseWorkerClient)
    client.url = "https://example.supabase.co"
    client.http = FakeHTTP()
    registered = []
    client.request = lambda method, path, body=None: registered.append((method, path, body))

    output = tmp_path / "openmontage-output.mp4"
    output.write_bytes(b"mp4-content" * 200)
    job = {"id": "job-1", "owner_id": "owner-1"}

    first = client.upload_artifact(job, str(output), artifact_type="output", content_type="video/mp4")
    second = client.upload_artifact(job, str(output), artifact_type="output", content_type="video/mp4")

    assert first["object_path"] != second["object_path"]
    assert first["object_path"].startswith("owner-1/job-1/")
    assert second["object_path"].startswith("owner-1/job-1/")
    assert first["object_path"].endswith("-openmontage-output.mp4")
    assert second["object_path"].endswith("-openmontage-output.mp4")
    assert all(post["headers"]["x-upsert"] == "false" for post in client.http.posts)
    assert len(registered) == 2
    assert all(row[0] == "POST" and row[1] == "job_artifacts" for row in registered)
