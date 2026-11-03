"""Make keyframe: a still for one shot from the approved cast, place and
product images, made by an image edit model with every picture as a reference.

The still is the shot's first frame (docs/STORY_ROOM.md). Only images the
server approved in the document are sent: the characters in frame, the
products in the shot's props and the scene's place. Library photos never are.
Each picture gets exactly one stated job and what not to take from it
("Image 1 is Mira: use it for her face, hair and outfit only; take nothing
else from it"); a place lends the place only, never people; a product keeps
its label, shape and colour exactly. Then the shot: size and angle, the moment
it opens on (the previous shot's end state in the same place), who stands
where, the setting, the look in the document's register, and "no text, no
captions, no watermark". Output at the document's aspect.

A shot whose characters have no approved image, or whose products have no
approved photo, is refused before anything is sent (``KeyframeBlocked``): a
likeness or a product the model would have to invent is not a keyframe.

Estimated at the model's existing ``edit:<model>`` key for one output
(``price``); the router records that spending once the image is stored, and a
provider failure (``KeyframeFailed``) records nothing. The fal request runs in the
threadpool with a deadline, so the web worker's event loop is never held.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.services import pricing as cp

from . import clip
from .models import DocScene, Shot, StoryDoc

logger = logging.getLogger(__name__)

# Nano Banana 2.1 edit: up to 14 reference images addressed by order, every
# aspect the Story Room uses, and the edit model the app holds a likeness with.
KEYFRAME_MODEL = "google/nano-banana-2.1/edit"
KEYFRAME_RESOLUTION = "1K"
PROMPT_MAX = 4000
# The fal request is given this long, then cancelled.
TIMEOUT_SECONDS = 150
POLL_SECONDS = 1.5
RESULT_MAX_BYTES = 25 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 60

_ASPECT_WORDS = {"9:16": "vertical 9:16", "16:9": "horizontal 16:9", "1:1": "square 1:1"}
# The camera's height and side for a still, by shot type; the rest are at eye level.
_ANGLE_WORDS = {
    "aerial": "seen from high above",
    "pov": "from the eye line of the person whose view it is",
    "over_the_shoulder": "over one person's shoulder toward the other",
    "establishing": "a wide establishing view at eye level",
}
# The closing line of a still, per look.register.
_REGISTER_STILLS = {
    "cinematic": "A frame from a film: consistent identities and wardrobe, natural hands and faces.",
    "ugc": ("A frame from a phone video filmed by the person in it: phone-height framing, available light, a "
            "real lived-in place with everyday clutter, natural skin texture. Not a produced commercial: no rim "
            "light, no grading."),
    "documentary": "A documentary frame: natural available light, an unposed moment, natural hands and faces.",
    "animated": "A frame from an animated film: every character keeps the design in their reference image.",
}
_NO_TEXT = ("One single frame, not a collage, grid or split screen. No text, no captions, no watermark, no "
            "logos or readable signs other than a product's own label.")


class KeyframeBlocked(Exception):
    """The shot cannot be made into a keyframe yet; ``message`` says why, for people."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class KeyframeFailed(RuntimeError):
    """The provider failed or returned nothing usable."""


@dataclass
class KeyframePlan:
    shot_id: str
    prompt: str
    aspect: str
    references: list[dict] = field(default_factory=list)   # [{url, label, kind, name}] in the order sent

    @property
    def urls(self) -> list[str]:
        return [r["url"] for r in self.references]


def price_key() -> str:
    return cp.edit_key(KEYFRAME_MODEL, KEYFRAME_RESOLUTION)


def price() -> float:
    """Estimated USD for one keyframe (the edit model's own price for one output)."""
    return float(cp.edit_usd(KEYFRAME_MODEL, KEYFRAME_RESOLUTION))


def max_references() -> int:
    from app.clients.fal_client import EDIT_MODEL_CONFIG

    return int(EDIT_MODEL_CONFIG[KEYFRAME_MODEL]["max_inputs"])


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

def _names(items) -> str:
    names = [i.name or i.key for i in items]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"


def references(doc: StoryDoc, scene: DocScene, shot: Shot) -> list[dict]:
    """The approved images for the shot, characters first, then products, then
    the place. Raises KeyframeBlocked when a character in frame or a product
    in the shot has no approved image, or when nothing is left to anchor on."""
    in_frame = [c for c in (doc.cast(k) for k in shot.characters) if c is not None]
    props = [p for p in (doc.product(k) for k in shot.props) if p is not None]
    missing = [c for c in in_frame if not (c.image_approved and c.image_url)]
    if missing:
        raise KeyframeBlocked(f"Approve a reference image for {_names(missing)} in the Cast tab first.")
    unpictured = [p for p in props if not (p.image_approved and p.image_url)]
    if unpictured:
        raise KeyframeBlocked(f"Add a photo of {_names(unpictured)} in the Cast tab first. "
                              "A product is never generated.")
    refs: list[dict] = []

    def add(url: str, kind: str, name: str) -> None:
        if url and not any(r["url"] == url for r in refs):
            refs.append({"url": url, "label": f"{name} ({kind})", "kind": kind, "name": name})

    for entry in in_frame:
        add(entry.image_url, "character", entry.name or entry.key)
    for product in props:
        add(product.image_url, "product", product.name or product.key)
    place = doc.env(scene.environment_key)
    if place is not None and place.image_approved and place.image_url:
        add(place.image_url, "place", place.name or place.key)
    if not refs:
        if place is not None:
            raise KeyframeBlocked(f"Approve the image of {place.name or place.key} in the Cast tab first.")
        raise KeyframeBlocked("This shot has no character, product or place with an approved image to make a "
                              "keyframe from. Add one to the shot first.")
    if len(refs) > max_references():
        raise KeyframeBlocked(f"This shot has more people, products and places than one keyframe can hold "
                              f"(at most {max_references()} pictures). Split it into two shots.")
    return refs


def _job(number: int, ref: dict, doc: StoryDoc) -> str:
    """One reference's job in one sentence, with what not to take from it."""
    name = ref["name"]
    if ref["kind"] == "character":
        return (f"Image {number} is {name}: use it for {name}'s face, hair and outfit only; take nothing else "
                "from it, not its background, pose, framing or light.")
    if ref["kind"] == "product":
        product = next((p for p in doc.products if (p.name or p.key) == name), None)
        keep = f" ({'; '.join(product.must_keep)})" if product and product.must_keep else ""
        return (f"Image {number} is the real product, {name}: keep its label, shape and colour exactly{keep}; "
                "take nothing else from it, not its background or any hands.")
    return (f"Image {number} is the place, {name}: the place only, no people from it; use its layout, "
            "surfaces and light.")


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

def build_prompt(db: Session, user_id: int, doc: StoryDoc, scene: DocScene, shot: Shot, refs: list[dict]) -> str:
    in_frame = [c for c in (doc.cast(k) for k in shot.characters) if c is not None]
    props = [p for p in (doc.product(k) for k in shot.props) if p is not None]
    kind = "concept ad" if doc.format == "ad" else "film"
    head = [f"The first frame of one shot of a {_ASPECT_WORDS.get(doc.aspect, doc.aspect)} {kind}, as a single "
            "still image. Each reference picture has exactly one job:"]
    head += [_job(i, ref, doc) for i, ref in enumerate(refs, 1)]

    lines = []
    size = clip._SHOT_WORDS.get(shot.type, "Shot")
    angle = _ANGLE_WORDS.get(shot.type, "at eye level")
    camera = clip._CAMERA_WORDS.get(shot.camera, "a steady camera")
    lines.append(f"{size}, {angle}. The shot then plays with {camera}; this is its opening frame.")
    previous = clip._previous_shot(doc, scene, shot)
    begins = previous.end_state.strip().rstrip(".") if previous is not None else ""
    action = shot.action.strip().rstrip(".") or (scene.summary or "").strip().rstrip(".")
    if action:
        lines.append(f"The moment: the start of this action: {action}.")
    if begins:
        lines.append(f"Starting pose: {begins}.")
    if shot.frame_position.strip():
        lines.append(f"Frame: {shot.frame_position.strip().rstrip('.')}.")
    if in_frame:
        chars: dict = {}

        def who(c) -> str:
            # The picture carries the likeness; a few words say who is who.
            name = c.name or c.key
            likeness = clip._likeness(db, user_id, c, chars).strip()
            if likeness.lower().startswith(name.lower()):
                likeness = likeness[len(name):].lstrip(" ,;:")
            likeness = clip._short(likeness)
            return f"{name} ({likeness})" if likeness else name

        people = "; ".join(who(c) for c in in_frame)
        count = len(in_frame)
        lines.append(f"Exactly {count} {'person' if count == 1 else 'people'} in frame, no one else: {people}.")
    else:
        lines.append("No people in frame.")
    if props:
        products = "; ".join(f"{p.name}, exactly as in its reference image" for p in props)
        lines.append(f"Product in frame: {products}." + (" Hands never cover the label." if in_frame else ""))
    env_text, _ = clip._environment_text(db, user_id, doc, scene)
    if env_text:
        lines.append(f"Setting: {env_text}.")
    lines.append(clip._look_line(doc))
    if shot.on_screen_text:
        lines.append("Keep the centre band of the frame clear for a text overlay added later.")
    lines.append(_REGISTER_STILLS.get(doc.look.register, _REGISTER_STILLS["cinematic"]))

    top = "\n".join(head)
    tail = "\n" + _NO_TEXT
    body = clip.fit("\n".join(line for line in lines if line), max(400, PROMPT_MAX - len(top) - len(tail) - 1))
    return f"{top}\n{body}{tail}"


def plan(db: Session, user_id: int, doc: StoryDoc, shot_id: str) -> KeyframePlan | None:
    """The keyframe request for one shot, or None when the shot is not in the
    document. Raises KeyframeBlocked (see ``references``)."""
    found = doc.find_shot(shot_id)
    if found is None:
        return None
    scene, shot = found
    refs = references(doc, scene, shot)
    return KeyframePlan(shot_id=shot.id, prompt=build_prompt(db, user_id, doc, scene, shot, refs),
                        aspect=doc.aspect, references=refs)


def arguments(keyframe: KeyframePlan) -> dict:
    from app.clients.fal_client import build_edit_arguments

    return build_edit_arguments(KEYFRAME_MODEL, keyframe.prompt, keyframe.urls, aspect_ratio=keyframe.aspect,
                                resolution=KEYFRAME_RESOLUTION, output_format="png", num_images=1)


# ---------------------------------------------------------------------------
# The provider call
# ---------------------------------------------------------------------------

def _run(client, args: dict) -> dict:
    """Upload our own images to fal storage, submit and wait for the result
    (threadpool), cancelling the request when it outlives TIMEOUT_SECONDS."""
    import fal_client as fal_sdk

    from app.services.fal_inputs import resolve_fal_inputs

    handle = client.submit(KEYFRAME_MODEL, arguments=resolve_fal_inputs(args))
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while not isinstance(client.status(KEYFRAME_MODEL, handle.request_id, with_logs=False), fal_sdk.Completed):
        if time.monotonic() > deadline:
            try:
                client.cancel(KEYFRAME_MODEL, handle.request_id)
            except Exception:
                logger.warning(f"Could not cancel keyframe request {handle.request_id}")
            raise TimeoutError(f"Keyframe request {handle.request_id} did not finish in {TIMEOUT_SECONDS}s")
        time.sleep(POLL_SECONDS)
    return client.result(KEYFRAME_MODEL, handle.request_id)


async def render(db: Session, keyframe: KeyframePlan) -> bytes:
    """The keyframe's image bytes. Raises KeyframeFailed for anything the
    provider does wrong."""
    from app.clients.fal_client import drop_safety_flagged
    from app.services.fal_keys import get_sync_client
    from app.services.url_fetch import afetch_bytes

    try:
        client = get_sync_client(db)
        args = arguments(keyframe)
        result = await run_in_threadpool(_run, client, args)
        result, blocked = drop_safety_flagged(result if isinstance(result, dict) else {})
        images = result.get("images") or []
        image = images[0] if images else None
        url = image.get("url") if isinstance(image, dict) else image
        if not url:
            raise KeyframeFailed("blocked by the safety filter" if blocked else "no image returned")
        return await afetch_bytes(url, max_bytes=RESULT_MAX_BYTES, timeout=FETCH_TIMEOUT_SECONDS)
    except KeyframeFailed:
        raise
    except Exception as exc:
        logger.warning(f"Keyframe for shot {keyframe.shot_id} failed: {type(exc).__name__}: {exc}")
        raise KeyframeFailed("the provider failed") from exc
