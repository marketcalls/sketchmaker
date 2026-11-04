"""Story Room to Faceless Studio: the hand-off, and that what it sets reaches the render."""

from datetime import datetime, timedelta

import pytest

from app import render
from app.models.asset import UserAsset
from app.models.faceless import FacelessCharacter, FacelessProject
from app.models.story_room import StoryThread
from app.services import quality_gate
from app.services.faceless import media, orchestrator, render_job
from app.services.story_room.models import dump, normalize

from test_faceless_support import (  # noqa: F401
    api, complete_step, fal, get_project, get_run, png_bytes, probe, start, static_path, write_lock_is_free,
)


def stored_image(prefix="env", color=(120, 90, 40)) -> dict:
    return media.run_async(media.store_bytes(png_bytes(color=color), user_id=1, storage="images", prefix=prefix,
                                             ext=".png", content_type="image/png"))


def story(**overrides) -> dict:
    plate = overrides.pop("plate_url", None)
    raw = {
        "format": "story", "title": "The harbour", "logline": "A town wakes.", "synopsis": "Morning comes.",
        "aspect": "9:16", "target_seconds": 30, "language": "en",
        "look": {"visual_style": "warm film stock", "palette": "amber", "lighting": "low sun"},
        "characters": [{"key": "c1", "name": "Asha", "role": "lead", "description": "A young fisher in a blue coat."}],
        "environments": [{"key": "e1", "name": "Harbour", "description": "A small stone harbour.",
                          "time_of_day": "dawn", "image_url": plate, "image_approved": bool(plate)}],
        "scenes": [
            {"id": "sc1", "heading": "Harbour", "environment_key": "e1", "shots": [
                {"id": "s1.1", "type": "wide", "camera": "static", "duration_seconds": 3, "action": "Boats rest.",
                 "voiceover": "[softly] The town wakes *slowly*.", "characters": ["c1"], "on_screen_text": "Dawn"},
                {"id": "s1.2", "type": "close_up", "camera": "dolly_in", "duration_seconds": 4, "action": "She looks up.",
                 "characters": ["c1"], "transition_in": "smash_cut",
                 "dialogue": [{"character_key": "c1", "line": "It is time.", "delivery": "calm"}]},
            ]},
            {"id": "sc2", "heading": "Open sea", "shots": [
                {"id": "s2.1", "type": "wide", "camera": "static", "duration_seconds": 3, "action": "Open water.",
                 "voiceover": "And the day begins."},
            ]},
        ],
        **overrides,
    }
    return raw


def thread_for(db, doc: dict, **fields) -> int:
    normalized = normalize(doc)
    thread = StoryThread(user_id=1, title=normalized.title or "Story", format=normalized.format,
                         story=dump(normalized), story_version=1, **fields)
    db.add(thread)
    db.commit()
    return thread.id


def hand_off(client, thread_id: int, **body) -> dict:
    response = client.post(f"/api/story-room/threads/{thread_id}/to-faceless", json=body)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"project_id"}
    return get_project(client, response.json()["project_id"])


def test_a_shot_list_becomes_a_scripted_project_with_no_provider_call(owner_client, db, fal):
    project = hand_off(owner_client, thread_for(db, story()))
    assert project["status"] == "scripted"
    assert project["script_version"] == 1
    assert project["usd_by_step"] == {}
    assert fal.submitted == [] and fal.status_calls == 0

    scenes = project["script"]["scenes"]
    assert [s["id"] for s in scenes] == ["s1", "s2", "s3"]
    assert scenes[0]["shot"]["kind"] == "still" and scenes[1]["shot"]["kind"] == "clip"
    assert scenes[0]["narration"] == "The town wakes .", "no stage directions are read aloud"
    assert scenes[0]["on_screen_text"] == "Dawn"
    assert scenes[1]["transition_in"] == "cut" and scenes[1]["sfx"] == "hit", "a smash cut lands on a hit"
    assert scenes[1]["dialogue"][0]["text"] == "It is time."
    assert project["script"]["model"] == "story_room"
    # The same checks a script saved in the Studio gets.
    assert project["compliance"]["script_version"] == 1
    assert project["originality"]["script_version"] == 1


def test_unsaved_characters_are_saved_and_linked_in_the_story(owner_client, db):
    thread_id = thread_for(db, story())
    project = hand_off(owner_client, thread_id)

    char = db.query(FacelessCharacter).one()
    assert (char.name, char.kind) == ("Asha", "fictional")
    assert project["cast_ids"] == [char.id]
    assert project["script"]["scenes"][0]["shot"]["characters"] == [str(char.id)]

    db.expire_all()
    thread = db.query(StoryThread).filter(StoryThread.id == thread_id).one()
    assert thread.story["characters"][0]["ref_id"] == char.id
    assert thread.story_version == 2

    # A second hand-off finds the character instead of saving it again.
    hand_off(owner_client, thread_id)
    assert db.query(FacelessCharacter).count() == 1
    db.expire_all()
    assert db.query(StoryThread).filter(StoryThread.id == thread_id).one().story_version == 2


def test_an_approved_place_sets_the_look_and_the_plates(owner_client, db):
    plate = stored_image()
    project = hand_off(owner_client, thread_for(db, story(plate_url=plate["url"])))
    settings_ = project["settings"]
    assert settings_["grade_look"] == "warm_film", "the story's look words pick a house look"
    assert settings_["grade_match"] is True
    # One scene per shot: the two shots at the harbour have the plate, the open sea has not.
    assert settings_["grade_plates"] == {"s1": {"file": plate["file"], "storage": "images"},
                                         "s2": {"file": plate["file"], "storage": "images"}}


def test_no_approved_place_means_no_matching(owner_client, db):
    settings_ = hand_off(owner_client, thread_for(db, story()))["settings"]
    assert "grade_plates" not in settings_ and "grade_match" not in settings_


def test_grade_plates_reach_the_render(owner_client, db, fal, monkeypatch):
    """Real ffmpeg: the engine matches the plate's colour on the clips of those scenes."""
    client = owner_client
    plate = stored_image()
    pid = hand_off(client, thread_for(db, story(plate_url=plate["url"])))["id"]
    complete_step(db, client, pid, "storyboard")
    complete_step(db, client, pid, "voice")
    complete_step(db, client, pid, "clips")

    seen = {}
    real = render.render_timeline

    def spy(timeline, out_path, **kwargs):
        seen["timeline"] = timeline
        seen["refs"] = {c.get("match_ref") for c in timeline["clips"]}
        import os

        seen["plate_on_disk"] = all(os.path.isfile(r) for r in seen["refs"] if r)
        seen["lock_free"] = write_lock_is_free()
        return real(timeline, out_path, **kwargs)

    monkeypatch.setattr(render, "render_timeline", spy)
    run = start(client, pid, "render", options={"resolution": "720p"})
    assert render_job.render_tick(db) == run["id"]
    assert get_run(client, run["id"])["status"] == "completed", get_run(client, run["id"])

    timeline = seen["timeline"]
    assert timeline["grade"]["look"] == "warm_film"
    assert timeline["grade"]["match"] is True
    assert seen["plate_on_disk"] and seen["lock_free"]
    matched = [c for c in timeline["clips"] if c.get("match_ref")]
    # Scenes s1 and s2 are matched; s3 (the open sea) and the outro are not.
    assert len(matched) == 2
    assert all(c["match_ref"].endswith(plate["file"]) for c in matched)
    assert len([c for c in timeline["clips"] if c["kind"] in ("image", "video") and not c.get("match_ref")]) == 2

    info = probe(static_path(get_project(client, pid)["render"]["url"]))
    assert {s["codec_type"] for s in info["streams"]} == {"video", "audio"}


def test_turning_match_clips_off_keeps_the_look_and_drops_the_plates(owner_client, db, fal, monkeypatch):
    client = owner_client
    plate = stored_image()
    pid = hand_off(client, thread_for(db, story(plate_url=plate["url"])))["id"]
    complete_step(db, client, pid, "storyboard")

    response = client.put(f"/api/faceless/projects/{pid}", json={"settings": {"grade_match": False}})
    assert response.status_code == 200
    assert response.json()["settings"]["grade_plates"], "the plates stay for when it is turned on again"

    seen = {}

    def spy(timeline, out_path, **kwargs):
        seen["timeline"] = timeline
        raise render.RenderCancelled("enough")

    monkeypatch.setattr(render, "render_timeline", spy)
    start(client, pid, "render", options={"resolution": "720p"})
    render_job.render_tick(db)
    assert seen["timeline"]["grade"]["match"] is False
    assert not [c for c in seen["timeline"]["clips"] if c.get("match_ref")]


def test_a_forged_plate_is_ignored(owner_client, db, fal, monkeypatch):
    """Plates are bare names in the owner's images/ folder, nothing else."""
    from app.services.faceless import grade

    forged = {"s1": {"file": "../../../etc/passwd", "storage": "images"},
              "s2": {"file": "x.png", "storage": "private"}}
    assert grade.plates({"grade_plates": forged}) == {}


def test_an_ad_runs_to_length_and_draws_its_logo_on_the_end_card(owner_client, db, fal, monkeypatch):
    client = owner_client
    ad = story(format="ad", target_seconds=15, ad={"brand": "Tide", "cta": "Sail today", "offer": "First trip free"})
    project = hand_off(client, thread_for(db, ad))
    pid = project["id"]
    assert project["script"]["format"] == "ad"
    assert project["script"]["exact_seconds"] == 15.0
    assert project["script"]["outro_title"] == "Sail today"
    complete_step(db, client, pid, "storyboard")
    complete_step(db, client, pid, "clips")

    logo = stored_image(prefix="logo", color=(200, 30, 30))
    asset = UserAsset(user_id=1, kind="logo", name="Logo", filename=logo["file"], storage_type="images",
                      content_type="image/png", file_size_bytes=logo["bytes"])
    db.add(asset)
    db.commit()
    response = client.put(f"/api/faceless/projects/{pid}", json={"settings": {"ad_logo_asset_id": asset.id}})
    assert response.status_code == 200, response.text

    seen = {}
    real = render.render_timeline

    def spy(timeline, out_path, **kwargs):
        seen["timeline"] = timeline
        return real(timeline, out_path, **kwargs)

    monkeypatch.setattr(render, "render_timeline", spy)
    run = start(client, pid, "render", options={"resolution": "720p"})
    render_job.render_tick(db)
    assert get_run(client, run["id"])["status"] == "completed", get_run(client, run["id"])

    timeline = seen["timeline"]
    assert timeline["duration"] == pytest.approx(15.0, abs=0.05)
    assert [o for o in timeline["overlays"] if o["kind"] == "logo"], "the end card carries the logo"
    outro = next(o for o in timeline["overlays"] if o["kind"] == "outro_card")
    assert (outro["title"], outro["subtitle"]) == ("Sail today", "First trip free")
    info = probe(static_path(get_project(client, pid)["render"]["url"]))
    assert float(info["format"]["duration"]) == pytest.approx(15.0, abs=0.3)


def test_an_approved_product_photo_is_sent_and_checked_from_disk(owner_client, db, fal, monkeypatch):
    """Own files are local paths now: the reference only accepted https URLs here, which would
    have dropped every product reference in silence."""
    client = owner_client
    photo = stored_image(prefix="product", color=(10, 150, 90))
    doc = story()
    doc["products"] = [{"key": "p1", "name": "Bottle", "image_url": photo["url"], "image_approved": True,
                        "must_keep": ["blue label"]}]
    doc["scenes"][0]["shots"][0]["props"] = ["p1"]
    doc["scenes"][0]["shots"][0]["characters"] = []
    pid = hand_off(client, thread_for(db, doc))["id"]

    references = []

    async def check_still(_blob, **kwargs):
        references.extend(label for label, _bytes in kwargs["references"])
        return {**quality_gate.nothing_to_check("still", "x"), "verdict": quality_gate.PASS, "reasons": []}

    monkeypatch.setattr(quality_gate, "available", lambda _db: True)
    monkeypatch.setattr(quality_gate, "check_still", check_still)
    complete_step(db, client, pid, "storyboard", scene_ids=["s1"])

    endpoint, arguments = fal.submitted[0]
    assert "edit" in endpoint, "a reference photo means the edit model"
    assert photo["url"] in str(arguments), "the local URL: fal_inputs uploads it inside fal_submit"
    assert "the product Bottle" in references, "the check compares against the photo, read from disk"


def test_a_script_cannot_point_a_provider_at_someone_elses_file(owner_client, db, fal):
    from app.services.faceless.pricing import _owned_image_url

    assert _owned_image_url("/static/images/1/a.png", 1)
    assert _owned_image_url("/static/videos/uploads/1/a.png", 1)
    for url in ("/static/images/2/a.png", "/static/images/1/../../x.png", "https://evil.test/a.png",
                "/private_media/1/a.png", "", None, 7):
        assert not _owned_image_url(url, 1), url


def test_no_shots_is_a_sentence(owner_client, db):
    doc = story()
    doc["scenes"] = []
    response = owner_client.post(f"/api/story-room/threads/{thread_for(db, doc)}/to-faceless", json={})
    assert response.status_code == 400
    assert "no shots" in response.json()["detail"]
    assert write_lock_is_free(), "a refusal lets the write lock go"


def test_a_template_that_cannot_take_the_format_is_refused(owner_client, db):
    doc = story(aspect="16:9")
    response = owner_client.post(f"/api/story-room/threads/{thread_for(db, doc)}/to-faceless",
                                 json={"template_id": "micro_drama"})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_length"
    assert db.query(FacelessProject).count() == 0
    assert db.query(FacelessCharacter).count() == 0, "nothing lands from a refused hand-off"


def test_an_unknown_template_is_refused(owner_client, db):
    response = owner_client.post(f"/api/story-room/threads/{thread_for(db, story())}/to-faceless",
                                 json={"template_id": "nope"})
    assert response.status_code == 400 and response.json()["code"] == "unknown_template"


def test_a_busy_thread_answers_409(owner_client, db):
    thread_id = thread_for(db, story(), busy_until=datetime.utcnow() + timedelta(minutes=5))
    response = owner_client.post(f"/api/story-room/threads/{thread_id}/to-faceless", json={})
    assert response.status_code == 409
    assert write_lock_is_free()


def test_someone_elses_thread_is_not_found(owner_client):
    assert owner_client.post("/api/story-room/threads/99/to-faceless", json={}).status_code == 404


def test_the_hand_off_is_rate_limited(owner_client, db):
    thread_id = thread_for(db, story())
    codes = [owner_client.post(f"/api/story-room/threads/{thread_id}/to-faceless", json={}).status_code
             for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_the_project_cap_is_a_sentence(owner_client, db, monkeypatch):
    from app.services.story_room import faceless as handoff

    monkeypatch.setattr(handoff, "MAX_PROJECTS", 0)
    response = owner_client.post(f"/api/story-room/threads/{thread_for(db, story())}/to-faceless", json={})
    assert response.status_code == 400
    assert "at most 0" in response.json()["detail"]


def test_the_tick_ignores_a_hand_off_project_until_a_step_starts(owner_client, db, fal):
    hand_off(owner_client, thread_for(db, story()))
    assert orchestrator.tick(db) == 0
    assert fal.submitted == []
