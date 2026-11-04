"""Shared stubs for the Faceless Studio tests. It has no tests of its own.

Providers are stubbed at services/faceless/media.py. Everything else is real: the app with
its routers and error handler, SQLite, the storage folders, ffprobe, and ffmpeg when a test
renders. The stub also proves the rule that matters most on SQLite: at every provider call,
another connection must be able to take the write lock at once.
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
import tempfile

import pytest

from app.config import settings
from app.services import fal_inputs, storyscript as ss
from app.services.faceless import media, orchestrator

MEDIA_CACHE = tempfile.mkdtemp(prefix="faceless-test-media-")


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, timeout=60)


def _cached(name: str, make) -> bytes:
    path = os.path.join(MEDIA_CACHE, name)
    if not os.path.exists(path):
        make(path)
    with open(path, "rb") as fh:
        return fh.read()


def png_bytes(size=(720, 1280), color=(40, 70, 120)) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def mp3_bytes(seconds: float = 2.0) -> bytes:
    return _cached(f"tone{seconds}.mp3", lambda p: _ffmpeg(
        "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}", "-c:a", "libmp3lame", "-q:a", "6", p))


def mp4_bytes(seconds: float = 2.0) -> bytes:
    return _cached(f"clip{seconds}.mp4", lambda p: _ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=size=720x1280:rate=30:duration={seconds}", "-c:v", "libx264",
        "-preset", "ultrafast", "-pix_fmt", "yuv420p", p))


def write_lock_is_free() -> bool:
    conn = sqlite3.connect(settings.database_path, timeout=0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.rollback()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


class FakeFal:
    """fal, as media.py sees it. Every request completes on its first status check."""

    def __init__(self):
        self.submitted: list[tuple[str, dict]] = []
        self.status_calls = 0
        self.result_calls = 0
        self.downloads: list[str] = []
        self.lock_violations: list[str] = []
        self.next_status_error = []     # exceptions to raise, one per call
        self.next_result_error = []
        self.next_download_error = []
        self.next_submit_error = []
        self.running = False            # True: requests stay "running"
        self.download_override: dict[str, bytes] = {}
        self.results: dict[str, dict] = {}

    def _check_lock(self, where: str) -> None:
        if not write_lock_is_free():
            self.lock_violations.append(where)

    def submit(self, _db, endpoint: str, arguments: dict) -> str:
        self._check_lock(f"submit {endpoint}")
        if self.next_submit_error:
            raise self.next_submit_error.pop(0)
        request_id = f"req-{len(self.submitted) + 1}"
        self.submitted.append((endpoint, json.loads(json.dumps(arguments))))
        self.results[request_id] = self._result_for(endpoint, request_id)
        return request_id

    def status(self, _db, _endpoint: str, _request_id: str) -> str:
        self._check_lock("status")
        self.status_calls += 1
        if self.next_status_error:
            raise self.next_status_error.pop(0)
        return "running" if self.running else "completed"

    def result(self, _db, _endpoint: str, request_id: str) -> dict:
        self._check_lock("result")
        self.result_calls += 1
        if self.next_result_error:
            raise self.next_result_error.pop(0)
        return self.results[request_id]

    async def download(self, url: str, _max_bytes: int) -> bytes:
        self._check_lock("download")
        self.downloads.append(url)
        if self.next_download_error:
            raise self.next_download_error.pop(0)
        if url in self.download_override:
            return self.download_override[url]
        if url.endswith(".png"):
            return png_bytes()
        if url.endswith(".mp3"):
            return mp3_bytes()
        return mp4_bytes()

    @staticmethod
    def _result_for(endpoint: str, request_id: str) -> dict:
        base = f"https://fal.test/{request_id}"
        if "tts" in endpoint:
            return {"audio": {"url": f"{base}.mp3", "content_type": "audio/mpeg"},
                    "timestamps": [{"text": "Hello", "start": 0.1, "end": 0.6},
                                   {"text": "there", "start": 0.7, "end": 1.2}]}
        if "music" in endpoint:
            return {"audio": {"url": f"{base}.mp3", "content_type": "audio/mpeg"}}
        if "h3-max" in endpoint or "video" in endpoint:
            return {"video": {"url": f"{base}.mp4", "content_type": "video/mp4"}, "reference_tokens": 5000}
        return {"images": [{"url": f"{base}.png", "content_type": "image/png"}], "seed": 7}


@pytest.fixture
def fal(monkeypatch) -> FakeFal:
    fake = FakeFal()
    monkeypatch.setattr(media, "fal_submit", fake.submit)
    monkeypatch.setattr(media, "fal_status", fake.status)
    monkeypatch.setattr(media, "fal_result", fake.result)
    monkeypatch.setattr(media, "download", fake.download)
    # A real person's photos go up to fal storage just before a request is submitted.
    monkeypatch.setattr(fal_inputs, "upload_local_file", lambda _path: "https://fal.test/uploaded.png")
    return fake


@pytest.fixture
def api():
    """The real app, including its Faceless error handler. No lifespan, so no scheduler: the
    tests call the ticks themselves."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def scene(sid: str, index: int, kind: str = "still", narration: str = "Hello there, this is a short line.",
          **extra) -> dict:
    return {"id": sid, "index": index, "beat": "main", "duration": 3.0, "narration": narration,
            "shot": {"kind": kind, "visual_prompt": f"A quiet harbour at dawn, view {index}.",
                     "direction": "Slow push in."}, **extra}


def script_for(template_id: str = "reel", scenes: list[dict] | None = None, **extra) -> dict:
    data = {
        "template_id": template_id, "title": "Harbour at dawn", "premise": "A town wakes up.",
        "length_seconds": 30, "outro_title": "Harbour at dawn",
        "scenes": scenes or [scene("s1", 0), scene("s2", 1, kind="clip")], **extra,
    }
    return ss.Script.model_validate(data).model_dump(mode="json")


@pytest.fixture
def llm(monkeypatch):
    """The script engine's LLM calls, stubbed. ``llm.script`` is what a draft returns."""

    class Fake:
        script = None
        calls = 0

    async def draft(_db, **kwargs):
        Fake.calls += 1
        return ss.Script.model_validate(Fake.script or script_for(kwargs.get("template_id") or "reel"))

    monkeypatch.setattr(ss, "draft_script", draft)
    return Fake


def make_project(client, llm, **body) -> dict:
    """A scripted project through the real routes."""
    response = client.post("/api/faceless/projects", json={"title": "Harbour", "idea": "A town wakes up.",
                                                           "template_id": "reel", "length_seconds": 30, **body})
    assert response.status_code == 201, response.text
    project = response.json()
    response = client.post(f"/api/faceless/projects/{project['id']}/script", json={})
    assert response.status_code == 200, response.text
    return response.json()


def start(client, project_id: int, step: str, **body) -> dict:
    response = client.post(f"/api/faceless/projects/{project_id}/steps/{step}", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def get_run(client, run_id: int) -> dict:
    response = client.get(f"/api/faceless/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def get_project(client, project_id: int) -> dict:
    response = client.get(f"/api/faceless/projects/{project_id}")
    assert response.status_code == 200, response.text
    return response.json()


def tick_until_done(db, client, run_id: int, max_ticks: int = 12) -> dict:
    for _ in range(max_ticks):
        orchestrator.tick(db)
        run = get_run(client, run_id)
        if run["status"] not in ("queued", "running"):
            return run
    raise AssertionError(f"Run {run_id} did not finish: {get_run(client, run_id)}")


def complete_step(db, client, project_id: int, step: str, **body) -> dict:
    run = tick_until_done(db, client, start(client, project_id, step, **body)["id"])
    assert run["status"] == "completed", run
    return run


def probe(path: str) -> dict:
    result = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                            capture_output=True, text=True, timeout=60, check=True)
    return json.loads(result.stdout)


def static_path(url: str) -> str:
    assert url.startswith("/static/"), url
    return str(settings.static_dir / url[len("/static/"):])


def walk_keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from walk_keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from walk_keys(inner)
