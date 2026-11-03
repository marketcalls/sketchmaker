"""StoryDoc: the structured story document a Story Room thread is built around.

The director rewrites it on every turn and people edit it by hand, so nothing
that comes in is trusted. ``normalize`` turns any JSON-ish value into a valid
StoryDoc: unknown enum values are coerced to the nearest valid one, missing or
duplicate ids are re-keyed, references to unknown cast or environment keys are
dropped (or matched by name), text and list sizes are capped and every shot
lasts 1 to 15 seconds. The stored document is always ``StoryDoc`` valid.

``image_url`` and ``image_approved`` on cast, environment and product entries,
and ``keyframe_url`` and ``keyframe_approved`` on shots, belong to the server:
``carry_images`` copies them by key (shots by id) from the stored document
onto a new one (from the model or the client), so neither can set or clear
them. A product's photo is always an upload of the real product, never a
generated image.

Documents stored before a field existed load with its default.
"""

from __future__ import annotations

import difflib
import math
import re
import warnings
from typing import Any, Literal

from pydantic import BaseModel, Field

FORMATS = ("story", "ad")
ASPECTS = ("9:16", "16:9", "1:1")
SHOT_TYPES = (
    "establishing", "wide", "medium", "close_up", "extreme_close_up", "insert",
    "over_the_shoulder", "pov", "two_shot", "aerial", "tracking", "cutaway",
)
CAMERAS = (
    "static", "pan", "tilt", "dolly_in", "dolly_out", "tracking", "handheld",
    "crane", "orbit", "whip_pan", "zoom", "rack_focus",
)
TRANSITIONS = (
    "cut", "jump_cut", "match_cut", "smash_cut", "cross_cut", "dissolve",
    "whip_pan", "j_cut", "l_cut", "fade_in", "fade_out",
)

REGISTERS = ("cinematic", "ugc", "documentary", "animated")
OBJECTIVES = ("awareness", "consideration", "conversion")
# Ad placements in seconds (60 only when the user asks for it), with the beats
# and voiceover words each one holds.
AD_PLACEMENTS = (6, 15, 30)
AD_BEATS = {6: (2, 2), 15: (4, 6), 30: (6, 8)}
AD_WORD_BUDGETS = {6: (8, 12), 15: (30, 35), 30: (60, 70)}

MIN_TARGET_SECONDS = 5
MAX_TARGET_SECONDS = 600
MIN_SHOT_SECONDS = 1.0
MAX_SHOT_SECONDS = 15.0
MAX_SCENES = 30
MAX_SHOTS_PER_SCENE = 12
MAX_SHOTS_TOTAL = 120
MAX_CHARACTERS = 12
MAX_ENVIRONMENTS = 12
MAX_PRODUCTS = 4
MAX_MUST_KEEP = 8
MAX_HOOK_VARIANTS = 3
MAX_DIALOGUE_LINES = 8
MAX_QUESTIONS = 16
MAX_MANDATORIES = 10

# Text caps, in characters.
SHORT = 200
MEDIUM = 600
LONG = 2000
SYNOPSIS = 4000
TREATMENT = 12000

Format = Literal["story", "ad"]
Aspect = Literal["9:16", "16:9", "1:1"]
ShotType = Literal[
    "establishing", "wide", "medium", "close_up", "extreme_close_up", "insert",
    "over_the_shoulder", "pov", "two_shot", "aerial", "tracking", "cutaway",
]
Camera = Literal[
    "static", "pan", "tilt", "dolly_in", "dolly_out", "tracking", "handheld",
    "crane", "orbit", "whip_pan", "zoom", "rack_focus",
]
Transition = Literal[
    "cut", "jump_cut", "match_cut", "smash_cut", "cross_cut", "dissolve",
    "whip_pan", "j_cut", "l_cut", "fade_in", "fade_out",
]
Register = Literal["cinematic", "ugc", "documentary", "animated"]
Objective = Literal["awareness", "consideration", "conversion"]


class AdBrief(BaseModel):
    product: str = ""
    brand: str = ""
    offer: str = ""
    key_message: str = ""
    cta: str = ""
    mandatories: list[str] = Field(default_factory=list)
    objective: Objective = "consideration"
    audience_mindset: str = ""
    proposition: str = ""
    creativity: str = ""
    hook_variants: list[str] = Field(default_factory=list)


# "register" shadows ABCMeta.register on the class only; instances read the
# field as usual, which is the name the shared document contract uses.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message='Field name "register"')

    class Look(BaseModel):
        visual_style: str = ""
        palette: str = ""
        lighting: str = ""
        camera_feel: str = ""
        music: str = ""
        register: Register = "cinematic"


class Product(BaseModel):
    """A real product shown in the piece. Its picture is only ever an
    uploaded photo (set by the server), never a generated image."""

    key: str
    name: str = ""
    description: str = ""
    must_keep: list[str] = Field(default_factory=list)
    image_url: str = ""
    image_approved: bool = False


class CastEntry(BaseModel):
    key: str
    ref_id: int | None = None
    name: str = ""
    role: str = ""
    description: str = ""
    wardrobe: str = ""
    voice_notes: str = ""
    image_prompt: str = ""
    image_url: str | None = None
    image_approved: bool = False


class EnvEntry(BaseModel):
    key: str
    ref_id: int | None = None
    name: str = ""
    description: str = ""
    time_of_day: str = ""
    mood: str = ""
    image_prompt: str = ""
    image_url: str | None = None
    image_approved: bool = False


class DialogueLine(BaseModel):
    character_key: str = ""
    line: str = ""
    delivery: str = ""


class Shot(BaseModel):
    id: str
    type: ShotType = "medium"
    b_roll: bool = False
    camera: Camera = "static"
    duration_seconds: float = Field(default=3.0, ge=MIN_SHOT_SECONDS, le=MAX_SHOT_SECONDS)
    transition_in: Transition = "cut"
    action: str = ""
    characters: list[str] = Field(default_factory=list)
    dialogue: list[DialogueLine] = Field(default_factory=list)
    voiceover: str = ""
    on_screen_text: str = ""
    sound: str = ""
    props: list[str] = Field(default_factory=list)     # Product keys in frame
    frame_position: str = ""                            # who is where, facing which way
    end_state: str = ""                                 # the pose or state the shot ends in
    keyframe_url: str = ""                              # set only by the server
    keyframe_approved: bool = False


class DocScene(BaseModel):
    id: str
    heading: str = ""
    environment_key: str | None = None
    purpose: str = ""
    summary: str = ""
    shots: list[Shot] = Field(default_factory=list)


class StoryDoc(BaseModel):
    format: Format = "story"
    title: str = ""
    logline: str = ""
    synopsis: str = ""
    genre: str = ""
    tone: str = ""
    audience: str = ""
    language: str = "en"
    aspect: Aspect = "9:16"
    target_seconds: int = Field(default=30, ge=MIN_TARGET_SECONDS, le=MAX_TARGET_SECONDS)
    ad: AdBrief | None = None
    look: Look = Field(default_factory=Look)
    characters: list[CastEntry] = Field(default_factory=list)
    environments: list[EnvEntry] = Field(default_factory=list)
    products: list[Product] = Field(default_factory=list)
    scenes: list[DocScene] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    treatment: str = ""

    def shot_count(self) -> int:
        return sum(len(s.shots) for s in self.scenes)

    def total_seconds(self) -> float:
        return round(sum(sh.duration_seconds for s in self.scenes for sh in s.shots), 2)

    def find_shot(self, shot_id: str) -> tuple[DocScene, Shot] | None:
        for scene in self.scenes:
            for shot in scene.shots:
                if shot.id == shot_id:
                    return scene, shot
        return None

    def cast(self, key: str | None) -> CastEntry | None:
        return next((c for c in self.characters if c.key == key), None) if key else None

    def env(self, key: str | None) -> EnvEntry | None:
        return next((e for e in self.environments if e.key == key), None) if key else None

    def product(self, key: str | None) -> Product | None:
        return next((p for p in self.products if p.key == key), None) if key else None

    def all_shots(self) -> list[tuple[DocScene, Shot]]:
        return [(scene, shot) for scene in self.scenes for shot in scene.shots]


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------

def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


# Common spellings and crew shorthand the model (or a person) may use.
_SHOT_ALIASES = {
    "ews": "establishing", "est": "establishing", "establish": "establishing", "master": "wide",
    "ws": "wide", "long": "wide", "long_shot": "wide", "full": "wide", "full_shot": "wide",
    "wide_shot": "wide", "extreme_wide": "establishing", "ms": "medium", "mid": "medium",
    "medium_shot": "medium", "mcu": "close_up", "medium_close_up": "close_up", "cu": "close_up",
    "closeup": "close_up", "close": "close_up", "close_up_shot": "close_up", "ecu": "extreme_close_up",
    "xcu": "extreme_close_up", "extreme_closeup": "extreme_close_up", "macro": "extreme_close_up",
    "detail": "insert", "insert_shot": "insert", "product": "insert", "product_shot": "insert",
    "hero": "insert", "hero_shot": "insert", "ots": "over_the_shoulder", "over_shoulder": "over_the_shoulder",
    "point_of_view": "pov", "two": "two_shot", "twoshot": "two_shot", "2_shot": "two_shot",
    "drone": "aerial", "birds_eye": "aerial", "overhead": "aerial", "top_down": "aerial",
    "follow": "tracking", "tracking_shot": "tracking", "steadicam": "tracking", "b_roll": "cutaway",
    "broll": "cutaway", "cut_away": "cutaway", "reaction": "close_up", "reaction_shot": "close_up",
}
_CAMERA_ALIASES = {
    "locked": "static", "locked_off": "static", "fixed": "static", "still": "static", "none": "static",
    "tripod": "static", "pan_left": "pan", "pan_right": "pan", "tilt_up": "tilt", "tilt_down": "tilt",
    "push": "dolly_in", "push_in": "dolly_in", "slow_push_in": "dolly_in", "dolly": "dolly_in",
    "pull": "dolly_out", "pull_out": "dolly_out", "pull_back": "dolly_out", "track": "tracking",
    "follow": "tracking", "steadicam": "tracking", "gimbal": "tracking", "truck": "tracking",
    "hand_held": "handheld", "shaky": "handheld", "jib": "crane", "boom": "crane", "drone": "crane",
    "arc": "orbit", "circle": "orbit", "360": "orbit", "whip": "whip_pan", "swish_pan": "whip_pan",
    "zoom_in": "zoom", "zoom_out": "zoom", "crash_zoom": "zoom", "snap_zoom": "zoom", "focus_pull": "rack_focus",
    "pull_focus": "rack_focus", "rack": "rack_focus",
}
_TRANSITION_ALIASES = {
    "hard_cut": "cut", "straight_cut": "cut", "none": "cut", "jump": "jump_cut", "jumpcut": "jump_cut",
    "match": "match_cut", "graphic_match": "match_cut", "smash": "smash_cut", "crosscut": "cross_cut",
    "intercut": "cross_cut", "parallel_cut": "cross_cut", "cross_dissolve": "dissolve", "mix": "dissolve",
    "whip": "whip_pan", "swish": "whip_pan", "j": "j_cut", "jcut": "j_cut", "l": "l_cut", "lcut": "l_cut",
    "fade": "fade_in", "fade_from_black": "fade_in", "fade_up": "fade_in", "fade_to_black": "fade_out",
    "fade_down": "fade_out", "cut_to_black": "fade_out",
}
_REGISTER_ALIASES = {
    "film": "cinematic", "cinema": "cinematic", "filmic": "cinematic", "commercial": "cinematic",
    "photoreal": "cinematic", "premium": "cinematic", "user_generated": "ugc", "user_generated_content": "ugc",
    "creator": "ugc", "selfie": "ugc", "phone": "ugc", "influencer": "ugc", "testimonial": "ugc",
    "tiktok": "ugc", "doc": "documentary", "docu": "documentary", "observational": "documentary",
    "verite": "documentary", "vlog": "ugc", "animation": "animated", "cartoon": "animated", "anime": "animated",
    "3d": "animated", "pixar": "animated", "illustrated": "animated", "claymation": "animated",
}
_OBJECTIVE_ALIASES = {
    "brand": "awareness", "branding": "awareness", "reach": "awareness", "launch": "awareness",
    "demo": "consideration", "demonstration": "consideration", "engagement": "consideration",
    "performance": "conversion", "sales": "conversion", "sale": "conversion", "activation": "conversion",
    "direct_response": "conversion", "acquisition": "conversion", "purchase": "conversion", "retargeting": "conversion",
}


def coerce_enum(value: Any, allowed: tuple[str, ...], aliases: dict[str, str], default: str) -> str:
    """The allowed value closest to ``value``: exact, alias, prefix, then fuzzy."""
    slug = _slug(value)
    if not slug:
        return default
    if slug in allowed:
        return slug
    if slug in aliases:
        return aliases[slug]
    for word in slug.split("_"):
        if word in aliases:
            return aliases[word]
    for option in allowed:
        if slug.startswith(option) or option.startswith(slug):
            return option
    close = difflib.get_close_matches(slug, list(allowed) + list(aliases), n=1, cutoff=0.6)
    if close:
        return aliases.get(close[0], close[0])
    return default


def coerce_aspect(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in ASPECTS:
        return text
    words = {"vertical": "9:16", "portrait": "9:16", "reel": "9:16", "shorts": "9:16", "tiktok": "9:16",
             "landscape": "16:9", "horizontal": "16:9", "widescreen": "16:9", "youtube": "16:9",
             "square": "1:1"}
    for word, aspect in words.items():
        if word in text:
            return aspect
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[:x/]\s*(\d+(?:\.\d+)?)\s*$", text)
    if m and float(m.group(2)) > 0:
        ratio = float(m.group(1)) / float(m.group(2))
        return min(ASPECTS, key=lambda a: abs(_ratio(a) - ratio))
    return "9:16"


def _ratio(aspect: str) -> float:
    w, h = aspect.split(":")
    return float(w) / float(h)


def _text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value if v is not None)
    elif isinstance(value, dict):
        value = "; ".join(f"{k}: {v}" for k, v in value.items())
    text = str(value).replace("\x00", "").strip()
    return text[:limit]


def _number(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        m = re.search(r"\d+(?:\.\d+)?", str(value or ""))
        if not m:
            return default
        number = float(m.group(0))
    return number if math.isfinite(number) else default


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "y")
    return bool(value)


def _ref_id(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _strings(value: Any, limit: int, each: int) -> list[str]:
    if isinstance(value, str):
        value = [v for v in re.split(r"\n+", value) if v.strip()]
    out = []
    for item in _list(value):
        text = _text(item, each)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _image_url(value: Any) -> str | None:
    text = _text(value, LONG)
    return text or None


class _Keys:
    """Keeps ids like "c1", "s3" or "s3.2" unique, issuing new ones on demand."""

    def __init__(self, pattern: str):
        self.pattern = re.compile(pattern)
        self.used: set[str] = set()

    def take(self, wanted: Any, make) -> str:
        key = str(wanted or "").strip()
        if key and self.pattern.match(key) and key not in self.used:
            self.used.add(key)
            return key
        n = 1
        while make(n) in self.used:
            n += 1
        key = make(n)
        self.used.add(key)
        return key


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------

def normalize(raw: Any, *, default_format: str = "story") -> StoryDoc:
    """Any JSON-ish value as a valid StoryDoc (see the module docstring)."""
    if isinstance(raw, StoryDoc):
        raw = raw.model_dump(mode="json")
    data = _dict(raw)
    fmt = _slug(data.get("format"))
    if fmt not in FORMATS:
        fmt = "ad" if fmt in ("advert", "advertisement", "commercial", "promo", "spot") else default_format
    if fmt not in FORMATS:
        fmt = "story"

    # Cast and environments first, so scenes and shots can be checked against them.
    cast_keys = _Keys(r"^c\d{1,4}$")
    characters: list[CastEntry] = []
    for item in _list(data.get("characters"))[:MAX_CHARACTERS * 2]:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"), 120)
        if not name and not _text(item.get("description"), 10):
            continue
        characters.append(CastEntry(
            key=cast_keys.take(item.get("key") or item.get("id"), lambda n: f"c{n}"),
            ref_id=_ref_id(item.get("ref_id")),
            name=name or "Unnamed",
            role=_text(item.get("role"), SHORT),
            description=_text(item.get("description"), LONG),
            wardrobe=_text(item.get("wardrobe"), MEDIUM),
            voice_notes=_text(item.get("voice_notes"), MEDIUM),
            image_prompt=_text(item.get("image_prompt"), LONG),
            image_url=_image_url(item.get("image_url")),
            image_approved=_bool(item.get("image_approved")),
        ))
        if len(characters) >= MAX_CHARACTERS:
            break

    env_keys = _Keys(r"^e\d{1,4}$")
    environments: list[EnvEntry] = []
    for item in _list(data.get("environments"))[:MAX_ENVIRONMENTS * 2]:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"), 120)
        if not name and not _text(item.get("description"), 10):
            continue
        environments.append(EnvEntry(
            key=env_keys.take(item.get("key") or item.get("id"), lambda n: f"e{n}"),
            ref_id=_ref_id(item.get("ref_id")),
            name=name or "Unnamed place",
            description=_text(item.get("description"), LONG),
            time_of_day=_text(item.get("time_of_day"), 40),
            mood=_text(item.get("mood"), 120),
            image_prompt=_text(item.get("image_prompt"), LONG),
            image_url=_image_url(item.get("image_url")),
            image_approved=_bool(item.get("image_approved")),
        ))
        if len(environments) >= MAX_ENVIRONMENTS:
            break

    product_keys = _Keys(r"^p\d{1,4}$")
    products: list[Product] = []
    for item in _list(data.get("products"))[:MAX_PRODUCTS * 2]:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"), 120)
        if not name and not _text(item.get("description"), 10):
            continue
        products.append(Product(
            key=product_keys.take(item.get("key") or item.get("id"), lambda n: f"p{n}"),
            name=name or "Product",
            description=_text(item.get("description"), MEDIUM),
            must_keep=_strings(item.get("must_keep"), MAX_MUST_KEEP, SHORT),
            image_url=_text(item.get("image_url"), LONG),
            image_approved=_bool(item.get("image_approved")),
        ))
        if len(products) >= MAX_PRODUCTS:
            break
    for entry in characters + environments + products:
        if not entry.image_url:
            entry.image_approved = False

    cast_by_name = {c.name.strip().lower(): c.key for c in characters}
    env_by_name = {e.name.strip().lower(): e.key for e in environments}
    cast_set = {c.key for c in characters}
    env_set = {e.key for e in environments}

    def cast_key(value: Any) -> str | None:
        text = str(value or "").strip()
        if text in cast_set:
            return text
        return cast_by_name.get(text.lower())

    def env_key(value: Any) -> str | None:
        text = str(value or "").strip()
        if text in env_set:
            return text
        return env_by_name.get(text.lower())

    product_by_name = {p.name.strip().lower(): p.key for p in products}
    product_set = {p.key for p in products}

    def product_key(value: Any) -> str | None:
        text = str(value or "").strip()
        if text in product_set:
            return text
        return product_by_name.get(text.lower())

    scene_keys = _Keys(r"^s\d{1,4}$")
    shot_keys = _Keys(r"^s\d{1,4}\.\d{1,4}$")
    scenes: list[DocScene] = []
    total_shots = 0
    for item in _list(data.get("scenes")):
        if len(scenes) >= MAX_SCENES or total_shots >= MAX_SHOTS_TOTAL:
            break
        if not isinstance(item, dict):
            continue
        scene_id = scene_keys.take(item.get("id"), lambda n: f"s{n}")
        shots: list[Shot] = []
        for raw_shot in _list(item.get("shots")):
            if len(shots) >= MAX_SHOTS_PER_SCENE or total_shots >= MAX_SHOTS_TOTAL:
                break
            if not isinstance(raw_shot, dict):
                continue
            shots.append(_shot(raw_shot, scene_id, shot_keys, cast_key, product_key))
            total_shots += 1
        scenes.append(DocScene(
            id=scene_id,
            heading=_text(item.get("heading"), SHORT),
            environment_key=env_key(item.get("environment_key")),
            purpose=_text(item.get("purpose"), SHORT),
            summary=_text(item.get("summary"), LONG),
            shots=shots,
        ))

    ad = None
    raw_ad = data.get("ad")
    if isinstance(raw_ad, dict) or fmt == "ad":
        raw_ad = _dict(raw_ad)
        ad = AdBrief(
            product=_text(raw_ad.get("product"), SHORT),
            brand=_text(raw_ad.get("brand"), SHORT),
            offer=_text(raw_ad.get("offer"), MEDIUM),
            key_message=_text(raw_ad.get("key_message"), MEDIUM),
            cta=_text(raw_ad.get("cta"), SHORT),
            mandatories=_strings(raw_ad.get("mandatories"), MAX_MANDATORIES, SHORT),
            objective=coerce_enum(raw_ad.get("objective"), OBJECTIVES, _OBJECTIVE_ALIASES, "consideration"),
            audience_mindset=_text(raw_ad.get("audience_mindset"), MEDIUM),
            proposition=_text(raw_ad.get("proposition"), MEDIUM),
            creativity=_text(raw_ad.get("creativity"), SHORT),
            hook_variants=_strings(raw_ad.get("hook_variants"), MAX_HOOK_VARIANTS, MEDIUM),
        )
    look = _dict(data.get("look"))
    target = int(round(_number(data.get("target_seconds"), 30)))
    return StoryDoc(
        format=fmt,
        title=_text(data.get("title"), SHORT),
        logline=_text(data.get("logline"), MEDIUM),
        synopsis=_text(data.get("synopsis"), SYNOPSIS),
        genre=_text(data.get("genre"), 120),
        tone=_text(data.get("tone"), SHORT),
        audience=_text(data.get("audience"), SHORT),
        language=(_text(data.get("language"), 20) or "en"),
        aspect=coerce_aspect(data.get("aspect")),
        target_seconds=max(MIN_TARGET_SECONDS, min(MAX_TARGET_SECONDS, target)),
        ad=ad,
        look=Look(
            visual_style=_text(look.get("visual_style"), MEDIUM),
            palette=_text(look.get("palette"), SHORT),
            lighting=_text(look.get("lighting"), SHORT),
            camera_feel=_text(look.get("camera_feel"), SHORT),
            music=_text(look.get("music"), SHORT),
            register=coerce_enum(look.get("register"), REGISTERS, _REGISTER_ALIASES, "cinematic"),
        ),
        characters=characters,
        environments=environments,
        products=products,
        scenes=scenes,
        open_questions=_strings(data.get("open_questions"), MAX_QUESTIONS, 300),
        treatment=_text(data.get("treatment"), TREATMENT),
    )


def _shot(raw: dict, scene_id: str, keys: _Keys, cast_key, product_key) -> Shot:
    in_frame: list[str] = []
    for value in _list(raw.get("characters")):
        key = cast_key(value)
        if key and key not in in_frame:
            in_frame.append(key)
    props: list[str] = []
    for value in _list(raw.get("props")):
        key = product_key(value)
        if key and key not in props:
            props.append(key)
    keyframe_url = _text(raw.get("keyframe_url"), LONG)
    dialogue = []
    for line in _list(raw.get("dialogue"))[:MAX_DIALOGUE_LINES]:
        if isinstance(line, str):
            line = {"line": line}
        if not isinstance(line, dict):
            continue
        text = _text(line.get("line") or line.get("text"), MEDIUM)
        if not text:
            continue
        dialogue.append(DialogueLine(
            character_key=cast_key(line.get("character_key") or line.get("character")) or "",
            line=text,
            delivery=_text(line.get("delivery") or line.get("emotion"), 120),
        ))
    seconds = _number(raw.get("duration_seconds", raw.get("duration")), 3.0)
    seconds = round(max(MIN_SHOT_SECONDS, min(MAX_SHOT_SECONDS, seconds)), 1)
    return Shot(
        id=keys.take(raw.get("id"), lambda n: f"{scene_id}.{n}"),
        type=coerce_enum(raw.get("type"), SHOT_TYPES, _SHOT_ALIASES, "medium"),
        b_roll=_bool(raw.get("b_roll")),
        camera=coerce_enum(raw.get("camera"), CAMERAS, _CAMERA_ALIASES, "static"),
        duration_seconds=seconds,
        transition_in=coerce_enum(raw.get("transition_in"), TRANSITIONS, _TRANSITION_ALIASES, "cut"),
        action=_text(raw.get("action"), LONG),
        characters=in_frame,
        dialogue=dialogue,
        voiceover=_text(raw.get("voiceover"), LONG),
        on_screen_text=_text(raw.get("on_screen_text"), 300),
        sound=_text(raw.get("sound"), MEDIUM),
        props=props,
        frame_position=_text(raw.get("frame_position"), MEDIUM),
        end_state=_text(raw.get("end_state"), MEDIUM),
        keyframe_url=keyframe_url,
        keyframe_approved=bool(keyframe_url) and _bool(raw.get("keyframe_approved")),
    )


def empty_doc(fmt: str = "story", title: str = "") -> StoryDoc:
    return normalize({"format": fmt, "title": title, "target_seconds": 15 if fmt == "ad" else 30},
                     default_format=fmt)


def dump(doc: StoryDoc) -> dict:
    return doc.model_dump(mode="json")


def carry_images(previous: StoryDoc | None, doc: StoryDoc) -> StoryDoc:
    """Server-owned image fields: copied by key (shots by id) from
    ``previous``; a key that is new has none. The model and the client can
    never set or clear them."""
    old_cast = {c.key: c for c in previous.characters} if previous else {}
    old_env = {e.key: e for e in previous.environments} if previous else {}
    old_products = {p.key: p for p in previous.products} if previous else {}
    old_shots = {shot.id: shot for _, shot in previous.all_shots()} if previous else {}
    for entry in doc.characters:
        old = old_cast.get(entry.key)
        entry.image_url = old.image_url if old else None
        entry.image_approved = bool(old and old.image_url and old.image_approved)
    for entry in doc.environments:
        old = old_env.get(entry.key)
        entry.image_url = old.image_url if old else None
        entry.image_approved = bool(old and old.image_url and old.image_approved)
    for product in doc.products:
        old = old_products.get(product.key)
        product.image_url = old.image_url if old else ""
        product.image_approved = bool(old and old.image_url and old.image_approved)
    for _, shot in doc.all_shots():
        old = old_shots.get(shot.id)
        shot.keyframe_url = old.keyframe_url if old else ""
        shot.keyframe_approved = bool(old and old.keyframe_url and old.keyframe_approved)
    return doc


def summary_counts(story: Any) -> tuple[int, int]:
    """(scenes, shots) of a stored document without validating all of it."""
    scenes = _list(_dict(story).get("scenes"))
    return len(scenes), sum(len(_list(_dict(s).get("shots"))) for s in scenes)
