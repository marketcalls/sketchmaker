"""Step plans: what a step will do and what it is estimated to cost.

plan_step() is the single source of a step's estimate. GET /quote returns its USD,
breakdown and assumptions; POST /steps/{step} calls the same function and stores its
items (each item is one provider request with its fal arguments and its own estimate,
so what is recorded follows what actually landed). Every unit price comes from
app/services/pricing.py.

Selection rules: without scene_ids a step covers the scenes that still need it
(no current asset); with scene_ids, or options.regenerate, it covers exactly
those scenes again, so a deliberate regeneration costs again, while a retry of the
same request (same idempotency key) never starts a second run.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.faceless import FacelessCharacter, FacelessProject
from app.services import pricing as cp

from . import catalog, consent, media, prompts
from .errors import Conflict, InvalidRequest
from .scenes import (
    digest, fit_to_length, is_ad, plan_timing, scene_by_id, scene_characters, scenes_of, shot_kind,
    shot_of, total_seconds, tts_characters, voice_is_current,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

@dataclass
class Ctx:
    db: Session
    project: FacelessProject
    script: dict
    chars: list
    char_by_id: dict
    timing: list
    template: dict | None
    style: str
    narrator_voice: str
    narrator_settings: dict
    settings: dict = field(default_factory=dict)
    # Seconds after the last scene: the outro card, or an ad's end card.
    outro: float = catalog.OUTRO_SECONDS

    @property
    def user_id(self) -> int:
        return self.project.user_id

    @property
    def is_ad(self) -> bool:
        return is_ad(self.script)

    @property
    def total(self) -> float:
        """The whole video: scenes plus outro or end card."""
        return round(total_seconds(self.timing) + self.outro, 3)

    def assets(self, scene_id: str) -> dict:
        return dict((self.project.scene_assets or {}).get(str(scene_id)) or {})

    def timing_of(self, scene_id: str) -> dict | None:
        return next((t for t in self.timing if t["scene_id"] == str(scene_id)), None)


def narrator_of(project: FacelessProject, script: dict, template: dict | None) -> tuple[str, dict]:
    voice = project.narrator_voice or (script or {}).get("narrator_voice")
    tpl_voice = (template or {}).get("voice") or {}
    if voice not in catalog.VOICE_IDS:
        voice = next((v for v in tpl_voice.get("suggested_voices") or [] if v in catalog.VOICE_IDS), None)
    if voice not in catalog.VOICE_IDS:
        voice = catalog.DEFAULT_NARRATOR_VOICE
    settings = dict(project.voice_settings or {})
    settings.setdefault("stability", float(tpl_voice.get("stability", catalog.DEFAULT_STABILITY)))
    settings.setdefault("similarity_boost", float(tpl_voice.get("similarity_boost", catalog.DEFAULT_SIMILARITY)))
    return voice, {"stability": float(settings["stability"]), "similarity_boost": float(settings["similarity_boost"])}


def style_of(project: FacelessProject, script: dict, template: dict | None) -> str:
    preset = catalog.STYLE_PROMPTS.get(project.style or "")
    if preset:
        return preset
    return (script or {}).get("visual_style") or (template or {}).get("visual_style") or ""


def build_ctx(db: Session, project: FacelessProject, chars: list | None = None) -> Ctx:
    from .scripts import template as load_template

    script = project.script or {}
    tpl = load_template(project.template_id)
    if chars is None:
        ids = list(project.cast_ids or [])
        for scene in scenes_of(script):
            for cid in scene_characters(scene):
                if cid not in [str(i) for i in ids]:
                    ids.append(cid)
            for line in scene.get("dialogue") or []:
                cid = str(line.get("character_id") or "")
                if cid and cid not in [str(i) for i in ids]:
                    ids.append(cid)
        numeric = []
        for i in ids:
            try:
                numeric.append(int(i))
            except (TypeError, ValueError):
                continue
        chars = (
            db.query(FacelessCharacter)
            .filter(FacelessCharacter.user_id == project.user_id, FacelessCharacter.id.in_(numeric or [0]))
            .all()
        )
    voice, settings = narrator_of(project, script, tpl)
    timing = plan_timing(script, project.scene_assets or {}, voice, settings, consent.voice_map(chars))
    outro = catalog.OUTRO_SECONDS
    if is_ad(script):
        # An ad runs exactly its placement length: scenes are trimmed or held
        # around the end card (scenes.fit_to_length).
        timing, outro = fit_to_length(timing, float(script["exact_seconds"]))
    return Ctx(
        db=db, project=project, script=script, chars=chars, char_by_id={str(c.id): c for c in chars},
        timing=timing, template=tpl, style=style_of(project, script, tpl), narrator_voice=voice,
        narrator_settings=settings, settings=dict(project.settings or {}), outro=outro,
    )


# ---------------------------------------------------------------------------
# Character references
# ---------------------------------------------------------------------------

_ROLE_ORDER = {"sheet": 0, "reference": 1, "frame": 2}


def reference_images(char: FacelessCharacter, user_id: int, limit: int) -> list[str]:
    entries = [
        m for m in (char.media or [])
        if m.get("kind") == "image" and m.get("role") in _ROLE_ORDER and m.get("usable_as_reference", True)
    ]
    entries.sort(key=lambda m: (_ROLE_ORDER[m["role"]], m.get("created_at") or ""))
    # Private (real person) media becomes a placeholder that the scheduler
    # resolves to a provider upload at submit time.
    return [media.provider_ref(m, user_id) for m in entries[:limit]]


def reference_videos(char: FacelessCharacter, user_id: int) -> list[tuple[str, float]]:
    out = []
    for m in char.media or []:
        d = float(m.get("duration") or 0)
        if m.get("kind") == "video" and catalog.REFERENCE_VIDEO_MIN_SECONDS <= d <= catalog.REFERENCE_VIDEO_MAX_SECONDS:
            out.append((media.provider_ref(m, user_id), d))
    return out


def _chars_in(ctx: Ctx, scene: dict) -> list:
    return [ctx.char_by_id[cid] for cid in scene_characters(scene) if cid in ctx.char_by_id]


def _speakers_in(ctx: Ctx, scene: dict) -> list:
    out = []
    for line in scene.get("dialogue") or []:
        char = ctx.char_by_id.get(str(line.get("character_id") or ""))
        if char is not None and char not in out:
            out.append(char)
    return out


# ---------------------------------------------------------------------------
# Models and prices
# ---------------------------------------------------------------------------

def t2i_models() -> list[str]:
    from app.clients.fal_client import MODEL_CONFIG

    return [m for m in MODEL_CONFIG if cp.image_key(m, "1k") in cp.USD_COSTS]


def edit_models() -> list[str]:
    from app.clients.fal_client import EDIT_MODEL_CONFIG

    return [m for m in EDIT_MODEL_CONFIG if cp.edit_key(m) in cp.USD_COSTS]


def _choice(value, allowed, default, label):
    value = value or default
    if value not in allowed:
        raise InvalidRequest(f"{label} must be one of: {', '.join(allowed)}.")
    return value


def _still_models(ctx: Ctx, options: dict) -> tuple[str, str, str]:
    t2i = _choice(options.get("t2i_model") or ctx.settings.get("t2i_model"), t2i_models(),
                  catalog.DEFAULT_T2I_MODEL, "Text to image model")
    edit = _choice(options.get("edit_model") or ctx.settings.get("edit_model"), edit_models(),
                   catalog.DEFAULT_EDIT_MODEL, "Edit model")
    res = _choice((options.get("resolution") or ctx.settings.get("still_resolution") or "").lower() or None,
                  catalog.STILL_RESOLUTIONS, catalog.DEFAULT_STILL_RESOLUTION, "Still resolution")
    return t2i, edit, res


def _image_item(*, kind: str, prompt: str, refs: list[str], t2i: str, edit: str,
                res: str, aspect: str, label: str, extra: dict) -> dict:
    """One still: edit model with references, or text to image without."""
    from app.clients.fal_client import build_edit_arguments, build_generation_arguments, edit_max_images
    from app.clients.fal_client import EDIT_MODEL_CONFIG

    seed = random.randint(1, 2_147_483_646)
    if refs:
        refs = refs[: EDIT_MODEL_CONFIG[edit]["max_inputs"]]
        arguments = build_edit_arguments(edit, prompt, refs, aspect_ratio=aspect, resolution=res.upper(),
                                         output_format="png", num_images=edit_max_images(edit, 1), seed=seed)
        key, model = cp.edit_key(edit, res), edit
    else:
        arguments = build_generation_arguments(prompt, t2i, aspect_ratio=aspect, resolution=res, num_images=1,
                                               seed=seed)
        key, model = cp.image_key(t2i, res), t2i
    return {
        "kind": kind, "endpoint": model, "arguments": arguments, "key": key, "unit": "image",
        "units": 1, "usd": cp.usd_for(key), "label": label, "seed": seed, "model": model,
        "prompt_hash": digest(prompt, model, res, aspect, refs), **extra,
    }


# ---------------------------------------------------------------------------
# Scene selection
# ---------------------------------------------------------------------------

def _select(ctx: Ctx, scene_ids: list | None, default_filter) -> tuple[list[dict], bool]:
    """(scenes in script order, explicit). Explicit when scene_ids were given."""
    scenes = scenes_of(ctx.script)
    if not scenes:
        raise InvalidRequest("Draft a script first.", code="no_script")
    if scene_ids:
        wanted = [str(s) for s in scene_ids]
        unknown = [s for s in wanted if scene_by_id(ctx.script, s) is None]
        if unknown:
            raise InvalidRequest(f"Unknown scene '{unknown[0]}'.", code="unknown_scene")
        return [s for s in scenes if str(s.get("id")) in wanted], True
    return [s for s in scenes if default_filter(s)], False


# ---------------------------------------------------------------------------
# Quality checks (app/services/quality_gate.py)
# ---------------------------------------------------------------------------

QA_LABEL = "Quality check (vision read)"


def wants_quality_check(ctx: Ctx, options: dict) -> bool:
    """Whether stills and clips of this step get a quality check. Not when the user
    turned it off (options.quality_check false) or the default model cannot see
    images: only a check that can run is ever quoted."""
    from app.services import quality_gate

    return options.get("quality_check") is not False and quality_gate.available(ctx.db)


def qa_fields(ctx: Ctx, scene: dict, chars: list, products: list[tuple[str, str]], check: bool) -> dict:
    """What the scheduler needs to check one item: the scene text, the cast
    names and which references to compare against."""
    from app.services import quality_gate

    if not check:
        return {}
    shot = shot_of(scene)
    text = (shot.get("visual_prompt") or shot.get("direction") or scene.get("narration") or "").strip()
    refs = [{"label": f"the product {name}", "url": url} for name, url in products[:2]]
    refs += [{"label": c.name, "character_id": c.id} for c in chars[:3]]
    return {"qa_requested": True, "qa_usd": quality_gate.price(), "qa_scene": text[:600],
            "qa_cast": [c.name for c in chars][:6],
            "qa_refs": refs, "qa_aspect": ctx.project.aspect}


def _qa_note(items: list[dict], what: str) -> str | None:
    checked = [i for i in items if i.get("qa_requested")]
    if not checked:
        return None
    return (f"Includes a quality check of each {what} (about ${checked[0]['qa_usd']:g} each): one vision read "
            "against the scene and the cast references. A failed check shows a warning with its reasons; "
            "regenerating is your choice.")


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _owned_image_url(url: str, user_id: int) -> bool:
    """A product photo URL in the script is only used when it is the /static path of
    one of the owner's stored images (a hand-edited script must not send any other
    URL to a provider)."""
    from app.services.storage_service import storage_service

    if not isinstance(url, str) or ".." in url:
        return False
    return any(url.startswith(storage_service.get_public_url("", storage, user_id=user_id))
               for storage in ("images", "uploads"))


def product_refs(ctx: Ctx, scene: dict) -> list[tuple[str, str]]:
    """(name, photo URL) of each product in the scene with an approved photo."""
    out = []
    for p in scene.get("products") or []:
        url = (p or {}).get("image_url") or ""
        if url and _owned_image_url(url, ctx.user_id):
            out.append(((p.get("name") or "product").strip()[:80], url))
    return out[:3]


def clip_parts(ctx: Ctx, scene: dict, max_parts: int | None = None) -> list[int]:
    """Clip lengths a clip scene is split into (empty for other scenes)."""
    if shot_kind(scene) != "clip":
        return []
    max_parts = max(1, min(4, int(max_parts or catalog.DEFAULT_MAX_CLIPS_PER_SCENE)))
    timing = ctx.timing_of(str(scene["id"])) or {"duration": 5.0}
    return _clip_seconds(timing["duration"])[:max_parts]


def still_count(ctx: Ctx, scene: dict) -> tuple[int, bool]:
    """(stills, chained). A clip scene split into n parts gets n + 1 stills,
    the first and last frames of its parts."""
    count = int(shot_of(scene).get("images") or 1)
    parts = len(clip_parts(ctx, scene))
    if parts > 1:
        return max(count, parts + 1), True
    return count, False


def _plan_storyboard(ctx: Ctx, scene_ids, options) -> tuple[list[dict], list[str], list]:
    from app.clients.fal_client import EDIT_MODEL_CONFIG

    t2i, edit, res = _still_models(ctx, options)
    aspect = catalog.MODEL_ASPECT[ctx.project.aspect]
    regenerate = bool(options.get("regenerate"))
    items, notes, used = [], [], []
    cap = int(EDIT_MODEL_CONFIG.get(edit, {}).get("max_inputs") or 14)
    check = wants_quality_check(ctx, options)
    extra_frames = 0

    def build(scene):
        nonlocal extra_frames
        chars = _chars_in(ctx, scene)
        # The product photo goes first so it is never the one cut by the
        # edit model's input limit.
        products = product_refs(ctx, scene)
        groups = [(f"the product {name}", 1) for name, _ in products]
        refs = [url for _, url in products]
        per_char = max(1, min(catalog.REFS_PER_CHARACTER, (min(14, cap) - len(refs)) // max(1, len(chars))))
        for c in chars:
            urls = reference_images(c, ctx.user_id, per_char)
            if urls:
                groups.append((c.name, len(urls)))
                refs.extend(urls)
        count, chained = still_count(ctx, scene)
        if chained:
            extra_frames += count - int(shot_of(scene).get("images") or 1)
        out = []
        qa = qa_fields(ctx, scene, chars, products, check)
        for i in range(count):
            prompt = prompts.still_prompt(scene, chars, groups, ctx.style, i, count, chained=chained,
                                          products=bool(products))
            item = _image_item(
                kind="still", prompt=prompt, refs=refs, t2i=t2i, edit=edit, res=res, aspect=aspect,
                label=f"Still, {'character edit' if refs else 'text to image'}",
                extra={"scene_id": str(scene["id"]), "index": i, "of": count, "prompt": prompt,
                       "chained": chained, **qa},
            )
            item["usd"] += float(qa.get("qa_usd") or 0)
            out.append(item)
        return chars, out

    def needs(scene) -> bool:
        if shot_kind(scene) in ("user_media", "card"):
            return False
        if regenerate:
            return True
        stills = ctx.assets(scene["id"]).get("stills") or []
        return len([s for s in stills if s]) < still_count(ctx, scene)[0]

    scenes, _explicit = _select(ctx, scene_ids, needs)
    for scene in scenes:
        chars, scene_items = build(scene)
        used.extend(c for c in chars if c not in used)
        items.extend(scene_items)
    edits = sum(1 for i in items if i["key"].startswith("edit:"))
    notes.append(f"{len(items)} stills: {edits} with character or product references ({edit}), "
                 f"{len(items) - edits} text to image ({t2i}), {res.upper()}, aspect {ctx.project.aspect}.")
    if extra_frames:
        notes.append(f"Includes {extra_frames} extra still(s): a scene split into clip parts gets one still per "
                     "part plus its last frame, so each part starts where the previous one ends.")
    qa_note = _qa_note(items, "still")
    if qa_note:
        notes.append(qa_note)
    return items, notes, used


def _clip_seconds(target: float) -> list[int]:
    """Clip lengths covering ``target`` seconds, each 2 to 15 s."""
    target = max(float(catalog.CLIP_MIN_SECONDS), float(target))
    n = max(1, math.ceil(round(target, 2) / catalog.CLIP_MAX_SECONDS))
    each = max(catalog.CLIP_MIN_SECONDS, min(catalog.CLIP_MAX_SECONDS, math.ceil(round(target / n, 2))))
    return [each] * n


def reference_token_budget(image_count: int, video_seconds: list[float], resolution: str | None = None) -> int:
    """Worst-case H3 Max reference tokens beyond the included allowance, from
    the Stories budget rates but with the measured length of each reference
    video (Stories budgets an unknown video at the 15 s maximum). The video
    rate may be per output resolution; an unknown one takes the highest."""
    from app.clients.fal_client import STORY_VIDEO_MODELS

    rt = STORY_VIDEO_MODELS[catalog.H3_FAMILY]["reference_tokens"]
    per_video = rt["per_video_second"]
    if isinstance(per_video, dict):
        per_video = per_video.get(resolution or "", max(per_video.values()))
    tokens = image_count * rt["per_image"]
    tokens += sum(math.ceil(s) for s in video_seconds) * per_video
    return max(0, int(tokens) - rt["included"])


def _plan_clips(ctx: Ctx, scene_ids, options) -> tuple[list[dict], list[str], list]:
    from app.clients.fal_client import (
        STORY_VIDEO_MODELS, build_story_arguments, resolve_story_options, story_reference_token_usd,
    )

    res = _choice((options.get("resolution") or ctx.settings.get("clip_resolution") or "").lower() or None,
                  catalog.CLIP_RESOLUTIONS, catalog.DEFAULT_CLIP_RESOLUTION, "Clip resolution")
    mode = _choice(options.get("mode") or ctx.settings.get("clip_mode"), catalog.CLIP_MODES,
                   catalog.DEFAULT_CLIP_MODE, "Clip mode")
    max_parts = int(options.get("max_clips_per_scene") or catalog.DEFAULT_MAX_CLIPS_PER_SCENE)
    max_parts = max(1, min(4, max_parts))
    regenerate = bool(options.get("regenerate"))
    per_second = cp.usd_for(cp.video_key(catalog.H3_FAMILY, res))
    # H3 Max takes a last frame in image and reference mode (fal schema:
    # end_image_url, "the video ends exactly on this image"). A family
    # without one starts each later part from the previous part's last frame,
    # extracted by the scheduler (orchestrator._chain_start).
    end_field = STORY_VIDEO_MODELS[catalog.H3_FAMILY].get("end_field")
    register = str((ctx.script or {}).get("look_register") or "")
    items, notes, used, estimated, chained_scenes = [], [], [], False, 0
    check = wants_quality_check(ctx, options)

    def needs(scene) -> bool:
        if shot_kind(scene) != "clip":
            return False
        return regenerate or not (ctx.assets(scene["id"]).get("clips") or [])

    scenes, _explicit = _select(ctx, scene_ids, needs)
    missing_still = []
    for scene in scenes:
        sid = str(scene["id"])
        timing = ctx.timing_of(sid) or {"duration": 5.0, "measured": False}
        estimated = estimated or not timing["measured"]
        lengths = _clip_seconds(timing["duration"])[:max_parts]
        stills = [s for s in (ctx.assets(sid).get("stills") or []) if s]
        chars = _chars_in(ctx, scene)
        scene_mode = mode
        if scene_mode == "reference" and not any(reference_images(c, ctx.user_id, 1) for c in chars):
            scene_mode = "image"
        if scene_mode == "image" and not stills:
            missing_still.append(sid)
            continue
        used.extend(c for c in chars if c not in used)
        products = product_refs(ctx, scene)
        shot = shot_of(scene)
        # A hero product shot opens on the product photo itself: the product
        # is never redrawn from a description.
        hero_url = products[0][1] if products and shot.get("hero_product") and not chars else None
        keyframe = shot.get("keyframe_url") or ""
        keyframe = keyframe if _owned_image_url(keyframe, ctx.user_id) else ""
        chained = len(lengths) > 1 and len(stills) > 1
        chained_scenes += 1 if chained else 0
        for part, seconds in enumerate(lengths):
            start = stills[min(part, len(stills) - 1)] if stills else None
            start_url = media.public_url(start, ctx.user_id) if start else None
            end_url, from_previous = None, False
            if chained and part + 1 < len(stills):
                if end_field:
                    end_url = media.public_url(stills[part + 1], ctx.user_id)
                elif part > 0:
                    from_previous = True
            # from_previous: start_url (still k) is replaced at submit time by
            # the last frame of part k-1, and stays the fallback.
            part_mode = "image" if (hero_url and part == 0) else scene_mode
            if hero_url and part == 0:
                start_url = hero_url
            elif part == 0 and keyframe:
                start_url = keyframe  # the approved panel is the first frame
            if part_mode == "image":
                opts = resolve_story_options(catalog.H3_FAMILY, "image-to-video", str(seconds), res, None)
                prompt = prompts.clip_prompt_image(scene, ctx.style, part, len(lengths), seconds=seconds,
                                                   register=register, ends_on_frame=bool(end_url),
                                                   hero_product=bool(hero_url and part == 0))
                arguments = build_story_arguments(opts, prompt, image_url=start_url, end_image_url=end_url,
                                                  seed=random.randint(1, 2_147_483_646))
                token_usd, budget, refs_meta = 0.0, 0, {}
            else:
                per_char = max(1, min(catalog.REFS_PER_CHARACTER,
                                      (catalog.H3_MAX_REFERENCE_IMAGES - len(products)) // max(1, len(chars))))
                image_urls, video_urls, groups, video_total = [url for _, url in products], [], [], 0.0
                video_seconds: list[float] = []
                for c in chars:
                    urls = reference_images(c, ctx.user_id, per_char)
                    vids = []
                    for url, d in reference_videos(c, ctx.user_id)[:1]:
                        if len(video_urls) + len(vids) < 3 and video_total + d <= catalog.REFERENCE_VIDEO_MAX_SECONDS:
                            vids.append(url)
                            video_seconds.append(d)
                            video_total += d
                    image_urls.extend(urls)
                    video_urls.extend(vids)
                    groups.append((c.name, len(urls), len(vids)))
                image_urls = image_urls[: catalog.H3_MAX_REFERENCE_IMAGES]
                aspect = catalog.MODEL_ASPECT[ctx.project.aspect]
                opts = resolve_story_options(catalog.H3_FAMILY, "reference-to-video", str(seconds), res, aspect)
                prompt = prompts.clip_prompt_reference(
                    scene, groups, ctx.style, bool(start_url),
                    products=[name for name, _ in products], seconds=seconds, register=register,
                    part=part, parts=len(lengths), ends_on_frame=bool(end_url))
                arguments = build_story_arguments(opts, prompt, image_urls=image_urls, video_urls=video_urls,
                                                  seed=random.randint(1, 2_147_483_646))
                # fal's reference-to-video schema takes image_url as the first
                # frame and end_image_url as the last (verified 2026-10-30).
                if start_url:
                    arguments["image_url"] = start_url
                if end_url:
                    arguments[end_field] = end_url
                frames = (1 if start_url else 0) + (1 if end_url else 0)
                budget = reference_token_budget(len(image_urls) + frames, video_seconds, res)
                token_usd = story_reference_token_usd(catalog.H3_FAMILY, budget)
                refs_meta = {"reference_images": len(image_urls), "reference_videos": len(video_urls)}
            qa = qa_fields(ctx, scene, chars, products, check)
            usd = per_second * seconds + token_usd + float(qa.get("qa_usd") or 0)
            item = {
                "kind": "clip", "scene_id": sid, "index": part, "of": len(lengths),
                "endpoint": opts["endpoint"], "arguments": arguments,
                "key": cp.video_key(catalog.H3_FAMILY, res), "unit": "second", "units": seconds,
                "usd": usd, "token_usd": token_usd, "token_budget": budget,
                "label": f"H3 Max clip {res} ({'reference' if part_mode == 'reference' else 'image'} to video)",
                "model": opts["endpoint"], "mode": part_mode, "resolution": res, "seconds": seconds,
                "seed": arguments.get("seed"), "prompt": prompt, **refs_meta, **qa,
            }
            if from_previous:
                item["chain_from"] = part - 1
            items.append(item)
    if missing_still:
        raise InvalidRequest(
            "These scenes need a storyboard still before they can be animated: " + ", ".join(missing_still),
            code="still_required", extra={"scene_ids": missing_still},
        )
    secs = sum(i["units"] for i in items)
    notes.append(f"{len(items)} clips, {secs} seconds of H3 Max at {res}, billed on the requested length.")
    if chained_scenes:
        notes.append(f"{chained_scenes} scene(s) split into parts: each part runs from one storyboard still to "
                     "the next, so the parts join without a jump.")
    if estimated:
        notes.append("Clip lengths follow scene lengths estimated at 165 words per minute; generate the "
                     "voices first to time clips to the real narration.")
    if any(i.get("token_usd") for i in items):
        notes.append("Reference clips are estimated at the worst case of reference tokens; what is recorded "
                     "follows the tokens fal reports when each clip finishes.")
    qa_note = _qa_note(items, "clip (its first, middle and last frames)")
    if qa_note:
        notes.append(qa_note)
    return items, notes, used


def _plan_voice(ctx: Ctx, scene_ids, options) -> tuple[list[dict], list[str], list]:
    regenerate = bool(options.get("regenerate"))
    language = (ctx.project.language or "en")[:2]
    normalization = (ctx.script or {}).get("tts_text_normalization") or "auto"
    items, notes, used = [], [], []

    def lines_of(scene):
        t = ctx.timing_of(scene["id"])
        return t["lines"] if t else []

    def needs(scene) -> bool:
        lines = lines_of(scene)
        return bool(lines) and (regenerate or not voice_is_current(ctx.assets(scene["id"]), lines))

    # options.lines: re-voice only these line indexes of the given scenes
    # (the user's "Re-voice" on a take the free check flagged).
    only = options.get("lines")
    if only is not None:
        if not isinstance(only, list) or not scene_ids or len(only) > catalog.MAX_DIALOGUE_LINES + 1 \
                or not all(isinstance(i, int) and not isinstance(i, bool) for i in only):
            raise InvalidRequest("Pick the lines to voice again within one scene.", code="invalid_lines")
        only = set(only)
    scenes, explicit = _select(ctx, scene_ids, needs)
    for scene in scenes:
        sid = str(scene["id"])
        stored = {int(v.get("index", -1)): v for v in ctx.assets(sid).get("voice") or []}
        for char in _speakers_in(ctx, scene):
            if char not in used:
                used.append(char)
        for line in lines_of(scene):
            if only is not None and line["index"] not in only:
                continue
            current = stored.get(line["index"])
            if not (explicit or regenerate) and current and current.get("hash") == line["hash"]:
                continue
            if len(line["text"]) > 5000:
                raise InvalidRequest(f"Scene {sid} has a line over 5,000 characters. Shorten it.")
            chars = tts_characters(line["text"])
            arguments = {
                "text": line["text"],
                "voice": line["voice"],
                "stability": line["settings"]["stability"],
                "similarity_boost": line["settings"]["similarity_boost"],
                "language_code": language,
                "apply_text_normalization": normalization,
                "output_format": "mp3_44100_128",
                "timestamps": True,
            }
            items.append({
                "kind": "voice", "scene_id": sid, "index": line["index"], "endpoint": catalog.TTS_ENDPOINT,
                "arguments": arguments, "key": cp.ELEVEN_V4_KEY, "unit": "1k characters",
                "units": round(chars / 1000, 3), "usd": cp.tts_usd(chars),
                "label": "Eleven v4 voice", "chars": chars, "hash": line["hash"], "voice": line["voice"],
                "speaker": line["speaker"], "character_id": line["character_id"], "text": line["text"],
            })
    total = sum(i["chars"] for i in items)
    voices = sorted({i["voice"] for i in items})
    notes.append(f"{len(items)} voice clips, {total} characters (audio tags included) with "
                 f"{', '.join(voices) or 'no voices'}; scene lengths follow the measured audio.")
    return items, notes, used


def music_sections(ctx: Ctx, plan: dict, track_start: float, track_len: float) -> list[dict]:
    """Composition plan sections for one track: the template's sections with
    their boundaries moved to the nearest scene cut, each 3 to 120 seconds."""
    sections = plan.get("sections") or [{"section_name": "main", "fraction": 1.0}]
    weight = sum(float(s.get("fraction") or 0) for s in sections) or 1.0
    cuts = [t["start"] - track_start for t in ctx.timing if 0 < t["start"] - track_start < track_len]
    bounds, acc = [], 0.0
    for s in sections[:-1]:
        acc += float(s.get("fraction") or 0) / weight * track_len
        snapped = min(cuts, key=lambda c: abs(c - acc)) if cuts else acc
        bounds.append(snapped if abs(snapped - acc) <= max(4.0, track_len * 0.08) else acc)
    edges = [0.0] + bounds + [track_len]
    raw = []
    for s, a, b in zip(sections, edges[:-1], edges[1:]):
        raw.append([s, max(0.0, b - a)])
    merged: list[list] = []
    for s, length in raw:  # fold sections shorter than 3 s into their neighbour
        if merged and (length < 3.0 or merged[-1][1] < 3.0):
            merged[-1][1] += length
        else:
            merged.append([s, length])
    out = []
    for s, length in merged:
        parts = max(1, math.ceil(length / 120.0))
        for k in range(parts):
            name = s.get("section_name") or "section"
            out.append({
                "section_name": (name if parts == 1 else f"{name} part {k + 1}")[:100],
                "seconds": length / parts,
                "positive_local_styles": list(s.get("positive_local_styles") or []),
                "negative_local_styles": list(s.get("negative_local_styles") or []),
                "lines": [],
            })
    total_ms = int(round(track_len * 1000))
    used_ms = 0
    for i, sec in enumerate(out):
        ms = total_ms - used_ms if i == len(out) - 1 else int(round(sec.pop("seconds") * 1000))
        sec.pop("seconds", None)
        sec["duration_ms"] = max(3000, min(120000, ms))
        used_ms += sec["duration_ms"]
    return out


MUSIC_TRACK_MAX = 600.0      # provider limit per track
MUSIC_MIN_LAST_TRACK = 12.0  # a shorter remainder ends on the previous track's fade


def music_track_lengths(body: float, total: float) -> list[float]:
    """Track lengths that cover the video for the fewest billed minutes.

    Full 600 s tracks, then the remainder. A remainder under 12 s is not worth
    a further billed minute (the music fades out early), and a last track is
    never extended into a further minute only for the silent outro.
    """
    full, rest = divmod(total, MUSIC_TRACK_MAX)
    lengths = [MUSIC_TRACK_MAX] * int(full)
    if rest >= MUSIC_MIN_LAST_TRACK or not lengths:
        last = rest if lengths else total
        body_rest = max(0.0, body - MUSIC_TRACK_MAX * len(lengths))
        if body_rest > 0:
            last = min(last, cp.music_minutes(body_rest) * 60.0)
        lengths.append(round(max(3.0, last), 3))
    return lengths


def _plan_music(ctx: Ctx, scene_ids, options) -> tuple[list[dict], list[str], list]:
    mood_id = options.get("mood") or ctx.project.music_mood or "template"
    if mood_id not in catalog.MUSIC_MOOD_IDS:
        raise InvalidRequest("Unknown music mood.", code="unknown_mood")
    if mood_id == "none":
        raise InvalidRequest("Music is off for this project (mood 'none').", code="music_off")
    if not scenes_of(ctx.script):
        raise InvalidRequest("Draft a script first.", code="no_script")
    base = dict((ctx.script or {}).get("music") or (ctx.template or {}).get("music") or {})
    mood = next(m for m in catalog.MUSIC_MOODS if m["id"] == mood_id)
    positive = list(mood["positive"]) or list(base.get("positive_global_styles") or ["cinematic underscore"])
    negative = list(mood["negative"]) or list(base.get("negative_global_styles") or [])
    instrumental = options.get("instrumental", True) is not False
    if instrumental:
        negative += [s for s in ("vocals", "singing", "lyrics") if s not in negative]
    body = total_seconds(ctx.timing)
    total = body + ctx.outro
    lengths = music_track_lengths(body, total)
    tracks = len(lengths)
    plan_hash = digest(positive, negative, round(total, 1), tracks, base.get("sections"))
    current = ctx.project.music or {}
    if current.get("plan_hash") == plan_hash and current.get("tracks") and not options.get("regenerate"):
        raise Conflict("Music for this timing already exists. Pass options.regenerate to make a new track.",
                       code="nothing_to_do")
    items = []
    start = 0.0
    for k, length in enumerate(lengths):
        if k:
            start += lengths[k - 1]
        plan = {
            "positive_global_styles": positive,
            "negative_global_styles": negative,
            "sections": music_sections(ctx, base, start, length),
        }
        items.append({
            "kind": "music", "index": k, "of": tracks, "endpoint": catalog.MUSIC_ENDPOINT,
            "arguments": {"composition_plan": plan, "respect_sections_durations": True,
                          "output_format": "mp3_44100_128"},
            "key": cp.ELEVEN_MUSIC_KEY, "unit": "minute", "units": cp.music_minutes(length),
            "usd": cp.music_usd(length), "label": "ElevenLabs Music",
            "start": round(start, 3), "seconds": round(length, 3), "mood": mood_id, "plan_hash": plan_hash,
            "instrumental": instrumental,
        })
    notes = [f"{tracks} track(s) of {', '.join(f'{x:.0f}' for x in lengths)} s for {total:.0f} s of video "
             f"(scenes plus outro), billed per started minute per track; "
             f"{'instrumental' if instrumental else 'vocals allowed'}."]
    if any(not t["measured"] for t in ctx.timing):
        notes.append("Some scene lengths are still estimates; generate the voices first so sections follow the cuts.")
    return items, notes, []


def _plan_render(ctx: Ctx, scene_ids, options) -> tuple[list[dict], list[str], list]:
    scenes = scenes_of(ctx.script)
    if not scenes:
        raise InvalidRequest("Draft a script first.", code="no_script")
    res = _choice(options.get("resolution") or ctx.settings.get("render_resolution"), catalog.RENDER_RESOLUTIONS,
                  catalog.DEFAULT_RENDER_RESOLUTION, "Render resolution")
    missing = []
    used = []
    for scene in scenes:
        a = ctx.assets(scene["id"])
        if shot_kind(scene) != "card" and not (a.get("stills") or a.get("clips") or a.get("user_media")):
            missing.append(str(scene["id"]))
        for c in _chars_in(ctx, scene) + _speakers_in(ctx, scene):
            if c not in used:
                used.append(c)
    if missing:
        raise InvalidRequest("These scenes have no picture yet (storyboard still, clip or your own media): "
                             + ", ".join(missing), code="visual_required", extra={"scene_ids": missing})
    total = ctx.total
    notes = [f"Render of {total:.1f} s at {res} ({catalog.FRAME_SIZES[res][ctx.project.aspect][0]}x"
             f"{catalog.FRAME_SIZES[res][ctx.project.aspect][1]}). It runs on this machine, so it has no provider cost."]
    if ctx.is_ad:
        exact = float(ctx.script["exact_seconds"])
        if total > exact + 0.05:
            notes.append(f"The narration needs {total:.1f} s, more than the {exact:g} s placement; shorten the "
                         "voice lines to fit it exactly.")
        else:
            notes.append(f"Fitted to exactly {exact:g} s, ending on a {ctx.outro:.1f} s end card with the call "
                         "to action.")
    if any(not t["measured"] for t in ctx.timing):
        notes.append("Some scenes have no voice yet: they use estimated lengths and no captions.")
    if not (ctx.project.music or {}).get("tracks"):
        notes.append("No music track: the video will have voice only.")
    elif options.get("music") is False:
        notes.append("Music is off for this render: the video will have voice only.")
    item = {
        "kind": "render", "endpoint": None, "arguments": {"resolution": res, **{
            k: options[k] for k in ("captions", "music", "music_gain_db") if k in options}},
        "key": cp.RENDER_MINUTE_KEY, "unit": "minute", "units": cp.render_minutes(total),
        "usd": cp.render_usd(total), "label": "Render", "seconds": round(total, 3),
        "resolution": res,
    }
    return [item], notes, used


def _plan_thumbnails(ctx: Ctx, scene_ids, options) -> tuple[list[dict], list[str], list]:
    if not scenes_of(ctx.script):
        raise InvalidRequest("Draft a script first.", code="no_script")
    t2i, edit, _res = _still_models(ctx, options)
    aspect = catalog.MODEL_ASPECT[ctx.project.aspect]
    packaging = ctx.project.packaging or {}
    suggestions = list(packaging.get("thumbnail_prompts") or [])
    hook = scenes_of(ctx.script)[0]
    title = (ctx.script.get("title") or ctx.project.title or "").strip()
    default_text = " ".join(title.split()[:4]).upper()
    items, used = [], []
    for k in range(3):
        s = suggestions[k] if k < len(suggestions) else {}
        ids = [str(c) for c in (s.get("characters") or [])] or scene_characters(hook) or \
            [str(c) for c in (ctx.project.cast_ids or [])][:1]
        chars = [ctx.char_by_id[i] for i in ids if i in ctx.char_by_id][:2]
        groups, refs = [], []
        for c in chars:
            urls = reference_images(c, ctx.user_id, catalog.REFS_PER_CHARACTER)
            if urls:
                groups.append((c.name, len(urls)))
                refs.extend(urls)
        used.extend(c for c in chars if c not in used)
        base = s.get("prompt") or shot_of(hook).get("visual_prompt") or shot_of(hook).get("direction") or title
        prompt = prompts.thumbnail_prompt(base, chars, groups, ctx.style)
        texts = options.get("texts") if isinstance(options.get("texts"), list) else []
        text = texts[k] if k < len(texts) and isinstance(texts[k], str) and texts[k].strip() else None
        items.append(_image_item(
            kind="thumbnail", prompt=prompt, refs=refs, t2i=t2i, edit=edit, res="1k", aspect=aspect,
            label=f"Thumbnail, {'character edit' if refs else 'text to image'}",
            extra={"index": k, "text": (text or s.get("text") or default_text)[:60], "prompt": prompt},
        ))
    notes = ["3 thumbnail variants at 1K with a clean area for the headline; the headline is drawn by the app, "
             "not by the model."]
    return items, notes, used


PLANNERS = {
    "storyboard": _plan_storyboard,
    "clips": _plan_clips,
    "voice": _plan_voice,
    "music": _plan_music,
    "render": _plan_render,
    "thumbnails": _plan_thumbnails,
}


def _finish(step: str, items: list[dict], notes: list[str], used: list) -> dict:
    for n, item in enumerate(items, start=1):
        item["id"] = f"i{n}"
        item["usd"] = round(float(item["usd"]), cp.USD_DECIMALS)
    groups: dict[tuple, dict] = {}
    for item in items:
        # A quality check folded into an item's estimate gets its own line.
        qa = float(item.get("qa_usd") or 0)
        parts = [(item["label"], item["key"], item["unit"], item["units"], item["usd"] - qa)]
        if qa:
            parts.append((QA_LABEL, cp.QA_VISION_CHECK_KEY, "check", 1, qa))
        for label, key, unit, units, usd in parts:
            g = groups.setdefault((label, key, unit), {"label": label, "key": key, "unit": unit,
                                                       "units": 0, "usd": 0.0, "count": 0})
            g["units"] = round(g["units"] + units, 3)
            g["usd"] = round(g["usd"] + usd, cp.USD_DECIMALS)
            g["count"] += 1
    breakdown = []
    for g in groups.values():
        g["unit_usd"] = round(g["usd"] / g["units"], cp.USD_DECIMALS) if g["units"] else 0
        breakdown.append(g)
    return {
        "step": step,
        "usd": round(sum(i["usd"] for i in items), cp.USD_DECIMALS),
        "breakdown": breakdown,
        "assumptions": notes,
        "scene_ids": sorted({i["scene_id"] for i in items if i.get("scene_id")},
                            key=lambda s: (len(s), s)),
        "items": items,
        "characters": [c.id for c in used],
    }


def max_total_seconds(aspect: str) -> float:
    """Longest video (scenes, without the outro) any step may work towards:
    the format's cap (180 s vertical and square, 900 s for 16:9) plus 10 per
    cent, because measured narration runs a little over the drafted length."""
    return catalog.MAX_LENGTH_SECONDS.get(aspect, min(catalog.MAX_LENGTH_SECONDS.values())) *         (1 + catalog.LENGTH_TOLERANCE)


def check_total_length(ctx: Ctx) -> None:
    total = total_seconds(ctx.timing)
    cap = max_total_seconds(ctx.project.aspect)
    if total > cap:
        raise InvalidRequest(
            f"The script runs {total / 60:.1f} minutes; {ctx.project.aspect} videos can be at most "
            f"{catalog.MAX_LENGTH_SECONDS.get(ctx.project.aspect, 180) / 60:g} minutes. Shorten the script.",
            code="too_long", extra={"seconds": round(total, 1), "max_seconds": round(cap, 1)},
        )


def plan_step(ctx: Ctx, step: str, scene_ids: list | None = None, options: dict | None = None) -> dict:
    """The plan and price of one step. Raises InvalidRequest for impossible requests."""
    if step not in PLANNERS:
        raise InvalidRequest(f"Unknown step '{step}'. Steps: {', '.join(PLANNERS)}.", code="unknown_step")
    options = dict(options or {})
    check_total_length(ctx)
    try:
        items, notes, used = PLANNERS[step](ctx, scene_ids, options)
    except ValueError as exc:
        if isinstance(exc, InvalidRequest):
            raise
        logger.warning(f"Planning the {step} step failed: {exc}", exc_info=True)
        raise InvalidRequest("Some of the options for this step are not valid. Check them and try again.")
    return _finish(step, items, notes, used)


def plan_sheet(char: FacelessCharacter, options: dict | None = None) -> dict:
    """A reference sheet for one character (edit model over its references)."""
    options = dict(options or {})
    edit = _choice(options.get("edit_model"), edit_models(), catalog.DEFAULT_EDIT_MODEL, "Edit model")
    refs = reference_images(char, char.user_id, 4)
    if not refs:
        raise InvalidRequest("Upload at least one photo or video of the character first.", code="reference_required")
    style = catalog.STYLE_PROMPTS.get(options.get("style") or "", "") or (char.style_notes or "")
    prompt = prompts.sheet_prompt(char, len(refs), style)
    item = _image_item(kind="sheet", prompt=prompt, refs=refs, t2i=catalog.DEFAULT_T2I_MODEL, edit=edit,
                       res="1k", aspect="16:9", label="Character sheet", extra={"prompt": prompt})
    return _finish("sheet", [item], [f"One 16:9 reference sheet from {len(refs)} reference image(s) with {edit}."],
                   [char])


def quote_view(plan: dict) -> dict:
    """What GET /quote returns (no provider arguments)."""
    return {k: plan[k] for k in ("step", "usd", "breakdown", "assumptions", "scene_ids", "characters")}
