"""Plain-sentence prompts for the image edit models (Magix and Virtual Try-On).

Edit models follow written instructions, not indented JSON with lists of
options: a list such as background ["pure white", "neutral gray", "subtle
gradient"] leaves the choice to chance, and quality filler spends attention.
So every field here holds one choice, and the prompt reads as sentences:
what to make, what to keep exactly, one job per reference image, then the
setting, pose, light and camera.

A targeted edit drops the mode template entirely: "Change only X to Y. Keep
A, B, C exactly." The keep list is written out again on every iteration,
because anything an edit prompt does not name is open to change.

Every reference image gets exactly one job and a line saying what not to
take from it (scenario-multi-reference); an unassigned reference lends
everything it shows.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Reference image roles
# ---------------------------------------------------------------------------

# role: (label, what the image lends, what not to take from it; {n} is the
# image number)
IMAGE_ROLES: dict[str, tuple[str, str, str]] = {
    "subject": (
        "a person", "Include this person with their face, hair, skin tone and build exactly as shown",
        "Do not take the background, light or colour grade of image {n}",
    ),
    "scene": (
        "the setting", "Use this place as the setting: its architecture, objects and layout",
        "Do not take any person from image {n}",
    ),
    "style": (
        "the look", "Copy its photographic look only: colour grade, contrast, grain and light quality",
        "Do not take the people, objects, clothing or setting of image {n}",
    ),
    "outfit": (
        "the outfit", "Dress the main person in this outfit, keeping its garments, colours, pattern, fabric and cut",
        "Do not copy the face, body, pose or background of anyone in image {n}",
    ),
    "product": (
        "a product", "Include this exact product with its shape, proportions, colours and label unchanged",
        "Do not take the background, props or surface of image {n}",
    ),
    "light": (
        "the light", "Match its lighting only: the direction, softness and colour of the light",
        "Do not take the people, objects or setting of image {n}",
    ),
}
DEFAULT_EXTRA_ROLE = "subject"


def clean_role(role: str | None, fallback: str = DEFAULT_EXTRA_ROLE) -> str:
    return role if role in IMAGE_ROLES else fallback


def reference_lines(roles: list[str]) -> list[str]:
    """One line per image after the first: "Image N (what it shows) = JOB only."

    Image 1 is always the photo being edited and is described by the task
    sentence, so it gets no line here.
    """
    lines = []
    for index, role in enumerate(roles[1:], start=2):
        label, lends, avoid = IMAGE_ROLES[clean_role(role)]
        lines.append(f"Image {index} ({label}) = {clean_role(role).upper()} only. {lends}. {avoid.format(n=index)}.")
    return lines


# ---------------------------------------------------------------------------
# Magix modes: one choice per field
# ---------------------------------------------------------------------------

PORTRAIT_KEEP = (
    "Keep their face exactly as it is: face shape, eyes, nose, mouth, brows, skin tone, skin texture and natural "
    "marks, so they are immediately recognisable."
)
PHOTO_FINISH = (
    "It must look like a real photograph: natural skin texture with pores, individual strands of hair, true fabric "
    "weave."
)

CORPORATE_BACKGROUNDS = {
    "neutral_gray": "a plain neutral grey backdrop",
    "clean_white": "a clean white backdrop",
    "soft_gradient": "a soft light grey gradient backdrop",
    "office_blur": "a softly blurred modern office",
    "outdoor_blur": "a softly blurred outdoor setting with trees",
}
DATING_VIBES = {
    "confident_authentic": "confident and genuinely themselves",
    "playful_fun": "playful and fun-loving",
    "warm_approachable": "warm and approachable",
    "adventurous": "adventurous",
    "sophisticated": "sophisticated and classy",
    "casual_relaxed": "casual and relaxed",
}
FOUNDER_VIBES = {
    "visionary": "forward-looking and calm",
    "approachable_ceo": "warm and accessible",
    "tech_innovator": "modern and technically credible",
    "disruptor": "bold and direct",
    "thought_leader": "thoughtful and authoritative",
    "creative_founder": "creative and open",
}
INFLUENCER_AESTHETICS = {
    "glamorous": ("polished and glamorous", "soft, flattering beauty light"),
    "natural_beauty": ("natural and relatable", "soft daylight from a window"),
    "golden_hour": ("warm and dreamy", "low golden-hour sun from behind, with a soft fill on the face"),
    "urban_chic": ("trendy street style", "open shade on a city street"),
    "soft_dreamy": ("soft and romantic", "diffused, low-contrast light"),
    "vibrant_bold": ("energetic and bold", "bright, crisp daylight"),
}
AVATAR_STYLES = {
    "semi_realistic": "a painterly, semi-realistic digital painting",
    "3d_pixar": "a 3D animated feature film character",
    "anime": "a Japanese anime illustration",
    "comic_book": "a comic book illustration with inked lines and flat colour",
    "digital_art": "a contemporary digital painting",
    "fantasy": "a fantasy character painting",
}
PRODUCT_SURFACES = {
    "white_seamless": "a seamless white sweep",
    "marble": "a white marble counter",
    "wood": "a warm oak tabletop",
    "concrete": "a smooth grey concrete slab",
    "linen": "a natural linen cloth",
    "slate": "a dark wet slate surface",
}
DEFAULT_PRODUCT_SURFACE = "white_seamless"

# mode: kind, task, setting, pose, light, camera, mood, extra sentence
_M = dict
MAGIX_MODES: dict[str, dict] = {
    "studio_portrait": _M(
        task="a professional studio portrait", setting="a seamless pure white studio backdrop",
        pose="head and shoulders, shoulders slightly angled, chin forward and down",
        light="a large softbox at 45 degrees to one side, a soft fill from the other side and a subtle hair light "
              "from behind",
        camera="eye level, an 85mm portrait lens, focus on the eyes", mood="confident and approachable"),
    "cinematic": _M(
        task="a still from a feature film", setting="a cinematic location with a little atmospheric haze",
        pose="a story-suggesting position, caught mid-thought",
        light="one motivated source in the scene falling in from the side in a Rembrandt pattern",
        camera="a 50mm lens at f/2, the background in soft focus",
        mood="contemplative and dramatic", extra="Teal and orange colour grade."),
    "corporate_headshot": _M(
        task="a corporate headshot", setting=CORPORATE_BACKGROUNDS["neutral_gray"],
        pose="head and shoulders facing the camera, a genuine slight smile, neat grooming",
        light="a soft key light at 35 degrees with gentle fill", camera="eye level, an 85mm portrait lens",
        mood="professional and trustworthy"),
    "fashion_editorial": _M(
        task="a high-fashion editorial photograph", setting="a bare studio with a deep grey paper backdrop",
        pose="an editorial pose with strong body lines", light="a beauty dish above and in front, hard and sculpting",
        camera="an 85mm lens at a slightly low angle", mood="bold and confident"),
    "dating": _M(
        task="a dating profile photo", setting="a relaxed outdoor terrace with soft greenery behind",
        pose="natural and relaxed, a genuine warm smile, looking just past the camera",
        light="warm late-afternoon sun from the side", camera="eye level, a 50mm lens at f/2",
        mood=DATING_VIBES["confident_authentic"]),
    "founder_headshot": _M(
        task="a startup founder headshot", setting="a simple dark charcoal backdrop",
        pose="head and shoulders, a calm and direct look into the lens", light="a soft key light from the left with a "
        "gentle rim light", camera="eye level, an 85mm portrait lens", mood=FOUNDER_VIBES["visionary"]),
    "influencer": _M(
        task="a social media portrait", setting="a bright, styled interior",
        pose="natural yet photogenic, engaging the camera", light=INFLUENCER_AESTHETICS["glamorous"][1],
        camera="a 35mm lens at eye level", mood=INFLUENCER_AESTHETICS["glamorous"][0]),
    "street_portrait": _M(
        task="a street portrait", setting="a city street with textured walls and shop fronts",
        pose="relaxed, connected to the street, an authentic expression",
        light="golden-hour light down the street", camera="a 35mm lens at eye level", mood="raw and energetic"),
    "environmental": _M(
        task="an environmental portrait", setting="a real place that says something about who they are",
        pose="natural, at ease in the space", light="window light from one side",
        camera="a 35mm lens, medium-wide, showing the surroundings", mood="genuine"),
    "lifestyle": _M(
        task="a candid lifestyle portrait", setting="a calm, uncluttered cafe interior",
        pose="relaxed, mid-moment, a natural smile", light="soft window light from the side",
        camera="a 50mm lens at eye level", mood="warm and relaxed"),
    "low_key": _M(
        task="a dramatic low-key portrait", setting="a pure black background",
        pose="emerging from the shadow, a still, intense expression", light="a single hard light from the side, "
        "most of the frame in deep shadow", camera="an 85mm lens", mood="mysterious and powerful"),
    "high_key": _M(
        task="a bright high-key portrait", setting="a pure white background with no shadows",
        pose="fresh and open, a light smile", light="several large soft sources wrapping around, shadows lifted",
        camera="eye level, an 85mm lens", mood="fresh and optimistic"),
    "black_white": _M(
        task="a black and white portrait", setting="a plain mid-grey backdrop", pose="a quiet, emotionally "
        "present expression", light="soft side light that models the face", camera="an 85mm lens",
        mood="timeless", extra="Monochrome, with deep blacks, bright whites and smooth midtones."),
    "beauty_closeup": _M(
        task="a beauty close-up", setting="a soft neutral backdrop", pose="the face filling the frame",
        light="butterfly light from a beauty dish above the camera", camera="a 100mm macro lens, extreme close-up",
        mood="polished and luminous"),
    "athletic": _M(
        task="an athletic portrait", setting="a dark training space", pose="a powerful stance, focused and determined",
        light="hard directional light from the side that sculpts the muscles", camera="a 70mm lens from a low angle",
        mood="powerful and focused"),
    "creative_color": _M(
        task="a creative colour portrait", setting="a dark studio", pose="an edgy, confident expression",
        light="cyan gel light from the left and red gel light from the right", camera="an 85mm lens",
        mood="artistic and contemporary"),
    "vintage_retro": _M(
        task="a 1970s film portrait", setting="a warm wood-panelled room", pose="relaxed, a soft expression",
        light="warm tungsten lamp light from the side", camera="a 50mm lens", mood="nostalgic and warm",
        extra="Warm film tones, lifted blacks and fine organic grain."),
    "minimalist": _M(
        task="a minimalist portrait", setting="a plain soft grey wall with generous empty space around them",
        pose="simple and elegant", light="a single soft source from the side", camera="an 85mm lens",
        mood="calm and serene"),
    "cultural": _M(
        task="a cultural heritage portrait", setting="a setting that suits traditional dress",
        pose="dignified and proud, in traditional clothing, textiles and jewellery", light="soft light that shows "
        "the textiles", camera="an 85mm lens, medium shot showing the attire", mood="celebratory and dignified"),
    "conceptual": _M(
        task="a conceptual fine-art portrait", setting="a surreal setting with one symbolic prop",
        pose="interacting with the symbolic prop", light="soft, directional light from one side",
        camera="a 50mm lens", mood="dreamlike"),
    "luxury": _M(
        task="a luxury portrait", setting="a clean, dark backdrop with a hint of gold",
        pose="confident and composed, in refined attire", light="rich, soft key light with a gentle rim",
        camera="an 85mm lens", mood="sophisticated and elegant"),
    "avatar": _M(kind="avatar", medium=AVATAR_STYLES["semi_realistic"]),
    "restoration": _M(kind="restoration"),
    "product": _M(
        kind="product", setting=PRODUCT_SURFACES[DEFAULT_PRODUCT_SURFACE],
        light="soft window light from the left, with a soft contact shadow falling to the right",
        camera="a 100mm lens at the product's height, the whole product sharp", mood="clean and premium"),
}


def _clean(value) -> str:
    """One line of text, or "" for empty and placeholder values."""
    if not isinstance(value, str):
        return ""
    text = re.sub(r"\s+", " ", value).strip().strip(".")
    if text.upper().replace(" ", "_") in {"NULL", "NONE", "PRESERVE_ORIGINAL", "PRESERVE", "KEEP_ORIGINAL", "N/A"}:
        return ""
    return text


def mode_spec(mode: str, mode_options: dict | None = None) -> dict:
    """The mode's single choices with the user's options applied."""
    spec = dict(MAGIX_MODES.get(mode) or MAGIX_MODES["studio_portrait"])
    spec.setdefault("kind", "portrait")
    opts = mode_options or {}
    if mode == "corporate_headshot" and opts.get("background") in CORPORATE_BACKGROUNDS:
        spec["setting"] = CORPORATE_BACKGROUNDS[opts["background"]]
    elif mode == "dating" and opts.get("dating_vibe") in DATING_VIBES:
        spec["mood"] = DATING_VIBES[opts["dating_vibe"]]
    elif mode == "founder_headshot" and opts.get("vibe") in FOUNDER_VIBES:
        spec["mood"] = FOUNDER_VIBES[opts["vibe"]]
    elif mode == "influencer" and opts.get("aesthetic") in INFLUENCER_AESTHETICS:
        spec["mood"], spec["light"] = INFLUENCER_AESTHETICS[opts["aesthetic"]]
    elif mode == "avatar" and opts.get("style") in AVATAR_STYLES:
        spec["medium"] = AVATAR_STYLES[opts["style"]]
    elif mode == "product":
        spec["setting"] = PRODUCT_SURFACES.get(opts.get("surface"), spec["setting"])
        spec["label"] = _clean(opts.get("label_text")).replace('"', "'")[:120]
    return spec


def _task_and_keep(spec: dict) -> list[str]:
    kind = spec["kind"]
    if kind == "product":
        keep = ("Keep the product exactly: its shape, proportions, colours, materials and every mark on it, adding "
                "and removing nothing.")
        if spec.get("label"):
            keep += f' The label reads "{spec["label"]}", spelled exactly, and appears once; no other text.'
        return ["Make a product photograph of the exact product in image 1.", keep]
    if kind == "avatar":
        return [f"Turn the person in image 1 into {spec['medium']} avatar portrait.",
                "Keep them recognisable: the same face shape, features, hair and skin tone, carried into the style."]
    if kind == "restoration":
        return ["Restore the photo in image 1.",
                "Keep the people, the composition and the character of the original exactly; repair only damage, "
                "scratches, noise, blur and colour casts, with natural skin texture kept."]
    return [f"Turn the photo of the person in image 1 into {spec['task']}.", PORTRAIT_KEEP]


def _scene_lines(spec: dict) -> list[str]:
    kind = spec["kind"]
    if kind == "restoration":
        return []
    if kind == "avatar":
        return ["Head and shoulders, facing the viewer, on a simple background that suits the style."]
    lines = []
    if kind == "product":
        lines.append(f"The product stands on {spec['setting']}.")
    elif spec.get("setting"):
        lines.append(f"Setting: {spec['setting']}.")
    if spec.get("pose"):
        lines.append(f"Pose: {spec['pose']}.")
    if spec.get("light"):
        lines.append(f"Light: {spec['light']}.")
    if spec.get("camera"):
        lines.append(f"Camera: {spec['camera']}.")
    if spec.get("mood"):
        lines.append(f"Mood: {spec['mood']}.")
    if spec.get("extra"):
        lines.append(spec["extra"])
    if kind == "product":
        lines.append("It must look like a real product photograph: true materials, crisp edges and a natural "
                     "shadow where it touches the surface.")
    else:
        lines.append(PHOTO_FINISH)
    return lines


def _user_line(prompt: str | None) -> str:
    text = _clean(prompt)
    # The page sends "Apply <mode> style" when the user typed nothing.
    if not text or re.fullmatch(r"apply [a-z0-9 _&-]+ style", text, re.IGNORECASE):
        return ""
    return f"Also: {text}."


def build_magix_prompt(mode: str, prompt: str | None, mode_options: dict | None = None,
                       image_roles: list[str] | None = None) -> str:
    """The mode applied to image 1, as sentences."""
    spec = mode_spec(mode, mode_options)
    lines = _task_and_keep(spec)
    lines += reference_lines(image_roles or [])
    lines += _scene_lines(spec)
    user = _user_line(prompt)
    if user:
        lines.append(user)
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Magix with the parsed intent (litellm_client.enhance_magix_prompt)
# ---------------------------------------------------------------------------

def _keep_list(spec: dict, preserve) -> list[str]:
    if spec["kind"] == "product":
        core = ["the product's shape, proportions, colours, materials and label"]
    else:
        core = ["the face and identity", "skin tone", "body shape"]
    items = list(core)
    seen = {c.lower() for c in core}
    for item in preserve if isinstance(preserve, list) else []:
        text = _clean(item)
        low = text.lower()
        # The parser's own schema hints sometimes come back as items.
        if not text or len(text) > 80 or "always include" in low or "everything" in low or low in seen:
            continue
        if spec["kind"] != "product" and low in {"face", "identity", "facial features", "body shape", "skin tone"}:
            continue
        seen.add(low)
        items.append(text)
    for default in ("the pose", "the expression", "the hair", "the clothing", "the background", "the lighting",
                    "the framing", "the colours"):
        if len(items) >= 12:
            break
        bare = default[4:]
        if not any(bare in i.lower() for i in items):
            items.append(default)
    return items


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _changes(user_intent: dict) -> list[tuple[str, str]]:
    changes = user_intent.get("specific_changes") or []
    if isinstance(changes, dict):
        changes = [changes]
    out = []
    for change in changes if isinstance(changes, list) else []:
        if not isinstance(change, dict):
            continue
        what, to = _clean(change.get("what_to_change")), _clean(change.get("change_to"))
        if what and to:
            out.append((what, to))
    return out


def magix_prompt_from_intent(user_intent: dict, mode: str, prompt: str | None = None,
                             mode_options: dict | None = None, image_roles: list[str] | None = None) -> str:
    """Sentences from the parsed intent.

    A targeted edit drops the mode template: "Change only X to Y. Keep A, B,
    C exactly." Scene changes and style applications keep the mode's choices
    and override the fields the user asked about.
    """
    spec = mode_spec(mode, mode_options)
    keep = _keep_list(spec, user_intent.get("preserve_from_original"))
    changes = _changes(user_intent)
    refs = reference_lines(image_roles or [])

    if user_intent.get("edit_type") == "targeted_edit" and changes:
        if len(changes) == 1:
            change = f"Change only {changes[0][0]} in image 1: make it {changes[0][1]}."
        else:
            change = "Change only these in image 1: " + "; ".join(f"{w} to {t}" for w, t in changes) + "."
        changed = {w.lower() for w, _ in changes}
        kept = [k for k in keep if not any(w in k.lower() or k.lower().removeprefix("the ") in w for w in changed)]
        lines = [change, f"Keep everything else exactly as it is in image 1: {_join(kept)}.", *refs]
        return " ".join(lines)

    lines = _task_and_keep(spec)
    lines += refs
    scene = user_intent.get("scene_override") or {}
    location = _clean(scene.get("location"))
    if location and spec["kind"] not in ("avatar", "restoration"):
        place = location
        for key, suffix in (("environment", " setting"), ("time_of_day", ""), ("weather", " weather")):
            extra = _clean(scene.get(key))
            if extra:
                place += f", {extra}{suffix}"
        spec["setting"] = place
    direction = user_intent.get("subject_direction") or {}
    pose = ", ".join(x for x in (_clean(direction.get("pose")), _clean(direction.get("expression")),
                                 _clean(direction.get("action"))) if x)
    if pose and spec["kind"] == "portrait":
        spec["pose"] = pose
    framing = user_intent.get("framing_override") or {}
    shot = _clean(framing.get("shot_type"))
    if shot and spec.get("camera"):
        spec["camera"] = f"{shot}, {spec['camera']}"
    lines += _scene_lines(spec)
    for key, value in (user_intent.get("appearance_changes") or {}).items():
        text = _clean(value)
        if text:
            lines.append(f"Change the {key.replace('_', ' ')}: {text}.")
    for what, to in changes:
        lines.append(f"Change {what} to {to}.")
    for item in user_intent.get("additional_requirements") or []:
        line = _user_line(item)
        if line:
            lines.append(line)
    if not (user_intent.get("additional_requirements") or changes):
        user = _user_line(prompt)
        if user:
            lines.append(user)
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Virtual Try-On
# ---------------------------------------------------------------------------

# mode: (setting, light, mood)
TRYON_MODES: dict[str, tuple[str, str, str]] = {
    "natural": ("a clean, plain light grey background", "soft natural light from the front", "casual and comfortable"),
    "professional": ("a clean neutral grey studio backdrop", "classic three-point studio light", "polished and confident"),
    "glamour": ("a soft gradient studio backdrop", "soft beauty light with gentle highlights", "glamorous and elegant"),
    "outdoor_day": ("a sunny park with soft greenery behind", "warm afternoon sunlight from the side", "fresh and relaxed"),
    "evening": ("an elegant evening venue with warm lights blurred behind", "warm, low indoor light",
                "elegant and refined"),
    "urban": ("a modern city street", "natural street light in open shade", "trendy and cool"),
    "nature": ("a forest path", "dappled sunlight through the trees", "peaceful and natural"),
    "party": ("a festive party venue with coloured lights blurred behind", "lively, colourful party light",
              "fun and celebratory"),
    "athletic": ("a bright gym", "bright, clean light", "active and motivated"),
    "romantic": ("a softly blurred setting at sunset", "warm, diffused sunset light", "romantic and dreamy"),
}

TRYON_REFERENCES = (
    "Image 1 is the person. Image 2 = GARMENT only: dress the person in image 1 in this outfit, keeping its colours, "
    "pattern, fabric and cut."
)


def build_tryon_prompt(mode: str, user_prompt: str | None, use_dress_background: bool = False,
                       user_intent: dict | None = None) -> str:
    """The try-on as sentences, with the parsed intent applied when given."""
    setting, light, mood = TRYON_MODES.get(mode) or TRYON_MODES["natural"]
    intent = user_intent or {}
    pose = "the same pose as in image 1"
    lines = [TRYON_REFERENCES]
    if use_dress_background:
        lines.append("Do not copy the face, body or pose of anyone in image 2; place the person in front of the "
                     "background of image 2.")
    else:
        lines.append("Do not copy the face, body, pose or background of anyone in image 2.")
    lines.append("Keep the person's face, identity, skin tone, hair and body proportions exactly as in image 1.")

    scene = intent.get("scene_override") or {}
    location = _clean(scene.get("location"))
    if location and not use_dress_background:
        setting = location
        for key in ("environment", "time_of_day", "weather"):
            extra = _clean(scene.get(key))
            if extra:
                setting += f", {extra}"
    direction = intent.get("pose_direction") or {}
    pose_parts = [_clean(direction.get(k)) for k in ("body_pose", "body_angle", "arm_position", "action")]
    if any(pose_parts):
        pose = ", ".join(p for p in pose_parts if p)
    fit = intent.get("garment_fit") or {}
    fit_text = ", ".join(x for x in (_clean(fit.get("fit_style")), _clean(fit.get("drape")),
                                     _clean(fit.get("adjustments"))) if x)
    lines.append(f"The garment fits their body naturally{', ' + fit_text if fit_text else ''}, with real folds "
                 "and drape where it bends.")
    if not use_dress_background:
        lines.append(f"Setting: {setting}.")
    atmosphere = intent.get("atmosphere_override") or {}
    light = _clean(atmosphere.get("lighting_feel")) or light
    mood = _clean(atmosphere.get("mood")) or mood
    lines += [f"Pose: {pose}.", f"Light: {light}.", f"Mood: {mood}."]
    tone = _clean(atmosphere.get("color_tone"))
    if tone:
        lines.append(f"Colour: {tone}.")
    styling = intent.get("styling_additions") or {}
    for key in ("accessories", "shoes", "styling_notes"):
        text = _clean(styling.get(key))
        if text:
            lines.append(f"Add {text}." if key != "styling_notes" else f"Styling: {text}.")
    extras = [t for t in (_clean(x) for x in intent.get("additional_requirements") or []) if t]
    for text in extras:
        lines.append(f"Also: {text}.")
    if not extras:
        user = _user_line(user_prompt)
        if user:
            lines.append(user)
    lines.append("It must look like a real photograph: true fabric texture, natural skin and believable light on "
                 "the garment.")
    return " ".join(lines)
