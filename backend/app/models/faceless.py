"""Faceless models that other features use: the cast library and the activity log.

Faceless Studio's project pipeline is deferred, so its tables are not here yet.

faceless_character  A cast member owned by one user, used by Story Room's Cast tab,
                    Motion Graphics and My Assets. ``kind`` is "fictional" or
                    "real_person". A real person needs a consent attestation
                    (attested_at, text version, relationship self|with_permission)
                    before any media is uploaded or generated; revoking it
                    (consent_revoked_at) blocks every later generation that uses the
                    character. ``media`` is a JSON list of stored files:
                    {id, role: reference|sheet|source_video|frame, kind: image|video,
                    file, storage, url, width, height, duration, source_id,
                    usable_as_reference, created_at}. ``bible`` is
                    storyscript.CharacterBible as JSON.
faceless_activity   Append-only log: consent attestations and revocations, drafts.
                    Also the counter behind the hourly caps.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text

from app.database import AUTOINCREMENT, Base


class FacelessCharacter(Base):
    __tablename__ = "faceless_character"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    kind = Column(String(20), nullable=False, default="fictional")  # fictional | real_person
    role = Column(String(120))  # protagonist, rival, narrator, mascot...
    personality = Column(Text)
    notes = Column(Text)
    style_notes = Column(Text)
    species = Column(String(60), default="human")
    catchphrase = Column(String(200))

    # Consent (real_person only)
    consent_attested_at = Column(DateTime)
    consent_text_version = Column(String(40))
    consent_relationship = Column(String(30))  # self | with_permission
    consent_revoked_at = Column(DateTime)

    bible = Column(JSON)          # storyscript.CharacterBible
    media = Column(JSON)          # list of stored media entries (see module docstring)
    voice_id = Column(String(60))
    voice_settings = Column(JSON)  # {stability, similarity_boost}
    safety_flags = Column(JSON)    # list of storyscript.SafetyFlag
    is_archived = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FacelessActivity(Base):
    __tablename__ = "faceless_activity"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    character_id = Column(Integer, index=True)
    kind = Column(String(40), nullable=False, index=True)
    detail = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
