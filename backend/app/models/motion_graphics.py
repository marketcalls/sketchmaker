"""Motion Graphics Studio models (/motion-graphics).

Data model
----------
mg_brand_kit   One per user: logo (stored raster image), palette tokens
               (primary, secondary, background, text), fonts from the bundled
               OFL list (display, text), motion intensity (calm, standard,
               punchy) and whether to use the brand background. New projects
               copy it into their ``brand`` snapshot when auto-apply is on.
mg_project     One video: template, style, primary aspect plus variant
               aspects, the spec (app/services/motion_graphics/spec.py, the
               storyboard the user edits) and its version, the brand snapshot,
               audio choices ({voice: {enabled, voice_id, stability,
               similarity_boost}, music: {enabled, mood}}), assets ({uploads:
               {id: entry}, voice: {...words}, music: {...beats, rights},
               images: {scene_id:slot: upload id}}), outputs per aspect
               ({video_id, duration, width, height, job_id, rendered_at}) and
               the estimated USD per job kind.
mg_job         One job (audio or render): the quote it was approved on, the
               estimated USD, an idempotency key and ``items``
               (voice, music, image: fal requests; render: one per aspect).
               The scheduler advances fal items and renders one aspect at a
               time under the system-wide render slot.
mg_activity    Append-only log (drafts, uploads, jobs; previews are not logged);
               also the counter behind the hourly caps.

Rendered videos are ordinary gallery rows (Video.video_type
"motion_graphics", model "motion-graphics-studio"); projects keep the ids as
plain integers.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from app.database import AUTOINCREMENT, Base


class MGBrandKit(Base):
    __tablename__ = "mg_brand_kit"
    __table_args__ = (UniqueConstraint("user_id", name="uq_mg_brand_kit_user"), AUTOINCREMENT)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    name = Column(String(80))
    logo = Column(JSON)        # {file, storage, width, height}
    palette = Column(JSON)     # {primary, secondary, background, text}
    fonts = Column(JSON)       # {display, text}
    intensity = Column(String(20), nullable=False, default="standard")
    use_brand_background = Column(Boolean, nullable=False, default=False)
    auto_apply = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MGProject(Base):
    __tablename__ = "mg_project"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False, default="Untitled")
    template_id = Column(String(40), nullable=False)
    style_id = Column(String(40), nullable=False)
    aspect = Column(String(10), nullable=False, default="9:16")
    variants = Column(JSON)        # extra aspects rendered in the same job
    brief = Column(Text)
    spec = Column(JSON, nullable=False)
    spec_version = Column(Integer, nullable=False, default=1)
    brand = Column(JSON)           # brand kit snapshot or null
    audio = Column(JSON)           # {voice: {...}, music: {...}}
    assets = Column(JSON)          # {uploads, voice, music, images}
    outputs = Column(JSON)         # {aspect: {video_id, duration, width, height, job_id, rendered_at}}
    status = Column(String(20), nullable=False, default="draft")  # draft | producing | rendered
    usd_by_step = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MGJob(Base):
    __tablename__ = "mg_job"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_mg_job_idem"), AUTOINCREMENT)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("mg_project.id", ondelete="CASCADE"), index=True)
    kind = Column(String(20), nullable=False, index=True)  # audio | render
    status = Column(String(20), nullable=False, default="queued", index=True)
    # queued | running | render_queued | rendering | completed | partial | failed | cancelled
    idempotency_key = Column(String(80), nullable=False)
    options = Column(JSON)
    quote = Column(JSON)
    items = Column(JSON)
    progress = Column(Integer, default=0)
    estimated_usd = Column(Float, default=0, nullable=False)
    cancel_requested = Column(Boolean, default=False, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    error = Column(Text)
    heartbeat_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class MGActivity(Base):
    __tablename__ = "mg_activity"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    project_id = Column(Integer, index=True)
    kind = Column(String(40), nullable=False, index=True)
    detail = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
