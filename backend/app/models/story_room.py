"""Story Room models (/stories): chat threads with an AI director, and the
environment library.

Data model
----------
story_thread        One story or ad. ``story`` is the current StoryDoc
                    (app/services/story_room/models.py) as JSON and
                    ``story_version`` counts every change to it (turns, manual
                    edits, restores, cast saves and links). ``memory`` is the
                    rolling summary the director keeps so long threads stay
                    within the model's context window. ``busy_until`` is set
                    while a chat turn runs (a second turn gets 409) and expires
                    on its own if the worker dies.
story_message       One chat message. An assistant reply keeps the document it
                    produced (``story_snapshot``) so the user can restore it.
story_environment   A place in the user's library, shared by every thread.
                    ``media`` is a JSON list of
                    photos {url, key, content_type, width, height}; the files
                    live under the user's images/{user_id}/ folder and are
                    deleted with the entry.

Characters live in faceless_character: one library.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text

from app.database import AUTOINCREMENT, Base


class StoryThread(Base):
    __tablename__ = "story_thread"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False, default="Untitled story")
    format = Column(String(10), nullable=False, default="story")  # story | ad
    story = Column(JSON)
    story_version = Column(Integer, nullable=False, default=0)
    memory = Column(Text)
    busy_until = Column(DateTime)
    turns_used = Column(Integer, nullable=False, default=0)
    estimated_usd = Column(Float, nullable=False, default=0)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class StoryMessage(Base):
    __tablename__ = "story_message"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("story_thread.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user | assistant
    content = Column(Text, nullable=False, default="")
    story_version = Column(Integer)
    story_snapshot = Column(JSON)
    estimated_usd = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class StoryEnvironment(Base):
    __tablename__ = "story_environment"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text)
    time_of_day = Column(String(40))
    mood = Column(String(120))
    style_notes = Column(Text)
    media = Column(JSON)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
