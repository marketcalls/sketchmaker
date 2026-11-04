"""Faceless Studio models (/faceless): cast library, series, projects and step runs.

faceless_character      A cast member owned by one user, also used by Story Room's Cast
                        tab, Motion Graphics and My Assets. ``kind`` is "fictional" or
                        "real_person". A real person needs a consent attestation
                        (attested_at, text version, relationship self|with_permission)
                        before any media is uploaded or generated; revoking it
                        (consent_revoked_at) blocks every later generation that uses the
                        character. ``media`` is a JSON list of stored files:
                        {id, role: reference|sheet|source_video|frame, kind: image|video,
                        file, storage, url, width, height, duration, source_id,
                        usable_as_reference, created_at}. ``bible`` is
                        storyscript.CharacterBible as JSON.
faceless_series         A recurring show: template, style, cast ids, world notes and
                        episode memory (short summaries of the episodes made so far, fed
                        back into the next draft).
faceless_project        One video. The current script (storyscript.Script as JSON) and
                        its version number, per-scene assets (``scene_assets[scene_id]``:
                        stills, clips, user media, voice lines with word timings), the
                        music tracks with their rights record, the render result,
                        packaging, compliance and originality reports, and the estimated
                        USD of what landed, per step.
faceless_script_version Every saved script, so older versions can be restored and later
                        episodes are checked for originality against them.
faceless_step_run       One step: storyboard, clips, voice, music, render, thumbnails, a
                        character sheet or a queued script draft. Holds the quote it
                        started on, an idempotency key, and ``items``: one entry per
                        provider request with its status, fal request id, estimated USD
                        and result. The scheduler advances these (orchestrator.py).
faceless_activity       Append-only log: consent attestations and revocations, drafts,
                        step runs. Also the counter behind the hourly caps.

Video and Image rows produced here are ordinary gallery rows (video_type "faceless",
Image.art_style "faceless_thumbnail"); the project keeps their ids as plain integers,
not foreign keys, so deleting a video from the gallery never has to know about this
table.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

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


class FacelessSeries(Base):
    __tablename__ = "faceless_series"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    logline = Column(Text)
    template_id = Column(String(60))
    style = Column(String(60))
    tone = Column(String(200))
    cast_ids = Column(JSON)        # list of character ids
    world_notes = Column(Text)
    rules = Column(JSON)           # continuity rules, list of strings
    episode_memory = Column(JSON)  # list of {project_id, title, premise, outcome, situation}
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FacelessProject(Base):
    __tablename__ = "faceless_project"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    series_id = Column(Integer, ForeignKey("faceless_series.id", ondelete="SET NULL"), index=True)
    title = Column(String(200), nullable=False, default="Untitled")
    idea = Column(Text)
    template_id = Column(String(60), nullable=False)
    aspect = Column(String(10), nullable=False, default="9:16")
    length_seconds = Column(Integer, nullable=False, default=60)
    language = Column(String(10), nullable=False, default="en")
    style = Column(String(60))
    narrator_voice = Column(String(60))
    voice_settings = Column(JSON)
    caption_preset = Column(String(30), default="bold_pop")
    music_mood = Column(String(40))
    cast_ids = Column(JSON)        # list of character ids (max 6)
    facts = Column(JSON)           # list of storyscript.Fact for fact mode
    settings = Column(JSON)        # model choices and render options
    status = Column(String(20), nullable=False, default="draft")  # draft | scripted | producing | rendered

    script = Column(JSON)          # storyscript.Script, current version
    script_version = Column(Integer, nullable=False, default=0)
    scene_assets = Column(JSON)    # {scene_id: {...}}
    music = Column(JSON)           # {tracks, mood, plan_hash, instrumental, run_id, rights}
    render = Column(JSON)          # {video_id, run_id, duration, width, height, rendered_at}
    output_video_id = Column(Integer)
    packaging = Column(JSON)
    thumbnails = Column(JSON)      # list of {index, image_id, file, raw_file, text, run_id}
    compliance = Column(JSON)      # {flags, checked_at, script_version, blocked}
    originality = Column(JSON)     # OriginalityReport plus script_version
    usd_by_step = Column(JSON)     # {step: estimated USD of what landed}

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FacelessScriptVersion(Base):
    __tablename__ = "faceless_script_version"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_faceless_script_version"), AUTOINCREMENT)

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("faceless_project.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    source = Column(String(20), nullable=False)  # draft | edit | revise | restore
    script = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class FacelessStepRun(Base):
    __tablename__ = "faceless_step_run"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_faceless_step_run_idem"), AUTOINCREMENT)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("faceless_project.id", ondelete="CASCADE"), index=True)
    character_id = Column(Integer, ForeignKey("faceless_character.id", ondelete="CASCADE"), index=True)
    step = Column(String(20), nullable=False, index=True)
    # queued | running | completed | partial | failed | cancelled. While one worker settles a
    # finished item the row is "processing", and a temporary failure hands it back as
    # "in_progress" (job_state.claim_job, fail_claimed_job); the API shows both as "running".
    status = Column(String(20), nullable=False, default="queued", index=True)
    idempotency_key = Column(String(80), nullable=False)
    scene_ids = Column(JSON)
    options = Column(JSON)
    quote = Column(JSON)           # {usd, breakdown, assumptions}
    items = Column(JSON)           # list of provider requests (see orchestrator)
    progress = Column(Integer, default=0)
    estimated_usd = Column(Float, default=0, nullable=False)  # the quote total
    usd_spent = Column(Float, default=0, nullable=False)      # estimated USD of what landed
    cancel_requested = Column(Boolean, default=False, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    error = Column(Text)
    heartbeat_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class FacelessActivity(Base):
    __tablename__ = "faceless_activity"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    project_id = Column(Integer, index=True)
    character_id = Column(Integer, index=True)
    kind = Column(String(40), nullable=False, index=True)
    detail = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
