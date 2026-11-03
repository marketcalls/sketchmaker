"""Response shapes for /api/faceless (documented in app/routers/faceless.py)."""

from __future__ import annotations

from app.models.faceless import FacelessCharacter

from . import catalog, consent, media


def _iso(value):
    return value.isoformat() if value else None


def media_view(entry: dict, char: FacelessCharacter) -> dict:
    """One stored character file. Real person media is private: its URL is the
    owner-only file route, never a /static path."""
    return {
        "id": entry.get("id"),
        "kind": entry.get("kind"),
        "role": entry.get("role"),
        "url": media.owner_url(entry, char.user_id, char.id),
        "private": media.is_private(entry),
        "width": entry.get("width"),
        "height": entry.get("height"),
        "duration": entry.get("duration"),
        "source_id": entry.get("source_id"),
        "usable_as_reference": entry.get("usable_as_reference", True),
        "created_at": entry.get("created_at"),
    }


def character_view(char: FacelessCharacter) -> dict:
    reason = consent.generation_block_reason(char)
    return {
        "id": char.id,
        "name": char.name,
        "kind": char.kind,
        "role": char.role,
        "personality": char.personality,
        "notes": char.notes,
        "style_notes": char.style_notes,
        "species": char.species,
        "catchphrase": char.catchphrase,
        "consent": {
            "status": consent.consent_status(char),
            "attested_at": _iso(char.consent_attested_at),
            "text_version": char.consent_text_version,
            "relationship": char.consent_relationship,
            "revoked_at": _iso(char.consent_revoked_at),
            "current_version": catalog.CONSENT_TEXT_VERSION,
        },
        "bible": char.bible,
        "media": [media_view(m, char) for m in char.media or []],
        "voice_id": char.voice_id,
        "voice_settings": char.voice_settings,
        "safety_flags": char.safety_flags or [],
        "can_generate": reason is None,
        "block_reason": reason,
        "is_archived": bool(char.is_archived),
        "created_at": _iso(char.created_at),
        "updated_at": _iso(char.updated_at),
    }
