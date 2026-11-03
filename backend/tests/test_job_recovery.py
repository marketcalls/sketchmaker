"""Temporary failures must not throw away a result the provider already billed for."""
import uuid

from fal_client.client import FalClientHTTPError
import httpx
import pytest

from app.models.content import GenerationJob
from app.services.fal_keys import FalKeyMissing
from app.services import job_state
from app.services.job_state import MAX_SERVER_ERROR_RETRIES, claim_job, fail_claimed_job, release_orphaned_claims
from app.services.scheduler_service import _fail_job


@pytest.fixture(autouse=True)
def owner(owner_client):
    """Jobs reference the owner's row. Job ids restart with each fresh database here, so
    the retry counter is cleared too."""
    job_state._server_errors.clear()


def _job(db, status="in_progress"):
    job = GenerationJob(job_id=uuid.uuid4().hex, user_id=1, request_id=uuid.uuid4().hex, status=status,
                        prompt="a red bicycle", model="test-model")
    db.add(job)
    db.commit()
    return job


def _http_error(code):
    return FalClientHTTPError("boom", code, {}, response=httpx.Response(code))


def _fail_claimed(db, job, exc):
    try:
        raise exc
    except Exception:
        return fail_claimed_job(db, GenerationJob, job.id, "It failed.")


def _status(db, job):
    db.expire_all()
    return db.query(GenerationJob).filter(GenerationJob.id == job.id).first().status


@pytest.mark.parametrize("exc", [
    httpx.ReadTimeout("slow"),
    httpx.ConnectError("offline"),
    FalKeyMissing("no key"),
    _http_error(401),
    _http_error(429),
    _http_error(503),
])
def test_temporary_failure_hands_a_claimed_job_back(seeded, exc):
    job = _job(seeded)
    assert claim_job(seeded, GenerationJob, job.id)
    assert _fail_claimed(seeded, job, exc) is False
    assert _status(seeded, job) == "in_progress"
    assert claim_job(seeded, GenerationJob, job.id), "the poller must be able to claim it again"


@pytest.mark.parametrize("exc", [_http_error(422), KeyError("images"), ValueError("bad result")])
def test_permanent_failure_fails_the_job(seeded, exc):
    job = _job(seeded)
    assert claim_job(seeded, GenerationJob, job.id)
    assert _fail_claimed(seeded, job, exc) is True
    assert _status(seeded, job) == "failed"


def test_repeated_server_errors_eventually_fail_the_job(seeded):
    job = _job(seeded)
    for _ in range(MAX_SERVER_ERROR_RETRIES):
        assert claim_job(seeded, GenerationJob, job.id)
        assert _fail_claimed(seeded, job, _http_error(500)) is False
    assert claim_job(seeded, GenerationJob, job.id)
    assert _fail_claimed(seeded, job, _http_error(500)) is True
    assert _status(seeded, job) == "failed"
    assert (GenerationJob.__name__, job.id) not in job_state._server_errors


def test_missing_key_does_not_fail_an_unclaimed_job_during_polling(seeded):
    job = _job(seeded)
    try:
        raise FalKeyMissing("no key")
    except Exception:
        assert _fail_job(seeded, GenerationJob, job.id, False, "It failed.") is False
    assert _status(seeded, job) == "in_progress"


def test_a_real_error_still_fails_an_unclaimed_job(seeded):
    job = _job(seeded)
    try:
        raise ValueError("bad")
    except Exception:
        assert _fail_job(seeded, GenerationJob, job.id, False, "It failed.") is True
    assert _status(seeded, job) == "failed"


def test_startup_releases_claims_left_by_the_last_run(seeded):
    job = _job(seeded)
    assert claim_job(seeded, GenerationJob, job.id)
    assert release_orphaned_claims(seeded) >= 1
    assert _status(seeded, job) == "in_progress"
