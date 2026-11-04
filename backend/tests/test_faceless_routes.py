"""The Studio's routes: quotes in USD, idempotency, the checks a step passes, scripts, series,
and the consent gates on characters."""

import json

import pytest

from app.models.faceless import FacelessActivity, FacelessProject, FacelessStepRun
from app.models.usage_log import UsageLog
from app.services import fal_inputs, pricing as cp, storyscript as ss
from app.services.faceless import catalog, media, orchestrator

from test_faceless_support import (  # noqa: F401
    api, complete_step, fal, get_project, get_run, llm, make_project, png_bytes, scene, script_for, start,
    tick_until_done, walk_keys,
)

CONSENT = {"accepted": True, "text_version": catalog.CONSENT_TEXT_VERSION, "relationship": "self"}


def quote(client, pid, step, **params):
    response = client.get(f"/api/faceless/projects/{pid}/quote", params={"step": step, **params})
    assert response.status_code == 200, response.text
    return response.json()


def upload_photo(client, char_id):
    response = client.post(f"/api/faceless/characters/{char_id}/media",
                           files={"file": ("a.png", png_bytes((600, 900)), "image/png")})
    assert response.status_code == 200, response.text
    return response.json()


def real_person(client, photo=True):
    response = client.post("/api/faceless/characters", json={"name": "Mira", "kind": "real_person", "consent": CONSENT})
    assert response.status_code == 201, response.text
    return upload_photo(client, response.json()["id"]) if photo else response.json()


# --- Quotes ------------------------------------------------------------------

def test_quote_is_in_usd_with_the_reference_structure(owner_client, llm):
    pid = make_project(owner_client, llm)["id"]
    q = quote(owner_client, pid, "storyboard")
    assert set(q) == {"step", "usd", "breakdown", "assumptions", "scene_ids", "characters"}
    assert q["usd"] == pytest.approx(2 * cp.usd_for(cp.image_key(catalog.DEFAULT_T2I_MODEL, "1k")))
    assert set(q["breakdown"][0]) == {"label", "key", "unit", "units", "unit_usd", "usd", "count"}
    assert isinstance(q["usd"], float)
    assert q["scene_ids"] == ["s1", "s2"]


def test_post_quote_answers_like_get(owner_client, llm):
    pid = make_project(owner_client, llm)["id"]
    response = owner_client.post(f"/api/faceless/projects/{pid}/quote", json={"step": "voice"})
    assert response.status_code == 200
    assert response.json()["usd"] == quote(owner_client, pid, "voice")["usd"] > 0


@pytest.mark.parametrize("step", ["storyboard", "voice", "music", "thumbnails"])
def test_every_quoted_key_has_a_usd_cost(owner_client, llm, step):
    pid = make_project(owner_client, llm)["id"]
    for line in quote(owner_client, pid, step)["breakdown"]:
        assert line["key"] in cp.USD_COSTS


def test_default_models_and_voice_and_music_have_usd_costs():
    from app.services.faceless import pricing

    assert catalog.DEFAULT_T2I_MODEL in pricing.t2i_models()
    assert catalog.DEFAULT_EDIT_MODEL in pricing.edit_models()
    for key in (cp.ELEVEN_V4_KEY, cp.ELEVEN_MUSIC_KEY, cp.RENDER_MINUTE_KEY, cp.QA_VISION_CHECK_KEY):
        assert key in cp.USD_COSTS
    for resolution in catalog.CLIP_RESOLUTIONS:
        assert cp.video_key(catalog.H3_FAMILY, resolution) in cp.USD_COSTS


def test_a_render_has_no_provider_cost(owner_client, db, fal, llm):
    pid = make_project(owner_client, llm)["id"]
    complete_step(db, owner_client, pid, "storyboard")
    q = quote(owner_client, pid, "render")
    assert q["usd"] == 0.0
    assert any("no provider cost" in note for note in q["assumptions"])


def test_no_response_speaks_of_credits_or_plans(owner_client, db, fal, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    run = complete_step(db, client, pid, "storyboard")
    payloads = [client.get("/api/faceless/config").json(), quote(client, pid, "voice"), run,
                get_project(client, pid), client.get("/api/faceless/projects").json()]
    for payload in payloads:
        keys = set(walk_keys(payload))
        assert not {k for k in keys if "credit" in k.lower()}, keys
        assert "paid_plan" not in keys and "credits_refunded" not in keys
    assert {"estimated_usd", "usd_spent"} <= set(run)
    assert "usd_by_step" in get_project(client, pid)


def test_config_has_prices_in_usd_and_the_limits(owner_client):
    config = owner_client.get("/api/faceless/config").json()
    assert config["prices"][cp.ELEVEN_V4_KEY] == cp.usd_for(cp.ELEVEN_V4_KEY)
    assert config["limits"]["drafts_per_hour"] == catalog.DRAFTS_PER_HOUR
    assert config["models"]["default_t2i"] == catalog.DEFAULT_T2I_MODEL
    assert config["steps"] == list(catalog.STEPS)
    assert config["grade_looks"]


# --- Starting a step ---------------------------------------------------------

def test_expected_usd_is_optional_and_a_changed_estimate_is_refused(owner_client, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    url = f"/api/faceless/projects/{pid}/steps/storyboard"
    q = quote(client, pid, "storyboard")

    changed = client.post(url, json={"expected_usd": q["usd"] + 1})
    assert changed.status_code == 409
    assert changed.json()["code"] == "quote_changed"
    assert changed.json()["quote"]["usd"] == q["usd"]

    assert client.post(url, json={"expected_usd": q["usd"]}).status_code == 202


def test_a_step_starts_without_expected_usd(owner_client, llm):
    pid = make_project(owner_client, llm)["id"]
    assert owner_client.post(f"/api/faceless/projects/{pid}/steps/voice", json={}).status_code == 202


def test_a_repeated_key_returns_the_same_run(owner_client, db, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    url = f"/api/faceless/projects/{pid}/steps/storyboard"
    first = client.post(url, json={"idempotency_key": "abc"})
    second = client.post(url, json={}, headers={"Idempotency-Key": "abc"})
    assert first.status_code == 202 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert db.query(FacelessStepRun).count() == 1

    other = client.post(f"/api/faceless/projects/{pid}/steps/voice", json={"idempotency_key": "abc"})
    assert other.status_code == 409 and other.json()["code"] == "key_reused"


def test_one_active_run_per_step_and_render_waits_for_the_others(owner_client, db, fal, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    run = start(client, pid, "storyboard")
    again = client.post(f"/api/faceless/projects/{pid}/steps/storyboard", json={})
    assert again.status_code == 409 and again.json() == {
        "detail": again.json()["detail"], "code": "step_active", "run_id": run["id"]}
    tick_until_done(db, client, run["id"])

    voice = start(client, pid, "voice")
    render = client.post(f"/api/faceless/projects/{pid}/steps/render", json={})
    assert render.status_code == 409 and render.json()["code"] == "steps_active"
    tick_until_done(db, client, voice["id"])

    start(client, pid, "render", options={"resolution": "720p"})
    blocked = client.post(f"/api/faceless/projects/{pid}/steps/music", json={})
    assert blocked.status_code == 409 and blocked.json()["code"] == "render_active"


def test_a_step_with_nothing_to_do_says_so(owner_client, db, fal, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    complete_step(db, client, pid, "storyboard")
    again = client.post(f"/api/faceless/projects/{pid}/steps/storyboard", json={})
    assert again.status_code == 409 and again.json()["code"] == "nothing_to_do"
    # Asked for by name it runs again, and replaces the old file.
    old = get_project(client, pid)["scenes"][0]["stills"][0]["url"]
    complete_step(db, client, pid, "storyboard", scene_ids=["s1"])
    assert get_project(client, pid)["scenes"][0]["stills"][0]["url"] != old
    assert client.get(old).status_code == 404


def test_clips_need_a_still_and_a_render_needs_pictures(owner_client, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    clips = client.post(f"/api/faceless/projects/{pid}/steps/clips", json={})
    assert clips.status_code == 400 and clips.json()["code"] == "still_required"
    assert clips.json()["scene_ids"] == ["s2"]
    render = client.post(f"/api/faceless/projects/{pid}/steps/render", json={})
    assert render.status_code == 400 and render.json()["code"] == "visual_required"


def test_a_failed_check_does_not_leave_the_write_lock_held(owner_client, llm):
    """start_step takes the lock first: its refusals must let it go straight away."""
    from test_faceless_support import write_lock_is_free

    client = owner_client
    pid = make_project(client, llm)["id"]
    assert client.post(f"/api/faceless/projects/{pid}/steps/clips", json={}).status_code == 400
    assert write_lock_is_free()


def test_a_blocking_compliance_flag_stops_a_step(owner_client, db, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    project = db.query(FacelessProject).filter(FacelessProject.id == pid).one()
    project.compliance = {"flags": [{"severity": "block"}], "blocked": True, "script_version": 1}
    db.commit()
    response = client.post(f"/api/faceless/projects/{pid}/steps/storyboard", json={})
    assert response.status_code == 403 and response.json()["code"] == "compliance_block"


def test_the_hourly_cap_on_steps_is_a_fixed_sentence(owner_client, llm, monkeypatch):
    client = owner_client
    pid = make_project(client, llm)["id"]
    monkeypatch.setattr(catalog, "STEP_RUNS_PER_HOUR", 1)
    assert client.post(f"/api/faceless/projects/{pid}/steps/storyboard", json={}).status_code == 202
    capped = client.post(f"/api/faceless/projects/{pid}/steps/voice", json={})
    assert capped.status_code == 429 and capped.json()["code"] == "rate_limited"
    for word in ("plan", "upgrade", "credit"):
        assert word not in capped.json()["detail"].lower()


def test_routes_that_spend_money_are_rate_limited(owner_client, llm):
    client = owner_client
    project = client.post("/api/faceless/projects", json={"template_id": "reel", "length_seconds": 30}).json()
    codes = [client.post(f"/api/faceless/projects/{project['id']}/script", json={}).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_a_cancel_of_a_queued_run_closes_it_on_the_next_tick(owner_client, db, fal, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    run = start(client, pid, "storyboard")
    assert client.post(f"/api/faceless/runs/{run['id']}/cancel").json()["cancel_requested"]
    orchestrator.tick(db)
    done = get_run(client, run["id"])
    assert done["status"] == "cancelled"
    assert fal.submitted == []
    assert done["usd_spent"] == 0


def test_deleting_a_project_waits_for_its_run(owner_client, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    run = start(client, pid, "storyboard")
    response = client.delete(f"/api/faceless/projects/{pid}")
    assert response.status_code == 409 and response.json()["run_id"] == run["id"]


def test_unknown_ids_are_not_found(owner_client):
    assert owner_client.get("/api/faceless/projects/99").status_code == 404
    assert owner_client.get("/api/faceless/runs/99").status_code == 404
    assert owner_client.get("/api/faceless/series/99").status_code == 404
    assert owner_client.post("/api/faceless/projects/99/steps/voice", json={}).status_code == 404


# --- Projects and scripts ----------------------------------------------------

def test_project_checks_its_choices_and_length(owner_client):
    client = owner_client
    bad = [({"template_id": "nope"}, "unknown_template"),
           ({"template_id": "reel", "narrator_voice": "nope"}, "unknown_voice"),
           ({"template_id": "reel", "music_mood": "nope"}, "unknown_mood"),
           ({"template_id": "reel", "style": "nope"}, "unknown_style"),
           ({"template_id": "reel", "length_seconds": 170}, "invalid_length")]
    for body, code in bad:
        response = client.post("/api/faceless/projects", json=body)
        assert response.status_code == 400 and response.json()["code"] == code, body


def test_script_versions_save_restore_and_checks(owner_client, llm):
    client = owner_client
    project = make_project(client, llm)
    pid = project["id"]
    edited = dict(project["script"])
    edited["title"] = "A new title"
    saved = client.put(f"/api/faceless/projects/{pid}/script", json={"script": edited})
    assert saved.status_code == 200 and saved.json()["script_version"] == 2

    versions = client.get(f"/api/faceless/projects/{pid}/script/versions").json()
    assert versions["current"] == 2
    assert [v["version"] for v in versions["versions"]] == [2, 1]
    assert client.get(f"/api/faceless/projects/{pid}/script/versions/1").json()["script"]["title"] == "Harbour at dawn"

    restored = client.post(f"/api/faceless/projects/{pid}/script/versions/1/restore")
    assert restored.status_code == 200
    assert restored.json()["script_version"] == 3
    assert restored.json()["script"]["title"] == "Harbour at dawn"

    assert client.get(f"/api/faceless/projects/{pid}/compliance").json()["script_version"] == 3
    assert client.get(f"/api/faceless/projects/{pid}/originality").json()["script_version"] == 3
    assert client.get(f"/api/faceless/projects/{pid}/script/versions/9").status_code == 404


def test_a_script_is_validated_before_it_is_saved(owner_client, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    response = client.put(f"/api/faceless/projects/{pid}/script", json={"script": {"scenes": "nonsense"}})
    assert response.status_code == 400 and response.json()["code"] == "invalid_script"
    assert get_project(client, pid)["script_version"] == 1


def test_revising_a_scene_makes_a_new_version(owner_client, llm, monkeypatch):
    client = owner_client
    pid = make_project(client, llm)["id"]

    async def revise(_db, *, script, scene_id, instruction, **_kwargs):
        return ss.Scene.model_validate(scene(scene_id, 0, narration=f"Revised: {instruction}"))

    monkeypatch.setattr(ss, "revise_scene", revise)
    response = client.post(f"/api/faceless/projects/{pid}/scenes/s1/revise", json={"instruction": "shorter"})
    assert response.status_code == 200, response.text
    project = response.json()
    assert project["script_version"] == 2
    assert project["script"]["scenes"][0]["narration"] == "Revised: shorter"
    assert client.post(f"/api/faceless/projects/{pid}/scenes/nope/revise",
                       json={"instruction": "x"}).status_code == 404


def test_a_revision_loses_to_a_save_that_happened_meanwhile(owner_client, llm, monkeypatch):
    client = owner_client
    project = make_project(client, llm)
    pid = project["id"]

    async def revise(_db, *, scene_id, **_kwargs):
        edited = dict(project["script"])
        edited["title"] = "Saved meanwhile"
        assert client.put(f"/api/faceless/projects/{pid}/script", json={"script": edited}).status_code == 200
        return ss.Scene.model_validate(scene(scene_id, 0))

    monkeypatch.setattr(ss, "revise_scene", revise)
    response = client.post(f"/api/faceless/projects/{pid}/scenes/s1/revise", json={"instruction": "x"})
    assert response.status_code == 409 and response.json()["code"] == "script_changed"


def test_llm_errors_reach_the_user_as_sentences(owner_client, llm, monkeypatch):
    client = owner_client
    project = client.post("/api/faceless/projects", json={"template_id": "reel", "length_seconds": 30}).json()

    async def draft(_db, **_kwargs):
        raise ss.LLMCallFailed("secret upstream detail sk-123")

    monkeypatch.setattr(ss, "draft_script", draft)
    response = client.post(f"/api/faceless/projects/{project['id']}/script", json={})
    assert response.status_code == 502
    assert response.json()["code"] == "llm_call_failed"
    assert "secret" not in response.json()["detail"]


def test_scene_media_replaces_the_picture_a_scene_needs(owner_client, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    url = f"/api/faceless/projects/{pid}/scenes/s1/media"
    response = client.post(url, files={"file": ("a.png", png_bytes(), "image/png")})
    assert response.status_code == 200, response.text
    first = next(s for s in response.json()["scenes"] if s["scene_id"] == "s1")["user_media"]
    assert first["kind"] == "image" and client.get(first["url"]).status_code == 200

    # A replacement deletes the old file.
    response = client.post(url, files={"file": ("b.png", png_bytes(color=(1, 2, 3)), "image/png")})
    assert client.get(first["url"]).status_code == 404

    response = client.delete(url)
    assert response.status_code == 200
    assert next(s for s in response.json()["scenes"] if s["scene_id"] == "s1")["user_media"] is None
    assert client.delete(url).status_code == 404


def test_project_settings_merge_and_are_validated(owner_client, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    url = f"/api/faceless/projects/{pid}"
    assert client.put(url, json={"settings": {"caption_position": "upper"}}).status_code == 200
    project = client.put(url, json={"settings": {"selected_thumbnail": 2}}).json()
    assert project["settings"]["caption_position"] == "upper"
    assert project["selected_thumbnail"] == 2
    assert client.put(url, json={"settings": {"caption_highlight": "red"}}).status_code == 422
    bad_model = client.put(url, json={"settings": {"t2i_model": "not-a-model"}})
    assert bad_model.status_code == 400


def test_packaging_is_stored_and_thumbnails_start_as_a_step(owner_client, llm, monkeypatch):
    client = owner_client
    pid = make_project(client, llm)["id"]

    async def package(_db, **_kwargs):
        return ss.Packaging(titles=["A title"], description="About this.", first_line="Look.", disclosure_line="AI.")

    monkeypatch.setattr(ss, "package", package)
    plain = client.post(f"/api/faceless/projects/{pid}/package", json={})
    assert plain.status_code == 200, plain.text
    assert plain.json()["run"] is None
    assert plain.json()["packaging"]["script_version"] == 1

    usd = quote(client, pid, "thumbnails")["usd"]
    changed = client.post(f"/api/faceless/projects/{pid}/package", json={"thumbnails": True, "expected_usd": usd + 1})
    assert changed.status_code == 409 and changed.json()["code"] == "quote_changed"

    both = client.post(f"/api/faceless/projects/{pid}/package",
                       json={"thumbnails": True, "texts": ["A", "B", "C"], "expected_usd": usd})
    assert both.status_code == 200, both.text
    assert both.json()["run"]["step"] == "thumbnails"


def test_the_log_lists_what_happened_to_a_project(owner_client, llm):
    client = owner_client
    pid = make_project(client, llm)["id"]
    start(client, pid, "storyboard")
    kinds = [e["kind"] for e in client.get(f"/api/faceless/projects/{pid}/log").json()["events"]]
    assert kinds == ["draft", "step_run"]


# --- Series ------------------------------------------------------------------

def test_series_crud_and_episode_memory(owner_client, llm):
    client = owner_client
    created = client.post("/api/faceless/series", json={"title": "Harbour tales", "template_id": "reel",
                                                        "rules": ["x" * 400]})
    assert created.status_code == 201, created.text
    series = created.json()
    assert len(series["rules"][0]) == 300
    assert client.get("/api/faceless/series").json()["series"][0]["project_count"] == 0

    project = make_project(client, llm, series_id=series["id"])
    detail = client.get(f"/api/faceless/series/{series['id']}").json()
    assert [p["id"] for p in detail["projects"]] == [project["id"]]
    assert detail["episode_memory"][0]["project_id"] == project["id"], "a draft is remembered for the next one"

    updated = client.put(f"/api/faceless/series/{series['id']}", json={"tone": "Quiet"}).json()
    assert updated["tone"] == "Quiet" and updated["project_count"] == 1
    assert client.post("/api/faceless/series", json={"title": "x", "template_id": "nope"}).status_code == 400

    assert client.delete(f"/api/faceless/series/{series['id']}").json() == {"deleted": True}
    assert get_project(client, project["id"])["series_id"] is None, "projects stay, detached"


def test_deleting_a_project_forgets_its_episode(owner_client, llm):
    client = owner_client
    series = client.post("/api/faceless/series", json={"title": "Tales"}).json()
    project = make_project(client, llm, series_id=series["id"])
    client.delete(f"/api/faceless/projects/{project['id']}")
    assert client.get(f"/api/faceless/series/{series['id']}").json()["episode_memory"] == []


# --- Consent gates -----------------------------------------------------------

def test_a_real_person_needs_the_consent_text_to_be_created(owner_client):
    response = owner_client.post("/api/faceless/characters", json={"name": "Mira", "kind": "real_person"})
    assert response.status_code == 400 and response.json()["code"] == "consent_required"


def test_a_project_with_a_revoked_character_cannot_start_a_step(owner_client, db, llm):
    client = owner_client
    char = real_person(client)
    in_frame = scene("s1", 0)
    in_frame["shot"]["characters"] = [str(char["id"])]
    llm.script = script_for(scenes=[in_frame])
    pid = make_project(client, llm, cast_ids=[char["id"]])["id"]

    assert client.post(f"/api/faceless/characters/{char['id']}/consent/revoke").status_code == 200
    response = client.post(f"/api/faceless/projects/{pid}/steps/storyboard", json={})
    assert response.status_code == 403
    assert response.json()["code"] == "consent_required"
    assert db.query(FacelessStepRun).count() == 0
    revoked = db.query(FacelessActivity).filter(FacelessActivity.kind == "consent_revoked").one()
    assert revoked.character_id == char["id"], "the audit trail keeps the revocation"


def test_consent_revoked_during_a_run_stops_what_is_not_yet_sent(owner_client, db, fal, llm):
    client = owner_client
    char = real_person(client)
    many = []
    for i in range(catalog.MAX_IN_FLIGHT_PER_RUN + 1):
        shot = scene(f"s{i + 1}", i)
        shot["shot"]["characters"] = [str(char["id"])]
        many.append(shot)
    llm.script = script_for(scenes=many)
    pid = make_project(client, llm, cast_ids=[char["id"]])["id"]
    run = start(client, pid, "storyboard")
    fal.running = True
    orchestrator.tick(db)
    sent = len(fal.submitted)
    assert sent == catalog.MAX_IN_FLIGHT_PER_RUN

    client.post(f"/api/faceless/characters/{char['id']}/consent/revoke")
    fal.running = False
    tick_until_done(db, client, run["id"])
    assert len(fal.submitted) == sent, "nothing more was sent with this likeness"
    items = get_run(client, run["id"])["items"]
    stopped = [i for i in items if i["status"] == "cancelled"]
    assert len(stopped) == 1 and stopped[0]["code"] == "consent_required"
    assert "refund" not in stopped[0]["error"].lower()


def test_a_real_person_reference_stays_a_placeholder_in_the_database(owner_client, db, llm, monkeypatch):
    """A fal URL exists only for the request. The photo goes up to fal at submit time."""
    client = owner_client
    char = real_person(client)
    assert char["media"][0]["private"] is True
    assert char["media"][0]["url"].startswith("/api/faceless/characters/")

    uploaded, sent = [], []
    monkeypatch.setattr(fal_inputs, "upload_local_file", lambda path: uploaded.append(path) or "https://fal.test/up.png")
    monkeypatch.setattr(media, "fal_status", lambda *_a: "running")

    def submit(_db, _endpoint, arguments):
        sent.append(arguments)
        return "req-1"

    monkeypatch.setattr(media, "fal_submit", submit)
    response = client.post(f"/api/faceless/characters/{char['id']}/sheet", json={})
    assert response.status_code == 202, response.text
    run = response.json()
    orchestrator.tick(db)

    assert uploaded, "the private file was uploaded for the request"
    assert "https://fal.test/up.png" in str(sent[0])
    db.expire_all()
    stored = str(db.query(FacelessStepRun).filter(FacelessStepRun.id == run["id"]).one().items[0]["arguments"])
    assert media.PRIVATE_REF in stored
    assert "fal.test" not in stored


def test_sheet_needs_a_reference_and_quotes_in_usd(owner_client):
    client = owner_client
    char = client.post("/api/faceless/characters", json={"name": "Asha"}).json()
    assert client.get(f"/api/faceless/characters/{char['id']}/sheet/quote").status_code == 400
    upload_photo(client, char["id"])
    q = client.get(f"/api/faceless/characters/{char['id']}/sheet/quote").json()
    assert q["usd"] == cp.usd_for(cp.edit_key(catalog.DEFAULT_EDIT_MODEL))


def test_a_sheet_lands_on_the_character(owner_client, db, fal):
    client = owner_client
    char = client.post("/api/faceless/characters", json={"name": "Asha"}).json()
    upload_photo(client, char["id"])
    run = client.post(f"/api/faceless/characters/{char['id']}/sheet", json={}).json()

    blocked = client.delete(f"/api/faceless/characters/{char['id']}")
    assert blocked.status_code == 409 and blocked.json()["code"] == "step_active"

    done = tick_until_done(db, client, run["id"])
    assert done["status"] == "completed"
    media_roles = [m["role"] for m in client.get(f"/api/faceless/characters/{char['id']}").json()["media"]]
    assert media_roles == ["reference", "sheet"]
    assert db.query(UsageLog).count() == 1


def test_a_sheet_finished_after_consent_was_revoked_is_not_kept(owner_client, db, fal):
    client = owner_client
    char = real_person(client)
    run = client.post(f"/api/faceless/characters/{char['id']}/sheet", json={}).json()
    fal.running = True
    orchestrator.tick(db)
    client.post(f"/api/faceless/characters/{char['id']}/consent/revoke")
    fal.running = False
    done = tick_until_done(db, client, run["id"])
    assert done["status"] == "completed"
    assert client.get(f"/api/faceless/characters/{char['id']}").json()["media"] == []
    assert fal.downloads == [], "the likeness was not even fetched"
    assert db.query(UsageLog).count() == 1, "fal billed it all the same"


def test_a_step_on_someone_with_outdated_consent_is_refused(owner_client, db):
    from app.models.faceless import FacelessCharacter

    client = owner_client
    char = real_person(client)
    row = db.query(FacelessCharacter).filter(FacelessCharacter.id == char["id"]).one()
    row.consent_text_version = "old"
    db.commit()
    response = client.post(f"/api/faceless/characters/{char['id']}/sheet", json={})
    assert response.status_code == 403 and response.json()["code"] == "consent_required"


# --- Script changes while something is running ---------------------------------

def _edit(script: dict, change) -> dict:
    edited = json.loads(json.dumps(script))
    change(edited["scenes"])
    return edited


def _save(client, pid, script):
    return client.put(f"/api/faceless/projects/{pid}/script", json={"script": script})


def _in_flight(client, db, fal, llm, step="storyboard"):
    """A project with a paid request at the provider."""
    project = make_project(client, llm)
    run = start(client, project["id"], step)
    fal.running = True
    orchestrator.tick(db)
    assert fal.submitted
    return project, run


def _retext(scenes):
    scenes[0]["narration"] = "Completely new words for this scene."
    scenes[0]["shot"]["visual_prompt"] = "A lighthouse in a storm."


def _rekind(scenes):
    scenes[0]["shot"]["kind"] = "clip"
    scenes[1]["shot"]["kind"] = "still"


@pytest.mark.parametrize("change", [_retext, _rekind])
def test_text_and_kind_can_change_while_a_paid_item_is_in_flight(owner_client, db, fal, llm, change):
    client = owner_client
    project, run = _in_flight(client, db, fal, llm)
    pid = project["id"]

    response = _save(client, pid, _edit(project["script"], change))
    assert response.status_code == 200, response.text
    assert response.json()["script_version"] == 2

    fal.running = False
    done = tick_until_done(db, client, run["id"])
    assert done["status"] == "completed"
    after = get_project(client, pid)
    assert all(s["stills"][0]["url"] for s in after["scenes"]), "each picture lands on the scene it was made for"
    assert after["script"] == response.json()["script"], "the edit is still there when the results have landed"
    assert db.query(UsageLog).count() == 2
    assert fal.lock_violations == []


def test_the_storyboard_can_change_a_shot_and_use_own_media_during_its_own_run(owner_client, db, fal, llm):
    """What StoryboardStep.tsx sends: the project's script with one shot kind changed, also
    straight after an upload."""
    client = owner_client
    project, run = _in_flight(client, db, fal, llm)
    pid = project["id"]

    def save_shot_kind(current, scene_id, kind):
        script = dict(current["script"])
        script["scenes"] = [{**s, "shot": {**s["shot"], "kind": kind}} if s["id"] == scene_id else s
                            for s in script["scenes"]]
        return _save(client, pid, script)

    changed = save_shot_kind(get_project(client, pid), "s2", "card")
    assert changed.status_code == 200, changed.text

    uploaded = client.post(f"/api/faceless/projects/{pid}/scenes/s1/media",
                           files={"file": ("a.png", png_bytes(), "image/png")})
    assert uploaded.status_code == 200, uploaded.text
    own = save_shot_kind(uploaded.json(), "s1", "user_media")
    assert own.status_code == 200, own.text
    assert next(s for s in own.json()["scenes"] if s["scene_id"] == "s1")["shot"] == "user_media"

    fal.running = False
    assert tick_until_done(db, client, run["id"])["status"] == "completed"


def test_a_voice_clip_from_old_text_lands_but_is_not_used_for_the_new_text(owner_client, db, fal, llm):
    """The reason a text edit is safe during the voice step: clips carry a hash of their text."""
    client = owner_client
    project, run = _in_flight(client, db, fal, llm, step="voice")
    pid = project["id"]

    edited = _save(client, pid, _edit(project["script"], _retext))
    assert edited.status_code == 200, edited.text
    fal.running = False
    assert tick_until_done(db, client, run["id"])["status"] == "completed"

    scenes = {s["scene_id"]: s for s in get_project(client, pid)["scenes"]}
    assert scenes["s1"]["voice"][0]["current"] is False, "the old words must not play under the new text"
    assert scenes["s1"]["measured"] is False
    assert scenes["s2"]["voice"][0]["current"] is True, "the scene that did not change keeps its clip"
    # The changed line is voiced again, and only that one.
    q = quote(client, pid, "voice")
    assert q["scene_ids"] == ["s1"] and q["usd"] > 0
    assert db.query(UsageLog).count() == 2, "both clips were paid for"


def _add(scenes):
    scenes.append({**scenes[-1], "id": "s9", "index": len(scenes)})


def _remove(scenes):
    scenes.pop(0)


def _move(scenes):
    scenes.reverse()


def _rename(scenes):
    scenes[0]["id"] = "s9"


@pytest.mark.parametrize("change", [_add, _remove, _move, _rename])
@pytest.mark.parametrize("step", ["storyboard", "render"])
def test_scenes_cannot_be_added_removed_moved_or_renamed_during_a_step(owner_client, db, fal, llm, change, step):
    from test_faceless_support import write_lock_is_free

    client = owner_client
    project = make_project(client, llm)
    pid = project["id"]
    if step == "render":  # not paid, but a queued render reads the script when it starts
        complete_step(db, client, pid, "storyboard")
    run = start(client, pid, step)

    response = _save(client, pid, _edit(project["script"], change))
    assert response.status_code == 409
    assert response.json()["code"] == "steps_active"
    assert response.json()["run_ids"] == [run["id"]]
    assert "added, removed or moved" in response.json()["detail"]
    assert get_project(client, pid)["script_version"] == project["script_version"]
    assert write_lock_is_free(), "a refusal lets the write lock go"


def test_scenes_can_change_again_when_the_step_has_finished(owner_client, db, fal, llm):
    client = owner_client
    project = make_project(client, llm)
    pid = project["id"]
    run = start(client, pid, "storyboard")
    assert _save(client, pid, _edit(project["script"], _move)).status_code == 409
    tick_until_done(db, client, run["id"])
    assert _save(client, pid, _edit(project["script"], _move)).status_code == 200


def test_a_new_draft_or_an_old_version_cannot_land_during_a_step(owner_client, db, fal, llm):
    """Both replace every scene under the same ids: s1 of another draft is another scene, so
    comparing ids would let a picture land on the wrong story."""
    from test_faceless_support import write_lock_is_free

    client = owner_client
    project = make_project(client, llm)
    pid = project["id"]
    assert _save(client, pid, _edit(project["script"], _retext)).status_code == 200  # version 2, same ids
    run = start(client, pid, "storyboard")
    calls = llm.calls

    draft = client.post(f"/api/faceless/projects/{pid}/script", json={})
    restore = client.post(f"/api/faceless/projects/{pid}/script/versions/1/restore")
    for response, doing in ((draft, "drafting"), (restore, "restoring")):
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "steps_active"
        assert response.json()["run_ids"] == [run["id"]]
        assert doing in response.json()["detail"]
    assert llm.calls == calls, "the LLM was paid for a draft that cannot land"
    assert get_project(client, pid)["script_version"] == 2
    assert write_lock_is_free()

    tick_until_done(db, client, run["id"])
    assert client.post(f"/api/faceless/projects/{pid}/script/versions/1/restore").status_code == 200


def test_revising_one_scene_is_allowed_during_a_step(owner_client, db, fal, llm, monkeypatch):
    """It edits one scene in place: the same ids in the same order."""
    client = owner_client
    project, run = _in_flight(client, db, fal, llm)
    pid = project["id"]

    async def revise(_db, *, scene_id, **_kwargs):
        return ss.Scene.model_validate(scene(scene_id, 0, narration="Revised."))

    monkeypatch.setattr(ss, "revise_scene", revise)
    response = client.post(f"/api/faceless/projects/{pid}/scenes/s1/revise", json={"instruction": "shorter"})
    assert response.status_code == 200, response.text
    assert [s["id"] for s in response.json()["script"]["scenes"]] == ["s1", "s2"]
    fal.running = False
    assert tick_until_done(db, client, run["id"])["status"] == "completed"


def test_a_save_during_a_queued_draft_is_allowed_as_nothing_paid_is_on_its_way(owner_client, db, llm):
    client = owner_client
    project = make_project(client, llm)
    pid = project["id"]
    queued = client.post(f"/api/faceless/projects/{pid}/script", json={"background": True})
    assert queued.status_code == 202, queued.text
    assert _save(client, pid, _edit(project["script"], _move)).status_code == 200
    # But a second draft is the double click this guards against.
    again = client.post(f"/api/faceless/projects/{pid}/script", json={"background": True})
    assert again.status_code == 409 and again.json()["code"] == "script_active"
    assert again.json()["run_id"] == queued.json()["id"]
    inline = client.post(f"/api/faceless/projects/{pid}/script", json={})
    assert inline.status_code == 409 and inline.json()["code"] == "script_active"


def test_a_long_draft_cannot_start_under_a_running_step(owner_client, db, llm):
    client = owner_client
    project = client.post("/api/faceless/projects", json={
        "template_id": "reel", "length_seconds": 30}).json()
    pid = project["id"]
    assert client.put(f"/api/faceless/projects/{pid}/script", json={"script": script_for()}).status_code == 200
    start(client, pid, "storyboard")
    queued = client.post(f"/api/faceless/projects/{pid}/script", json={"background": True})
    assert queued.status_code == 409 and queued.json()["code"] == "steps_active"
    assert db.query(FacelessStepRun).filter(FacelessStepRun.step == "script").count() == 0


def _during_a_draft(client, llm_patch, monkeypatch, pid, while_drafting):
    """Run ``while_drafting`` while one inline draft sits in its LLM call, on another thread."""
    import threading

    reached, release = threading.Event(), threading.Event()
    calls = []

    async def draft(_db, **_kwargs):
        calls.append(1)
        reached.set()
        release.wait(20)
        return ss.Script.model_validate(script_for())

    monkeypatch.setattr(ss, "draft_script", draft)
    results = {}

    def first():
        results["first"] = client.post(f"/api/faceless/projects/{pid}/script", json={})

    thread = threading.Thread(target=first)
    thread.start()
    assert reached.wait(20), "the draft never reached the LLM"
    try:
        results["other"] = while_drafting()
    finally:
        release.set()
        thread.join(20)
    return results, calls


def test_a_double_click_pays_for_one_draft(owner_client, llm, monkeypatch):
    client = owner_client
    pid = client.post("/api/faceless/projects", json={"template_id": "reel", "length_seconds": 30}).json()["id"]
    results, calls = _during_a_draft(client, llm, monkeypatch, pid,
                                     lambda: client.post(f"/api/faceless/projects/{pid}/script", json={}))
    assert results["other"].status_code == 409
    assert results["other"].json()["code"] == "script_active"
    assert results["first"].status_code == 200, results["first"].text
    assert len(calls) == 1, "two LLM calls for one draft"
    assert get_project(client, pid)["script_version"] == 1


def test_no_step_can_start_during_an_inline_draft(owner_client, llm, monkeypatch):
    client = owner_client
    project = make_project(client, llm)
    pid = project["id"]

    def others():
        return {"step": client.post(f"/api/faceless/projects/{pid}/steps/storyboard", json={}),
                "queued": client.post(f"/api/faceless/projects/{pid}/script", json={"background": True}),
                "save": _save(client, pid, project["script"])}

    results, _calls = _during_a_draft(client, llm, monkeypatch, pid, others)
    for name in ("step", "queued"):
        assert results["other"][name].status_code == 409, name
        assert results["other"][name].json()["code"] == "script_active", name
    assert results["other"]["save"].status_code == 200, "nothing paid is on its way, so a save is harmless"
    assert results["first"].status_code == 200, results["first"].text
    # And the guard goes with the draft.
    assert client.post(f"/api/faceless/projects/{pid}/steps/storyboard", json={}).status_code == 202


def test_a_failed_draft_lets_go_of_its_guard(owner_client, monkeypatch):
    client = owner_client
    pid = client.post("/api/faceless/projects", json={"template_id": "reel", "length_seconds": 30}).json()["id"]

    async def draft(_db, **_kwargs):
        raise ss.LLMCallFailed("down")

    monkeypatch.setattr(ss, "draft_script", draft)
    assert client.post(f"/api/faceless/projects/{pid}/script", json={}).status_code == 502
    assert orchestrator._inline_drafts == set()


def test_the_inline_draft_checks_again_before_it_saves(owner_client, db, llm, monkeypatch):
    """A run that got in some other way must not have the script change under it."""
    client = owner_client
    project = make_project(client, llm)
    pid = project["id"]

    async def draft(_db, **_kwargs):
        row = FacelessStepRun(user_id=1, project_id=pid, step="voice", status="queued", idempotency_key="sneaked",
                              items=[], quote={}, options={}, scene_ids=[], estimated_usd=0, usd_spent=0)
        db.add(row)
        db.commit()
        return ss.Script.model_validate(script_for())

    monkeypatch.setattr(ss, "draft_script", draft)
    response = client.post(f"/api/faceless/projects/{pid}/script", json={})
    assert response.status_code == 409 and response.json()["code"] == "steps_active"
    assert get_project(client, pid)["script_version"] == 1


# --- The event loop ------------------------------------------------------------

def _write_routes():
    from app.routers import faceless as router_module

    for route in router_module.router.routes:
        if set(route.methods or ()) & {"POST", "PUT", "PATCH", "DELETE"}:
            yield route


def test_no_route_that_writes_runs_on_the_event_loop():
    """A route waiting for the write lock inside async def freezes the whole app."""
    import inspect

    offenders = [route.path for route in _write_routes() if inspect.iscoroutinefunction(route.endpoint)]
    assert offenders == []
    assert len(list(_write_routes())) > 20


@pytest.mark.parametrize("route", ["character", "character_media", "scene_media", "draft"])
def test_a_busy_writer_does_not_freeze_the_app(owner_client, db, llm, route):
    """Another connection holds the write lock while a write comes in: other requests must
    still be answered at once, and the write goes through when the lock is free."""
    import asyncio
    import sqlite3
    import time

    import httpx

    from app.config import settings
    from app.main import app

    client = owner_client
    project = client.post("/api/faceless/projects", json={"template_id": "reel", "length_seconds": 30}).json()
    pid = project["id"]
    photo = {"file": ("a.png", png_bytes((600, 900)), "image/png")}
    if route == "character":
        request = {"method": "POST", "url": "/api/faceless/characters", "json": {"name": "Asha"}}
    elif route == "character_media":
        char = client.post("/api/faceless/characters", json={"name": "Asha"}).json()
        request = {"method": "POST", "url": f"/api/faceless/characters/{char['id']}/media", "files": photo}
    elif route == "scene_media":
        assert client.put(f"/api/faceless/projects/{pid}/script", json={"script": script_for()}).status_code == 200
        request = {"method": "POST", "url": f"/api/faceless/projects/{pid}/scenes/s1/media", "files": photo}
    else:
        request = {"method": "POST", "url": f"/api/faceless/projects/{pid}/script", "json": {}}
    db.rollback()

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver",
                                     cookies=client.cookies) as http:
            writer = sqlite3.connect(settings.database_path, timeout=0)
            writer.execute("BEGIN IMMEDIATE")
            started = time.monotonic()
            try:
                waiting = asyncio.create_task(http.request(**request))
                await asyncio.sleep(0.3)  # the write reaches the lock
                other = await asyncio.wait_for(http.get("/api/faceless/voices"), timeout=5)
                elapsed = time.monotonic() - started
                assert not waiting.done(), "the write should still be waiting for the lock"
            finally:
                writer.rollback()
                writer.close()
            return elapsed, other, await waiting

    elapsed, other, written = asyncio.run(scenario())
    assert other.status_code == 200
    assert elapsed < 3, f"the app was frozen for {elapsed:.1f} s by a waiting write"
    assert written.status_code in (200, 201), written.text


# --- The character routes, now on the thread pool --------------------------------

def test_the_bible_route_calls_the_writer_and_stores_its_flags(owner_client, db, monkeypatch):
    client = owner_client
    char = client.post("/api/faceless/characters", json={"name": "Asha", "notes": "A fisher."}).json()
    upload_photo(client, char["id"])
    seen = {}

    async def describe(_db, *, name, image_urls, **_kwargs):
        seen.update(name=name, images=len(image_urls))
        return ss.CharacterBible(name=name, canonical_description="A young fisher.", likeness_clause="a young fisher")

    monkeypatch.setattr(ss, "describe_character", describe)
    response = client.post(f"/api/faceless/characters/{char['id']}/bible")
    assert response.status_code == 200, response.text
    assert response.json()["bible"]["likeness_clause"] == "a young fisher"
    assert seen == {"name": "Asha", "images": 1}, "the photo goes to the vision model"
    assert db.query(FacelessActivity).filter(FacelessActivity.kind == "bible").count() == 1


def test_a_character_video_is_probed_and_gives_frames_with_real_ffmpeg(owner_client):
    from test_faceless_support import mp4_bytes

    client = owner_client
    char = client.post("/api/faceless/characters", json={"name": "Asha"}).json()
    response = client.post(f"/api/faceless/characters/{char['id']}/media",
                           files={"file": ("a.mp4", mp4_bytes(), "video/mp4")})
    assert response.status_code == 200, response.text
    roles = [m["role"] for m in response.json()["media"]]
    assert roles[0] == "source_video" and roles.count("frame") == catalog.FRAMES_PER_CHARACTER_VIDEO
    for entry in response.json()["media"]:
        assert client.get(entry["url"]).status_code == 200

    # Removing the video takes its frames with it, and their files.
    source = response.json()["media"][0]
    frame_url = response.json()["media"][1]["url"]
    after = client.delete(f"/api/faceless/characters/{char['id']}/media/{source['id']}")
    assert after.status_code == 200 and after.json()["media"] == []
    assert client.get(frame_url).status_code == 404


def test_a_scene_video_upload_works_with_real_ffmpeg(owner_client, llm):
    from test_faceless_support import mp4_bytes

    client = owner_client
    pid = make_project(client, llm)["id"]
    response = client.post(f"/api/faceless/projects/{pid}/scenes/s1/media",
                           files={"file": ("a.mp4", mp4_bytes(), "video/mp4")})
    assert response.status_code == 200, response.text
    own = next(s for s in response.json()["scenes"] if s["scene_id"] == "s1")["user_media"]
    assert own["kind"] == "video" and own["duration"] > 1
    too_big_a_lie = client.post(f"/api/faceless/projects/{pid}/scenes/s1/media",
                                files={"file": ("a.txt", b"not media at all", "text/plain")})
    assert too_big_a_lie.status_code == 400


def test_revoking_consent_through_put_erases_the_files(owner_client, db):
    from app.models.faceless import FacelessCharacter

    client = owner_client
    char = real_person(client)
    row = db.query(FacelessCharacter).filter(FacelessCharacter.id == char["id"]).one()
    path = media.local_path(row.media[0], 1)
    import os

    assert os.path.exists(path)
    response = client.put(f"/api/faceless/characters/{char['id']}", json={"revoke_consent": True})
    assert response.status_code == 200, response.text
    assert response.json()["consent"]["status"] == "revoked"
    assert not os.path.exists(path), "nothing of the likeness stays stored"
    assert client.post(f"/api/faceless/characters/{char['id']}/consent", json=CONSENT).status_code == 200


def test_deleting_a_character_removes_its_files(owner_client, db):
    import os

    from app.models.faceless import FacelessCharacter

    client = owner_client
    char = client.post("/api/faceless/characters", json={"name": "Asha"}).json()
    upload_photo(client, char["id"])
    entry = db.query(FacelessCharacter).filter(FacelessCharacter.id == char["id"]).one().media[0]
    path = media.local_path(entry, 1)
    assert os.path.exists(path)
    db.rollback()
    assert client.delete(f"/api/faceless/characters/{char['id']}").json() == {"deleted": True}
    assert not os.path.exists(path)
    assert db.query(FacelessActivity).filter(FacelessActivity.kind == "character_deleted").count() == 1
