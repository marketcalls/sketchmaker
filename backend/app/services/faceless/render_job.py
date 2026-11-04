"""The render step: build a Timeline from a project and render it.

Runs only on a scheduler thread, one render at a time across the system:
render_tick() first takes the shared render slot (app/services/render_queue.py, also
used by /motion-graphics), then claims the oldest queued render. A render whose process
died is requeued once, then failed.

Every source is linked or copied into a private work directory first; the render engine
never touches the network. The result is stored as a gallery Video (video_type
"faceless", model "faceless-studio"). No write is held while ffmpeg runs: progress is a
short update and commit, and the result is applied under the lock at the end.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.database import apply_row_lock
from app.models.content import Video
from app.models.faceless import FacelessProject, FacelessStepRun
from app.services.job_state import is_temporary_failure, update_job_if

from . import activity, catalog, media
from .grade import load_plates, plate_key, timeline_grade
from .pricing import Ctx, build_ctx
from .scenes import is_ad, scene_by_id, shot_kind, total_seconds

logger = logging.getLogger(__name__)

VIDEO_TYPE = "faceless"
VIDEO_MODEL = "faceless-studio"
ACCENT = "#FFD166"
PROGRESS_EVERY_SECONDS = 2.0
# Wall-clock budget of one render: a fixed allowance plus a multiple of the
# video length. Past it the render is stopped and failed, so a stuck decoder can
# never hold the system-wide render slot forever.
RENDER_BUDGET_BASE_SECONDS = 20 * 60
RENDER_BUDGET_PER_VIDEO_SECOND = 8.0
# Sources in the work directory, and the free disk the render needs beyond them
# (output, audio and the encoder's temporary file).
RENDER_MAX_SOURCE_BYTES = 6 * 1024 ** 3
RENDER_DISK_MARGIN_BYTES = 1024 ** 3
RENDER_OUTPUT_BYTES_PER_SECOND = 1_000_000  # 1080p at CRF 20 stays well under 8 Mbit/s
VOICE_LUFS = -16.0  # every voice take is leveled to this before the mix
# The ad logo (project settings ad_logo_asset_id, a raster My Assets image)
# sits in ``local`` under this key once copied into the work directory.
AD_LOGO_KEY = "__ad_logo__"
AD_LOGO_EXTS = (".png", ".jpg", ".jpeg", ".webp")
SFX_GAIN = {"whoosh": -9.0, "hit": -6.0, "riser": -12.0}


def _sfx_paths() -> dict[str, str]:
    """Whoosh, hit and riser, synthesized once by /motion-graphics (lavfi, no
    samples) and cached on local disk; empty when they cannot be made."""
    try:
        from app.services.motion_graphics.audio import sfx_paths

        return sfx_paths()
    except Exception as exc:
        logger.warning(f"Faceless render: sound effects unavailable: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def _assets_needed(ctx: Ctx) -> list[dict]:
    """Every stored file the render reads."""
    out = []
    for t in ctx.timing:
        a = ctx.assets(t["scene_id"])
        for key in ("stills", "clips"):
            out.extend(x for x in a.get(key) or [] if x)
        if a.get("user_media"):
            out.append(a["user_media"])
        stored = {int(v["index"]): v for v in a.get("voice") or []}
        for line in t["lines"]:
            clip = stored.get(line["index"])
            if clip and clip.get("hash") == line["hash"]:
                out.append(clip)
    out.extend((ctx.project.music or {}).get("tracks") or [])
    return out


# Scene transitions as render engine transitions: J and L cuts are hard cuts
# whose voice and picture are offset (build_timeline).
RENDER_TRANSITION = {"cut": "cut", "crossfade": "crossfade", "dip_black": "dip_black",
                     "j_cut": "cut", "l_cut": "cut"}


def scene_transition(ctx: Ctx, scene: dict, n: int) -> str:
    """How scene ``n`` arrives: the scene's own transition (Story Room
    handoffs carry the director's), else the template's. Templates cut hard
    (cuts are made in the edit unless the brief asks otherwise); only the
    sleep template dissolves."""
    if n == 0:
        return "cut"
    value = scene.get("transition_in") or (ctx.template or {}).get("transition") or "cut"
    return value if value in RENDER_TRANSITION else "cut"


def _fit(entry: dict, width: int, height: int) -> str:
    """Cover, unless the source is clearly another shape than the frame (a
    square product photo animated for a vertical video): then contained over
    its own blurred fill rather than cropped to a sliver."""
    w, h = entry.get("width"), entry.get("height")
    if not w or not h:
        return "cover"
    ratio = (float(w) / float(h)) / (width / height)
    return "contain" if ratio > 1.3 or ratio < 1 / 1.3 else "cover"


def _video_slot(entry: dict, src: str, start: float, length: float, slot: float, width: int, height: int,
                transition: str) -> dict:
    """A video clip filling ``slot`` seconds. A clip a little short plays
    slightly slower (speed >= CLIP_MIN_SPEED); a larger gap holds its last
    frame under a slow push-in. Never a frozen frame."""
    out = {"start": round(start, 3), "duration": round(slot, 3), "kind": "video", "src": src,
           "transition_in": transition, "loop_video": False, "hold": "push_in",
           "fit": _fit(entry, width, height)}
    if length > 0 and slot > length + 0.04 and length / slot >= catalog.CLIP_MIN_SPEED:
        out["speed"] = round(length / slot, 4)
    return out


def _visuals(ctx: Ctx, scene: dict, start: float, dur: float, local: dict, transition: str,
             size: tuple[int, int] = (1080, 1920), inner: str = "cut") -> list[dict]:
    """Base track clips for one scene, back to back from ``start``.
    ``transition`` brings the scene in; within it, clip parts cut hard (they
    are chained on shared frames) and stills use ``inner``."""
    width, height = size
    a = ctx.assets(scene["id"])
    um = a.get("user_media")
    if um and local.get(um["file"]):
        if um.get("kind") == "video":
            length = float(um.get("duration") or 0)
            return [_video_slot(um, local[um["file"]], start, length, dur, width, height, transition)]
        return [{"start": start, "duration": dur, "kind": "image", "src": local[um["file"]],
                 "motion": "ken_burns", "transition_in": transition}]
    stills = [s for s in a.get("stills") or [] if s and local.get(s["file"])]
    clips = [c for c in a.get("clips") or [] if c and local.get(c["file"])]
    out: list[dict] = []
    t = start
    end = start + dur
    lengths = []
    for clip in clips:
        if end - t < 0.5:
            break
        length = float(clip.get("duration") or clip.get("seconds") or 5.0)
        lengths.append(length)
        slot = min(length, end - t)
        out.append(_video_slot(clip, local[clip["file"]], t, length, slot, width, height,
                               transition if not out else "cut"))
        t += slot
    remaining = end - t
    if out:
        if remaining > 0.05:
            # The last part fills the scene: slower by a few per cent, or
            # held under a push-in (the next scene's cut follows).
            last = out[-1]
            slot = last["duration"] + remaining
            out[-1] = _video_slot(clips[len(out) - 1], last["src"], last["start"], lengths[len(out) - 1],
                                  slot, width, height, last["transition_in"])
    elif stills and remaining > 0.05:
        each = remaining / len(stills)
        for still in stills:
            out.append({"start": round(t, 3), "duration": round(each, 3), "kind": "image",
                        "src": local[still["file"]], "motion": "ken_burns",
                        "transition_in": transition if not out else inner})
            t += each
    if not out:
        out.append({"start": start, "duration": dur, "kind": "gradient",
                    "gradient": ["#0B1020", "#1B2338", "#04060A"], "transition_in": transition})
    return out


def build_timeline(ctx: Ctx, local: dict, options: dict) -> dict:
    """Timeline dict (validated by app.render) for the project's current state."""
    project, script = ctx.project, ctx.script
    res = options.get("resolution") or catalog.DEFAULT_RENDER_RESOLUTION
    width, height = catalog.FRAME_SIZES[res][project.aspect]
    preset = options.get("captions") or project.caption_preset or script.get("caption_preset") or "bold_pop"
    if preset not in catalog.CAPTION_STYLE_IDS:
        preset = "bold_pop"
    names = {cid: c.name for cid, c in ctx.char_by_id.items()}

    clips: list[dict] = []
    overlays: list[dict] = []
    words: list[dict] = []
    audio: list[dict] = []
    body = total_seconds(ctx.timing)
    outro = ctx.outro
    total = round(body + outro, 3)
    ad = ctx.is_ad
    template_inner = "crossfade" if (ctx.template or {}).get("transition") == "crossfade" else "cut"
    sfx = _sfx_paths() if any(s.get("sfx") for s in script.get("scenes") or []) else {}
    split = catalog.SPLIT_EDIT_SECONDS

    for n, t in enumerate(ctx.timing):
        scene = scene_by_id(script, t["scene_id"]) or {}
        start, dur = t["start"], t["duration"]
        cut = scene_transition(ctx, scene, n)
        # L cut: this picture arrives before the previous scene's voice ends.
        if cut == "l_cut" and clips and clips[-1]["duration"] > split + 0.5:
            clips[-1]["duration"] = round(clips[-1]["duration"] - split, 3)
            start, dur = round(start - split, 3), round(dur + split, 3)
        transition = RENDER_TRANSITION[cut]
        if shot_kind(scene) == "card" and not ctx.assets(t["scene_id"]).get("user_media"):
            clips.append({"start": start, "duration": dur, "kind": "gradient",
                          "gradient": ["#10162A", "#04060A"], "transition_in": transition})
            if scene.get("on_screen_text"):
                overlays.append({"kind": "text", "text": scene["on_screen_text"], "start": start,
                                 "duration": dur, "anchor": "center", "z": 20,
                                 "enter": {"type": "word_pop", "duration": 0.6}})
        else:
            visuals = _visuals(ctx, scene, start, dur, local, transition, (width, height), template_inner)
            plate = local.get(plate_key(str(t["scene_id"])))
            if plate:
                for v in visuals:
                    if v["kind"] in ("image", "video"):
                        v["match_ref"] = plate  # colour matched when the grade asks (grade.py)
            clips.extend(visuals)
            # The title card covers the first scene of a story; an ad opens
            # on its hook, so the hook's text is up from the first frame.
            if scene.get("on_screen_text") and (n > 0 or ad):
                lead = 0.0 if (ad and n == 0) else 0.3
                overlays.append({"kind": "text", "text": scene["on_screen_text"], "start": round(t["start"] + lead, 3),
                                 "duration": round(max(0.5, t["duration"] - lead - 0.2), 3), "anchor": "top",
                                 "z": 15, "style": {"size": 46, "weight": 800},
                                 **({"enter": {"type": "none", "duration": 0}} if ad and n == 0 else {})})
        stat = scene.get("stat")
        if stat and stat.get("value") and dur > 1.5:
            overlays.append({"kind": "stat_card", "value": str(stat["value"]), "label": stat.get("label") or None,
                             "start": round(start + 0.53, 3), "duration": round(max(1.0, dur - 0.8), 3), "z": 30})
        effect = sfx.get(scene.get("sfx") or "")
        if effect and n > 0:
            # A whoosh leads into the cut; a hit lands on it.
            at = t["start"] - (0.3 if scene.get("sfx") == "whoosh" else 0.0)
            audio.append({"src": effect, "start": round(max(0.0, at), 3), "role": "sfx",
                          "gain_db": SFX_GAIN.get(scene["sfx"], -9.0)})

        stored = {int(v["index"]): v for v in ctx.assets(t["scene_id"]).get("voice") or []}
        # J cut: this scene's voice starts before its picture.
        cursor = max(0.0, t["start"] - split) if cut == "j_cut" else t["start"]
        for line in t["lines"]:
            clip = stored.get(line["index"])
            if not clip or clip.get("hash") != line["hash"] or not local.get(clip["file"]):
                continue
            audio.append({"src": local[clip["file"]], "start": round(cursor, 3), "role": "voice"})
            speaker = names.get(str(line.get("character_id") or "")) or None
            for w in clip.get("words") or []:
                words.append({"text": w["text"], "start": round(cursor + float(w["start"]), 3),
                              "end": round(cursor + float(w["end"]), 3), "speaker": speaker})
            cursor += float(clip["duration"]) + catalog.LINE_PAUSE_SECONDS

    if ctx.timing:
        first = ctx.timing[0]
        first_scene = scene_by_id(script, first["scene_id"]) or {}
        title = (script.get("title") or project.title or "").strip()
        if title and not ad:
            overlays.append({
                "kind": "title_card", "title": title, "start": 0.0,
                "duration": round(min(catalog.TITLE_CARD_SECONDS, first["duration"]), 3),
                "narrow": bool(first_scene.get("stat")), "z": 40,
            })
        label = script.get("dramatization_label")
        if label:
            overlays.append({"kind": "text", "text": label, "start": 0.0, "duration": round(min(4.0, body), 3),
                             "anchor": "top_left", "z": 50, "style": {"size": 26, "weight": 600}})

    # Outro: the last picture with the outro card over it, no voice. An ad
    # ends on its brand beat: the call to action, the offer and the logo.
    last_still = None
    for t in reversed(ctx.timing):
        stills = [s for s in ctx.assets(t["scene_id"]).get("stills") or [] if s and local.get(s["file"])]
        if stills:
            last_still = stills[-1]
            break
    into_outro = "cut" if ad else "crossfade"
    if last_still:
        clips.append({"start": round(body, 3), "duration": round(outro, 3), "kind": "image",
                      "src": local[last_still["file"]], "motion": "push_in", "zoom_from": 1.04, "zoom_to": 1.12,
                      "transition_in": into_outro})
    else:
        clips.append({"start": round(body, 3), "duration": round(outro, 3), "kind": "color",
                      "color": "#04060A", "transition_in": into_outro})
    card = script.get("ad") or {}
    if ad:
        outro_title = (card.get("cta") or card.get("brand") or script.get("outro_title") or "").strip()
        subtitle = (card.get("offer") or "").strip() or None
    else:
        outro_title = (script.get("outro_title") or script.get("title") or project.title or "").strip()
        subtitle = script.get("vote_prompt") or None
    if outro_title:
        overlays.append({"kind": "outro_card", "title": outro_title, "subtitle": subtitle,
                         "start": round(body, 3), "duration": round(outro, 3), "z": 60})
    logo = local.get(AD_LOGO_KEY)
    if ad and logo:
        overlays.append({"kind": "logo", "src": logo, "start": round(body, 3), "duration": round(outro, 3),
                         "anchor": "top", "width": 220, "z": 65})
    overlays.append({"kind": "scrim", "start": 0.0, "duration": total, "z": 1})
    overlays.append({"kind": "vignette", "start": 0.0, "duration": total, "z": 2})

    music = project.music or {}
    if music.get("tracks") and project.music_mood != "none" and options.get("music", True) is not False:
        tpl_gain = ((ctx.template or {}).get("music") or {}).get("gain_db", -18.0)
        # Music is leveled against the voice by the engine (output.voice_lufs);
        # the template's and the user's gain only trim that, relative to the
        # template default.
        gain = float(options.get("music_gain_db", tpl_gain)) - float(tpl_gain)
        tracks = [tr for tr in music["tracks"] if local.get(tr["file"])]
        for k, tr in enumerate(tracks):
            start = float(tr.get("start") or 0.0)
            span = (float(tracks[k + 1].get("start")) - start) if k + 1 < len(tracks) else total - start
            have = float(tr.get("duration") or 0) or span
            # Loop only a track that is clearly too short (a regenerated
            # timeline); a few seconds short (the outro, see
            # pricing.music_track_lengths) just ends on its fade.
            loop = have + 15.0 < span
            audio.append({
                "src": local[tr["file"]], "start": round(start, 3), "role": "music", "gain_db": gain,
                "duck_under_voice": True, "fade_in": 1.0 if k == 0 else 0.0,
                "fade_out": 2.0 if k == len(tracks) - 1 else 0.0,
                "loop": loop, "duration": round(span if loop else min(span, have), 3),
            })

    timeline = {
        "width": width, "height": height, "fps": 30, "duration": total, "background": "#04060A",
        "accent": ACCENT, "clips": clips, "overlays": overlays, "audio": audio,
        # Voice leveled to -16 LUFS with a gentle bus compressor, music 16 LU
        # under it while ducked; the whole mix then goes to -14 LUFS, -1.5 dBTP.
        "output": {"loudness_lufs": -14, "crf": 20, "preset": "veryfast", "threads": 2,
                   "voice_lufs": VOICE_LUFS, "music_under_voice_lu": 16.0, "voice_compressor": True},
    }
    grade = timeline_grade(project.settings)
    if grade:
        timeline["grade"] = grade  # base track only: titles, captions and the end card stay ungraded
    if words and preset != "none":
        # The project's caption choices (schemas.ProjectSettings), else the defaults.
        prefs = project.settings or {}
        highlight = prefs.get("caption_highlight")
        if not (isinstance(highlight, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", highlight)):
            highlight = ACCENT
        timeline["captions"] = {
            "words": words, "preset": preset, "highlight": highlight,
            "platform_safe_zone": "ads" if ad else catalog.SAFE_ZONE[project.aspect],
        }
        if prefs.get("caption_position") in ("lower", "middle", "upper"):
            timeline["captions"]["position"] = prefs["caption_position"]
    return timeline


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def work_root() -> str | None:
    """Disk-backed scratch space (XDG_CACHE_HOME, set in app/config.py); None falls back
    to the system temp directory."""
    base = os.environ.get("XDG_CACHE_HOME")
    if not base:
        return None
    root = os.path.join(base, "faceless-render")
    try:
        os.makedirs(root, exist_ok=True)
        return root if os.access(root, os.W_OK) else None
    except OSError:
        return None


def _sweep_workdirs() -> None:
    """Remove work directories left by a render whose process died. Called
    with the render slot held, so no faceless render is using them."""
    root = work_root() or tempfile.gettempdir()
    try:
        names = [n for n in os.listdir(root) if n.startswith("faceless_render_")]
    except OSError:
        return
    for name in names:
        shutil.rmtree(os.path.join(root, name), ignore_errors=True)


class RenderStopped(RuntimeError):
    """A render stopped for a reason whose message is written for the user."""


def _close(db: Session, run: FacelessStepRun, status: str, error: str | None = None) -> None:
    items = [dict(i) for i in run.items or []]
    for item in items:
        item["status"] = "done" if status == "completed" else ("cancelled" if status == "cancelled" else "failed")
        item["error"] = error
    media.set_json(run, "items", items)
    run.status = status
    run.error = error[:1000] if error else None
    run.progress = 100
    run.completed_at = datetime.utcnow()


def _renders(db: Session, *conditions):
    return db.query(FacelessStepRun).filter(FacelessStepRun.step == "render", *conditions)


def _lock_render(db: Session, run_id: int) -> FacelessStepRun | None:
    return apply_row_lock(db.query(FacelessStepRun).filter(FacelessStepRun.id == run_id)).first()


def _close_cancelled_before_start(db: Session) -> None:
    query = (FacelessStepRun.status == "queued", FacelessStepRun.cancel_requested == True)  # noqa: E712
    if _renders(db, *query).first() is None:
        return
    for run in apply_row_lock(_renders(db, *query)).all():
        _close(db, run, "cancelled", "Cancelled")
    db.commit()


def _requeue_orphans(db: Session) -> None:
    """Holding the render slot proves that a faceless render still marked "running" has no
    process: it goes back in the queue once, then fails."""
    running = (FacelessStepRun.status == "running",)
    if _renders(db, *running).first() is None:
        return
    for run in apply_row_lock(_renders(db, *running)).all():
        if (run.attempts or 0) >= catalog.RENDER_MAX_ATTEMPTS:
            _close(db, run, "failed", "The render stopped responding. Please try again.")
        else:
            logger.warning(f"Faceless render {run.id} was orphaned (process died); requeued")
            run.status = "queued"
    db.commit()


def render_tick(db: Session) -> int | None:
    """Claim and run at most one render. Returns the run id rendered, if any.

    The system-wide render slot (app/services/render_queue.py, shared with
    /motion-graphics) is taken before claiming, so at most one render of any studio runs
    at a time.
    """
    from app.services.render_queue import render_slot

    _close_cancelled_before_start(db)

    with render_slot("faceless") as acquired:
        if not acquired:
            return None  # another render (either studio) holds the slot
        _sweep_workdirs()
        _requeue_orphans(db)
        run = _renders(db, FacelessStepRun.status == "queued").order_by(FacelessStepRun.created_at).first()
        if run is None:
            db.rollback()
            return None
        run_id = run.id
        now = datetime.utcnow()
        if not update_job_if(db, FacelessStepRun, run_id, ("queued",), {
                "status": "running", "started_at": run.started_at or now, "heartbeat_at": now,
                "attempts": int(run.attempts or 0) + 1, "progress": 0}):
            return None
        execute(db, run_id)
        return run_id


def _place_source(asset: dict, user_id: int, dest: str) -> int:
    """Put a stored file in the work directory: a hard link when the folder allows it
    (a replaced or deleted source cannot disturb the render, and no bytes are copied),
    otherwise a copy. Returns its size; raises RenderStopped when the file is gone."""
    source = media.local_path(asset, user_id)
    if not os.path.isfile(source):
        logger.error(f"Faceless render: stored file {asset.get('file')} is missing")
        raise RenderStopped("A file this project uses is missing. Upload it again, then render once more")
    size = os.path.getsize(source)
    try:
        os.link(source, dest)
    except OSError:
        shutil.copyfile(source, dest)
    return size


def _discard(written: list[dict], user_id: int) -> None:
    for asset in written:
        try:
            media.run_async(media.delete_stored(asset, user_id))
        except Exception as exc:
            logger.warning(f"Could not delete faceless render file: {type(exc).__name__}")
    written.clear()


def execute(db: Session, run_id: int) -> None:
    from app.render import RenderCancelled, render_timeline

    run = db.query(FacelessStepRun).filter(FacelessStepRun.id == run_id).first()
    project = db.query(FacelessProject).filter(FacelessProject.id == run.project_id).first() if run else None
    if run is None:
        return
    if project is None:
        run = _lock_render(db, run_id)
        _close(db, run, "failed", "The project was deleted.")
        db.commit()
        return

    user_id = project.user_id
    options = dict(((run.items or [{}])[0] or {}).get("arguments") or {})
    try:
        workdir = tempfile.mkdtemp(prefix=f"faceless_render_{run_id}_", dir=work_root())
    except OSError as exc:
        logger.error(f"Faceless render {run_id} could not make its work folder: {exc}", exc_info=True)
        run = _lock_render(db, run_id)
        _close(db, run, "failed", "The render could not start (no work space). Please try again.")
        db.commit()
        return
    planned = float(((run.items or [{}])[0] or {}).get("seconds") or 0) or 60.0
    budget = RENDER_BUDGET_BASE_SECONDS + RENDER_BUDGET_PER_VIDEO_SECOND * planned
    reserve = RENDER_DISK_MARGIN_BYTES + int(RENDER_OUTPUT_BYTES_PER_SECOND * planned)
    started = time.monotonic()
    state = {"last": 0.0, "checked": 0.0, "cancel": False, "timeout": False}
    written: list[dict] = []  # stored files to remove if the render does not land

    def check_cancel() -> bool:
        if time.monotonic() - started > budget:
            state["timeout"] = True
            return True
        flag = db.query(FacelessStepRun.cancel_requested).filter(FacelessStepRun.id == run_id).scalar()
        db.rollback()
        return bool(flag)

    def progress(fraction: float) -> None:
        now = time.monotonic()
        if now - state["last"] < PROGRESS_EVERY_SECONDS and fraction < 1.0:
            return
        state["last"] = now
        try:
            db.query(FacelessStepRun).filter(FacelessStepRun.id == run_id).update(
                {FacelessStepRun.progress: int(max(0.0, min(1.0, float(fraction))) * 95),
                 FacelessStepRun.heartbeat_at: datetime.utcnow()}, synchronize_session=False)
            db.commit()
            state["cancel"] = check_cancel()
        except Exception as exc:
            db.rollback()
            logger.warning(f"Render {run_id}: progress update failed: {exc}")

    def cancelled() -> bool:
        now = time.monotonic()
        if now - state["checked"] >= PROGRESS_EVERY_SECONDS:
            state["checked"] = now
            try:
                state["cancel"] = check_cancel()
            except Exception:
                db.rollback()
        return state["cancel"]

    try:
        ctx = build_ctx(db, project)
        local: dict[str, str] = {}
        src_dir = os.path.join(workdir, "src")
        os.makedirs(src_dir, exist_ok=True)
        placed = 0
        for asset in _assets_needed(ctx):
            if asset["file"] in local:
                continue
            path = os.path.join(src_dir, os.path.basename(asset["file"]))
            if shutil.disk_usage(workdir).free < reserve:
                raise RenderStopped("The render could not start right now. Please try again in a few minutes")
            placed += _place_source(asset, user_id, path)
            if placed > RENDER_MAX_SOURCE_BYTES:
                raise RenderStopped("The project's media is too large to render in one piece")
            local[asset["file"]] = path
        logo = _ad_logo(db, project)
        if logo:
            path = os.path.join(src_dir, f"ad_logo{logo[1]}")
            with open(path, "wb") as fh:
                fh.write(logo[0])
            local[AD_LOGO_KEY] = path
        load_plates(project, src_dir, local)
        if cancelled():
            raise RenderCancelled("render cancelled")
        timeline = build_timeline(ctx, local, options)
        out_path = os.path.join(workdir, f"out_{uuid.uuid4().hex}.mp4")
        result = render_timeline(timeline, out_path, workdir=os.path.join(workdir, "engine"),
                                 progress=progress, cancel=cancelled)
        thumb = media.video_thumbnail(result.path, at_seconds=min(1.5, max(0.1, result.duration / 3)))
        # Streamed from disk: a 15 minute 1080p render can be several hundred MB.
        stored = media.run_async(media.store_file(result.path, user_id=user_id, storage="videos",
                                                  prefix="faceless", ext=".mp4", content_type="video/mp4"))
        written.append(stored)
        thumb_stored = None
        if thumb:
            thumb_stored = media.run_async(media.store_bytes(thumb, user_id=user_id, storage="thumbnails",
                                                             prefix="faceless_thumb", ext=".jpg",
                                                             content_type="image/jpeg"))
            written.append(thumb_stored)
        run = _lock_render(db, run_id)
        project = apply_row_lock(db.query(FacelessProject).filter(FacelessProject.id == run.project_id)).first()
        if project is None:
            raise RenderStopped("The project was deleted during the render")
        transcript = " ".join(
            (s.get("narration") or "") + " " + " ".join(d.get("text", "") for d in s.get("dialogue") or [])
            for s in (ctx.script or {}).get("scenes") or []  # what this render used, not a later edit
        )
        video = Video(
            filename=stored["file"],
            thumbnail_filename=thumb_stored["file"] if thumb_stored else None,
            prompt=(project.title or "")[:2000],
            transcript=" ".join(transcript.split())[:20000] or None,
            video_type=VIDEO_TYPE,
            has_subtitles=1 if timeline.get("captions") else 0,
            duration_seconds=round(float(result.duration), 3),
            width=result.width,
            height=result.height,
            fps=30,
            model=VIDEO_MODEL,
            file_size_bytes=int(result.size_bytes),
            user_id=user_id,
        )
        db.add(video)
        db.flush()
        project.output_video_id = video.id
        project.status = "rendered"
        media.set_json(project, "render", {
            "video_id": video.id, "run_id": run.id, "duration": video.duration_seconds,
            "width": video.width, "height": video.height, "resolution": options.get("resolution"),
            "captions": bool(timeline.get("captions")), "rendered_at": datetime.utcnow().isoformat(),
        })
        _close(db, run, "completed")
        item = dict((run.items or [{}])[0])
        item["result"] = {"video_id": video.id}
        media.set_json(run, "items", [item])
        activity.log_activity(db, run.user_id, "render", project_id=project.id, run_id=run.id, video_id=video.id)
        video_id = video.id
        duration = float(result.duration)
        db.commit()
        written.clear()  # landed: the gallery row owns the files now
        _notify(db, user_id, "completed", video_id)
        logger.info(f"Faceless render {run_id} completed: video {video_id}, {duration:.1f}s")
    except RenderCancelled:
        db.rollback()
        _discard(written, user_id)
        run = _lock_render(db, run_id)
        if state["timeout"]:
            logger.error(f"Faceless render {run_id} exceeded its {budget:.0f} s budget and was stopped")
            _close(db, run, "failed", "The render took too long and was stopped. Please try again.")
            db.commit()
            _notify(db, user_id, "failed", None, "The render took too long")
        else:
            _close(db, run, "cancelled", "Cancelled")
            db.commit()
    except Exception as exc:
        db.rollback()
        _discard(written, user_id)
        logger.exception(f"Faceless render {run_id} failed: {exc}")
        run = _lock_render(db, run_id)
        if run is None:
            db.rollback()
        elif is_temporary_failure(FacelessStepRun, run_id, exc) and (run.attempts or 0) < catalog.RENDER_MAX_ATTEMPTS:
            # A full disk or a locked database at the last moment: render it once more.
            run.status = "queued"
            db.commit()
        else:
            shown = str(exc) if isinstance(exc, RenderStopped) else "The render could not be finished"
            _close(db, run, "failed", f"{shown}. Please try again." if not isinstance(exc, RenderStopped) else f"{shown}.")
            db.commit()
            _notify(db, user_id, "failed", None, shown)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _ad_logo(db: Session, project: FacelessProject) -> tuple[bytes, str] | None:
    """(bytes, extension) of an ad project's logo, read by asset id from the
    owner's My Assets (never a URL). Optional: any problem means no logo."""
    asset_id = (project.settings or {}).get("ad_logo_asset_id")
    if not asset_id or not is_ad(project.script):
        return None
    try:
        from app.services import assets

        asset = assets.owned(db, project.user_id, int(asset_id), kinds=("logo", "image"))
        ext = assets.extension(asset)
        if ext not in AD_LOGO_EXTS:
            return None  # an SVG logo is not drawn by the renderer
        content = media.run_async(media.read_bytes({"file": asset.filename, "storage": asset.storage_type},
                                                   project.user_id))
        return (content, ext) if content else None
    except Exception as exc:
        db.rollback()
        logger.warning(f"Faceless render: ad logo {asset_id} skipped: {exc}")
        return None


def _notify(db: Session, user_id: int, status: str, video_id: int | None, error: str | None = None) -> None:
    try:
        from app.services.alert_service import send_job_completion_notification

        send_job_completion_notification(db=db, user_id=user_id, job_type="video", status=status,
                                         result_id=video_id, error_message=error)
    except Exception as exc:
        db.rollback()
        logger.warning(f"Faceless render notification failed: {exc}")
