"""What happens when things fail: a paid result is never lost to a temporary failure, and a
restart resumes what was in flight."""

from datetime import datetime, timedelta

from fal_client.client import FalClientHTTPError
import httpx
import pytest
from sqlalchemy.exc import OperationalError

from app.models.faceless import FacelessStepRun
from app.models.usage_log import UsageLog
from app.services import job_state
from app.services.faceless import catalog, orchestrator, render_job, script_job
from app.services.fal_keys import FalKeyMissing

from test_faceless_support import (  # noqa: F401
    api, complete_step, fal, get_project, get_run, llm, make_project, png_bytes, scene, script_for, start,
    tick_until_done,
)


@pytest.fixture(autouse=True)
def no_wait_between_retries(monkeypatch):
    job_state._server_errors.clear()
    monkeypatch.setattr(orchestrator, "RETRY_SECONDS", 0)


def _http_error(code):
    return FalClientHTTPError("boom", code, {}, response=httpx.Response(code))


def _row(db, run_id) -> FacelessStepRun:
    db.expire_all()
    return db.query(FacelessStepRun).filter(FacelessStepRun.id == run_id).one()


def _usage(db) -> int:
    return db.query(UsageLog).count()


def _project_with_one_still(client, llm):
    llm.script = script_for(scenes=[scene("s1", 0)])
    return make_project(client, llm)["id"]


@pytest.mark.parametrize("error", [
    httpx.ConnectError("offline"), httpx.ReadTimeout("slow"), FalKeyMissing("no key"), _http_error(401),
    _http_error(429), _http_error(503),
])
def test_a_temporary_failure_hands_the_job_back_and_the_result_lands_later(owner_client, db, fal, llm, error):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)  # submitted
    assert fal.submitted

    fal.next_result_error = [error]
    orchestrator.tick(db)
    row = _row(db, run["id"])
    assert row.items[0]["status"] == "submitted"
    assert row.items[0]["request_id"] == "req-1"
    assert row.status == "running", "the claim must be released"
    assert _usage(db) == 0
    assert get_run(client, run["id"])["status"] == "running"

    orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "completed"
    assert _usage(db) == 1, "settled once"
    assert len(fal.submitted) == 1, "never asked fal to make it again"


def test_a_download_that_keeps_failing_never_loses_the_paid_result(owner_client, db, fal, llm):
    """More failures than any permanent limit: the item waits, and is then saved."""
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)

    for _ in range(catalog.MAX_POLL_ERRORS + orchestrator.MAX_HANDLE_ERRORS + 5):
        fal.next_download_error = [httpx.ConnectError("offline")]
        orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "running"
    assert _usage(db) == 0

    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"
    assert _usage(db) == 1
    assert len(fal.submitted) == 1


def test_status_checks_failing_for_a_long_time_do_not_fail_the_item(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    for _ in range(catalog.MAX_POLL_ERRORS + 5):
        fal.next_status_error = [httpx.ConnectError("offline")]
        orchestrator.tick(db)
    assert _row(db, run["id"]).items[0]["status"] == "submitted"
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"


def test_a_machine_asleep_past_the_timeout_still_collects_the_result(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    row = _row(db, run["id"])
    items = [dict(i) for i in row.items]
    items[0]["submitted_at"] = (datetime.utcnow() - timedelta(seconds=catalog.ITEM_TIMEOUT_SECONDS + 60)).isoformat()
    row.items = items
    db.commit()

    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"
    assert _usage(db) == 1


def test_a_request_fal_says_is_still_running_past_the_timeout_fails(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    row = _row(db, run["id"])
    items = [dict(i) for i in row.items]
    items[0]["submitted_at"] = (datetime.utcnow() - timedelta(seconds=catalog.ITEM_TIMEOUT_SECONDS + 60)).isoformat()
    row.items = items
    db.commit()

    fal.running = True
    orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "failed"
    assert "took too long" in done["error"]
    assert "credit" not in done["error"].lower()
    assert _usage(db) == 0


def _submitted_long_ago(db, run_id, delta: timedelta) -> None:
    row = _row(db, run_id)
    items = [dict(i) for i in row.items]
    items[0]["submitted_at"] = (datetime.utcnow() - delta).isoformat()
    row.items = items
    db.commit()


@pytest.mark.parametrize("failing", ["status", "result", "download"])
def test_a_laptop_waking_after_a_long_sleep_to_no_network_keeps_the_paid_result(owner_client, db, fal, llm, failing):
    """Asleep past every window, and the first call on waking hits a network error."""
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    _submitted_long_ago(db, run["id"], job_state.IN_FLIGHT_WINDOW + timedelta(hours=2))

    getattr(fal, f"next_{failing}_error").append(httpx.ConnectError("no network yet"))
    orchestrator.tick(db)
    assert _row(db, run["id"]).items[0]["status"] == "submitted"
    assert get_run(client, run["id"])["status"] == "running"

    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"
    assert _usage(db) == 1
    assert len(fal.submitted) == 1


def test_a_cancelled_run_stops_waiting_for_a_provider_that_stays_out_of_reach(owner_client, db, fal, llm):
    """A temporary error never ends an item by itself, so this is the way out, for example
    after the key was swapped for another account's and fal answers 403 for good."""
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    fal.next_status_error = [_http_error(403)]
    orchestrator.tick(db)
    assert client.post(f"/api/faceless/runs/{run['id']}/cancel").status_code == 200

    # Cancelled, but only just out of reach: a blip must not lose the result.
    fal.next_status_error = [_http_error(403)]
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "running"

    row = _row(db, run["id"])
    items = [dict(i) for i in row.items]
    items[0]["unreachable_since"] = (
        datetime.utcnow() - timedelta(seconds=orchestrator.CANCEL_GIVES_UP_SECONDS + 5)).isoformat()
    row.items = items
    db.commit()
    fal.next_status_error = [_http_error(403)]
    orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "cancelled"
    assert done["items"][0]["error"] == orchestrator.NOT_COLLECTED
    assert _usage(db) == 0


def test_a_good_answer_ends_a_run_of_being_out_of_reach(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    fal.next_status_error = [httpx.ConnectError("offline")]
    orchestrator.tick(db)
    assert "unreachable_since" in _row(db, run["id"]).items[0]
    fal.running = True
    orchestrator.tick(db)
    assert "unreachable_since" not in _row(db, run["id"]).items[0]


def test_scattered_5xx_answers_do_not_add_up_to_losing_a_paid_result(owner_client, db, fal, llm):
    """A long poll collects a few 5xx answers, then one more on the result. fal has billed it,
    and each of those failures was followed by a good answer. Exactly the limit on purpose:
    job_state forgets its count when the limit is passed, so more would step over the bug."""
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)

    for _ in range(job_state.MAX_SERVER_ERROR_RETRIES):
        fal.next_status_error = [_http_error(503)]
        orchestrator.tick(db)
        fal.running = True
        orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "running"

    fal.running = False
    fal.next_result_error = [_http_error(503)]
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "running", "a result fal billed was thrown away"

    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"
    assert _usage(db) == 1


def test_a_good_result_resets_only_its_own_phase(owner_client, db, fal, llm):
    """fal can keep answering 5xx for a run that truly failed while its status looks fine, so
    good status checks must not reset the count on the result."""
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    fal.next_status_error = [_http_error(503)] * 3
    for _ in range(3):
        orchestrator.tick(db)
    for _ in range(job_state.MAX_SERVER_ERROR_RETRIES):
        fal.next_result_error = [_http_error(500)]
        orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "running"
    fal.next_result_error = [_http_error(500)]
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "failed"


def _not_found():
    return _http_error(404)


def test_status_errors_only_count_in_a_row(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)

    def failing_ticks(count):
        for _ in range(count):
            fal.next_status_error = [_not_found()]
            orchestrator.tick(db)

    fal.running = True
    for _ in range(3):
        failing_ticks(catalog.MAX_POLL_ERRORS - 1)
        orchestrator.tick(db)  # a good answer
        assert "poll_errors" not in _row(db, run["id"]).items[0]
    assert get_run(client, run["id"])["status"] == "running", "more errors than the limit, but never in a row"

    failing_ticks(catalog.MAX_POLL_ERRORS)
    assert get_run(client, run["id"])["status"] == "failed"


def test_a_permanent_failure_fails_the_item_not_its_neighbours(owner_client, db, fal, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]  # two scenes, so two stills
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    fal.download_override["https://fal.test/req-1.png"] = b"this is not an image"
    for _ in range(orchestrator.MAX_HANDLE_ERRORS + 1):
        orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "partial"
    statuses = {i["id"]: i["status"] for i in done["items"]}
    assert statuses == {"i1": "failed", "i2": "done"}
    assert done["error"] == orchestrator.RESULT_UNUSABLE
    assert _usage(db) == 1, "the failed item is not recorded"
    assert done["usd_spent"] == pytest.approx(done["estimated_usd"] / 2)


def test_repeated_5xx_answers_are_retried_a_limited_number_of_times(owner_client, db, fal, llm):
    """fal can answer 5xx for a run that truly failed."""
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    for _ in range(job_state.MAX_SERVER_ERROR_RETRIES):
        fal.next_result_error = [_http_error(500)]
        orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "running", "the retries job_state allows are not used up yet"
    fal.next_result_error = [_http_error(500)]
    orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "failed"
    assert done["error"] == orchestrator.PROVIDER_FAILED


def test_a_definite_answer_from_fal_fails_at_once(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    fal.next_result_error = [_http_error(422)]
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "failed"


def test_a_temporary_failure_waits_before_trying_again(owner_client, db, fal, llm, monkeypatch):
    """job_state's limit on 5xx retries assumes a 30 second poll, and this tick runs every 5
    seconds: without the wait a one minute outage would use the limit up."""
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    monkeypatch.setattr(orchestrator, "RETRY_SECONDS", 30)
    fal.next_result_error = [_http_error(503)]
    orchestrator.tick(db)
    calls = fal.result_calls
    status_calls = fal.status_calls
    orchestrator.tick(db)
    assert (fal.result_calls, fal.status_calls) == (calls, status_calls), "still waiting"

    row = _row(db, run["id"])
    items = [dict(i) for i in row.items]
    items[0]["retry_at"] = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
    row.items = items
    db.commit()
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"


def test_a_content_filter_refusal_fails_at_once_with_its_own_sentence(owner_client, db, fal, llm):
    from app.clients.fal_client import CONTENT_FILTER_ERROR

    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    fal.next_result_error = [FalClientHTTPError(
        "blocked", 422, {}, response=httpx.Response(422, json={"detail": [{"type": "content_policy_violation"}]}))]
    orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "failed"
    assert done["error"] == CONTENT_FILTER_ERROR


def test_a_failed_commit_while_claimed_goes_back_through_fail_claimed_job(owner_client, db, fal, llm, monkeypatch):
    """The database stays locked for longer than busy_timeout at the worst moment."""
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)

    real_save = orchestrator._save
    calls = []

    def locked_save(rc, items):
        calls.append(1)
        raise OperationalError("UPDATE", {}, Exception("database is locked"))

    monkeypatch.setattr(orchestrator, "_save", locked_save)
    orchestrator.tick(db)
    assert calls
    assert _row(db, run["id"]).status == "in_progress"
    assert get_run(client, run["id"])["status"] == "running", "the API never shows job_state's own statuses"

    monkeypatch.setattr(orchestrator, "_save", real_save)
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"
    assert _usage(db) == 1, "what landed before the failure is not recorded again"
    assert len(fal.submitted) == 1


def test_a_locked_database_while_landing_keeps_the_result_at_fal(owner_client, db, fal, llm, monkeypatch):
    import os

    from app.config import settings

    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)

    real = orchestrator.apply_still

    def locked(rc, item, landed):
        raise OperationalError("UPDATE", {}, Exception("database is locked"))

    monkeypatch.setitem(orchestrator.APPLIERS, "still", locked)
    orchestrator.tick(db)
    assert _row(db, run["id"]).items[0]["status"] == "submitted"
    assert _usage(db) == 0
    # The copy stored for the failed attempt is removed, so no orphan piles up.
    folder = settings.static_dir / "images" / "1"
    assert not [n for n in os.listdir(folder) if n.startswith("fl_still")] if folder.exists() else True

    monkeypatch.setitem(orchestrator.APPLIERS, "still", real)
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"
    assert _usage(db) == 1


def test_a_permanent_failure_of_the_claim_itself_fails_the_run_and_closes_its_items(owner_client, db, fal, llm,
                                                                                     monkeypatch):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)

    def broken(rc, items):
        raise KeyError("a bug")

    monkeypatch.setattr(orchestrator, "_save", broken)
    orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "failed"
    assert done["error"] == orchestrator.RUN_FAILED
    assert all(i["status"] != "submitted" for i in done["items"])


def test_a_restart_resumes_a_claimed_run(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)

    # A worker wins the claim and the process dies before it lands anything.
    assert job_state.claim_job(db, FacelessStepRun, run["id"], from_states=orchestrator.CLAIMABLE)
    assert _row(db, run["id"]).status == "processing"
    assert get_run(client, run["id"])["status"] == "running"
    assert get_run(client, run["id"])["completed_at"] is None
    orchestrator.tick(db)
    assert _row(db, run["id"]).status == "processing", "a live claim is left alone"
    assert fal.result_calls == 0

    assert orchestrator.release_orphaned_claims(db) == 1
    assert _row(db, run["id"]).status == "in_progress"
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"
    assert _usage(db) == 1
    assert len(fal.submitted) == 1, "a restart polls the request it has, and never pays for a new one"


def test_a_claim_left_by_a_dead_thread_is_released_after_its_window(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    assert job_state.claim_job(db, FacelessStepRun, run["id"], from_states=orchestrator.CLAIMABLE)
    row = _row(db, run["id"])
    row.completed_at = datetime.utcnow() - job_state.PROCESSING_WINDOW - timedelta(minutes=1)
    db.commit()
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"


def test_a_restart_during_submission_keeps_polling_the_requests_it_has(owner_client, db, fal, llm):
    """Request ids are committed as fal returns them, one at a time."""
    client = owner_client
    pid = make_project(client, llm)["id"]
    run = start(client, pid, "storyboard")
    fal.next_submit_error = []
    real_submit = fal.submit
    seen = []

    def submit(db_, endpoint, arguments):
        request_id = real_submit(db_, endpoint, arguments)
        seen.append(request_id)
        if len(seen) == 2:
            # The first id must already be on disk when the second is being made.
            first = _other_session_items(run["id"])[0]
            assert first["request_id"] == "req-1" and first["status"] == "submitted"
        return request_id

    from app.services.faceless import media

    media.fal_submit = submit
    try:
        orchestrator.tick(db)
    finally:
        media.fal_submit = fal.submit
    assert len(seen) == 2

    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"
    assert len(fal.submitted) == 2


def _other_session_items(run_id):
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        return session.query(FacelessStepRun).filter(FacelessStepRun.id == run_id).one().items
    finally:
        session.close()


def test_temporary_submit_failures_retry_then_give_up_without_spending(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    fal.next_submit_error = [httpx.ConnectError("offline")]
    orchestrator.tick(db)
    assert _row(db, run["id"]).items[0]["status"] == "pending"
    row = _row(db, run["id"])
    items = [dict(i) for i in row.items]
    items[0]["first_submit_error_at"] = (
        datetime.utcnow() - timedelta(seconds=orchestrator.SUBMIT_RETRY_SECONDS + 5)).isoformat()
    row.items = items
    db.commit()
    fal.next_submit_error = [httpx.ConnectError("offline")]
    orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "failed"
    assert done["error"] == orchestrator.SUBMIT_FAILED
    assert _usage(db) == 0


def test_no_fal_key_fails_a_pending_item_at_once_and_says_where_to_fix_it(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    fal.next_submit_error = [FalKeyMissing("no key")]
    orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "failed"
    assert "Settings" in done["error"]


def test_a_missing_key_does_not_fail_what_is_already_at_the_provider(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    run = start(client, pid, "storyboard")
    orchestrator.tick(db)
    for _ in range(3):
        fal.next_status_error = [FalKeyMissing("no key")]
        orchestrator.tick(db)
    assert _row(db, run["id"]).items[0]["status"] == "submitted"
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "completed"


def test_cancel_stops_pending_items_and_keeps_what_was_already_paid_for(owner_client, db, fal, llm):
    client = owner_client
    many = [scene(f"s{i + 1}", i) for i in range(catalog.MAX_IN_FLIGHT_PER_RUN + 2)]
    llm.script = script_for(scenes=many)
    pid = make_project(client, llm)["id"]
    run = start(client, pid, "storyboard")
    fal.running = True
    orchestrator.tick(db)
    assert len(fal.submitted) == catalog.MAX_IN_FLIGHT_PER_RUN

    assert client.post(f"/api/faceless/runs/{run['id']}/cancel").json()["cancel_requested"] is True
    fal.running = False
    orchestrator.tick(db)
    done = get_run(client, run["id"])
    counts = [i["status"] for i in done["items"]]
    assert counts.count("done") == catalog.MAX_IN_FLIGHT_PER_RUN
    assert counts.count("cancelled") == 2
    assert done["status"] == "partial"
    assert len(fal.submitted) == catalog.MAX_IN_FLIGHT_PER_RUN


def test_a_render_left_running_by_a_dead_process_is_requeued_once_then_failed(owner_client, db, fal, llm, monkeypatch):
    from app import render

    client = owner_client
    pid = _project_with_one_still(client, llm)
    complete_step(db, client, pid, "storyboard")
    run = start(client, pid, "render", options={"resolution": "720p"})

    # A restart: the row says running, and nothing holds the slot.
    row = _row(db, run["id"])
    row.status = "running"
    row.attempts = 1
    db.commit()

    attempts = []

    def fail_like_a_crash(_timeline, _out, **_kwargs):
        attempts.append(_row(db, run["id"]).attempts)
        raise render.RenderError("ffmpeg fell over: /secret/path")

    monkeypatch.setattr(render, "render_timeline", fail_like_a_crash)
    render_job.render_tick(db)
    assert attempts == [2], "requeued and tried again"
    done = get_run(client, run["id"])
    assert done["status"] == "failed"
    assert "/secret" not in done["error"], "error text is a fixed sentence"
    assert "credit" not in done["error"].lower() and "refund" not in done["error"].lower()


def test_a_render_out_of_attempts_is_failed_not_requeued(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    complete_step(db, client, pid, "storyboard")
    run = start(client, pid, "render", options={"resolution": "720p"})
    row = _row(db, run["id"])
    row.status = "running"
    row.attempts = catalog.RENDER_MAX_ATTEMPTS
    db.commit()
    render_job.render_tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "failed"
    assert "stopped responding" in done["error"]


def test_a_render_cancelled_before_it_starts_is_closed(owner_client, db, fal, llm):
    client = owner_client
    pid = _project_with_one_still(client, llm)
    complete_step(db, client, pid, "storyboard")
    run = start(client, pid, "render", options={"resolution": "720p"})
    client.post(f"/api/faceless/runs/{run['id']}/cancel")
    assert render_job.render_tick(db) is None
    assert get_run(client, run["id"])["status"] == "cancelled"


def test_a_render_waits_for_the_slot(owner_client, db, fal, llm):
    from app.services.render_queue import render_slot

    client = owner_client
    pid = _project_with_one_still(client, llm)
    complete_step(db, client, pid, "storyboard")
    run = start(client, pid, "render", options={"resolution": "720p"})
    with render_slot("another studio"):
        assert render_job.render_tick(db) is None
    assert get_run(client, run["id"])["status"] == "queued"


def _long_form_project(client):
    response = client.post("/api/faceless/projects", json={
        "title": "Long", "idea": "A long one.", "template_id": "explainer", "length_seconds": 120, "aspect": "16:9"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_a_long_form_draft_is_queued_and_finished_by_the_scheduler(owner_client, db, llm):
    client = owner_client
    pid = _long_form_project(client)
    llm.script = script_for("explainer", aspect="16:9", length_seconds=120)
    response = client.post(f"/api/faceless/projects/{pid}/script", json={})
    assert response.status_code == 202, response.text
    run = response.json()
    assert run["step"] == "script" and run["status"] == "queued"
    # Paid steps wait for it.
    blocked = client.post(f"/api/faceless/projects/{pid}/steps/storyboard", json={})
    assert blocked.status_code == 409 and blocked.json()["code"] == "script_active"

    assert script_job.script_tick(db) == run["id"]
    assert get_run(client, run["id"])["status"] == "completed"
    assert get_project(client, pid)["script_version"] == 1


def test_a_draft_interrupted_by_a_restart_is_drafted_again_once(owner_client, db, llm):
    client = owner_client
    pid = _long_form_project(client)
    llm.script = script_for("explainer", aspect="16:9", length_seconds=120)
    run = client.post(f"/api/faceless/projects/{pid}/script", json={}).json()
    row = _row(db, run["id"])
    row.status = "running"
    row.attempts = 1
    db.commit()

    assert script_job.script_tick(db) == run["id"]
    assert get_run(client, run["id"])["status"] == "completed"


def test_a_draft_that_keeps_being_interrupted_fails_with_a_sentence(owner_client, db, llm):
    client = owner_client
    pid = _long_form_project(client)
    run = client.post(f"/api/faceless/projects/{pid}/script", json={}).json()
    row = _row(db, run["id"])
    row.status = "running"
    row.attempts = script_job.MAX_ATTEMPTS
    db.commit()
    assert script_job.script_tick(db) is None
    done = get_run(client, run["id"])
    assert done["status"] == "failed"
    assert done["items"][0]["code"] == "stalled"


def test_scheduler_entry_points_exist_and_are_registered():
    """A tick that is not registered never runs, and tests calling the functions would not notice."""
    from app.services.scheduler_service import JobScheduler

    scheduler = JobScheduler()
    scheduler.scheduler.start(paused=True)
    try:
        scheduler.schedule_job_processor()
        ids = {job.id for job in scheduler.scheduler.get_jobs()}
    finally:
        scheduler.scheduler.shutdown(wait=False)
    assert {"faceless_step_processor", "faceless_script_processor", "faceless_render_processor"} <= ids


# --- A cancel while a tick is running ----------------------------------------

def _during_first_submit(monkeypatch, fal, action):
    from app.services.faceless import media

    def submit(db_, endpoint, arguments):
        request_id = fal.submit(db_, endpoint, arguments)
        if len(fal.submitted) == 1:
            action()
        return request_id

    monkeypatch.setattr(media, "fal_submit", submit)


def test_a_cancel_during_a_tick_stops_the_next_request(owner_client, db, fal, llm, monkeypatch):
    client = owner_client
    pid = make_project(client, llm)["id"]  # two stills
    run = start(client, pid, "storyboard")
    _during_first_submit(monkeypatch, fal, lambda: client.post(f"/api/faceless/runs/{run['id']}/cancel"))
    fal.running = True
    orchestrator.tick(db)

    assert len(fal.submitted) == 1, "a request went out after the cancel"
    assert [i["status"] for i in get_run(client, run["id"])["items"]] == ["submitted", "cancelled"]
    assert fal.lock_violations == [], "reading the flag must not hold a write"

    fal.running = False
    orchestrator.tick(db)
    assert get_run(client, run["id"])["status"] == "partial", "what was already paid for still lands"
    assert _usage(db) == 1


def test_consent_revoked_during_a_tick_stops_the_next_request(owner_client, db, fal, llm, monkeypatch):
    client = owner_client
    consent_text = {"accepted": True, "text_version": catalog.CONSENT_TEXT_VERSION, "relationship": "self"}
    char = client.post("/api/faceless/characters",
                       json={"name": "Mira", "kind": "real_person", "consent": consent_text}).json()
    client.post(f"/api/faceless/characters/{char['id']}/media", files={"file": ("a.png", png_bytes((600, 900)), "image/png")})
    shots = [scene("s1", 0), scene("s2", 1)]
    for shot in shots:
        shot["shot"]["characters"] = [str(char["id"])]
    llm.script = script_for(scenes=shots)
    pid = make_project(client, llm, cast_ids=[char["id"]])["id"]
    run = start(client, pid, "storyboard")
    _during_first_submit(monkeypatch, fal, lambda: client.post(f"/api/faceless/characters/{char['id']}/consent/revoke"))
    fal.running = True
    orchestrator.tick(db)

    assert len(fal.submitted) == 1, "a likeness went out after its consent was revoked"
    second = get_run(client, run["id"])["items"][1]
    assert (second["status"], second["code"]) == ("cancelled", "consent_required")


# --- Cancelling a queued draft -----------------------------------------------

def test_a_draft_cancelled_before_it_starts_costs_nothing(owner_client, db, llm):
    client = owner_client
    pid = _long_form_project(client)
    llm.script = script_for("explainer", aspect="16:9", length_seconds=120)
    run = client.post(f"/api/faceless/projects/{pid}/script", json={}).json()
    assert client.post(f"/api/faceless/runs/{run['id']}/cancel").json()["cancel_requested"] is True

    script_job.script_tick(db)

    done = get_run(client, run["id"])
    assert done["status"] == "cancelled"
    assert done["items"][0]["status"] == "cancelled"
    assert llm.calls == 0, "the LLM was paid for a cancelled draft"
    assert get_project(client, pid)["script_version"] == 0


def test_a_draft_cancelled_during_the_llm_call_saves_no_version(owner_client, db, monkeypatch):
    from app.services import storyscript as ss

    client = owner_client
    pid = _long_form_project(client)
    holder = {}

    async def draft(_db, **_kwargs):
        client.post(f"/api/faceless/runs/{holder['run']}/cancel")
        return ss.Script.model_validate(script_for("explainer", aspect="16:9", length_seconds=120))

    monkeypatch.setattr(ss, "draft_script", draft)
    holder["run"] = client.post(f"/api/faceless/projects/{pid}/script", json={}).json()["id"]

    script_job.script_tick(db)

    assert get_run(client, holder["run"])["status"] == "cancelled"
    assert get_project(client, pid)["script_version"] == 0, "a cancelled draft replaced the script"


# --- A finisher that fails ---------------------------------------------------

def _music_project(client, llm):
    return _project_with_one_still(client, llm)


def test_a_failed_finisher_keeps_nothing_and_finishes_later_without_paying_again(owner_client, db, fal, llm, monkeypatch):
    client = owner_client
    pid = _music_project(client, llm)
    run = start(client, pid, "music")

    def half_done(rc, items):
        from app.services.faceless import media

        media.set_json(rc.project(), "music", {"tracks": [{"half": "written"}]})
        raise KeyError("a bug")

    monkeypatch.setitem(orchestrator.FINALIZERS, "music", half_done)
    orchestrator.tick(db)  # submitted
    orchestrator.tick(db)  # landed, finisher fails
    assert fal.lock_violations == []
    assert get_run(client, run["id"])["status"] == "running", "the run waits for its finisher"
    assert get_run(client, run["id"])["items"][0]["status"] == "done"
    db.expire_all()
    from app.models.faceless import FacelessProject

    assert db.query(FacelessProject).filter(FacelessProject.id == pid).one().music is None, "a partial write was kept"
    usage, submitted, downloads = _usage(db), len(fal.submitted), len(fal.downloads)
    assert usage == 1

    monkeypatch.setitem(orchestrator.FINALIZERS, "music", orchestrator.finish_music)
    orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "completed"
    assert get_project(client, pid)["music"]["tracks"]
    assert (_usage(db), len(fal.submitted), len(fal.downloads)) == (usage, submitted, downloads), "paid twice"


def test_a_failed_finisher_waits_between_tries(owner_client, db, fal, llm, monkeypatch):
    client = owner_client
    pid = _music_project(client, llm)
    start(client, pid, "music")
    calls = []

    def failing(_rc, _items):
        calls.append(1)
        raise KeyError("a bug")

    monkeypatch.setitem(orchestrator.FINALIZERS, "music", failing)
    orchestrator.tick(db)
    orchestrator.tick(db)
    assert len(calls) == 1
    monkeypatch.setattr(orchestrator, "RETRY_SECONDS", 30)
    orchestrator.tick(db)
    assert len(calls) == 1, "tried again at once, and every 5 seconds from then on"


def test_cancel_is_the_way_out_of_a_finisher_that_never_works(owner_client, db, fal, llm, monkeypatch):
    import os

    client = owner_client
    pid = _music_project(client, llm)
    run = start(client, pid, "music")

    def failing(_rc, _items):
        raise KeyError("a bug")

    monkeypatch.setitem(orchestrator.FINALIZERS, "music", failing)
    orchestrator.tick(db)
    orchestrator.tick(db)
    client.post(f"/api/faceless/runs/{run['id']}/cancel")
    orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "failed"
    assert done["error"] == orchestrator.RESULT_UNUSABLE

    # The paid file is listed only on the run: deleting the project must still remove it.
    from app.models.faceless import FacelessStepRun as Run
    from app.services.faceless import media

    db.expire_all()
    result = db.query(Run).filter(Run.id == run["id"]).one().items[0]["result"]
    path = media.local_path({"file": result["file"], "storage": result["storage"]}, 1)
    assert os.path.exists(path)
    assert client.delete(f"/api/faceless/projects/{pid}").status_code == 200
    assert not os.path.exists(path)
