"""Unit tests for the worker queue lifecycle without live Supabase."""
from cloud.worker import process_one


class FakeClient:
    def __init__(self):
        self.finished = []
        self.failed = []
        self.cancelled = []
        self.job_record = {
            "id": "job-1", "project_id": "project-1", "lease_token": "lease-1",
            "status": "running", "progress": 0, "stage": "claimed",
        }

    def claim(self, worker_id, lease_seconds):
        return self.job_record

    def project(self, project_id):
        return {"id": project_id, "name": "test", "brief": "test brief"}

    def job(self, job_id):
        return self.job_record

    def heartbeat(self, job, progress, stage, message):
        return True

    def finish(self, job, result):
        self.finished.append(result)
        return True

    def fail(self, job, code, retryable):
        self.failed.append((code, retryable))
        return True

    def cancel(self, job):
        self.cancelled.append(job["id"])
        return True


def test_worker_completes_trusted_executor_result():
    client = FakeClient()

    def executor(*, job, project, report_progress, stop_event):
        report_progress(25, "planning", "started")
        return {"artifact_count": 1}

    assert process_one(client, executor, "test-worker") is True
    assert client.finished == [{"artifact_count": 1}]
    assert client.failed == []


def test_worker_marks_executor_exceptions_failed():
    client = FakeClient()

    def executor(**kwargs):
        raise ValueError("invalid test input")

    assert process_one(client, executor, "test-worker") is True
    assert client.failed == [("valueerror", False)]
    assert client.finished == []


def test_worker_stops_when_queue_is_empty():
    class EmptyClient(FakeClient):
        def claim(self, worker_id, lease_seconds):
            return None

    client = EmptyClient()
    assert process_one(client, lambda **kwargs: {}, "test-worker") is False
