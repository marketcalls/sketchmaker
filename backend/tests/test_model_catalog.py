"""Refresh models: what providers answer, what is filtered out, and what gets added.

The provider is faked at the HTTP layer, so the real request code runs.
"""

from datetime import datetime, timezone

import httpx
import pytest

from app.middleware.rate_limiter import limiter
from app.models.api import AIModel, APIProvider, APISettings
from app.services import model_catalog

NOW = int(datetime.now(timezone.utc).timestamp())
LONG_AGO = NOW - 86400 * 400

OPENAI = {"data": [
    {"id": "gpt-6.1-sol", "created": NOW, "shutdown_date": None},
    {"id": "gpt-6.1-sol-2026-09-10", "created": NOW},
    {"id": "gpt-4-old", "created": LONG_AGO},
    {"id": "gpt-5.4", "created": LONG_AGO, "shutdown_date": 1999999999},
    {"id": "gpt-image-2.5", "created": NOW},
    {"id": "gpt-realtime-2.1", "created": NOW},
    {"id": "gpt-live-1", "created": NOW},
    {"id": "gpt-5.3-codex", "created": NOW},
    {"id": "text-embedding-3-large", "created": NOW},
    {"id": "whisper-1", "created": NOW},
    {"id": "babbage-002", "created": LONG_AGO},
]}
ANTHROPIC = {"data": [
    {"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5", "created_at": "2026-09-20T00:00:00Z",
     "max_input_tokens": 1000000},
]}
GEMINI = {"models": [
    {"name": "models/gemini-4-argon", "displayName": "Gemini 4 Argon", "description": "Latest",
     "inputTokenLimit": 1048576, "supportedGenerationMethods": ["generateContent", "countTokens"]},
    {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
    {"name": "models/gemini-3.8-flash-tts", "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/gemini-3.8-live", "supportedGenerationMethods": ["bidiGenerateContent"]},
]}
OPENROUTER = {"data": [
    {"id": "openai/gpt-6.1-sol", "name": "OpenAI: GPT-6.1 Sol", "created": NOW, "context_length": 1050000,
     "architecture": {"output_modalities": ["text"]}},
    {"id": "openai/gpt-6.1-sol:batch", "name": "batch variant", "created": NOW,
     "architecture": {"output_modalities": ["text"]}},
    {"id": "openai/gpt-image-2", "created": NOW, "architecture": {"output_modalities": ["image"]}},
    {"id": "vendor/going-away", "created": NOW, "expiration_date": "2026-12-01",
     "architecture": {"output_modalities": ["text"]}},
    {"id": "~weird/slug name", "created": NOW, "architecture": {"output_modalities": ["text"]}},
]}


class FakeProviders:
    """Stands in for every provider. Records what was sent, so the tests can see the key
    went only where it belongs."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.routes.get(request.url.host)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, httpx.Response):
            return answer
        if answer is None:
            return httpx.Response(404, json={})
        return httpx.Response(200, json=answer)


@pytest.fixture
def providers(monkeypatch):
    def install(routes: dict) -> FakeProviders:
        fake = FakeProviders(routes)
        real_client = httpx.Client

        def client(**kwargs):
            return real_client(transport=httpx.MockTransport(fake.handle), **kwargs)

        monkeypatch.setattr(model_catalog.httpx, "Client", client)
        return fake
    return install


def names(offer) -> list[str]:
    return [m.name for m in offer.models]


def test_openai_keeps_only_chat_models_and_skips_snapshots(providers):
    providers({"api.openai.com": OPENAI})
    offer = model_catalog.fetch_offer("OpenAI", "sk-test")
    assert offer.status == model_catalog.STATUS_OK
    assert names(offer) == ["gpt-6.1-sol", "gpt-4-old"]
    # Filtered from the offer, but known to exist, so never reported as gone.
    assert "gpt-5.4" in offer.listed and "gpt-image-2.5" in offer.listed


def test_recent_models_are_recommended_and_old_ones_are_not(providers):
    providers({"api.openai.com": OPENAI})
    by_name = {m.name: m for m in model_catalog.fetch_offer("OpenAI", "k").models}
    assert by_name["gpt-6.1-sol"].recommended is True
    assert by_name["gpt-4-old"].recommended is False
    assert by_name["gpt-6.1-sol"].display_name == "GPT-6.1 Sol"


def test_anthropic_fields(providers):
    providers({"api.anthropic.com": ANTHROPIC})
    model = model_catalog.fetch_offer("Anthropic", "k").models[0]
    assert (model.name, model.display_name, model.context_window) == ("claude-opus-5-5", "Claude Opus 5.5", 1000000)
    assert model.released.year == 2026


def test_gemini_drops_the_prefix_and_keeps_chat_models(providers):
    providers({"generativelanguage.googleapis.com": GEMINI})
    offer = model_catalog.fetch_offer("Google Gemini", "k")
    assert names(offer) == ["gemini-4-argon"]
    assert "gemini-3.8-live" in offer.listed


def test_openrouter_drops_variants_images_and_bad_names(providers):
    providers({"openrouter.ai": OPENROUTER})
    assert names(model_catalog.fetch_offer("OpenRouter", "k")) == ["openai/gpt-6.1-sol"]


def test_each_provider_gets_its_key_in_a_header_and_never_in_the_url(providers):
    fake = providers({})
    for provider in model_catalog.SOURCES:
        model_catalog.fetch_offer(provider, "secret-key-value")
    assert len(fake.requests) == len(model_catalog.SOURCES)
    for request in fake.requests:
        assert "secret-key-value" not in str(request.url)
        assert any("secret-key-value" in value for value in request.headers.values())
    hosts = {r.url.host for r in fake.requests}
    assert hosts == {"api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com", "api.groq.com",
                     "api.x.ai", "api.cerebras.ai", "openrouter.ai", "inference.baseten.co"}


@pytest.mark.parametrize("code", [400, 401, 403])
def test_a_rejected_key_is_reported_as_such(providers, code):
    providers({"api.x.ai": httpx.Response(code, json={"error": "Incorrect API key sk-should-not-be-shown"})})
    assert model_catalog.fetch_offer("xAI", "k").status == model_catalog.STATUS_KEY_REJECTED


@pytest.mark.parametrize("answer", [
    httpx.Response(500, json={}),
    httpx.Response(429, json={}),
    httpx.Response(200, text="<html>not json</html>"),
    httpx.Response(200, json={"unexpected": True}),
    httpx.Response(200, json=[1, 2, 3]),
    httpx.ConnectTimeout("slow"),
])
def test_any_other_failure_is_unavailable_and_never_raises(providers, answer):
    providers({"api.groq.com": answer})
    assert model_catalog.fetch_offer("Groq", "k").status == model_catalog.STATUS_UNAVAILABLE


def test_a_redirect_is_not_followed_with_the_key(providers):
    fake = providers({"api.cerebras.ai": httpx.Response(302, headers={"Location": "https://evil.example/steal"})})
    assert model_catalog.fetch_offer("Cerebras", "k").status == model_catalog.STATUS_UNAVAILABLE
    assert [r.url.host for r in fake.requests] == ["api.cerebras.ai"]


def test_provider_text_is_cut_to_size(providers):
    providers({"openrouter.ai": {"data": [{
        "id": "v/m", "name": "N" * 500, "description": "D" * 5000, "created": NOW,
        "architecture": {"output_modalities": ["text"]},
    }]}})
    model = model_catalog.fetch_offer("OpenRouter", "k").models[0]
    assert len(model.display_name) == model_catalog.MAX_DISPLAY_NAME
    assert len(model.description) == model_catalog.MAX_DESCRIPTION


def test_the_new_list_is_capped_newest_first():
    models = [model_catalog.OfferedModel(f"m{i}", f"M{i}") for i in range(200)]
    offer = model_catalog.ProviderOffer(model_catalog.STATUS_OK, models=models)
    kept = model_catalog.new_models_for(offer, {"m0"})
    assert len(kept) == model_catalog.MAX_NEW_MODELS and kept[0].name == "m1"


# --- the routes ---


@pytest.fixture
def seeded_owner(owner_client, seeded, db):
    row = db.query(APISettings).first()
    row.set_key("openai_api_key", "sk-real-looking-key")
    db.commit()
    return owner_client


def provider_id(db, name: str) -> int:
    return db.query(APIProvider).filter(APIProvider.name == name).one().id


def test_refresh_needs_a_login(api):
    assert api.post("/api/settings/models/refresh").status_code == 401
    assert api.post("/api/settings/models/add-offered", json={"models": []}).status_code == 401


def test_refresh_asks_only_providers_with_a_key_and_adds_nothing(seeded_owner, db, providers):
    fake = providers({"api.openai.com": {"data": [{"id": "gpt-99", "created": NOW}, {"id": "gpt-6.1-sol", "created": NOW}]}})
    before = db.query(AIModel).count()

    body = seeded_owner.post("/api/settings/models/refresh").json()

    assert [r.url.host for r in fake.requests] == ["api.openai.com"]
    assert [p["provider"] for p in body["providers"]] == ["OpenAI"]
    offer = body["providers"][0]
    # Already in the app, so not offered again.
    assert [m["name"] for m in offer["new_models"]] == ["gpt-99"]
    assert offer["new_models"][0]["recommended"] is True
    assert db.query(AIModel).count() == before
    assert "sk-real-looking-key" not in str(body)


def test_models_the_provider_dropped_are_reported_but_kept(seeded_owner, db, providers):
    providers({"api.openai.com": {"data": [{"id": "gpt-6.1-sol", "created": NOW}]}})
    offer = seeded_owner.post("/api/settings/models/refresh").json()["providers"][0]
    assert "gpt-5.4" in offer["no_longer_listed"] and "gpt-6.1-sol" not in offer["no_longer_listed"]
    assert db.query(AIModel).filter(AIModel.name == "gpt-5.4").first() is not None


def test_nothing_is_reported_as_gone_when_the_provider_could_not_be_asked(seeded_owner, providers):
    providers({"api.openai.com": httpx.Response(401, json={})})
    offer = seeded_owner.post("/api/settings/models/refresh").json()["providers"][0]
    assert offer["status"] == model_catalog.STATUS_KEY_REJECTED
    assert offer["no_longer_listed"] == [] and offer["new_models"] == []


def test_no_keys_means_no_requests(owner_client, seeded, providers):
    fake = providers({})
    assert owner_client.post("/api/settings/models/refresh").json() == {"providers": []}
    assert fake.requests == []


def test_refresh_is_rate_limited(seeded_owner, providers):
    providers({"api.openai.com": {"data": []}})
    codes = [seeded_owner.post("/api/settings/models/refresh").status_code for _ in range(7)]
    assert codes[:6] == [200] * 6 and codes[6] == 429


def test_chosen_models_go_to_the_top_in_the_order_shown(seeded_owner, db):
    pid = provider_id(db, "OpenAI")
    response = seeded_owner.post("/api/settings/models/add-offered", json={"models": [
        {"provider_id": pid, "name": "gpt-99", "display_name": "GPT-99", "context_window": 1000},
        {"provider_id": pid, "name": "gpt-98"},
        {"provider_id": pid, "name": "gpt-6.1-sol", "display_name": "Must not overwrite"},
    ]})
    assert response.json() == {"added": 2}
    rows = db.query(AIModel).filter(AIModel.provider_id == pid).order_by(AIModel.sort_order, AIModel.id).all()
    assert [m.name for m in rows[:3]] == ["gpt-99", "gpt-98", "gpt-6.1-sol"]
    assert rows[0].is_latest and rows[0].is_active and rows[0].context_window == 1000
    assert rows[2].display_name == "GPT-6.1 Sol"


@pytest.mark.parametrize("name", ["bad name", "../../etc", "x" * 101, "", "<script>"])
def test_bad_names_are_refused_and_nothing_is_added(seeded_owner, db, name):
    pid = provider_id(db, "OpenAI")
    before = db.query(AIModel).count()
    response = seeded_owner.post("/api/settings/models/add-offered", json={"models": [
        {"provider_id": pid, "name": "gpt-good"}, {"provider_id": pid, "name": name},
    ]})
    assert response.status_code == 400
    db.rollback()
    assert db.query(AIModel).count() == before


def test_a_provider_that_is_not_a_language_model_is_refused(seeded_owner, db):
    response = seeded_owner.post("/api/settings/models/add-offered", json={"models": [
        {"provider_id": provider_id(db, "FAL"), "name": "something"},
    ]})
    assert response.status_code == 400
    limiter.reset()
    assert seeded_owner.post("/api/settings/models/add-offered", json={"models": [
        {"provider_id": 99999, "name": "something"},
    ]}).status_code == 400


def test_temperature_is_not_sent_to_claude_models_but_is_to_gpt_6():
    from app.clients.litellm_client import supports_temperature
    for name in ("claude-opus-5-5", "claude-some-future-model", "anthropic/claude-opus-5.5", "gpt-5.6-sol"):
        assert not supports_temperature(name)
    for name in ("gpt-6.1-sol", "gemini-4-argon", "grok-4.7"):
        assert supports_temperature(name)
