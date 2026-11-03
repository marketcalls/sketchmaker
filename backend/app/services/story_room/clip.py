"""Director prompts for the Quick clip maker: one shot, or the whole piece in
one take.

A shot prompt combines the shot size, camera move, action, where everyone
stands (frame_position), the pose the shot begins from (the previous shot's
end_state in the same place) and ends in, the likeness of every character in
frame (the library bible's clause when the character is saved, else the
story's own description), the products, the environment and the look in the
document's register. References come first from the approved images in the
document (characters in frame, products in the shot, the place), then from
the library (character sheets and references, environment photos), at most 4.
Each image's role is stated in words ("Image 1 is a character reference of
Mira: use it for face, hair and outfit only..."), and a character whose
picture is attached gets only a short likeness, so the words go to action,
camera and timing. Real person characters whose consent is not valid add no
photos.

A shot can open on a start frame (image-to-video) when the video family has
that mode: the shot's approved keyframe, else, for a hero product shot (no
people, a product with an approved photo), the product photo itself, since
the product is never generated. The result then carries ``start_frame`` and
no references, and the prompt animates from that frame.

The treatment clip fits the treatment to the prompt limit. Prompts are at
most 2000 characters (the Quick clip maker's limit, below every Stories
model's own) and model neutral: references are named in words, in the order
of the ``references`` list, never with a model's tag syntax. Every reference
URL is a public URL a provider can fetch (gallery, My Assets, environment
photos and fictional character media); private real person media is never
offered here. Duration and aspect come from the document.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from . import library
from .models import CastEntry, DocScene, Product, Shot, StoryDoc

logger = logging.getLogger(__name__)

MAX_REFERENCES = 4
DEFAULT_VIDEO_MODEL = "h3-max"
CLIP_PROMPT_MAX = 2000
# A character whose picture is attached is named with at most this much text.
SHORT_LIKENESS = 90

# The closing line of a shot prompt, per look.register.
_REGISTER_LINES = {
    "cinematic": "Consistent identities and wardrobe, natural hands and faces.",
    "ugc": ("Filmed on a phone by the person in it: phone-height framing, available light, a real lived-in "
            "place with everyday clutter, natural skin texture, at most a subtle handheld drift. Not a "
            "produced commercial: no dolly or crane moves, no rim light, no grading."),
    "documentary": ("Documentary and observational: natural available light, unposed moments, consistent "
                    "identities and wardrobe, natural hands and faces."),
    "animated": "Animated, consistent character designs and wardrobe in every shot.",
}
_NO_TEXT = "No on-screen text, captions, subtitles or watermarks."
# Camera moves a phone in someone's hand can make.
_UGC_CAMERAS = {"static", "handheld", "pan", "tilt", "zoom"}

_SHOT_WORDS = {
    "establishing": "Establishing shot", "wide": "Wide shot", "medium": "Medium shot", "close_up": "Close-up",
    "extreme_close_up": "Extreme close-up", "insert": "Insert shot", "over_the_shoulder": "Over-the-shoulder shot",
    "pov": "Point-of-view shot", "two_shot": "Two-shot", "aerial": "Aerial shot", "tracking": "Tracking shot",
    "cutaway": "Cutaway",
}
_CAMERA_WORDS = {
    "static": "locked-off static camera", "pan": "a smooth pan", "tilt": "a slow tilt",
    "dolly_in": "a slow dolly in", "dolly_out": "a slow dolly out", "tracking": "a tracking move following the action",
    "handheld": "subtle handheld movement", "crane": "a rising crane move", "orbit": "a slow orbit around the subject",
    "whip_pan": "a fast whip pan", "zoom": "a smooth zoom", "rack_focus": "a rack focus between subjects",
}


def prompt_limit(video_model: str | None = None) -> int:
    """The prompt length for a clip: CLIP_PROMPT_MAX, or less when the model
    (STORY_VIDEO_MODELS max_prompt) or the Stories request schema allows less."""
    try:
        from app.clients.fal_client import STORY_VIDEO_MODELS

        cfg = STORY_VIDEO_MODELS.get(video_model or DEFAULT_VIDEO_MODEL) or {}
        model_limit = int(cfg.get("max_prompt") or 0)
    except Exception:
        model_limit = 0
    schema_limit = 0
    try:
        from app.schemas.story import CreateStoryRequest

        for meta in CreateStoryRequest.model_fields["prompt"].metadata:
            if getattr(meta, "max_length", None):
                schema_limit = int(meta.max_length)
    except Exception:
        schema_limit = 0
    return min([CLIP_PROMPT_MAX] + [n for n in (model_limit, schema_limit) if n > 0])


def fit(text: str, limit: int) -> str:
    """``text`` cut at a paragraph or sentence boundary to at most ``limit``."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("\n\n", "\n", ". "):
        at = cut.rfind(sep)
        if at >= limit * 0.6:
            return cut[:at + (1 if sep == ". " else 0)].strip()
    return cut.rsplit(" ", 1)[0].strip()


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

class _Refs:
    """The reference images in the order they are sent, each with the role it
    plays (kind and name), so the prompt can say what to take from it."""

    def __init__(self):
        self.items: list[dict] = []
        self.roles: list[tuple[str, str, str]] = []   # (kind, name, sheet | photo)

    def add(self, url: str | None, kind: str, name: str, source: str = "photo") -> None:
        if not url or len(self.items) >= MAX_REFERENCES or any(r["url"] == url for r in self.items):
            return
        self.items.append({"url": url, "label": f"{name} ({kind})"})
        self.roles.append((kind, name, source))

    def names(self, kind: str) -> set[str]:
        return {name for k, name, _ in self.roles if k == kind}


def _character_media_urls(char) -> list[tuple[str, str]]:
    """Public image references of a library character as (url, "sheet" or
    "photo"): sheet first, then references. Private (real person) media is
    never offered."""
    from app.services.faceless import consent, media

    if consent.generation_block_reason(char):
        return []
    entries = [m for m in char.media or [] if isinstance(m, dict) and m.get("kind") == "image"
               and m.get("usable_as_reference", True) and not media.is_private(m)]
    entries.sort(key=lambda m: 0 if m.get("role") == "sheet" else 1)
    urls = []
    for entry in entries:
        try:
            url = media.public_url(entry, char.user_id)
        except Exception:
            logger.exception(f"Could not build a reference URL for character {char.id}")
            continue
        if url:
            urls.append((url, "sheet" if entry.get("role") == "sheet" else "photo"))
    return urls


def _role(kind: str, name: str, sheet: bool, products: dict[str, Product]) -> str:
    if kind == "character":
        what = "a character reference sheet" if sheet else "a character reference"
        return (f"{what} of {name}: use it for face, hair and outfit only; take nothing else from it, "
                "no panels, labels or text")
    if kind == "product":
        product = products.get(name)
        keep = "; ".join(product.must_keep) if product and product.must_keep else ""
        return (f"the real product, {name}: keep its label, shape and colour exactly"
                + (f" ({keep})" if keep else "") + "; take nothing else from it, not its background")
    return f"the place, {name}: use it for the setting, layout and light only; it has no people"


def _reference_line(refs: _Refs, products: list[Product] | None = None) -> str:
    """The reference images named in words, in the order they are sent, then
    the role of each (images of the same subject share one sentence)."""
    by_name = {p.name: p for p in products or []}
    line = "Reference images, in order: " + "; ".join(r["label"] for r in refs.items) + "."
    groups: dict[tuple[str, str], list[int]] = {}
    sheets: set[tuple[str, str]] = set()
    for i, (kind, name, source) in enumerate(refs.roles, 1):
        groups.setdefault((kind, name), []).append(i)
        if source == "sheet":
            sheets.add((kind, name))
    for (kind, name), numbers in groups.items():
        if len(numbers) == 1:
            subject = f"Image {numbers[0]} is"
        else:
            subject = "Images " + ", ".join(str(n) for n in numbers[:-1]) + f" and {numbers[-1]} are"
        line += f" {subject} {_role(kind, name, (kind, name) in sheets, by_name)}."
    return line


def _short(text: str, limit: int = SHORT_LIKENESS) -> str:
    """``text`` cut to its first clauses within ``limit``, at a comma or a word."""
    text = (text or "").strip().rstrip(".")
    if len(text) <= limit:
        return text
    cut = text[:limit]
    at = cut.rfind(", ")
    return (cut[:at] if at >= limit // 3 else cut.rsplit(" ", 1)[0]).strip().rstrip(",")


def _env_media_urls(env) -> list[str]:
    return [library.media_url(m, env.user_id) for m in env.media or [] if isinstance(m, dict) and m.get("key")]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def _likeness(db: Session, user_id: int, entry: CastEntry, chars: dict) -> str:
    char = chars.get(entry.key)
    if char is None and entry.ref_id:
        char = library.owned_character(db, user_id, entry.ref_id)
        chars[entry.key] = char
    if char is not None:
        clause = library.character_clause(char)
        if entry.wardrobe and entry.wardrobe.lower() not in clause.lower():
            clause = f"{clause}, wearing {entry.wardrobe}"
        return clause
    return library.entry_clause(entry)


def _look(doc: StoryDoc) -> str:
    parts = [doc.look.visual_style, doc.look.palette and f"palette {doc.look.palette}",
             doc.look.lighting and f"lighting {doc.look.lighting}", doc.look.camera_feel]
    return ", ".join(p.strip().rstrip(".") for p in parts if p and p.strip())


def _look_text(doc: StoryDoc) -> str:
    """The look in the document's own words; a cinematic piece with no
    visual style of its own is cinematic and photoreal."""
    look = _look(doc)
    if doc.look.register == "cinematic" and not doc.look.visual_style.strip():
        look = "Cinematic, photoreal" + (f", {look}" if look else "")
    return look


def _look_line(doc: StoryDoc) -> str:
    look = _look_text(doc)
    return f"Look: {look}." if look else ""


def _has_start_frame_mode(video_model: str | None) -> bool:
    """Whether the video family can open a clip on a given first frame."""
    try:
        from app.clients.fal_client import STORY_VIDEO_MODELS

        cfg = STORY_VIDEO_MODELS.get(video_model or DEFAULT_VIDEO_MODEL) or {}
        return bool((cfg.get("endpoints") or {}).get("image-to-video"))
    except Exception:
        return False


def _start_frame(shot: Shot, in_frame: list[CastEntry], props: list[Product], video_model: str | None) -> dict | None:
    """The first frame a shot opens on: its approved keyframe, else the photo
    of a product in a hero shot without people; None when the family cannot
    take one."""
    if not _has_start_frame_mode(video_model):
        return None
    if shot.keyframe_approved and shot.keyframe_url:
        return {"url": shot.keyframe_url, "label": f"Keyframe of shot {shot.id}", "kind": "keyframe"}
    if not in_frame:
        for product in props:
            if product.image_approved and product.image_url:
                return {"url": product.image_url, "label": f"{product.name} (product)", "kind": "product",
                        "name": product.name}
    return None


def _previous_shot(doc: StoryDoc, scene: DocScene, shot: Shot) -> Shot | None:
    """The shot before ``shot`` when it plays in the same place, else None."""
    flat = doc.all_shots()
    for i, (sc, sh) in enumerate(flat):
        if sh.id != shot.id:
            continue
        if i == 0:
            return None
        prev_scene, prev = flat[i - 1]
        same_place = prev_scene.id == scene.id or (
            scene.environment_key is not None and prev_scene.environment_key == scene.environment_key)
        return prev if same_place else None
    return None


def _product_text(product: Product, pictured: bool) -> str:
    if pictured:
        return f"{product.name}, exactly as in its reference image"
    parts = [product.name, product.description.strip().rstrip(".")]
    text = ", ".join(p for p in parts if p)
    if product.must_keep:
        text += "; keep exactly: " + "; ".join(product.must_keep)
    return text


def _environment_text(db: Session, user_id: int, doc: StoryDoc, scene: DocScene) -> tuple[str, object | None]:
    entry = doc.env(scene.environment_key)
    if entry is None:
        return (scene.heading or ""), None
    env = library.owned_environment(db, user_id, entry.ref_id) if entry.ref_id else None
    description = entry.description or (env.description if env else "") or ""
    parts = [entry.name, description, entry.time_of_day, entry.mood and f"{entry.mood} mood"]
    return ", ".join(p.strip().rstrip(".") for p in parts if p and p.strip()), env


def shot_clip(db: Session, user_id: int, doc: StoryDoc, shot_id: str, video_model: str | None = None) -> dict | None:
    """{prompt, references, start_frame, duration_seconds, aspect} for one
    shot, or None. ``start_frame`` ({url, label, kind}) is set when the clip
    should open on that image (image-to-video); references are empty then."""
    found = doc.find_shot(shot_id)
    if found is None:
        return None
    scene, shot = found
    chars: dict = {}
    refs = _Refs()
    in_frame = [c for c in (doc.cast(k) for k in shot.characters) if c is not None]
    props = [p for p in (doc.product(k) for k in shot.props) if p is not None]
    env_entry = doc.env(scene.environment_key)
    env_text, env = _environment_text(db, user_id, doc, scene)
    register = doc.look.register
    start = _start_frame(shot, in_frame, props, video_model)

    if start is None:
        # Approved images first, in order: characters in frame, products, the place.
        for entry in in_frame:
            if entry.image_approved:
                refs.add(entry.image_url, "character", entry.name)
        for product in props:
            if product.image_approved:
                refs.add(product.image_url, "product", product.name)
        if env_entry is not None and env_entry.image_approved:
            refs.add(env_entry.image_url, "environment", env_entry.name)
        # Library photos fill the remaining reference slots.
        for entry in in_frame:
            char = library.owned_character(db, user_id, entry.ref_id) if entry.ref_id else None
            chars[entry.key] = char
            if char is not None:
                for url, source in _character_media_urls(char)[:2]:
                    refs.add(url, "character", entry.name, source)
        if env is not None:
            for url in _env_media_urls(env)[:2]:
                refs.add(url, "environment", env_entry.name if env_entry else env.name)
    pictured = refs.names("character")
    pictured_products = refs.names("product")

    lines = []
    if start is not None and start["kind"] == "keyframe":
        lines.append("Start from the first frame, the approved keyframe of this shot: keep its composition, "
                     "people, wardrobe, place and light, and animate from it.")
    elif start is not None:
        product = next(p for p in props if p.name == start["name"])
        keep = f" ({'; '.join(product.must_keep)})" if product.must_keep else ""
        lines.append(f"Start from the first frame, the real product photo of {product.name}: keep its label, shape "
                     f"and colour exactly{keep}. The product rests fixed in place while the camera moves.")
    camera = shot.camera
    camera_words = _CAMERA_WORDS.get(camera, "a steady camera")
    if register == "ugc" and camera not in _UGC_CAMERAS:
        camera_words = "a subtle handheld drift"
    action = shot.action.strip().rstrip(".") or (scene.summary or "The scene unfolds").strip().rstrip(".")
    lines.append(f"{_SHOT_WORDS.get(shot.type, 'Shot')} with {camera_words}. {action}.")
    if shot.frame_position.strip():
        lines.append(f"Frame: {shot.frame_position.strip().rstrip('.')}.")
    previous = _previous_shot(doc, scene, shot)
    begins = previous.end_state.strip().rstrip(".") if previous is not None else ""
    ends = shot.end_state.strip().rstrip(".")
    if begins or ends:
        lines.append(" ".join(x for x in (begins and f"Begins: {begins}.", ends and f"Ends: {ends}.") if x))
    if in_frame:
        def who(c: CastEntry) -> str:
            likeness = _likeness(db, user_id, c, chars)
            # The picture carries the likeness; the words name who is who.
            if c.name in pictured or (start is not None and start["kind"] == "keyframe"):
                return _short(likeness)
            return likeness
        people = "; ".join(f"{c.name}: {who(c)}" for c in in_frame)
        count = len(in_frame)
        lines.append(f"In frame ({count} {'person' if count == 1 else 'people'}): {people}.")
    else:
        lines.append("No people in frame." if shot.b_roll or shot.type in ("insert", "cutaway") or props else "")
    if props and not (start is not None and start["kind"] == "product"):
        products = "; ".join(_product_text(p, p.name in pictured_products) for p in props)
        lines.append(f"Product in frame: {products}." + (" Hands never cover the label." if in_frame else ""))
    if env_text and not (start is not None and start["kind"] == "product"):
        lines.append(f"Setting: {env_text}.")
    lines.append(_look_line(doc))
    for d in shot.dialogue:
        speaker = doc.cast(d.character_key)
        name = speaker.name if speaker else "Voice"
        delivery = f" ({d.delivery})" if d.delivery else ""
        lines.append(f'{name}{delivery}: "{d.line}"')
    if shot.voiceover:
        lines.append(f'Voiceover: "{shot.voiceover}"')
    if shot.sound:
        lines.append(f"Sound: {shot.sound}.")
    if shot.on_screen_text:
        lines.append("Keep the centre band of the frame clear for a text overlay added later.")
    lines.append(f"{_REGISTER_LINES.get(register, _REGISTER_LINES['cinematic'])} {_NO_TEXT}")

    limit = prompt_limit(video_model)
    tail = ("\n" + _reference_line(refs, doc.products)) if refs.items else ""
    body = fit("\n".join(line for line in lines if line), max(200, limit - len(tail)))
    prompt = fit(body + tail, limit)
    return {"prompt": prompt, "references": refs.items,
            "start_frame": {"url": start["url"], "label": start["label"], "kind": start["kind"]} if start else None,
            "duration_seconds": shot.duration_seconds, "aspect": doc.aspect, "shot_id": shot.id, "scene_id": scene.id}


def compose_treatment(doc: StoryDoc) -> str:
    """A treatment built from the document itself, for a document without one
    (hand-written, or older than the treatment field)."""
    out = []
    who = ", ".join(c.name for c in doc.characters) or "the cast"
    opening = (f"A {doc.target_seconds} second {doc.aspect} {'concept ad' if doc.format == 'ad' else 'short film'}"
               f"{': ' + doc.title if doc.title else ''}. {doc.logline or doc.synopsis or ''} With {who}.")
    out.append(re.sub(r"\s+", " ", opening).strip())
    if doc.environments:
        out.append("Setting: " + " ".join(
            f"{e.name}: {e.description}".strip().rstrip(".") + "." for e in doc.environments))
    t = 0.0
    for i, scene in enumerate(doc.scenes, 1):
        length = sum(s.duration_seconds for s in scene.shots)
        start, t = t, t + length
        body = " ".join(f"{_SHOT_WORDS.get(s.type, 'Shot')}, {_CAMERA_WORDS.get(s.camera, '')}: "
                        f"{s.action.strip().rstrip('.')}." for s in scene.shots)
        lines = [f"Scene {i} ({start:g}-{t:g} seconds): {body}".strip()]
        for s in scene.shots:
            for d in s.dialogue:
                speaker = doc.cast(d.character_key)
                delivery = f" ({d.delivery})" if d.delivery else ""
                lines.append(f'{speaker.name if speaker else "Voice"}{delivery}: "{d.line}"')
        out.append("\n".join(lines))
    look = _look_text(doc)
    if look:
        out.append(f"Visual direction: {look}, {doc.aspect}. {_REGISTER_LINES.get(doc.look.register, '')}".strip())
    if doc.look.music:
        out.append(f"Audio direction: {doc.look.music}; natural delivery and accurate lip sync.")
    constraints = (f"Important constraints: exactly {len(doc.characters)} "
                   f"{'person' if len(doc.characters) == 1 else 'people'}; consistent identities, wardrobe and "
                   "place in every shot; no distorted faces or hands, no extra fingers, no robotic dialogue.")
    for product in doc.products:
        constraints += f" {_product_text(product, product.image_approved).rstrip('.')}, identical in every shot."
    if doc.format == "ad" and doc.ad and doc.ad.brand:
        constraints += " A fictional concept advertisement, not an official one."
    out.append(constraints)
    return "\n\n".join(out)


def treatment_clip(db: Session, user_id: int, doc: StoryDoc, video_model: str | None = None) -> dict:
    """{prompt, references, duration_seconds, aspect} for the whole piece in one take."""
    refs = _Refs()
    for entry in doc.characters:
        if entry.image_approved:
            refs.add(entry.image_url, "character", entry.name)
    for product in doc.products:
        if product.image_approved:
            refs.add(product.image_url, "product", product.name)
    for entry in doc.environments:
        if entry.image_approved:
            refs.add(entry.image_url, "environment", entry.name)
    for entry in doc.characters:
        char = library.owned_character(db, user_id, entry.ref_id) if entry.ref_id else None
        if char is not None:
            for url, source in _character_media_urls(char)[:1]:
                refs.add(url, "character", entry.name, source)
    for entry in doc.environments:
        env = library.owned_environment(db, user_id, entry.ref_id) if entry.ref_id else None
        if env is not None:
            for url in _env_media_urls(env)[:1]:
                refs.add(url, "environment", entry.name)
    limit = prompt_limit(video_model)
    tail = ("\n\n" + _reference_line(refs, doc.products)) if refs.items else ""
    text = doc.treatment.strip() or compose_treatment(doc)
    if len(text) + len(tail) > limit:
        compact = compose_treatment(doc)
        if len(compact) < len(text):
            text = compact
    prompt = fit(text, max(200, limit - len(tail))) + tail
    duration = max(2, min(int(doc.target_seconds), 15))
    return {"prompt": prompt, "references": refs.items, "duration_seconds": duration, "aspect": doc.aspect}
