import pytest

from app.utils import secret_box


def test_round_trip():
    token = secret_box.encrypt("sk-the-actual-key", "openai_api_key")
    assert token.startswith("v3:")
    assert "sk-the-actual-key" not in token
    assert secret_box.decrypt(token, "openai_api_key") == "sk-the-actual-key"


def test_tampered_ciphertext_is_rejected():
    token = secret_box.encrypt("value-to-protect", "fal_key")
    middle = len(token) // 2
    flipped = token[:middle] + ("A" if token[middle] != "A" else "B") + token[middle + 1:]
    assert secret_box.decrypt(flipped, "fal_key") is None


def test_value_from_another_column_does_not_decrypt():
    token = secret_box.encrypt("value-to-protect", "fal_key")
    assert secret_box.decrypt(token, "openai_api_key") is None


def test_no_plaintext_fallback():
    assert secret_box.decrypt("sk-stored-as-plain-text", "openai_api_key") is None
    assert secret_box.decrypt("v2:gAAAAAold-format", "openai_api_key") is None
    assert secret_box.decrypt("gAAAAAold-per-row-format", "openai_api_key") is None
    assert secret_box.decrypt(None, "openai_api_key") is None
    with pytest.raises(ValueError):
        secret_box.encrypt("", "openai_api_key")


def test_wrong_secret_key_reports_unreadable_through_the_canary():
    canary = secret_box.make_canary(secret_key="a" * 40, salt="s" * 40)
    assert secret_box.canary_status(canary, secret_key="a" * 40, salt="s" * 40) == "ok"
    assert secret_box.canary_status(canary, secret_key="b" * 40, salt="s" * 40) == "unreadable"
    assert secret_box.canary_status(canary, secret_key="a" * 40, salt="t" * 40) == "unreadable"
    assert secret_box.canary_status(None) == "absent"


def test_wrong_secret_key_cannot_read_a_key():
    token = secret_box.encrypt("value-to-protect", "fal_key", secret_key="a" * 40, salt="s" * 40)
    assert secret_box.decrypt(token, "fal_key", secret_key="b" * 40, salt="s" * 40) is None


def test_masks():
    assert secret_box.mask_key("sk-1234567890abcd") == "****abcd"
    assert secret_box.mask_key("short-key") is None
    assert secret_box.mask_key(None) is None
    assert secret_box.looks_masked("****abcd")
    assert secret_box.looks_masked("••••••")
    assert not secret_box.looks_masked("sk-1234567890abcd")
