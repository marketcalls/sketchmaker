import os
from unittest import mock

import pytest

from app.config import settings
from app.services import fal_inputs
from app.services.storage_service import UnsafeMediaPath, read_local_media


@pytest.fixture
def upload():
    fal_inputs.clear_memo()
    with mock.patch.object(fal_inputs, "upload_local_file", side_effect=lambda path: f"https://fal.media/{path.name}") as patched:
        yield patched
    fal_inputs.clear_memo()


def put(relative="images/1/a.png", content=b"data"):
    path = settings.static_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_own_static_urls_are_replaced(upload):
    put()
    assert fal_inputs.resolve_fal_inputs({"image_url": "/static/images/1/a.png"}) == {
        "image_url": "https://fal.media/a.png",
    }


def test_query_string_and_encoding_are_understood(upload):
    put("images/1/b c.png")
    assert fal_inputs.resolve_fal_inputs("/static/images/1/b%20c.png?v=2") == "https://fal.media/b c.png"


def test_remote_urls_and_other_values_pass_through(upload):
    arguments = {
        "https": "https://cdn.example.com/static/images/1/a.png",
        "data": "data:image/png;base64,AAAA",
        "prompt": "a picture of /static/ things",
        "seed": 7,
        "flag": True,
        "nothing": None,
    }
    assert fal_inputs.resolve_fal_inputs(arguments) == arguments
    upload.assert_not_called()


def test_nested_dicts_and_lists_are_walked_and_the_input_is_not_changed(upload):
    put("images/1/a.png")
    put("videos/1/v.mp4")
    arguments = {"refs": [{"url": "/static/images/1/a.png"}, "https://x.example/y.png"],
                 "deep": {"inner": {"video": ["/static/videos/1/v.mp4"]}}}
    resolved = fal_inputs.resolve_fal_inputs(arguments)
    assert resolved == {"refs": [{"url": "https://fal.media/a.png"}, "https://x.example/y.png"],
                        "deep": {"inner": {"video": ["https://fal.media/v.mp4"]}}}
    assert arguments["refs"][0]["url"] == "/static/images/1/a.png"


def test_repeated_files_hit_the_memo(upload):
    put()
    for _ in range(3):
        fal_inputs.resolve_fal_inputs(["/static/images/1/a.png", "/static/images/1/a.png"])
    assert upload.call_count == 1


def test_changed_mtime_uploads_again(upload):
    path = put()
    fal_inputs.resolve_fal_inputs("/static/images/1/a.png")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    fal_inputs.resolve_fal_inputs("/static/images/1/a.png")
    assert upload.call_count == 2


def test_expired_memo_uploads_again(upload):
    put()
    fal_inputs.resolve_fal_inputs("/static/images/1/a.png")
    with mock.patch.object(fal_inputs.time, "monotonic", return_value=fal_inputs.time.monotonic() + fal_inputs.MEMO_TTL_SECONDS + 1):
        fal_inputs.resolve_fal_inputs("/static/images/1/a.png")
    assert upload.call_count == 2


@pytest.mark.parametrize("url", [
    "/static/../sketchmaker.db",
    "/static/images/../../sketchmaker.db",
    "/static/%2e%2e/sketchmaker.db",
    "/static/..%2fsketchmaker.db",
    "/static/images\\..\\..\\sketchmaker.db",
    "/static/.tmp-partial",
    "/private_media/1/../../sketchmaker.db",
    "/private_media/../sketchmaker.db",
])
def test_traversal_is_rejected(upload, url):
    (settings.data_dir / "sketchmaker.db").touch()
    with pytest.raises(UnsafeMediaPath):
        fal_inputs.resolve_fal_inputs({"image_url": url})
    upload.assert_not_called()


def test_private_media_is_uploaded(upload):
    path = settings.private_media_dir / "1" / "face.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"data")
    assert fal_inputs.resolve_fal_inputs("/private_media/1/face.png") == "https://fal.media/face.png"


def test_missing_file_says_so(upload):
    with pytest.raises(FileNotFoundError):
        fal_inputs.resolve_fal_inputs("/static/images/1/gone.png")


def test_read_local_media():
    path = put()
    assert read_local_media("/static/images/1/a.png") == path.resolve()
    assert read_local_media("/static/images/1/gone.png") is None
    assert read_local_media("https://example.com/a.png") is None
    with pytest.raises(UnsafeMediaPath):
        read_local_media("/static/../sketchmaker.db")


def test_upload_goes_through_the_key_from_the_database(seeded):
    from app.models.api import APISettings
    from app.services import fal_keys

    row = seeded.query(APISettings).first()
    row.set_key("fal_key", "id:secret-value")
    seeded.commit()
    fal_keys._sync_client_for.cache_clear()
    client = fal_keys.get_sync_client()
    assert client.key == "id:secret-value"
    assert "FAL_KEY" not in os.environ
