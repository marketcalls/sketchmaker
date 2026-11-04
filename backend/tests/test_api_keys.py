from fastapi.testclient import TestClient

from app.seed import DEFAULT_MODELS
from app.models.api import APIProvider, APISettings
from conftest import make_app

SECRET = "sk-super-secret-value-abcd"
FAL_SECRET = "fal-key-id:fal-key-secret-wxyz"


def test_keys_never_come_back_in_plaintext(owner_client, seeded):
    assert owner_client.put("/api/settings/api-keys", json={
        "openai_api_key": SECRET, "fal_key": FAL_SECRET,
    }).status_code == 200

    bodies = [owner_client.get("/api/settings/api-keys").text]
    for path in ("/api/settings/providers", "/api/settings/models", "/api/users/providers", "/api/users/models",
                 "/api/users/profile", "/api/auth/me", "/api/usage/summary", "/api/usage/log",
                 "/api/pricing/costs"):
        response = owner_client.get(path)
        assert response.status_code == 200, path
        bodies.append(response.text)
    for body in bodies:
        assert SECRET not in body and FAL_SECRET not in body

    status = owner_client.get("/api/settings/api-keys").json()["keys"]
    assert status["openai"] == {"is_configured": True, "unreadable": False, "masked_key": "****abcd"}
    assert status["fal"]["masked_key"] == "****wxyz"
    assert status["groq"] == {"is_configured": False, "unreadable": False, "masked_key": None}


def test_stored_value_is_encrypted(owner_client, seeded):
    owner_client.put("/api/settings/api-keys", json={"openai_api_key": SECRET})
    seeded.expire_all()
    row = seeded.query(APISettings).first()
    assert row.openai_api_key.startswith("v3:") and SECRET not in row.openai_api_key
    assert row.get_key("openai_api_key") == SECRET


def test_short_keys_show_no_mask(owner_client, seeded):
    owner_client.put("/api/settings/api-keys", json={"groq_api_key": "gsk_short"})
    status = owner_client.get("/api/settings/api-keys").json()["keys"]["groq"]
    assert status["is_configured"] is True and status["masked_key"] is None


def test_masks_are_ignored_on_put(owner_client, seeded):
    owner_client.put("/api/settings/api-keys", json={"openai_api_key": SECRET})
    for mask in ("****abcd", "sk-a****abcd", "••••••••", "********"):
        assert owner_client.put("/api/settings/api-keys", json={"openai_api_key": mask}).status_code == 200
    seeded.expire_all()
    assert seeded.query(APISettings).first().get_key("openai_api_key") == SECRET


def test_empty_values_change_nothing_and_delete_clears(owner_client, seeded):
    owner_client.put("/api/settings/api-keys", json={"openai_api_key": SECRET})
    owner_client.put("/api/settings/api-keys", json={"openai_api_key": "", "fal_key": "   "})
    seeded.expire_all()
    row = seeded.query(APISettings).first()
    assert row.get_key("openai_api_key") == SECRET and row.fal_key is None

    assert owner_client.delete("/api/settings/api-keys/openai").status_code == 200
    assert owner_client.delete("/api/settings/api-keys/nonsense").status_code == 400
    status = owner_client.get("/api/settings/api-keys").json()["keys"]["openai"]
    assert status["is_configured"] is False


def test_unreadable_key_is_reported_not_returned(owner_client, seeded):
    row = seeded.query(APISettings).first()
    row.openai_api_key = "v3:not-a-real-token"
    row.secrets_canary = "v3:not-a-real-token"
    seeded.commit()
    body = owner_client.get("/api/settings/api-keys").json()
    assert body["secrets_unreadable"] is True
    assert body["keys"]["openai"] == {"is_configured": True, "unreadable": True, "masked_key": None}


def test_unauthenticated_requests_get_nothing(seeded):
    client = TestClient(make_app())
    for method, path in (("GET", "/api/settings/api-keys"), ("PUT", "/api/settings/api-keys"),
                         ("DELETE", "/api/settings/api-keys/openai"), ("GET", "/api/settings/providers"),
                         ("GET", "/api/settings/models"), ("GET", "/api/users/providers"),
                         ("GET", "/api/users/models")):
        response = client.request(method, path)
        assert response.status_code == 401, path
        assert set(response.json()) == {"detail"}


def test_users_providers_lists_only_configured_providers(owner_client, seeded):
    assert owner_client.get("/api/users/providers").json() == []
    owner_client.put("/api/settings/api-keys", json={"anthropic_api_key": SECRET, "fal_key": FAL_SECRET})
    names = [p["name"] for p in owner_client.get("/api/users/providers").json()]
    assert names == ["Anthropic"]


def test_seed_provides_providers_models_and_defaults(owner_client, seeded):
    body = owner_client.get("/api/settings/api-keys").json()
    assert body["default_model_id"] and body["fallback_model_id"]
    assert body["default_provider_id"] != body["fallback_provider_id"]
    providers = owner_client.get("/api/settings/providers").json()
    models = owner_client.get("/api/settings/models").json()
    assert len(providers) == 9 and len(models) == len(DEFAULT_MODELS)
    assert all("base_url" not in p for p in providers)
    opus = next(m for m in models if m["name"] == "claude-opus-5-5")
    assert opus["description"] and opus["id"] == body["default_model_id"]


def test_default_model_moves_the_provider_and_null_clears_the_fallback(owner_client, seeded):
    models = owner_client.get("/api/settings/models").json()
    other = next(m for m in models if m["name"] == "gpt-5.6-sol")
    owner_client.put("/api/settings/api-keys", json={"default_model_id": other["id"], "fallback_model_id": None})
    body = owner_client.get("/api/settings/api-keys").json()
    assert body["default_model_id"] == other["id"] and body["default_provider_id"] == other["provider_id"]
    assert body["fallback_model_id"] is None and body["fallback_provider_id"] is None
    assert owner_client.put("/api/settings/api-keys", json={"default_model_id": 999999}).status_code == 400


def test_deleted_model_is_not_seeded_back(owner_client, seeded):
    from app.seed import seed_defaults

    models = owner_client.get("/api/settings/models").json()
    victim = next(m for m in models if m["name"] == "claude-opus-5-5")
    assert owner_client.delete(f"/api/settings/models/{victim['id']}").status_code == 200
    assert seed_defaults(seeded) is False
    names = [m["name"] for m in owner_client.get("/api/settings/models").json()]
    assert "claude-opus-5-5" not in names
    assert owner_client.get("/api/settings/api-keys").json()["default_model_id"] is None


def _default_provider(owner_client, seeded) -> str:
    provider_id = owner_client.get("/api/settings/api-keys").json()["default_provider_id"]
    seeded.expire_all()
    return seeded.query(APIProvider).filter(APIProvider.id == provider_id).first().name


def test_first_llm_key_moves_the_default_to_a_provider_with_a_key(owner_client, seeded):
    assert _default_provider(owner_client, seeded) == "Anthropic"
    owner_client.put("/api/settings/api-keys", json={"openai_api_key": SECRET})
    assert _default_provider(owner_client, seeded) == "OpenAI"


def test_default_stays_when_its_provider_has_a_key(owner_client, seeded):
    owner_client.put("/api/settings/api-keys", json={"anthropic_api_key": SECRET})
    owner_client.put("/api/settings/api-keys", json={"openai_api_key": SECRET})
    assert _default_provider(owner_client, seeded) == "Anthropic"


def test_a_fal_key_alone_does_not_move_the_default(owner_client, seeded):
    owner_client.put("/api/settings/api-keys", json={"fal_key": FAL_SECRET})
    assert _default_provider(owner_client, seeded) == "Anthropic"


def test_reentering_a_key_clears_the_unreadable_state(owner_client, seeded):
    row = seeded.query(APISettings).first()
    row.secrets_canary = "v3:not-readable-with-these-secrets"
    seeded.commit()
    assert owner_client.get("/api/settings/api-keys").json()["secrets_unreadable"] is True
    owner_client.put("/api/settings/api-keys", json={"openai_api_key": SECRET})
    assert owner_client.get("/api/settings/api-keys").json()["secrets_unreadable"] is False
