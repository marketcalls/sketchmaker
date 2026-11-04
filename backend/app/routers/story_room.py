"""Story Room API (/api/story-room): chat threads with an AI director, the
story document, cast and environment library and clip prompts. Contract:
docs/STORY_ROOM.md.

Config
  GET    /config                        {price_per_turn, keyframe: {price, model, resolution}, limits:
                                         {max_threads, max_messages, max_message_chars, max_scenes,
                                         max_shots, max_products}, enums: {shot_types, cameras, transitions,
                                         registers, objectives}}. max_shots is per scene. Prices are
                                         estimates in USD.

Threads
  GET    /threads?q=&archived=          [{id, title, format, updated_at, scenes, shots, busy}]
  POST   /threads                       {format, title?, message?} -> Thread (201). With a message the
                                        first turn runs before the reply; if it fails the new thread is
                                        removed and the turn's error is returned.
  GET    /threads/{id}                  Thread {id, title, format, story, story_version, busy, turns_used,
                                        estimated_usd, is_archived, created_at, updated_at, messages}
  PATCH  /threads/{id}                  {title?, is_archived?} -> Thread
  DELETE /threads/{id}                  {deleted: true}
  POST   /threads/{id}/messages         {message} -> {user_message, assistant_message, story, story_version,
                                        estimated_usd, title}. 409 busy, 503 the model failed. A failed
                                        turn stores nothing, so the user can send the same message again.
  POST   /threads/{id}/messages/stream  Same body and checks, answered as text/event-stream: event user
                                        {user_message} (not saved yet), delta {text} (reply text as it is
                                        written), status {text}, replace {text} (the reply to show
                                        instead), then done {user_message, assistant_message, story,
                                        story_version, estimated_usd, title} or error {detail, status: 409
                                        | 503}. ": keep-alive" comments after 15 s of silence. Errors
                                        before the stream starts (400, 404, 409) are ordinary JSON replies.
                                        The turn finishes and is saved even if the client disconnects.
  PUT    /threads/{id}/story            {story, expected_version} -> {story, story_version} (409 stale)
  POST   /threads/{id}/restore/{message_id}       -> {story, story_version}
  POST   /threads/{id}/cast/{key}/save            -> {story, story_version, character | environment}
  POST   /threads/{id}/cast/{key}/link  {ref_id}  -> {story, story_version}
  POST   /threads/{id}/cast/{key}/image {image_id} | {asset_id} -> {story, story_version}
                                        key c1, e1 or p1; a product (p1) takes an asset_id only
  DELETE /threads/{id}/cast/{key}/image           -> {story, story_version}
  POST   /threads/{id}/shots/{shot_id}/keyframe {image_id} | {asset_id} | {made: true} -> {story, story_version}
                                        {made: true} approves the keyframe "Make keyframe" left on the shot
  DELETE /threads/{id}/shots/{shot_id}/keyframe   -> {story, story_version}
  POST   /threads/{id}/shots/{shot_id}/keyframe/generate -> {story, story_version, asset, estimated_usd}.
                                        "Make keyframe": a still from the approved cast, place and product
                                        images (services/story_room/keyframe.py), saved to My Assets and
                                        set as the shot's keyframe, not approved. 400 the shot is not ready
                                        (a sentence why), 409 busy, 503 the provider failed.
  GET    /threads/{id}/shots/{shot_id}/clip       -> {prompt, references: [{url, label}], start_frame: {url,
                                                     label, kind} | null, duration_seconds, aspect, shot_id,
                                                     scene_id}
  GET    /threads/{id}/treatment/clip             -> {prompt, references, duration_seconds, aspect}
  POST   /threads/{id}/to-faceless      {template_id?} -> {project_id}. A scripted Faceless Studio
                                        project from the shot list (no LLM, no provider cost). Unsaved
                                        characters are saved to the library first and linked in the
                                        story. 400 no shots yet or no template fits, 409 busy.

  Message = {id, role: user|assistant, content, story_version, can_restore, estimated_usd, created_at}
  Edits, restores, cast saves, links and image approvals answer 409 while a turn is running.
  image_url, image_approved, keyframe_url and keyframe_approved in a document are owned by the server: a
  PUT cannot set or clear them. Every turn and every PUT refreshes the plan checks in open_questions.

Environments
  GET    /environments?include_archived=false     [Environment]
  POST   /environments                  {name, description?, time_of_day?, mood?, style_notes?} -> Environment
  GET    /environments/{id}             Environment
  PUT    /environments/{id}             {name?, description?, time_of_day?, mood?, style_notes?, is_archived?}
  DELETE /environments/{id}             {deleted: true} (its photos are deleted too)
  POST   /environments/{id}/media       multipart "file" (PNG, JPEG or WebP, up to 25 MB, at most 6)
  DELETE /environments/{id}/media/{key}
  Environment = {id, name, description, time_of_day, mood, style_notes, media: [{url, key, content_type,
                 width, height}], is_archived, created_at, updated_at}
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.database import SessionLocal, apply_row_lock
from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import limiter
from app.models.story_room import StoryEnvironment, StoryMessage, StoryThread
from app.services import pricing as cp
from app.services.story_room import clip, director, faceless as handoff_service, keyframe, library
from app.services.story_room.library import LibraryError
from app.services.story_room.lint import apply_lint
from app.services.story_room.models import (
    CAMERAS, MAX_CHARACTERS, MAX_ENVIRONMENTS, MAX_PRODUCTS, MAX_SCENES, MAX_SHOTS_PER_SCENE, OBJECTIVES, REGISTERS,
    SHOT_TYPES, TRANSITIONS, CastEntry, EnvEntry, Product, StoryDoc, carry_images, dump, empty_doc, normalize,
    summary_counts,
)

logger = logging.getLogger(__name__)

router = APIRouter()

TURN_LIMIT = "20/minute"
POST_LIMIT = "30/minute"
UPLOAD_LIMIT = "20/minute"
KEYFRAME_LIMIT = "10/minute"

MAX_THREADS = 300
MAX_MESSAGES = 400
MAX_MESSAGE_CHARS = 4000
# A turn longer than this is treated as dead (its worker crashed): the thread
# accepts a new turn again.
TURN_SECONDS = 600
DEFAULT_TITLES = {"story": "Untitled story", "ad": "Untitled ad"}
_KEY = re.compile(r"^[ce]\d{1,4}$")
_IMAGE_KEY = re.compile(r"^[cep]\d{1,4}$")
_SHOT_ID = re.compile(r"^s\d{1,4}\.\d{1,4}$")


# ---------------------------------------------------------------------------
# Bodies
# ---------------------------------------------------------------------------

class ThreadCreate(BaseModel):
    format: Literal["story", "ad"] = "story"
    title: Optional[str] = Field(None, max_length=200)
    message: Optional[str] = Field(None, max_length=100_000)


class ThreadPatch(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    is_archived: Optional[bool] = None


class MessageIn(BaseModel):
    message: str = Field(..., max_length=100_000)


class StorySave(BaseModel):
    story: dict
    expected_version: int


class LinkIn(BaseModel):
    ref_id: int


class ImageIn(BaseModel):
    image_id: Optional[int] = None
    asset_id: Optional[int] = None
    # Shot keyframes only: approve the image "Make keyframe" left on the shot.
    made: bool = False


class EnvironmentIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=4000)
    time_of_day: Optional[str] = Field(None, max_length=40)
    mood: Optional[str] = Field(None, max_length=120)
    style_notes: Optional[str] = Field(None, max_length=2000)


class EnvironmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=4000)
    time_of_day: Optional[str] = Field(None, max_length=40)
    mood: Optional[str] = Field(None, max_length=120)
    style_notes: Optional[str] = Field(None, max_length=2000)
    is_archived: Optional[bool] = None


class HandoffIn(BaseModel):
    template_id: Optional[str] = Field(None, max_length=60)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(code: int, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail=message)


def _thread(db, user, thread_id: int, lock: bool = False) -> StoryThread:
    query = db.query(StoryThread).filter(StoryThread.id == thread_id, StoryThread.user_id == user.id)
    if lock:
        query = apply_row_lock(query.populate_existing())
    thread = query.first()
    if thread is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Story not found.")
    return thread


def _environment(db, user, env_id: int, lock: bool = False) -> StoryEnvironment:
    env = library.owned_environment(db, user.id, env_id, lock=lock)
    if env is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Environment not found.")
    return env


def _busy(thread: StoryThread) -> bool:
    return bool(thread.busy_until and thread.busy_until > datetime.utcnow())


def _not_busy(thread: StoryThread) -> None:
    if _busy(thread):
        raise _error(status.HTTP_409_CONFLICT,
                     "The director is still working on the last message. Wait for the reply, then try again.")


def _doc(thread: StoryThread) -> StoryDoc:
    return normalize(thread.story or {}, default_format=thread.format or "story")


def _store(thread: StoryThread, doc: StoryDoc) -> None:
    thread.story = dump(doc)
    thread.story_version = int(thread.story_version or 0) + 1
    thread.format = doc.format
    thread.updated_at = datetime.utcnow()


def _story_reply(thread: StoryThread, **extra) -> dict:
    return {"story": thread.story, "story_version": thread.story_version, **extra}


def _check_refs(db, user_id: int, doc: StoryDoc) -> StoryDoc:
    """Drop ref_ids that are not the user's own library items."""
    for entry in doc.characters:
        if entry.ref_id and library.owned_character(db, user_id, entry.ref_id) is None:
            entry.ref_id = None
    for entry in doc.environments:
        if entry.ref_id and library.owned_environment(db, user_id, entry.ref_id) is None:
            entry.ref_id = None
    return doc


def _message_view(m: StoryMessage) -> dict:
    return {
        "id": m.id, "role": m.role, "content": m.content or "", "story_version": m.story_version,
        "can_restore": m.story_snapshot is not None, "estimated_usd": float(m.estimated_usd or 0),
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _thread_view(db, thread: StoryThread) -> dict:
    messages = (db.query(StoryMessage).filter(StoryMessage.thread_id == thread.id)
                .order_by(StoryMessage.created_at, StoryMessage.id).limit(MAX_MESSAGES).all())
    return {
        "id": thread.id, "title": thread.title, "format": thread.format,
        # Normalized, so a document stored before a field existed reaches the page with its default.
        "story": dump(_doc(thread)) if thread.story else dump(empty_doc(thread.format or "story")),
        "story_version": int(thread.story_version or 0), "busy": _busy(thread),
        "turns_used": int(thread.turns_used or 0), "estimated_usd": float(thread.estimated_usd or 0),
        "is_archived": bool(thread.is_archived),
        "created_at": thread.created_at.isoformat() if thread.created_at else None,
        "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
        "messages": [_message_view(m) for m in messages],
    }


def _turn_price() -> float:
    """The estimate for one reply. The real tokens go to llm_usage (litellm_client), so
    a turn never calls record_usage."""
    return float(cp.usd_for(cp.STORY_CHAT_TURN_KEY))


def _library_error(exc: LibraryError) -> HTTPException:
    return _error(exc.status_code, exc.message)


# ---------------------------------------------------------------------------
# The chat turn
# ---------------------------------------------------------------------------

def _release(db, thread_id: int) -> None:
    """Clear the busy marker (the turn finished, failed or was cancelled)."""
    try:
        db.rollback()
        thread = apply_row_lock(
            db.query(StoryThread).filter(StoryThread.id == thread_id).populate_existing()).first()
        if thread is not None and thread.busy_until is not None:
            thread.busy_until = None
            db.commit()
        else:
            db.rollback()  # let go of the write lock the check above took
    except Exception:
        db.rollback()
        logger.exception(f"Story Room thread {thread_id}: could not clear the busy marker")


class _ThreadGone(Exception):
    pass


async def _ask_director(ctx, message: str, user_id: int):
    # Its own session: the request session has no transaction open while the
    # model is thinking, and this one holds no row locks.
    llm_db = SessionLocal()
    try:
        return await director.run_turn(llm_db, ctx, message, user_id)
    finally:
        llm_db.close()


def _check_turn(db, user, thread_id: int, message: str) -> str:
    """Everything a turn checks before it claims the thread; the message's text."""
    text = (message or "").strip()
    if not text:
        raise _error(status.HTTP_400_BAD_REQUEST, "Write a message for the director first.")
    if len(text) > MAX_MESSAGE_CHARS:
        raise _error(status.HTTP_400_BAD_REQUEST,
                     f"That message is {len(text):,} characters. Keep it under {MAX_MESSAGE_CHARS:,}.")
    thread = _thread(db, user, thread_id)
    used = db.query(StoryMessage).filter(StoryMessage.thread_id == thread.id).count()
    if used + 2 > MAX_MESSAGES:
        raise _error(status.HTTP_409_CONFLICT,
                     "This story has reached its message limit. Start a new story to keep going.")
    return text


def _claim(db, user, thread_id: int) -> StoryThread:
    """Mark the thread busy: one turn at a time (409 while another runs)."""
    thread = _thread(db, user, thread_id, lock=True)
    _not_busy(thread)
    thread.busy_until = datetime.utcnow() + timedelta(seconds=TURN_SECONDS)
    db.commit()
    return thread


def _turn_failure(exc: BaseException, thread_id: int) -> tuple[int, str]:
    """Status and sentence for a turn that failed."""
    if isinstance(exc, director.DirectorUnavailable):
        return status.HTTP_503_SERVICE_UNAVAILABLE, exc.message
    if isinstance(exc, _ThreadGone):
        return status.HTTP_404_NOT_FOUND, "This story was deleted."
    if isinstance(exc, Exception):
        logger.exception(f"Story Room turn failed on thread {thread_id}")
    else:
        logger.warning(f"Story Room turn on thread {thread_id} was interrupted ({type(exc).__name__})")
    return (status.HTTP_500_INTERNAL_SERVER_ERROR,
            "The director could not answer right now. Please try again.")


def _save_turn(db, user_id: int, thread_id: int, text: str, result) -> dict:
    """Store the turn (document, memory, title, both messages) and commit; the turn's
    response. A failure here leaves nothing behind: _release rolls back."""
    usd = _turn_price()
    thread = db.query(StoryThread).filter(StoryThread.id == thread_id, StoryThread.user_id == user_id)
    thread = apply_row_lock(thread).first()
    if thread is None:
        raise _ThreadGone()
    # Image fields from the stored document, not the one the turn started
    # from: a keyframe made while the director was writing is kept.
    doc = carry_images(_doc(thread), _check_refs(db, user_id, result.doc))
    _store(thread, doc)
    thread.memory = result.memory
    # The director names an untitled thread; a title the user
    # gave (at creation or by renaming) is kept.
    if result.title and (not thread.title or thread.title in DEFAULT_TITLES.values()):
        thread.title = result.title[:200]
    thread.turns_used = int(thread.turns_used or 0) + 1
    thread.estimated_usd = round(float(thread.estimated_usd or 0) + usd, 4)
    thread.busy_until = None
    now = datetime.utcnow()
    user_message = StoryMessage(thread_id=thread.id, role="user", content=text, created_at=now)
    assistant = StoryMessage(
        thread_id=thread.id, role="assistant", content=result.reply, story_version=thread.story_version,
        story_snapshot=thread.story, estimated_usd=usd,
        created_at=now + timedelta(microseconds=1),
    )
    db.add_all([user_message, assistant])
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant)
    return {
        "user_message": _message_view(user_message),
        "assistant_message": _message_view(assistant),
        "story": thread.story,
        "story_version": thread.story_version,
        "estimated_usd": usd,
        "title": thread.title,
    }


async def _run_turn(db, user, thread_id: int, message: str) -> dict:
    text = _check_turn(db, user, thread_id, message)
    user_id = user.id
    thread = _claim(db, user, thread_id)
    try:
        ctx = director.build_context(db, user_id, thread)
        db.commit()  # nothing is held while the model writes
        try:
            result = await _ask_director(ctx, text, user_id)
            return _save_turn(db, user_id, thread_id, text, result)
        except HTTPException:
            raise
        except Exception as exc:
            raise _error(*_turn_failure(exc, thread_id))
    finally:
        _release(db, thread_id)


# ---------------------------------------------------------------------------
# The streamed chat turn (Server-Sent Events)
# ---------------------------------------------------------------------------
#
# The endpoint checks and claims the thread before it answers, so 400/404/409
# are ordinary JSON errors. The turn itself runs in a producer task that outlives
# the request: a closed tab or a dropped connection only stops the event stream,
# while the producer still saves the reply (the user sees it when the thread is
# reopened). The response only reads the producer's queue.

# Seconds of silence after which the stream sends a comment line. Cloudflare
# closes a response that sends nothing for 100 seconds.
KEEPALIVE_SECONDS = 15.0
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
# The event loop keeps only weak references to tasks; a producer must not be
# garbage collected half way through a turn.
_TURN_TASKS: set = set()


@dataclass
class _StreamTurn:
    db: object          # the producer's own session: save, release
    ctx: object
    text: str
    user_id: int
    thread_id: int


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def _produce_turn(turn: _StreamTurn, queue: asyncio.Queue) -> None:
    """Run the turn to the end whatever happens to the client; every failure,
    cancellation included, rolls back and releases the thread."""
    llm_db = SessionLocal()
    try:
        result = None
        async for kind, payload in director.stream_turn(llm_db, turn.ctx, turn.text, turn.user_id):
            if kind == "result":
                result = payload
            else:
                queue.put_nowait((kind, {"text": payload}))
        if result is None:
            raise director.DirectorUnavailable("The director's answer could not be used. Please try again.")
        queue.put_nowait(("done", _save_turn(turn.db, turn.user_id, turn.thread_id, turn.text, result)))
    except BaseException as exc:
        _, detail = _turn_failure(exc, turn.thread_id)
        # In the stream a deleted story is a conflict; anything else means try again later.
        code = status.HTTP_409_CONFLICT if isinstance(exc, _ThreadGone) else status.HTTP_503_SERVICE_UNAVAILABLE
        queue.put_nowait(("error", {"detail": detail, "status": code}))
        if not isinstance(exc, Exception):
            raise
    finally:
        llm_db.close()
        _release(turn.db, turn.thread_id)
        turn.db.close()
        queue.put_nowait(None)


async def _stream_events(queue: asyncio.Queue, keepalive: float):
    """The response body: the producer's events, and a comment line whenever
    nothing has been sent for ``keepalive`` seconds. Cancelling or closing this
    generator (the client left) does not touch the producer."""
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=keepalive)
        except asyncio.TimeoutError:
            yield ": keep-alive\n\n"
            continue
        if item is None:
            return
        kind, data = item
        yield _sse(kind, data)


# ---------------------------------------------------------------------------
# Config and threads
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_config(current_user: CurrentUser):
    return {
        "price_per_turn": _turn_price(),
        "keyframe": {"price": keyframe.price(), "model": keyframe.KEYFRAME_MODEL,
                     "resolution": keyframe.KEYFRAME_RESOLUTION},
        "limits": {"max_threads": MAX_THREADS, "max_messages": MAX_MESSAGES, "max_message_chars": MAX_MESSAGE_CHARS,
                   "max_scenes": MAX_SCENES, "max_shots": MAX_SHOTS_PER_SCENE, "max_products": MAX_PRODUCTS},
        "enums": {"shot_types": list(SHOT_TYPES), "cameras": list(CAMERAS), "transitions": list(TRANSITIONS),
                  "registers": list(REGISTERS), "objectives": list(OBJECTIVES)},
    }


@router.get("/threads")
async def list_threads(current_user: CurrentUser, db: DbSession, q: Optional[str] = None, archived: bool = False):
    query = db.query(StoryThread).filter(StoryThread.user_id == current_user.id,
                                         StoryThread.is_archived == archived)
    if q and q.strip():
        term = q.strip()[:100].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(StoryThread.title.ilike(f"%{term}%", escape="\\"))
    out = []
    for t in query.order_by(StoryThread.updated_at.desc(), StoryThread.id.desc()).limit(MAX_THREADS).all():
        scenes, shots = summary_counts(t.story)
        out.append({"id": t.id, "title": t.title, "format": t.format,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                    "scenes": scenes, "shots": shots, "busy": _busy(t)})
    return out


@router.post("/threads", status_code=status.HTTP_201_CREATED)
@limiter.limit(POST_LIMIT)
async def create_thread(request: Request, body: ThreadCreate, current_user: CurrentUser, db: DbSession):
    count = db.query(StoryThread).filter(StoryThread.user_id == current_user.id).count()
    if count >= MAX_THREADS:
        raise _error(status.HTTP_400_BAD_REQUEST,
                     f"You can keep at most {MAX_THREADS} stories. Delete some first.")
    title = (body.title or "").strip()[:200] or DEFAULT_TITLES[body.format]
    doc = empty_doc(body.format, "" if title in DEFAULT_TITLES.values() else title)
    thread = StoryThread(user_id=current_user.id, title=title, format=body.format, story=dump(doc),
                         story_version=0, memory="", turns_used=0, estimated_usd=0, is_archived=False)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    if body.message and body.message.strip():
        thread_id = thread.id
        try:
            await _run_turn(db, current_user, thread_id, body.message)
        except BaseException:
            # A first message that failed must not leave an empty story behind.
            try:
                db.rollback()
                db.query(StoryThread).filter(StoryThread.id == thread_id, StoryThread.turns_used == 0).delete(
                    synchronize_session=False)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(f"Could not remove the empty story {thread_id}")
            raise
        thread = _thread(db, current_user, thread_id)
    return _thread_view(db, thread)


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: int, current_user: CurrentUser, db: DbSession):
    return _thread_view(db, _thread(db, current_user, thread_id))


@router.patch("/threads/{thread_id}")
@limiter.limit(POST_LIMIT)
async def update_thread(request: Request, thread_id: int, body: ThreadPatch, current_user: CurrentUser,
                        db: DbSession):
    thread = _thread(db, current_user, thread_id, lock=True)
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise _error(status.HTTP_400_BAD_REQUEST, "Give the story a title.")
        thread.title = title[:200]
    if body.is_archived is not None:
        thread.is_archived = body.is_archived
    db.commit()
    db.refresh(thread)
    return _thread_view(db, thread)


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: int, current_user: CurrentUser, db: DbSession):
    thread = _thread(db, current_user, thread_id, lock=True)
    db.query(StoryMessage).filter(StoryMessage.thread_id == thread.id).delete(synchronize_session=False)
    db.delete(thread)
    db.commit()
    return {"deleted": True}


@router.post("/threads/{thread_id}/messages")
@limiter.limit(TURN_LIMIT)
async def send_message(request: Request, thread_id: int, body: MessageIn, current_user: CurrentUser, db: DbSession):
    return await _run_turn(db, current_user, thread_id, body.message)


@router.post("/threads/{thread_id}/messages/stream")
@limiter.limit(TURN_LIMIT)
async def stream_message(request: Request, thread_id: int, body: MessageIn, current_user: CurrentUser,
                         db: DbSession):
    """The chat turn as Server-Sent Events (see the module docstring)."""
    text = _check_turn(db, current_user, thread_id, body.message)
    user_id = current_user.id
    thread = _claim(db, current_user, thread_id)
    turn_db = SessionLocal()
    try:
        ctx = director.build_context(db, user_id, thread)
        db.commit()  # the request session holds nothing while the turn runs
    except BaseException:
        turn_db.close()
        _release(db, thread_id)
        raise

    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(("user", {"user_message": {
        "id": None, "role": "user", "content": text, "story_version": None, "can_restore": False,
        "estimated_usd": 0.0, "created_at": datetime.utcnow().isoformat(),
    }}))
    turn = _StreamTurn(db=turn_db, ctx=ctx, text=text, user_id=user_id, thread_id=thread_id)
    task = asyncio.create_task(_produce_turn(turn, queue))
    _TURN_TASKS.add(task)
    task.add_done_callback(_TURN_TASKS.discard)
    return StreamingResponse(_stream_events(queue, KEEPALIVE_SECONDS), media_type="text/event-stream",
                             headers=STREAM_HEADERS)


# ---------------------------------------------------------------------------
# The document: edits, restores, cast
# ---------------------------------------------------------------------------

@router.put("/threads/{thread_id}/story")
@limiter.limit(POST_LIMIT)
async def save_story(request: Request, thread_id: int, body: StorySave, current_user: CurrentUser, db: DbSession):
    thread = _thread(db, current_user, thread_id, lock=True)
    _not_busy(thread)
    if body.expected_version != int(thread.story_version or 0):
        raise _error(status.HTTP_409_CONFLICT,
                     "This story changed since you opened it. Reload it and make your edit again.")
    try:
        doc = normalize(body.story, default_format=thread.format or "story")
    except Exception:
        logger.exception(f"Story Room thread {thread_id}: an edited document could not be read")
        raise _error(status.HTTP_400_BAD_REQUEST, "The story could not be saved. Check your edits and try again.")
    doc = apply_lint(carry_images(_doc(thread), _check_refs(db, current_user.id, doc)))
    _store(thread, doc)
    db.commit()
    return _story_reply(thread)


@router.post("/threads/{thread_id}/restore/{message_id}")
@limiter.limit(POST_LIMIT)
async def restore_story(request: Request, thread_id: int, message_id: int, current_user: CurrentUser,
                        db: DbSession):
    thread = _thread(db, current_user, thread_id, lock=True)
    _not_busy(thread)
    message = db.query(StoryMessage).filter(StoryMessage.id == message_id,
                                            StoryMessage.thread_id == thread.id).first()
    if message is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Message not found.")
    if message.story_snapshot is None:
        raise _error(status.HTTP_400_BAD_REQUEST, "This message has no story version to restore.")
    doc = normalize(message.story_snapshot, default_format=thread.format or "story")
    doc = carry_images(_doc(thread), _check_refs(db, current_user.id, doc))
    _store(thread, doc)
    db.commit()
    return _story_reply(thread)


def _cast_entry(doc: StoryDoc, key: str) -> CastEntry | EnvEntry | Product:
    entry = doc.cast(key) if key.startswith("c") else doc.product(key) if key.startswith("p") else doc.env(key)
    if entry is None:
        raise _error(status.HTTP_404_NOT_FOUND, "That cast member, place or product is not in this story.")
    return entry


def _check_key(key: str, products: bool = False) -> None:
    if not (_IMAGE_KEY if products else _KEY).match(key or ""):
        raise _error(status.HTTP_404_NOT_FOUND, "That cast member, place or product is not in this story.")


def _shot(doc: StoryDoc, shot_id: str):
    found = doc.find_shot(shot_id) if _SHOT_ID.match(shot_id or "") else None
    if found is None:
        raise _error(status.HTTP_404_NOT_FOUND, "That shot is not in this story.")
    return found[1]


@router.post("/threads/{thread_id}/cast/{key}/save")
@limiter.limit(POST_LIMIT)
async def save_cast(request: Request, thread_id: int, key: str, current_user: CurrentUser, db: DbSession):
    _check_key(key)
    thread = _thread(db, current_user, thread_id, lock=True)
    _not_busy(thread)
    doc = _doc(thread)
    entry = _cast_entry(doc, key)
    try:
        if isinstance(entry, CastEntry):
            char = library.owned_character(db, current_user.id, entry.ref_id)
            if char is None:
                char = library.save_character(db, current_user.id, entry)
                entry.ref_id = char.id
            _store(thread, doc)
            db.commit()
            db.refresh(char)
            return _story_reply(thread, character=library.character_view(char))
        env = library.owned_environment(db, current_user.id, entry.ref_id)
        if env is None:
            env = library.save_environment(db, current_user.id, entry)
            entry.ref_id = env.id
        _store(thread, doc)
        db.commit()
        db.refresh(env)
        return _story_reply(thread, environment=library.environment_view(env))
    except LibraryError as exc:
        db.rollback()
        raise _library_error(exc)


@router.post("/threads/{thread_id}/cast/{key}/link")
@limiter.limit(POST_LIMIT)
async def link_cast(request: Request, thread_id: int, key: str, body: LinkIn, current_user: CurrentUser,
                    db: DbSession):
    """Use a library item for ``key``. A key not in the story yet ("c3" when
    the cast is c1 and c2) adds the library item to it."""
    _check_key(key)
    thread = _thread(db, current_user, thread_id, lock=True)
    _not_busy(thread)
    doc = _doc(thread)
    if key.startswith("c"):
        char = library.owned_character(db, current_user.id, body.ref_id)
        if char is None:
            raise _error(status.HTTP_404_NOT_FOUND, "That character is not in your library.")
        entry = doc.cast(key)
        if entry is None:
            if len(doc.characters) >= MAX_CHARACTERS:
                raise _error(status.HTTP_400_BAD_REQUEST,
                             f"A story can have at most {MAX_CHARACTERS} characters.")
            entry = CastEntry(key=key)
            doc.characters.append(entry)
        bible = char.bible if isinstance(char.bible, dict) else {}
        entry.ref_id = char.id
        entry.name = char.name
        entry.role = entry.role or (char.role or "")
        entry.description = str(bible.get("canonical_description") or char.notes or entry.description or "")[:2000]
        entry.wardrobe = entry.wardrobe or str(bible.get("outfit") or "")[:600]
    else:
        env = library.owned_environment(db, current_user.id, body.ref_id)
        if env is None:
            raise _error(status.HTTP_404_NOT_FOUND, "That environment is not in your library.")
        entry = doc.env(key)
        if entry is None:
            if len(doc.environments) >= MAX_ENVIRONMENTS:
                raise _error(status.HTTP_400_BAD_REQUEST,
                             f"A story can have at most {MAX_ENVIRONMENTS} environments.")
            entry = EnvEntry(key=key)
            doc.environments.append(entry)
        entry.ref_id = env.id
        entry.name = env.name
        entry.description = env.description or entry.description
        entry.time_of_day = env.time_of_day or entry.time_of_day
        entry.mood = env.mood or entry.mood
    _store(thread, normalize(dump(doc), default_format=doc.format))
    db.commit()
    return _story_reply(thread)


async def _resolve_image(db, user, body: ImageIn) -> tuple[str, str, str]:
    """(url, filename, storage type) of the user's gallery image or My Assets image."""
    from app.models.content import Image
    from app.services import assets

    if (body.image_id is None) == (body.asset_id is None):
        raise _error(status.HTTP_400_BAD_REQUEST, "Choose one image: a generated image or one from My Assets.")
    if body.image_id is not None:
        image = db.query(Image).filter(Image.id == body.image_id, Image.user_id == user.id).first()
        if image is None:
            raise _error(status.HTTP_404_NOT_FOUND, "That image was not found in your gallery.")
        return image.get_url(), image.filename, "images"
    try:
        asset = assets.owned(db, user.id, body.asset_id, kinds=("image",))
    except assets.AssetNotFound:
        raise _error(status.HTTP_404_NOT_FOUND, "That image was not found in My Assets.")
    return assets.url_of(asset), asset.filename, asset.storage_type


@router.post("/threads/{thread_id}/cast/{key}/image")
@limiter.limit(POST_LIMIT)
async def approve_image(request: Request, thread_id: int, key: str, body: ImageIn, current_user: CurrentUser,
                        db: DbSession):
    """Approve a reference image for a character, place or product. The URL is
    always resolved here from an id the user owns. A product takes only an
    uploaded photo (My Assets), never a generated image. When a character or
    place is linked to the library, a copy of the image is added to that
    item's photos."""
    from app.services.storage_service import storage_service

    _check_key(key, products=True)
    thread = _thread(db, current_user, thread_id)
    _not_busy(thread)
    entry = _cast_entry(_doc(thread), key)
    if isinstance(entry, Product) and body.image_id is not None:
        raise _error(status.HTTP_400_BAD_REQUEST,
                     "A product needs a photo of the real product. Upload one, or pick it from My Assets.")
    url, filename, storage = await _resolve_image(db, current_user, body)

    char = env = None
    if not isinstance(entry, Product) and entry.ref_id:
        if isinstance(entry, CastEntry):
            char = library.owned_character(db, current_user.id, entry.ref_id)
        else:
            env = library.owned_environment(db, current_user.id, entry.ref_id, lock=False)
    if char is not None or env is not None:
        try:
            content = await storage_service.get_file_bytes(filename, storage, user_id=current_user.id)
            if content:
                if char is not None:
                    await library.copy_to_character(db, char, content)
                else:
                    await library.copy_to_environment(env, content)
        except Exception:
            # The approval still stands; only the library copy is skipped.
            logger.exception(f"Story Room thread {thread_id}: could not copy the approved image to the library")

    thread = _thread(db, current_user, thread_id, lock=True)
    _not_busy(thread)
    doc = _doc(thread)
    entry = _cast_entry(doc, key)
    entry.image_url = url
    entry.image_approved = True
    _store(thread, doc)
    db.commit()
    return _story_reply(thread)


@router.delete("/threads/{thread_id}/cast/{key}/image")
async def clear_image(thread_id: int, key: str, current_user: CurrentUser, db: DbSession):
    _check_key(key, products=True)
    thread = _thread(db, current_user, thread_id, lock=True)
    _not_busy(thread)
    doc = _doc(thread)
    entry = _cast_entry(doc, key)
    entry.image_url = "" if isinstance(entry, Product) else None
    entry.image_approved = False
    _store(thread, doc)
    db.commit()
    return _story_reply(thread)


@router.post("/threads/{thread_id}/shots/{shot_id}/keyframe")
@limiter.limit(POST_LIMIT)
async def approve_keyframe(request: Request, thread_id: int, shot_id: str, body: ImageIn, current_user: CurrentUser,
                           db: DbSession):
    """Approve the first frame of a shot: a gallery image the user generated
    or a My Assets image, resolved here, or ({made: true}) the keyframe
    "Make keyframe" left on the shot. Clips of the shot open on it in
    families with an image-to-video mode."""
    made = body.made and body.image_id is None and body.asset_id is None
    thread = _thread(db, current_user, thread_id)
    _not_busy(thread)
    _shot(_doc(thread), shot_id)
    url = None if made else (await _resolve_image(db, current_user, body))[0]
    thread = _thread(db, current_user, thread_id, lock=True)
    _not_busy(thread)
    doc = _doc(thread)
    shot = _shot(doc, shot_id)
    if made:
        # keyframe_url is server-owned: only an image made or approved here.
        if not shot.keyframe_url:
            raise _error(status.HTTP_400_BAD_REQUEST, "This shot has no keyframe to approve. Make one first.")
        url = shot.keyframe_url
    shot.keyframe_url = url
    shot.keyframe_approved = True
    _store(thread, doc)
    db.commit()
    return _story_reply(thread)


@router.post("/threads/{thread_id}/shots/{shot_id}/keyframe/generate")
@limiter.limit(KEYFRAME_LIMIT)
async def generate_keyframe(request: Request, thread_id: int, shot_id: str, current_user: CurrentUser,
                            db: DbSession):
    """Make keyframe: one still for the shot from its approved images
    (services/story_room/keyframe.py). The image is saved to My Assets and
    becomes the shot's keyframe, not approved: the user approves it or makes
    another. Its fal spending is recorded once it is stored."""
    from fastapi.concurrency import run_in_threadpool

    from app.services import assets
    from app.services.usage import record_usage

    thread = _thread(db, current_user, thread_id)
    _not_busy(thread)
    if not _SHOT_ID.match(shot_id or ""):
        raise _error(status.HTTP_404_NOT_FOUND, "That shot is not in this story.")
    try:
        plan = keyframe.plan(db, current_user.id, _doc(thread), shot_id)
    except keyframe.KeyframeBlocked as exc:
        raise _error(status.HTTP_400_BAD_REQUEST, exc.message)
    if plan is None:
        raise _error(status.HTTP_404_NOT_FOUND, "That shot is not in this story.")
    usd = keyframe.price()
    try:
        assets.check_room(db, current_user.id)
    except assets.AssetError as exc:
        raise _error(status.HTTP_400_BAD_REQUEST, str(exc))

    user_id = current_user.id
    name = f"Keyframe {shot_id}, {thread.title or 'story'}"[:assets.NAME_MAX]
    try:
        db.commit()  # nothing is held while the model works
        content = await keyframe.render(db, plan)
        try:
            info = await run_in_threadpool(assets.inspect_upload, content, "image")
        except assets.AssetError as exc:
            raise keyframe.KeyframeFailed("the result is not an image") from exc
        if info["kind"] != "image":
            raise keyframe.KeyframeFailed("the result is not an image")
        asset = await assets.store(db, user_id, info, name, source="keyframe", commit=False, extra={
            "thread_id": thread_id, "shot_id": shot_id, "model": keyframe.KEYFRAME_MODEL,
            "resolution": keyframe.KEYFRAME_RESOLUTION, "estimated_usd": usd,
        })
        record_usage(db, feature="story_room", usd=usd, model=keyframe.KEYFRAME_MODEL, units=1, unit="image",
                     job_type="story_keyframe", job_id=thread_id,
                     detail={"shot_id": shot_id, "price_key": keyframe.price_key(),
                             "references": len(plan.references), "asset_id": asset.id})
        db.commit()
        asset_id = asset.id
    except keyframe.KeyframeFailed:
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE,
                     "The keyframe could not be made right now. Please try again.")
    except Exception:
        logger.exception(f"Story Room keyframe failed for user {user_id} on thread {thread_id}")
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR,
                     "The keyframe could not be saved. Please try again.")

    # Saved in My Assets; the shot points at it unless it is gone.
    asset = assets.owned(db, user_id, asset_id)
    thread = db.query(StoryThread).filter(StoryThread.id == thread_id, StoryThread.user_id == user_id)
    thread = apply_row_lock(thread).first()
    doc = _doc(thread) if thread is not None else None
    found = doc.find_shot(shot_id) if doc is not None else None
    if found is None:
        db.rollback()
        raise _error(status.HTTP_409_CONFLICT,
                     "The shot was removed while its keyframe was being made. The image is saved in My Assets.")
    found[1].keyframe_url = assets.url_of(asset)
    found[1].keyframe_approved = False
    _store(thread, doc)
    db.commit()
    return _story_reply(thread, asset=assets.to_dict(asset), estimated_usd=usd)


@router.delete("/threads/{thread_id}/shots/{shot_id}/keyframe")
async def clear_keyframe(thread_id: int, shot_id: str, current_user: CurrentUser, db: DbSession):
    thread = _thread(db, current_user, thread_id, lock=True)
    _not_busy(thread)
    doc = _doc(thread)
    shot = _shot(doc, shot_id)
    shot.keyframe_url = ""
    shot.keyframe_approved = False
    _store(thread, doc)
    db.commit()
    return _story_reply(thread)


# ---------------------------------------------------------------------------
# Clip prompts
# ---------------------------------------------------------------------------

@router.get("/threads/{thread_id}/shots/{shot_id}/clip")
async def shot_clip(thread_id: int, shot_id: str, current_user: CurrentUser, db: DbSession,
                    video_model: Optional[str] = None):
    thread = _thread(db, current_user, thread_id)
    result = clip.shot_clip(db, current_user.id, _doc(thread), shot_id, video_model)
    if result is None:
        raise _error(status.HTTP_404_NOT_FOUND, "That shot is not in this story.")
    return result


@router.get("/threads/{thread_id}/treatment/clip")
async def treatment_clip(thread_id: int, current_user: CurrentUser, db: DbSession,
                         video_model: Optional[str] = None):
    thread = _thread(db, current_user, thread_id)
    doc = _doc(thread)
    if not doc.treatment.strip() and not doc.shot_count():
        raise _error(status.HTTP_400_BAD_REQUEST,
                     "The story has no treatment yet. Ask the director for a first draft.")
    return clip.treatment_clip(db, current_user.id, doc, video_model)


@router.post("/threads/{thread_id}/to-faceless")
@limiter.limit("10/minute")
def to_faceless(request: Request, thread_id: int, body: HandoffIn, current_user: CurrentUser, db: DbSession):
    """A scripted Faceless Studio project from the shot list (no LLM, no provider cost).
    Unsaved characters are saved to the library first and linked in the story. A plain def:
    it holds the write lock while it builds the script, on a pool thread."""
    try:
        thread = _thread(db, current_user, thread_id, lock=True)
        _not_busy(thread)
        doc = _doc(thread)
        before = [(c.key, c.ref_id) for c in doc.characters]
        project = handoff_service.handoff(db, current_user.id, doc, body.template_id)
        if [(c.key, c.ref_id) for c in doc.characters] != before:
            _store(thread, doc)
        project_id = project.id
        db.commit()
    except LibraryError as exc:
        db.rollback()
        raise _library_error(exc)
    except Exception:
        db.rollback()
        raise
    return {"project_id": project_id}


# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

@router.get("/environments")
async def list_environments(current_user: CurrentUser, db: DbSession, include_archived: bool = False):
    query = db.query(StoryEnvironment).filter(StoryEnvironment.user_id == current_user.id)
    if not include_archived:
        query = query.filter(StoryEnvironment.is_archived == False)  # noqa: E712
    return [library.environment_view(e) for e in query.order_by(StoryEnvironment.updated_at.desc()).all()]


@router.post("/environments", status_code=status.HTTP_201_CREATED)
@limiter.limit(POST_LIMIT)
async def create_environment(request: Request, body: EnvironmentIn, current_user: CurrentUser, db: DbSession):
    try:
        library.check_environment_room(db, current_user.id)
    except LibraryError as exc:
        raise _library_error(exc)
    env = StoryEnvironment(
        user_id=current_user.id, name=body.name.strip()[:120] or "Unnamed place", description=body.description,
        time_of_day=body.time_of_day, mood=body.mood, style_notes=body.style_notes, media=[], is_archived=False,
    )
    db.add(env)
    db.commit()
    db.refresh(env)
    return library.environment_view(env)


@router.get("/environments/{env_id}")
async def get_environment(env_id: int, current_user: CurrentUser, db: DbSession):
    return library.environment_view(_environment(db, current_user, env_id))


@router.put("/environments/{env_id}")
@limiter.limit(POST_LIMIT)
async def update_environment(request: Request, env_id: int, body: EnvironmentUpdate, current_user: CurrentUser,
                             db: DbSession):
    env = _environment(db, current_user, env_id, lock=True)
    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise _error(status.HTTP_400_BAD_REQUEST, "Give the environment a name.")
        env.name = name[:120]
    for field in ("description", "time_of_day", "mood", "style_notes"):
        if field in data:
            setattr(env, field, data[field])
    if data.get("is_archived") is not None:
        env.is_archived = bool(data["is_archived"])
    env.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(env)
    return library.environment_view(env)


@router.delete("/environments/{env_id}")
async def delete_environment(env_id: int, current_user: CurrentUser, db: DbSession):
    env = _environment(db, current_user, env_id, lock=True)
    files = list(env.media or [])
    db.delete(env)
    db.commit()
    await library.delete_environment_files(current_user.id, files)
    return {"deleted": True}


@router.post("/environments/{env_id}/media")
@limiter.limit(UPLOAD_LIMIT)
async def upload_environment_media(request: Request, env_id: int, current_user: CurrentUser, db: DbSession,
                                   file: UploadFile = File(...)):
    from sqlalchemy.orm.attributes import flag_modified

    env = _environment(db, current_user, env_id)
    if len(env.media or []) >= library.MAX_ENV_MEDIA:
        raise _error(status.HTTP_400_BAD_REQUEST,
                     f"An environment can have at most {library.MAX_ENV_MEDIA} photos. Remove one first.")
    content = await file.read(library.ENV_MEDIA_MAX_BYTES + 1)
    if not content:
        raise _error(status.HTTP_400_BAD_REQUEST, "The file is empty.")
    try:
        entry = await library.store_environment_image(current_user.id, content)
    except LibraryError as exc:
        raise _library_error(exc)
    env = _environment(db, current_user, env_id, lock=True)
    if len(env.media or []) >= library.MAX_ENV_MEDIA:
        db.rollback()
        await library.delete_environment_files(current_user.id, [entry])
        raise _error(status.HTTP_400_BAD_REQUEST,
                     f"An environment can have at most {library.MAX_ENV_MEDIA} photos. Remove one first.")
    env.media = list(env.media or []) + [entry]
    flag_modified(env, "media")
    env.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(env)
    return library.environment_view(env)


@router.delete("/environments/{env_id}/media/{key}")
async def delete_environment_media(env_id: int, key: str, current_user: CurrentUser, db: DbSession):
    from sqlalchemy.orm.attributes import flag_modified

    env = _environment(db, current_user, env_id, lock=True)
    removed = [m for m in env.media or [] if isinstance(m, dict) and m.get("key") == key]
    if not removed:
        raise _error(status.HTTP_404_NOT_FOUND, "Photo not found.")
    env.media = [m for m in env.media or [] if not (isinstance(m, dict) and m.get("key") == key)]
    flag_modified(env, "media")
    env.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(env)
    await library.delete_environment_files(current_user.id, removed)
    return library.environment_view(env)
