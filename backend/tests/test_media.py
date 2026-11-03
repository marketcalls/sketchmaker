from fastapi.testclient import TestClient
import pytest

from app.config import settings
from conftest import make_app

BODY = bytes(range(256)) * 4  # 1024 bytes
PNG = "images/1/picture.png"


def put(relative: str, content: bytes = BODY):
    path = settings.static_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_static_requires_a_session():
    put(PNG)
    client = TestClient(make_app())
    assert client.get(f"/static/{PNG}").status_code == 401
    assert client.head(f"/static/{PNG}").status_code == 401


def test_owner_gets_the_file(owner_client):
    put(PNG)
    response = owner_client.get(f"/static/{PNG}")
    assert response.status_code == 200
    assert response.content == BODY
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["accept-ranges"] == "bytes"
    assert "private" in response.headers["cache-control"]


def test_missing_file_is_404(owner_client):
    assert owner_client.get("/static/images/1/none.png").status_code == 404


@pytest.mark.parametrize("path", [
    "/static/..%2f..%2fsketchmaker.db",
    "/static/%2e%2e/%2e%2e/sketchmaker.db",
    "/static/%2e%2e%2fsketchmaker.db",
    "/static/images/..%2f..%2f..%2fsketchmaker.db",
    "/static/images/%2e%2e/%2e%2e/%2e%2e/sketchmaker.db",
    "/static/..%252f..%252fsketchmaker.db",
    "/static/%252e%252e/sketchmaker.db",
    "/static/images%5c..%5c..%5csketchmaker.db",
    "/static/images/1/picture.png%00.txt",
    "/static//etc/passwd",
    "/static/%2fetc/passwd",
])
def test_traversal_is_rejected(owner_client, path):
    (settings.data_dir / "sketchmaker.db").touch()
    put(PNG)
    response = owner_client.get(path)
    assert response.status_code == 404, f"{path} answered {response.status_code}"
    assert b"SQLite" not in response.content


def test_symlink_out_of_the_folder_is_rejected(owner_client):
    target = settings.data_dir / "secret-outside.txt"
    target.write_text("outside")
    link = settings.static_dir / "images" / "link.txt"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    assert owner_client.get("/static/images/link.txt").status_code == 404


def test_temp_files_of_a_write_in_progress_are_not_served(owner_client):
    put("images/1/.tmp-abc123")
    assert owner_client.get("/static/images/1/.tmp-abc123").status_code == 404


def test_range_request(owner_client):
    put(PNG)
    response = owner_client.get(f"/static/{PNG}", headers={"Range": "bytes=10-19"})
    assert response.status_code == 206
    assert response.content == BODY[10:20]
    assert response.headers["content-range"] == f"bytes 10-19/{len(BODY)}"
    assert response.headers["content-length"] == "10"


def test_open_ended_and_suffix_ranges(owner_client):
    put(PNG)
    tail = owner_client.get(f"/static/{PNG}", headers={"Range": "bytes=1000-"})
    assert tail.status_code == 206 and tail.content == BODY[1000:]
    suffix = owner_client.get(f"/static/{PNG}", headers={"Range": "bytes=-24"})
    assert suffix.status_code == 206 and suffix.content == BODY[-24:]


@pytest.mark.parametrize("value", ["bytes=2000-3000", "bytes=1024-"])
def test_out_of_bounds_range_is_rejected(owner_client, value):
    put(PNG)
    response = owner_client.get(f"/static/{PNG}", headers={"Range": value})
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(BODY)}"
    assert response.content != BODY


def test_svg_carries_the_sandbox_and_nosniff(owner_client):
    put("images/1/logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>")
    response = owner_client.get("/static/images/1/logo.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["x-content-type-options"] == "nosniff"
    csp = response.headers["content-security-policy"]
    assert csp.startswith("sandbox") and "default-src 'none'" in csp
    assert "script-src" not in csp
    assert "content-disposition" not in response.headers


@pytest.mark.parametrize("name", ["page.html", "page.htm", "page.xhtml", "feed.xml", "unknown.bin"])
def test_html_ish_types_are_sandboxed_and_downloaded(owner_client, name):
    put(f"images/1/{name}", b"<script>alert(1)</script>")
    response = owner_client.get(f"/static/images/1/{name}")
    assert response.headers["content-security-policy"].startswith("sandbox")
    assert response.headers["content-disposition"] == "attachment"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_plain_media_gets_the_app_policy_not_the_sandbox(owner_client):
    put(PNG)
    response = owner_client.get(f"/static/{PNG}")
    assert not response.headers["content-security-policy"].startswith("sandbox")
