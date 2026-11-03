import logging

import pytest

from app.utils import secret_box
from app.utils.logging import REDACTED, RedactingFilter, redact, register_secret


def record(message, *args, exc_info=None):
    return logging.LogRecord("test", logging.ERROR, __file__, 1, message, args, exc_info)


@pytest.mark.parametrize("secret", [
    "sk-abcdefghijklmnop1234",
    "sk-proj-abc_def-1234567890",
    "AIzaSyD-abcdefghijklmnopqrstuvwxyz",
    "gsk_abcdefghijklmnop",
    "xai-abcdefghijklmnop",
    "Bearer abc.def-ghi_jkl",
    "Key 1234abcd-ef56:0123456789abcdef",
])
def test_patterns_are_hidden(secret):
    assert secret not in redact(f"calling provider with {secret} now")
    assert REDACTED in redact(f"calling provider with {secret} now")


def test_ordinary_text_is_left_alone():
    text = "Generated 3 images in 12.5s with task-runner on model flux-3"
    assert redact(text) == text


def test_registered_values_are_hidden():
    register_secret("plain-looking-stored-value")
    assert "plain-looking-stored-value" not in redact("error for plain-looking-stored-value here")


def test_short_values_do_not_wipe_ordinary_words():
    register_secret("the")
    assert redact("the quick fox") == "the quick fox"


def test_decrypted_and_encrypted_keys_are_registered():
    token = secret_box.encrypt("stored-key-without-a-known-shape", "fal_key")
    assert "stored-key-without-a-known-shape" not in redact("x stored-key-without-a-known-shape y")
    assert secret_box.decrypt(token, "fal_key")


def test_filter_covers_args_and_keeps_the_record():
    item = record("key is %s", "sk-abcdefghijklmnop1234")
    assert RedactingFilter().filter(item) is True
    assert item.getMessage() == f"key is {REDACTED}"


def test_filter_covers_tracebacks():
    try:
        raise ValueError("bad key sk-abcdefghijklmnop1234")
    except ValueError:
        import sys

        item = record("failed", exc_info=sys.exc_info())
    RedactingFilter().filter(item)
    formatted = logging.Formatter().format(item)
    assert "sk-abcdefghijklmnop1234" not in formatted
    assert REDACTED in formatted


def test_child_logger_records_are_redacted_at_the_handler():
    import io

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        logging.getLogger("app.some.child").error("sending %s", "gsk_abcdefghijklmnop")
    finally:
        root.removeHandler(handler)
    assert "gsk_abcdefghijklmnop" not in stream.getvalue()


def test_uvicorn_access_lines_still_format():
    """uvicorn's access formatter unpacks exactly five args."""
    from uvicorn.logging import AccessFormatter

    item = record('%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "GET", "/api/x?key=sk-abcdefghijklmnop1234", "1.1", 200)
    RedactingFilter().filter(item)
    line = AccessFormatter(fmt="%(client_addr)s %(request_line)s %(status_code)s", use_colors=False).format(item)
    assert "/api/x?key=" in line and "200" in line
    assert "sk-abcdefghijklmnop1234" not in line
