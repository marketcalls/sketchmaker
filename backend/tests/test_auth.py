from datetime import datetime, timedelta
import re

from fastapi.testclient import TestClient
import jwt
import pytest

from app.config import settings
from app.middleware import rate_limiter
from app.middleware.rate_limiter import limiter, reset_rate_limits
from app.models.user import User
from app.routers import auth
from conftest import PASSWORD, USERNAME, make_app

COOKIE = "sm_session"
NEW_PASSWORD = "a different long password"
PUBLIC_ROUTES = {
    ("GET", "/api/auth/settings"),
    ("POST", "/api/auth/setup"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/refresh"),
}


def setup_owner(client):
    return client.post("/api/auth/setup", json={"username": USERNAME, "password": PASSWORD})


def login(client, password=PASSWORD, username=USERNAME):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def set_cookie_header(response) -> str:
    return next(v for k, v in response.headers.multi_items() if k == "set-cookie" and v.startswith(COOKIE))


def test_settings_reports_setup_required(api):
    assert api.get("/api/auth/settings").json() == {"setup_required": True}
    setup_owner(api)
    assert api.get("/api/auth/settings").json() == {"setup_required": False}


def test_setup_works_once(api):
    assert setup_owner(api).status_code == 200
    limiter.reset()
    second = api.post("/api/auth/setup", json={"username": "other_name", "password": PASSWORD})
    assert second.status_code == 409


@pytest.mark.parametrize("password", ["too short", "x" * 73, "é" * 40])
def test_password_rule_at_setup(api, password):
    response = api.post("/api/auth/setup", json={"username": USERNAME, "password": password})
    assert response.status_code == 422
    assert password not in response.text


def test_login_with_username(owner_client):
    owner_client.cookies.clear()
    response = login(owner_client)
    assert response.status_code == 200
    assert response.json()["user"]["username"] == USERNAME
    assert owner_client.get("/api/auth/me").status_code == 200


def test_wrong_password_and_unknown_username_read_the_same(owner_client):
    owner_client.cookies.clear()
    wrong = login(owner_client, password="not the password at all")
    unknown = login(owner_client, username="nobody")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert COOKIE not in owner_client.cookies


def test_account_lock_after_many_failures(owner_client, db, monkeypatch):
    """The account-wide lock, for guesses spread across many addresses."""
    monkeypatch.setattr(auth, "LOGIN_MAX_FAILED_ATTEMPTS", 10)
    owner_client.cookies.clear()
    limiter.enabled = False
    for _ in range(9):
        assert login(owner_client, password="not the password at all").status_code == 401
    assert db.query(User).first().locked_until is None
    assert login(owner_client, password="not the password at all").status_code == 401
    db.expire_all()
    owner = db.query(User).first()
    assert owner.locked_until > datetime.utcnow() + timedelta(minutes=14)
    # The right password is refused while locked.
    assert login(owner_client).status_code == 401
    # Attempts while locked do not extend the lock.
    first_lock = owner.locked_until
    login(owner_client, password="not the password at all")
    db.expire_all()
    assert db.query(User).first().locked_until == first_lock


def test_a_guesser_locks_out_itself_not_the_owner(owner_client, db):
    limiter.enabled = False
    guesser = TestClient(make_app(), client=("203.0.113.9", 50000))
    for _ in range(10):
        assert login(guesser, password="not the password at all").status_code == 401
    # Even the right password is refused from that address, with the same answer.
    blocked = login(guesser)
    assert blocked.status_code == 401
    assert blocked.json()["detail"] == auth.INVALID_LOGIN_DETAIL
    assert COOKIE not in guesser.cookies
    # The account is not locked, and everyone else still gets in.
    assert db.query(User).first().locked_until is None
    assert login(TestClient(make_app(), client=("198.51.100.7", 50000))).status_code == 200


def test_guessing_usernames_counts_too(owner_client):
    limiter.enabled = False
    guesser = TestClient(make_app(), client=("203.0.113.9", 50000))
    for number in range(10):
        assert login(guesser, username=f"nobody{number}").status_code == 401
    assert login(guesser).status_code == 401


def test_lock_expires_and_a_good_login_clears_the_counter(owner_client, db):
    owner_client.cookies.clear()
    owner = db.query(User).first()
    owner.failed_login_count = 10
    owner.failed_login_window_start = datetime.utcnow() - timedelta(minutes=20)
    owner.locked_until = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert login(owner_client).status_code == 200
    db.expire_all()
    owner = db.query(User).first()
    assert owner.failed_login_count == 0 and owner.locked_until is None


def test_login_is_rate_limited(owner_client):
    owner_client.cookies.clear()
    codes = [login(owner_client, password="not the password at all").status_code for _ in range(6)]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


def test_session_cookie_flags_over_http(api):
    header = set_cookie_header(setup_owner(api)).lower()
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "path=/" in header
    assert f"max-age={30 * 24 * 60 * 60}" in header
    assert "secure" not in header


def test_secure_follows_the_scheme():
    https = TestClient(make_app(), base_url="https://testserver")
    assert "secure" in set_cookie_header(setup_owner(https)).lower()


def test_token_is_hs256_with_the_required_claims(owner_client):
    claims = jwt.decode(owner_client.cookies[COOKIE], settings.JWT_SECRET_KEY, algorithms=["HS256"])
    assert {"sub", "pwd", "exp"} <= set(claims)


def _forged(claims: dict, key=None) -> str:
    return jwt.encode(claims, key or settings.JWT_SECRET_KEY, algorithm="HS256")


def test_tokens_without_a_valid_pwd_claim_are_refused(owner_client, db):
    owner = db.query(User).first()
    future = datetime.utcnow() + timedelta(days=1)
    cases = [
        _forged({"sub": "1", "exp": future}),  # the claim is required
        _forged({"sub": "1", "exp": future, "pwd": "wrong"}),
        _forged({"sub": "1", "exp": future, "pwd": owner.password_fingerprint()}, key="k" * 40),
        _forged({"sub": "1", "exp": datetime.utcnow() - timedelta(days=1), "pwd": owner.password_fingerprint()}),
    ]
    for token in cases:
        owner_client.cookies.set(COOKIE, token)
        assert owner_client.get("/api/auth/me").status_code == 401


def test_password_change_invalidates_old_cookies(owner_client):
    old_cookie = owner_client.cookies[COOKIE]
    response = owner_client.post("/api/users/change-password", json={
        "current_password": PASSWORD, "new_password": NEW_PASSWORD,
    })
    assert response.status_code == 200
    # This browser got a fresh session.
    assert owner_client.cookies[COOKIE] != old_cookie
    assert owner_client.get("/api/auth/me").status_code == 200
    # The old one no longer works, and neither does the old password.
    owner_client.cookies.set(COOKIE, old_cookie)
    assert owner_client.get("/api/auth/me").status_code == 401
    assert owner_client.post("/api/auth/refresh").status_code == 401
    owner_client.cookies.clear()
    assert login(owner_client).status_code == 401
    assert login(owner_client, password=NEW_PASSWORD).status_code == 200


def test_change_password_checks_current_and_the_rule(owner_client):
    wrong = owner_client.post("/api/users/change-password", json={
        "current_password": "not the password at all", "new_password": NEW_PASSWORD,
    })
    assert wrong.status_code == 400
    short = owner_client.post("/api/users/change-password", json={
        "current_password": PASSWORD, "new_password": "short",
    })
    assert short.status_code == 422


def test_logout_invalidates_every_session(owner_client):
    copied = owner_client.cookies[COOKIE]
    response = owner_client.post("/api/auth/logout")
    assert response.status_code == 200
    assert COOKIE not in owner_client.cookies
    owner_client.cookies.set(COOKIE, copied)
    assert owner_client.get("/api/auth/me").status_code == 401
    assert owner_client.post("/api/auth/refresh").status_code == 401


def test_refresh_reissues_the_session(owner_client):
    response = owner_client.post("/api/auth/refresh")
    assert response.status_code == 200
    assert COOKIE in response.headers.get("set-cookie", "")
    assert owner_client.get("/api/auth/me").status_code == 200


def test_every_protected_route_rejects_without_a_cookie():
    application = make_app()
    client = TestClient(application, raise_server_exceptions=False)
    # FastAPI nests included routers, so the OpenAPI schema is the flat list of routes.
    # /static is left out of the schema and gets its own check in test_media.py.
    routes = [
        (method.upper(), path)
        for path, operations in application.openapi()["paths"].items()
        for method in operations
    ]
    assert len(routes) >= 25
    for method, template in routes:
        if (method, template) in PUBLIC_ROUTES:
            continue
        path = re.sub(r"\{[^}]+\}", "1", template)
        response = client.request(method, path)
        assert response.status_code == 401, f"{method} {template} answered {response.status_code}"


def test_cross_site_write_is_refused(owner_client):
    evil = owner_client.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert evil.headers["x-sm-origin"] == "app"
    assert owner_client.get("/api/auth/me").status_code == 200
    same = owner_client.post("/api/auth/refresh", headers={"Origin": "http://testserver"})
    assert same.status_code == 200
    assert owner_client.post("/api/auth/refresh", headers={"Origin": "null"}).status_code == 403


def test_replies_carry_the_app_marker_and_no_store(api):
    response = api.get("/api/auth/me")
    assert response.status_code == 401
    assert response.headers["x-sm-origin"] == "app"
    assert "no-store" in response.headers["cache-control"]
    csp = response.headers["content-security-policy"]
    assert "unsafe-eval" not in csp and "upgrade-insecure-requests" not in csp
    assert "strict-transport-security" not in response.headers


def test_https_replies_add_hsts_without_preload():
    response = TestClient(make_app(), base_url="https://testserver").get("/api/auth/settings")
    assert "preload" not in response.headers["strict-transport-security"]
    assert "upgrade-insecure-requests" in response.headers["content-security-policy"]


def test_other_host_names_are_refused_locally(api):
    """DNS rebinding: a website's own name pointed at 127.0.0.1."""
    response = api.post("/api/auth/setup", headers={"Host": "evil.example:8000", "Origin": "http://evil.example:8000"},
                        json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 421
    assert api.get("/api/auth/settings").json() == {"setup_required": True}
    assert api.get("/api/auth/settings", headers={"Host": "evil.example"}).status_code == 421


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8000", "[::1]:8000", "LOCALHOST"])
def test_loopback_names_are_served(api, host):
    assert api.get("/api/auth/settings", headers={"Host": host}).status_code == 200


def test_behind_a_proxy_the_proxy_decides_the_names(api, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "*")
    assert api.get("/api/auth/settings", headers={"Host": "sketch.example.com"}).status_code == 200


def test_a_public_server_never_offers_web_setup(api, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "*")
    response = setup_owner(api)
    assert response.status_code == 403
    assert "terminal" in response.json()["detail"]
    assert COOKIE not in api.cookies
    assert api.get("/api/auth/settings").json() == {"setup_required": True}


def test_api_requests_have_a_ceiling_per_address(api, monkeypatch):
    monkeypatch.setattr(rate_limiter, "API_READ_LIMIT", rate_limiter.parse("3/minute"))
    codes = [api.get("/api/auth/settings").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    refused = api.get("/api/auth/settings")
    assert refused.headers["retry-after"] == "60"
    assert refused.headers["x-sm-origin"] == "app"
    assert refused.headers["x-content-type-options"] == "nosniff"
    other = TestClient(make_app(), client=("198.51.100.7", 50000))
    assert other.get("/api/auth/settings").status_code == 200


def test_writes_have_a_tighter_ceiling(api, monkeypatch):
    monkeypatch.setattr(rate_limiter, "API_WRITE_LIMIT", rate_limiter.parse("2/minute"))
    codes = [api.post("/api/auth/logout").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert api.get("/api/auth/settings").status_code == 200


def test_requests_that_cost_money_have_the_tightest_ceiling(owner_client, monkeypatch):
    monkeypatch.setattr(rate_limiter, "API_PAID_LIMIT", rate_limiter.parse("2/minute"))
    codes = [owner_client.post("/api/generate/image", json={}).status_code for _ in range(3)]
    assert codes[2] == 429
    assert owner_client.post("/api/auth/logout").status_code == 200


def test_story_room_is_not_counted_as_the_story_router(api, monkeypatch):
    monkeypatch.setattr(rate_limiter, "API_PAID_LIMIT", rate_limiter.parse("1/minute"))
    codes = [api.post("/api/story-room/x", json={}).status_code for _ in range(3)]
    assert 429 not in codes


def test_failed_logins_reset_with_the_rest_of_the_limits(owner_client):
    limiter.enabled = False
    owner_client.cookies.clear()
    for _ in range(10):
        login(owner_client, password="not the password at all")
    assert login(owner_client).status_code == 401
    reset_rate_limits()
    assert login(owner_client).status_code == 200


def test_a_stranger_cannot_push_a_large_body(api):
    big = b"x" * (1024 * 1024 + 1)
    refused = api.post("/api/subtitle/upload", content=big, headers={"Content-Type": "application/octet-stream"})
    assert refused.status_code == 401
    assert "sign in" in refused.json()["detail"]
    forged = {"Cookie": f"{COOKIE}=not.a.session", "Content-Type": "application/octet-stream"}
    assert api.post("/api/subtitle/upload", content=big, headers=forged).status_code == 401
    # A small body is the route's business, and login still works.
    assert api.post("/api/subtitle/upload", content=b"x").status_code != 500


def test_a_signed_in_user_can_send_a_large_body(owner_client):
    big = b"x" * (1024 * 1024 + 1)
    response = owner_client.post("/api/auth/logout", content=big, headers={"Content-Type": "application/octet-stream"})
    assert response.status_code == 200


def test_ipv6_counts_by_network_for_guessing(owner_client):
    limiter.enabled = False
    for number in range(10):
        guesser = TestClient(make_app(), client=(f"2001:db8:1:2::{number + 1:x}", 50000))
        assert login(guesser, password="not the password at all").status_code == 401
    # A new address in the same /64 is the same guesser.
    same_network = TestClient(make_app(), client=("2001:db8:1:2::ffff", 50000))
    assert login(same_network).status_code == 401
    assert login(TestClient(make_app(), client=("2001:db8:1:3::1", 50000))).status_code == 200


def test_ipv4_mapped_addresses_count_as_ipv4():
    from app.middleware.security import client_key
    assert client_key("::ffff:203.0.113.9") == "203.0.113.9"
    assert client_key("203.0.113.9") == "203.0.113.9"
    assert client_key(None) == "unknown"
    assert client_key("testclient") == "testclient"
