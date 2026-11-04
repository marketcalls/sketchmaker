"""The whole Studio: project to rendered video, with real ffmpeg and stubbed providers."""

import json

import pytest

from app import render
from app.models.content import Image, Video
from app.models.usage_log import UsageLog
from app.services import pricing as cp, render_queue
from app.services.faceless import render_job

from test_faceless_support import (  # noqa: F401
    api, complete_step, fal, get_project, get_run, llm, make_project, probe, start, static_path, walk_keys,
    write_lock_is_free,
)


def _render_and_check(db, client, project_id, monkeypatch, **options):
    """Render through the tick, proving no write and no slot rule is broken around ffmpeg."""
    seen = {}
    real = render.render_timeline

    def spy(timeline, out_path, **kwargs):
        seen["timeline"] = timeline
        seen["slot_held"] = render_queue.render_slot_busy()
        seen["lock_free"] = write_lock_is_free()
        return real(timeline, out_path, **kwargs)

    monkeypatch.setattr(render, "render_timeline", spy)
    run = start(client, project_id, "render", options={"resolution": "720p", **options})
    assert render_job.render_tick(db) == run["id"]
    run = get_run(client, run["id"])
    assert run["status"] == "completed", run
    assert seen["slot_held"], "render_timeline must run inside render_slot()"
    assert seen["lock_free"], "a write was held while ffmpeg ran"
    return run, seen["timeline"]


def test_project_to_rendered_video(owner_client, db, fal, llm, monkeypatch):
    client = owner_client
    project = make_project(client, llm)
    pid = project["id"]
    assert project["status"] == "scripted"
    assert project["script_version"] == 1

    complete_step(db, client, pid, "storyboard")
    project = get_project(client, pid)
    assert project["status"] == "producing"
    assert all(s["stills"] and s["stills"][0]["url"].startswith("/static/") for s in project["scenes"])

    voice = complete_step(db, client, pid, "voice")
    project = get_project(client, pid)
    assert project["timing_measured"] is True
    assert all(v["current"] and v["words"] for s in project["scenes"] for v in s["voice"])
    assert voice["usd_spent"] > 0

    complete_step(db, client, pid, "clips")
    project = get_project(client, pid)
    clip_scene = next(s for s in project["scenes"] if s["shot"] == "clip")
    assert clip_scene["clips"][0]["url"].startswith("/static/")
    # The still is handed to fal as its local URL: fal_inputs uploads it inside fal_submit.
    clip_args = next(args for endpoint, args in fal.submitted if "h3-max" in endpoint)
    assert clip_args["image_url"].startswith("/static/")

    complete_step(db, client, pid, "music")
    assert get_project(client, pid)["music"]["tracks"][0]["url"].startswith("/static/")

    _, timeline = _render_and_check(db, client, pid, monkeypatch)
    assert timeline["captions"]["words"], "the voice's word times should become captions"

    project = get_project(client, pid)
    assert project["status"] == "rendered"
    render_info = project["render"]
    assert render_info["url"] and render_info["thumbnail_url"]
    assert render_info["captions"] is True

    info = probe(static_path(render_info["url"]))
    streams = {s["codec_type"]: s for s in info["streams"]}
    assert streams["video"]["codec_name"] == "h264"
    assert (streams["video"]["width"], streams["video"]["height"]) == (720, 1280)
    assert "audio" in streams
    assert float(info["format"]["duration"]) == pytest.approx(project["total_seconds"], abs=0.5)
    assert client.get(render_info["url"]).status_code == 200

    video = db.query(Video).filter(Video.id == render_info["video_id"]).one()
    assert (video.video_type, video.model) == ("faceless", "faceless-studio")
    assert fal.lock_violations == []


def test_nothing_points_at_fal_after_the_steps(owner_client, db, fal, llm):
    """Rows keep local URLs. A fal URL is a request argument or a download, never stored."""
    pid = make_project(owner_client, llm)["id"]
    complete_step(db, owner_client, pid, "storyboard")
    complete_step(db, owner_client, pid, "voice")
    stored = json.dumps(get_project(owner_client, pid))
    runs = owner_client.get(f"/api/faceless/projects/{pid}/runs").json()
    assert "fal.test" not in stored
    assert "fal.test" not in json.dumps(runs)
    from app.models.faceless import FacelessProject, FacelessStepRun

    row = db.query(FacelessProject).filter(FacelessProject.id == pid).one()
    assert "fal.test" not in json.dumps(row.scene_assets)
    for run in db.query(FacelessStepRun).all():
        assert "fal.test" not in json.dumps(run.items)


def test_each_landed_item_is_recorded_once_in_usd(owner_client, db, fal, llm):
    pid = make_project(owner_client, llm)["id"]
    run = complete_step(db, owner_client, pid, "storyboard")
    rows = db.query(UsageLog).all()
    assert len(rows) == len(run["items"]) == 2
    assert {r.feature for r in rows} == {"faceless"}
    assert {r.job_id for r in rows} == {str(run["id"])}
    assert {r.model for r in rows} == {"blackforestlabs/flux-3/klein/text-to-image"}
    assert sum(r.usd for r in rows) == pytest.approx(run["estimated_usd"])
    assert run["usd_spent"] == pytest.approx(run["estimated_usd"])
    assert get_project(owner_client, pid)["usd_by_step"]["storyboard"] == pytest.approx(run["estimated_usd"])


def test_reference_clip_is_recorded_on_the_tokens_fal_reports(owner_client, db, fal, llm):
    """Estimated at the worst case, recorded at what fal says it used."""
    char = owner_client.post("/api/faceless/characters", json={"name": "Asha"}).json()
    from PIL import Image as PILImage
    import io

    buf = io.BytesIO()
    PILImage.new("RGB", (600, 900), (10, 90, 60)).save(buf, format="PNG")
    response = owner_client.post(f"/api/faceless/characters/{char['id']}/media",
                                 files={"file": ("a.png", buf.getvalue(), "image/png")})
    assert response.status_code == 200, response.text

    from test_faceless_support import scene, script_for

    with_cast = scene("s1", 0, kind="clip")
    with_cast["shot"]["characters"] = [str(char["id"])]
    llm.script = script_for(scenes=[with_cast])
    pid = make_project(owner_client, llm, cast_ids=[char["id"]])["id"]
    complete_step(db, owner_client, pid, "storyboard")
    run = complete_step(db, owner_client, pid, "clips", options={"mode": "reference"})
    item = run["items"][0]
    rows = db.query(UsageLog).filter(UsageLog.job_id == str(run["id"])).all()
    assert len(rows) == 1
    # 5000 tokens reported, 4096 included: 0.904k tokens over.
    seconds = rows[0].units
    expected = seconds * cp.usd_for(cp.video_key("h3-max", "768p")) + round(0.904 * 0.02, 4)
    assert rows[0].usd == pytest.approx(expected, abs=0.001)
    assert rows[0].usd <= item["usd"]


def test_thumbnails_become_gallery_images_with_a_drawn_headline(owner_client, db, fal, llm):
    pid = make_project(owner_client, llm)["id"]
    run = complete_step(db, owner_client, pid, "thumbnails", options={"texts": ["One", "Two", "Three"]})
    assert len(run["items"]) == 3
    project = get_project(owner_client, pid)
    assert [t["text"] for t in project["thumbnails"]] == ["One", "Two", "Three"]
    for thumb in project["thumbnails"]:
        assert owner_client.get(thumb["url"]).status_code == 200
        assert owner_client.get(thumb["raw_url"]).status_code == 200
    assert db.query(Image).filter(Image.art_style == "faceless_thumbnail").count() == 3


def test_a_fal_item_is_marked_done_only_with_its_file_on_disk(owner_client, db, fal, llm):
    pid = make_project(owner_client, llm)["id"]
    complete_step(db, owner_client, pid, "storyboard")
    project = get_project(owner_client, pid)
    for s in project["scenes"]:
        assert owner_client.get(s["stills"][0]["url"]).status_code == 200


def test_delete_project_removes_its_files_and_rows(owner_client, db, fal, llm, monkeypatch):
    import os

    client = owner_client
    pid = make_project(client, llm)["id"]
    complete_step(db, client, pid, "storyboard")
    complete_step(db, client, pid, "thumbnails")
    project = get_project(client, pid)
    still = static_path(project["scenes"][0]["stills"][0]["url"])
    thumb = static_path(project["thumbnails"][0]["url"])
    assert os.path.exists(still) and os.path.exists(thumb)

    assert client.delete(f"/api/faceless/projects/{pid}").json() == {"deleted": True}

    assert client.get(f"/api/faceless/projects/{pid}").status_code == 404
    assert not os.path.exists(still) and not os.path.exists(thumb)
    assert db.query(Image).filter(Image.art_style == "faceless_thumbnail").count() == 0


def test_quality_check_runs_after_the_result_and_does_not_hold_a_write(owner_client, db, fal, llm, monkeypatch):
    from app.services import quality_gate

    calls = []

    async def check_still(_blob, **kwargs):
        calls.append(write_lock_is_free())
        return {**quality_gate.nothing_to_check("still", "x"), "verdict": quality_gate.PASS, "reasons": []}

    monkeypatch.setattr(quality_gate, "available", lambda _db: True)
    monkeypatch.setattr(quality_gate, "check_still", check_still)
    pid = make_project(owner_client, llm)["id"]
    quote = owner_client.get(f"/api/faceless/projects/{pid}/quote", params={"step": "storyboard"}).json()
    assert any(line["key"] == cp.QA_VISION_CHECK_KEY for line in quote["breakdown"])

    run = complete_step(db, owner_client, pid, "storyboard")
    assert calls == [True, True]
    assert all(i["qa"] == "done" and i["qa_verdict"] == quality_gate.PASS for i in run["items"])
    # The usage log is fal only: the check is an LLM call that litellm_client logs.
    rows = db.query(UsageLog).filter(UsageLog.job_id == str(run["id"])).all()
    assert sum(r.usd for r in rows) == pytest.approx(2 * cp.usd_for(cp.image_key(
        "blackforestlabs/flux-3/klein/text-to-image", "1k")))
    assert run["usd_spent"] == pytest.approx(run["estimated_usd"])
    quality = get_project(owner_client, pid)["scenes"][0]["stills"][0]["quality"]
    assert quality["status"] == "done" and quality["verdict"] == quality_gate.PASS


def test_the_render_branches_the_happy_path_skips(owner_client, db, fal, llm, monkeypatch):
    """Cards, stat overlays, a user's own image and video, sound effects, every transition, a
    dramatization label and a landscape frame, all through the real engine. These build
    Timeline dicts by hand, so a wrong field would only show up here or in production."""
    from test_faceless_support import mp4_bytes, png_bytes, scene, script_for

    client = owner_client
    llm.script = script_for("reel", aspect="16:9", dramatization_label="Dramatized", scenes=[
        scene("s1", 0, stat={"value": "42%", "label": "of boats"}),
        scene("s2", 1, kind="card", on_screen_text="Meanwhile", transition_in="crossfade", sfx="whoosh"),
        scene("s3", 2, kind="user_media", transition_in="dip_black", sfx="hit"),
        scene("s4", 3, kind="user_media", transition_in="j_cut"),
        scene("s5", 4, transition_in="l_cut", on_screen_text="Later"),
    ])
    pid = make_project(client, llm, aspect="16:9", length_seconds=60)["id"]
    for sid, files in (("s3", ("a.png", png_bytes((1280, 720)), "image/png")),
                       ("s4", ("b.mp4", mp4_bytes(), "video/mp4"))):
        response = client.post(f"/api/faceless/projects/{pid}/scenes/{sid}/media", files={"file": files})
        assert response.status_code == 200, response.text
    complete_step(db, client, pid, "storyboard")
    complete_step(db, client, pid, "voice")
    response = client.put(f"/api/faceless/projects/{pid}", json={"settings": {
        "grade_look": "warm_film", "grade_strength": 0.5, "caption_highlight": "#00FF88", "caption_position": "middle"}})
    assert response.status_code == 200, response.text

    _, timeline = _render_and_check(db, client, pid, monkeypatch)

    kinds = {c["kind"] for c in timeline["clips"]}
    assert {"image", "video", "gradient"} <= kinds
    overlays = {o["kind"] for o in timeline["overlays"]}
    assert {"stat_card", "title_card", "outro_card", "text"} <= overlays
    assert {"sfx", "voice"} <= {a["role"] for a in timeline["audio"]}
    assert timeline["captions"]["highlight"] == "#00FF88"
    assert timeline["captions"]["position"] == "middle"

    project = get_project(client, pid)
    info = probe(static_path(project["render"]["url"]))
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1280, 720)
    assert float(info["format"]["duration"]) == pytest.approx(project["total_seconds"], abs=0.5)


def test_a_video_deleted_from_the_gallery_is_noticed_by_the_project(owner_client, db, fal, llm, monkeypatch):
    from test_faceless_support import scene, script_for

    client = owner_client
    llm.script = script_for(scenes=[scene("s1", 0)])
    pid = make_project(client, llm)["id"]
    complete_step(db, client, pid, "storyboard")
    _render_and_check(db, client, pid, monkeypatch)
    video_id = get_project(client, pid)["render"]["video_id"]
    db.query(Video).filter(Video.id == video_id).delete()
    db.commit()
    assert get_project(client, pid)["render"]["deleted"] is True


def test_render_option_music_false_is_honoured(owner_client, db, fal, llm, monkeypatch):
    from test_faceless_support import scene, script_for

    client = owner_client
    llm.script = script_for(scenes=[scene("s1", 0)])
    pid = make_project(client, llm)["id"]
    complete_step(db, client, pid, "storyboard")
    complete_step(db, client, pid, "music")
    seen = []

    def spy(timeline, _out_path, **_kwargs):
        seen.append(timeline)
        raise render.RenderCancelled("the timeline is all this test needs")

    monkeypatch.setattr(render, "render_timeline", spy)

    def roles(options):
        run = start(client, pid, "render", options={"resolution": "720p", **options})
        render_job.render_tick(db)
        assert get_run(client, run["id"])["status"] == "cancelled"
        return {a["role"] for a in seen[-1]["audio"]}

    assert "music" in roles({})
    assert "music" not in roles({"music": False})

    quote = client.get(f"/api/faceless/projects/{pid}/quote",
                       params={"step": "render", "options": json.dumps({"music": False})}).json()
    assert any("Music is off" in note for note in quote["assumptions"])


def test_a_text_edit_during_a_render_does_not_change_what_it_records(owner_client, db, fal, llm, monkeypatch):
    """Real ffmpeg. The edit lands, the video is the one asked for, and its transcript says what
    the video says."""
    from test_faceless_support import scene, script_for

    client = owner_client
    llm.script = script_for(scenes=[scene("s1", 0, narration="The words that were rendered.")])
    project = make_project(client, llm)
    pid = project["id"]
    complete_step(db, client, pid, "storyboard")
    complete_step(db, client, pid, "voice")
    real = render.render_timeline
    edited = {}

    def spy(timeline, out_path, **kwargs):
        script = json.loads(json.dumps(project["script"]))
        script["scenes"][0]["narration"] = "Words added after the render began."
        edited["response"] = client.put(f"/api/faceless/projects/{pid}/script", json={"script": script})
        return real(timeline, out_path, **kwargs)

    monkeypatch.setattr(render, "render_timeline", spy)
    run = start(client, pid, "render", options={"resolution": "720p"})
    render_job.render_tick(db)
    assert edited["response"].status_code == 200, edited["response"].text
    assert get_run(client, run["id"])["status"] == "completed"

    after = get_project(client, pid)
    assert after["script"]["scenes"][0]["narration"] == "Words added after the render began."
    video = db.query(Video).filter(Video.id == after["render"]["video_id"]).one()
    assert video.transcript == "The words that were rendered."
