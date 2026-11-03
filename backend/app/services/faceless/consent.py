"""Likeness consent for real person characters, and cast checks.

A character of kind "real_person" is built from photos of a real person. It
needs an attestation (the versioned checkbox text in catalog.CONSENT_TEXT,
relationship "self" or "with_permission") before media can be uploaded or
anything generated with it. Revoking consent blocks every later generation
that uses the character; existing results stay with the user, who can delete
them. A real person character whose bible flags a possible minor is blocked.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.faceless import FacelessCharacter

from . import catalog
from .errors import Blocked, InvalidRequest, NotFound

MINOR_CONFIDENCE = 0.4


def possible_minor(char: FacelessCharacter) -> bool:
    flags = list(char.safety_flags or [])
    bible = char.bible or {}
    flags += list(bible.get("safety_flags") or [])
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        if flag.get("kind") == "possible_minor" and float(flag.get("confidence") or 0) >= MINOR_CONFIDENCE:
            return True
    return False


def consent_status(char: FacelessCharacter) -> str:
    """not_required | missing | outdated | valid | revoked"""
    if char.kind != "real_person":
        return "not_required"
    if char.consent_revoked_at:
        return "revoked"
    if not char.consent_attested_at:
        return "missing"
    if char.consent_text_version != catalog.CONSENT_TEXT_VERSION:
        return "outdated"
    return "valid"


def generation_block_reason(char: FacelessCharacter) -> str | None:
    """Why nothing may be generated with this character, or None."""
    if char.is_archived:
        return f"{char.name} is archived. Restore the character first."
    status = consent_status(char)
    if status == "revoked":
        return f"Consent for {char.name} was revoked. Generation with this character is blocked."
    if status in ("missing", "outdated"):
        return (
            f"{char.name} is based on a real person. Confirm the likeness consent "
            f"(version {catalog.CONSENT_TEXT_VERSION}) before generating."
        )
    if char.kind == "real_person" and possible_minor(char):
        return (
            f"{char.name} may depict a minor. Real person characters of minors cannot be used."
        )
    return None


def require_can_generate(chars: list[FacelessCharacter]) -> None:
    reasons = [r for r in (generation_block_reason(c) for c in chars) if r]
    if reasons:
        raise Blocked(" ".join(reasons), code="consent_required",
                      extra={"characters": [c.id for c in chars if generation_block_reason(c)]})


def require_can_upload(char: FacelessCharacter) -> None:
    """Media of a real person may only be stored after a valid attestation."""
    status = consent_status(char)
    if status in ("missing", "outdated", "revoked"):
        raise Blocked(
            f"{char.name} is based on a real person. Confirm the likeness consent before uploading photos or video.",
            code="consent_required",
        )


def attest(char: FacelessCharacter, *, accepted: bool, text_version: str, relationship: str) -> None:
    if not accepted:
        raise InvalidRequest("The consent statement must be accepted.", code="consent_required")
    if text_version != catalog.CONSENT_TEXT_VERSION:
        raise InvalidRequest(
            f"The consent statement changed. Read and accept version {catalog.CONSENT_TEXT_VERSION}.",
            code="consent_outdated",
        )
    if relationship not in catalog.CONSENT_RELATIONSHIPS:
        raise InvalidRequest("Relationship must be 'self' or 'with_permission'.")
    char.consent_attested_at = datetime.utcnow()
    char.consent_text_version = text_version
    char.consent_relationship = relationship
    char.consent_revoked_at = None


def revoke(char: FacelessCharacter) -> None:
    char.consent_revoked_at = datetime.utcnow()


def load_cast(db: Session, user_id: int, ids: list | None) -> list[FacelessCharacter]:
    """The user's characters for ``ids`` in that order; NotFound for any other."""
    wanted: list[int] = []
    for raw in ids or []:
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            raise InvalidRequest(f"Unknown character id '{raw}'.")
        if cid not in wanted:
            wanted.append(cid)
    if len(wanted) > catalog.MAX_CAST:
        raise InvalidRequest(f"A project can have at most {catalog.MAX_CAST} characters.")
    if not wanted:
        return []
    rows = (
        db.query(FacelessCharacter)
        .filter(FacelessCharacter.user_id == user_id, FacelessCharacter.id.in_(wanted))
        .all()
    )
    by_id = {r.id: r for r in rows}
    missing = [cid for cid in wanted if cid not in by_id]
    if missing:
        raise NotFound(f"Character {missing[0]} not found.")
    return [by_id[cid] for cid in wanted]


def character_brief(char: FacelessCharacter) -> dict:
    """storyscript.CharacterBrief as a dict."""
    bible = char.bible or None
    brief = {
        "id": str(char.id),
        "name": char.name,
        "role": char.role or "",
        "personality": char.personality or "",
        "likeness_clause": (bible or {}).get("likeness_clause", "") if bible else "",
        "species": char.species or "human",
        "voice_id": char.voice_id,
        "catchphrase": char.catchphrase,
        "is_real_person": char.kind == "real_person",
        "is_user_self": char.kind == "real_person" and char.consent_relationship == "self",
        "consent_attested": consent_status(char) == "valid",
        "is_public_figure": any(
            isinstance(f, dict) and f.get("kind") == "public_figure" and float(f.get("confidence") or 0) >= 0.5
            for f in list(char.safety_flags or []) + list((bible or {}).get("safety_flags") or [])
        ),
        "is_minor": possible_minor(char),
        "bible": bible,
    }
    return brief


def voice_map(chars: list[FacelessCharacter]) -> dict[str, dict]:
    return {
        str(c.id): {
            "name": c.name,
            "voice_id": c.voice_id if c.voice_id in catalog.VOICE_IDS else None,
            "voice_settings": c.voice_settings or None,
        }
        for c in chars
    }
