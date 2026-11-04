"""Glue to the script engine (app/services/storyscript).

The engine is pure: it takes pydantic inputs and returns pydantic models.
This module builds those inputs from the database rows, stores the results as
JSON (model_dump(mode="json")) and maps engine errors to FacelessError.
"""

from __future__ import annotations

import inspect
import json
import logging
import math
from datetime import datetime

from sqlalchemy.orm import Session

from app.clients.litellm_client import LLM_KEY_REJECTED, is_llm_auth_error
from app.models.faceless import FacelessCharacter, FacelessProject, FacelessScriptVersion, FacelessSeries
from app.services import storyscript as ss

from . import consent
from .errors import FacelessError, InvalidRequest, NotReady, Unavailable, UpstreamError

logger = logging.getLogger(__name__)

MAX_PREVIOUS_SERIES = 20
MAX_PREVIOUS_RECENT = 10
MAX_EPISODE_MEMORY = 50


def dump(obj):
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [dump(o) for o in obj]
    return obj


def _supported(fn, kwargs: dict) -> dict:
    """Drop optional keyword arguments the engine function does not take."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind == p.VAR_KEYWORD for p in params.values()):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in params}


async def _call(fn, *args, **kwargs):
    try:
        result = fn(*args, **_supported(fn, kwargs))
        if inspect.isawaitable(result):
            result = await result
        return result
    except FacelessError:
        raise
    except ss.LLMNotConfigured as exc:
        logger.error(f"Script engine is not configured: {exc}")
        raise Unavailable("Add a language model key in Settings, under API keys, to draft scripts.",
                          code="llm_not_configured")
    except ss.InvalidLLMOutput as exc:
        logger.warning(f"Script engine returned an invalid result: {exc} ({getattr(exc, 'last_error', '')})")
        raise UpstreamError("The AI writer returned an invalid result. Please try again.",
                            code="invalid_llm_output")
    except getattr(ss, "LLMCallFailed", ss.StoryScriptError) as exc:
        if isinstance(exc, (ss.StoryScriptInputError, ss.LLMNotConfigured)):
            raise
        logger.warning(f"Script engine call failed: {exc}", exc_info=True)
        if is_llm_auth_error(exc) or is_llm_auth_error(exc.__cause__):
            raise UpstreamError(LLM_KEY_REJECTED, code="llm_key_rejected")
        raise UpstreamError("The AI writer could not be reached. Please try again.",
                            code="llm_call_failed")
    except ss.StoryScriptInputError as exc:
        raise InvalidRequest(str(exc), code="invalid_input")
    except NotImplementedError as exc:
        raise NotReady("The script engine is not available yet.", code="not_implemented") from exc


def _sync(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ss.StoryScriptInputError as exc:
        raise InvalidRequest(str(exc), code="invalid_input")
    except NotImplementedError as exc:
        raise NotReady("The script engine is not available yet.", code="not_implemented") from exc


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def templates() -> list[dict]:
    try:
        return [dump(t) for t in ss.list_templates()]
    except NotImplementedError:
        return []


def template(template_id: str) -> dict | None:
    try:
        return dump(ss.get_template(template_id))
    except (KeyError, NotImplementedError, ss.StoryScriptError):
        return None


def require_template(template_id: str) -> dict:
    tpl = template(template_id)
    if tpl is None:
        raise InvalidRequest(f"Unknown template '{template_id}'.", code="unknown_template")
    return tpl


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def cast_briefs(chars: list[FacelessCharacter]) -> list:
    return [ss.CharacterBrief.model_validate(consent.character_brief(c)) for c in chars]


def series_brief(db: Session, series: FacelessSeries | None, project: FacelessProject):
    if series is None:
        return None
    memory = [m for m in (series.episode_memory or []) if m.get("project_id") != project.id]
    episodes = [
        ss.EpisodeSummary(
            title=m.get("title") or "",
            premise=m.get("premise") or "",
            outcome=m.get("outcome") or "",
            situation=m.get("situation"),
        )
        for m in memory[-MAX_EPISODE_MEMORY:]
    ]
    return ss.SeriesBrief(
        id=series.id,
        title=series.title or "",
        logline=series.logline or "",
        world=series.world_notes or "",
        tone=series.tone or "",
        rules=list(series.rules or []),
        episode_number=len(episodes) + 1,
        previous_episodes=episodes,
    )


def facts_of(project: FacelessProject) -> list:
    out = []
    for i, f in enumerate(project.facts or []):
        if isinstance(f, dict) and (f.get("text") or "").strip():
            out.append(ss.Fact(id=str(f.get("id") or f"f{i + 1}"), text=f["text"],
                               source=f.get("source") or "", date=f.get("date") or ""))
    return out


# ---------------------------------------------------------------------------
# Drafting
# ---------------------------------------------------------------------------

async def draft(db: Session, project: FacelessProject, chars: list[FacelessCharacter],
                series: FacelessSeries | None) -> dict:
    script = await _call(
        ss.draft_script, db,
        template_id=project.template_id,
        idea=project.idea or project.title or "",
        length_seconds=int(project.length_seconds),
        aspect=project.aspect,
        cast=cast_briefs(chars),
        series=series_brief(db, series, project),
        facts=facts_of(project) or None,
        language=project.language or "en",
        narrator_voice=project.narrator_voice,
        user_id=project.user_id,
    )
    return dump(script)


async def revise(db: Session, script: dict, scene_id: str, instruction: str,
                 chars: list[FacelessCharacter] | None = None, user_id: int | None = None) -> dict:
    model = validate_script(script)
    scene = await _call(ss.revise_scene, db, script=model, scene_id=scene_id, instruction=instruction,
                        cast=cast_briefs(chars) if chars else None, user_id=user_id)
    return dump(scene)


async def describe(db: Session, char: FacelessCharacter, image_urls: list[str]) -> dict:
    bible = await _call(ss.describe_character, db, name=char.name, image_urls=image_urls,
                        notes=char.notes or None, user_id=char.user_id)
    return dump(bible)


async def make_package(db: Session, script: dict, aspect: str, chars: list[FacelessCharacter] | None = None,
                       user_id: int | None = None) -> dict:
    return dump(await _call(ss.package, db, script=validate_script(script), aspect=aspect,
                            cast=cast_briefs(chars) if chars else None, user_id=user_id))


def validate_script(data: dict):
    try:
        return ss.Script.model_validate(data)
    except Exception as exc:
        logger.warning(f"Script failed validation: {exc}")
        raise InvalidRequest("The script could not be saved because some of it is missing or too long. "
                             "Check each scene and try again.", code="invalid_script")


def validate_scene(data: dict):
    try:
        return ss.Scene.model_validate(data)
    except Exception as exc:
        logger.warning(f"Scene failed validation: {exc}")
        raise InvalidRequest("The scene could not be saved because some of it is missing or too long. "
                             "Check it and try again.", code="invalid_scene")


# ---------------------------------------------------------------------------
# Versions, compliance and originality
# ---------------------------------------------------------------------------

def save_version(db: Session, project: FacelessProject, script: dict, source: str) -> int:
    """Store ``script`` as the project's next version and make it current. No commit.

    Every save path (draft, edit, revise, restore) comes through here, so the
    script limits are checked here."""
    check_script_limits(script)
    version = int(project.script_version or 0) + 1
    script = dict(script)
    script["version"] = version
    db.add(FacelessScriptVersion(
        project_id=project.id, user_id=project.user_id, version=version, source=source, script=script,
    ))
    project.script = script
    project.script_version = version
    if script.get("title") and (not project.title or project.title == "Untitled"):
        project.title = script["title"][:200]
    if project.status == "draft":
        project.status = "scripted"
    return version


def previous_scripts(db: Session, project: FacelessProject) -> list:
    """The user's earlier scripts to compare against: the same series, else the last ten."""
    query = db.query(FacelessProject).filter(
        FacelessProject.user_id == project.user_id,
        FacelessProject.id != project.id,
        FacelessProject.script.isnot(None),
    )
    if project.series_id:
        rows = query.filter(FacelessProject.series_id == project.series_id) \
            .order_by(FacelessProject.created_at.desc()).limit(MAX_PREVIOUS_SERIES).all()
    else:
        rows = query.order_by(FacelessProject.created_at.desc()).limit(MAX_PREVIOUS_RECENT).all()
    out = []
    for row in rows:
        try:
            out.append(ss.Script.model_validate(row.script))
        except Exception:
            continue
    return out


def run_checks(db: Session, project: FacelessProject, chars: list[FacelessCharacter]) -> None:
    """Compliance and originality for the current script, stored on the project. No commit."""
    if not project.script:
        return
    script = validate_script(project.script)
    now = datetime.utcnow().isoformat()
    try:
        flags = dump(_sync(ss.compliance_check, script, cast_briefs(chars))) or []
        project.compliance = {
            "flags": flags,
            "blocked": any(f.get("severity") == "block" for f in flags),
            "checked_at": now,
            "script_version": project.script_version,
        }
    except NotReady:
        project.compliance = {"flags": [], "blocked": False, "checked_at": now,
                              "script_version": project.script_version, "unavailable": True}
    try:
        report = dump(_sync(ss.originality_check, script, previous_scripts(db, project))) or {}
        report["script_version"] = project.script_version
        report["checked_at"] = now
        project.originality = report
    except NotReady:
        project.originality = {"unavailable": True, "script_version": project.script_version, "checked_at": now}


def remember_episode(series: FacelessSeries | None, project: FacelessProject) -> None:
    """Upsert this project's summary into the series' episode memory. No commit."""
    if series is None or not project.script:
        return
    script = project.script
    entry = {
        "project_id": project.id,
        "title": script.get("title") or project.title or "",
        "premise": script.get("premise") or script.get("logline") or "",
        "outcome": script.get("outcome") or "",
        "situation": script.get("situation") or None,
    }
    memory = [m for m in (series.episode_memory or []) if m.get("project_id") != project.id]
    memory.append(entry)
    series.episode_memory = memory[-MAX_EPISODE_MEMORY:]


def _finite(value, low: float, high: float, label: str) -> None:
    if value is None:
        return
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise InvalidRequest(f"{label} must be a number.", code="invalid_script")
    if not math.isfinite(number) or number < low or number > high:
        raise InvalidRequest(f"{label} must be between {low:g} and {high:g}.", code="invalid_script")


def _text(value, limit: int, label: str) -> int:
    n = len(value) if isinstance(value, str) else 0
    if n > limit:
        raise InvalidRequest(f"{label} is too long ({n} characters, at most {limit}).", code="invalid_script")
    return n


def check_script_limits(script: dict) -> None:
    """Bounds on everything in a script that drives timing, prices, renders
    or storage. A script comes from the LLM or straight from the client (PUT
    /script), so none of it is trusted: durations must be finite and in
    range (JSON allows NaN and Infinity, and a negative silence would make a
    render free), text is bounded, and the whole document is capped."""
    from . import catalog

    if not isinstance(script, dict):
        raise InvalidRequest("The script is not valid.", code="invalid_script")
    try:
        size = len(json.dumps(script, allow_nan=False, default=str))
    except ValueError:
        raise InvalidRequest("The script contains a number that is not finite.", code="invalid_script")
    if size > catalog.MAX_SCRIPT_JSON_BYTES:
        raise InvalidRequest(f"The script is too large ({size // 1000} KB).", code="invalid_script")
    scenes = script.get("scenes") or []
    if len(scenes) > catalog.MAX_SCENES:
        raise InvalidRequest(f"A script can have at most {catalog.MAX_SCENES} scenes.")
    ids = [str(s.get("id")) for s in scenes if isinstance(s, dict)]
    if len(ids) != len(scenes) or len(set(ids)) != len(ids):
        raise InvalidRequest("Scene ids must be unique.", code="invalid_script")
    spoken = 0
    for scene in scenes:
        sid = scene.get("id")
        _finite(scene.get("duration"), 0, catalog.MAX_SCENE_SECONDS, f"Scene {sid} duration")
        _finite(scene.get("start"), 0, 24 * 3600, f"Scene {sid} start")
        _finite(scene.get("silence_after"), 0, catalog.MAX_SILENCE_SECONDS, f"Scene {sid} silence")
        shot = scene.get("shot") or {}
        if isinstance(shot, dict):
            _finite(shot.get("clip_seconds"), 0, catalog.CLIP_MAX_SECONDS * 4, f"Scene {sid} clip length")
            _text(shot.get("visual_prompt"), catalog.MAX_PROMPT_CHARS, f"Scene {sid} visual prompt")
            _text(shot.get("direction"), catalog.MAX_PROMPT_CHARS, f"Scene {sid} direction")
            if len(shot.get("characters") or []) > catalog.MAX_CAST * 2:
                raise InvalidRequest(f"Scene {sid} has too many characters in frame.", code="invalid_script")
        spoken += _text(scene.get("narration"), catalog.MAX_NARRATION_CHARS, f"Scene {sid} narration")
        _text(scene.get("on_screen_text"), catalog.MAX_ON_SCREEN_TEXT, f"Scene {sid} on screen text")
        dialogue = scene.get("dialogue") or []
        if len(dialogue) > catalog.MAX_DIALOGUE_LINES:
            raise InvalidRequest(f"Scene {sid} has more than {catalog.MAX_DIALOGUE_LINES} dialogue lines.",
                                 code="invalid_script")
        for line in dialogue:
            if isinstance(line, dict):
                spoken += _text(line.get("text"), catalog.MAX_LINE_CHARS, f"A dialogue line in scene {sid}")
    if spoken > catalog.MAX_SCRIPT_SPOKEN_CHARS:
        raise InvalidRequest(f"The script has {spoken} spoken characters; the limit is "
                             f"{catalog.MAX_SCRIPT_SPOKEN_CHARS}.", code="invalid_script")


def check_scene_count(script: dict) -> None:
    check_script_limits(script)


def apply_script(db: Session, project: FacelessProject, script: dict, source: str,
                 chars: list[FacelessCharacter]) -> int:
    """Save ``script`` as the next version of a locked project, then run the
    compliance and originality checks and update the series memory. No commit."""
    check_scene_count(script)
    version = save_version(db, project, script, source)
    db.flush()
    run_checks(db, project, chars)
    if project.series_id:
        series = db.query(FacelessSeries).filter(FacelessSeries.id == project.series_id).first()
        remember_episode(series, project)
    return version


def is_long_form(project: FacelessProject, tpl: dict | None) -> bool:
    """Drafts that take several LLM calls (outline plus chunks) run in the scheduler."""
    if int(project.length_seconds or 0) > 90:
        return True
    return bool(tpl) and not tpl.get("shorts", True)

