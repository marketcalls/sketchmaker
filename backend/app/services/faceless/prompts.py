"""Prompt building for stills, clips, thumbnails and character sheets.

Character consistency follows the story-telling lessons: the character's
likeness clause comes first, word for word, in every frame that shows the
character, and two or three reference images from different angles are sent
with it. Image prompts carry subject, action, setting, light and mood; the
house style is appended once; text, numbers, logos and signage are excluded
(on-screen text is drawn by the renderer, thumbnail text by Pillow).
"""

from __future__ import annotations

from . import catalog
from .scenes import shot_of

CAMERA_WORDS = {
    "pov": "first person point of view shot",
    "handheld": "handheld camera shot",
    "establishing": "wide establishing shot",
    "close_up": "close-up shot",
    "over_the_shoulder": "over the shoulder shot",
    "medium": "medium shot",
    "wide": "wide shot",
    "insert": "insert detail shot",
}
VARIATION_CAMERAS = ["medium shot", "close-up shot", "wide shot", "low angle shot"]


def likeness_clause(char) -> str:
    bible = getattr(char, "bible", None) or {}
    clause = (bible.get("likeness_clause") or "").strip()
    if clause:
        return clause
    description = (bible.get("canonical_description") or char.notes or "").strip()
    return f"{char.name}: {description}".strip(": ") if description else char.name


def _join(parts: list[str]) -> str:
    out = []
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        if p[-1] not in ".!?":
            p += "."
        out.append(p)
    return " ".join(out)


def _reference_note(groups: list[tuple[str, int]]) -> str:
    """'Images 1 to 2 show Mira. Image 3 shows Rook.' for the edit model inputs."""
    notes, n = [], 1
    for name, count in groups:
        if count <= 0:
            continue
        if count == 1:
            notes.append(f"Image {n} shows {name}")
        else:
            notes.append(f"Images {n} to {n + count - 1} show {name}")
        n += count
    if not notes:
        return ""
    return "Reference photos: " + "; ".join(notes) + ". Keep every character's face, hair, build and outfit consistent with their reference photos"


PRODUCT_CLAUSE = "Keep each product's label, shape and colour exactly as in its photo"


def still_prompt(scene: dict, chars: list, ref_groups: list[tuple[str, int]], style: str,
                 image_index: int = 0, image_count: int = 1, chained: bool = False,
                 products: bool = False) -> str:
    """``ref_groups`` labels the edit model inputs in order (products first,
    then characters). ``chained``: the stills are the first and last frames
    of a scene's clip parts, so they keep the camera and move the action on."""
    shot = shot_of(scene)
    clauses = [likeness_clause(c) for c in chars]
    base = (shot.get("visual_prompt") or "").strip() or (shot.get("direction") or "").strip()
    if not base:
        base = (scene.get("narration") or scene.get("beat_name") or "").strip()
    missing = [c for c in clauses if c and c not in base]
    camera = CAMERA_WORDS.get(shot.get("camera") or "medium", "medium shot")
    moment = ""
    if chained and image_index > 0:
        end_state = (shot.get("end_state") or "").strip()
        if image_index == image_count - 1 and end_state:
            moment = f"The same shot at the end of the action: {end_state}"
        else:
            moment = f"The same shot a moment later, the action {image_index} of {image_count - 1} of the way on"
    elif image_count > 1 and image_index > 0:
        camera = VARIATION_CAMERAS[image_index % len(VARIATION_CAMERAS)]
    parts = missing + [base, moment, f"Camera: {camera}"]
    if ref_groups:
        parts.append(_reference_note(ref_groups))
    if products:
        parts.append(PRODUCT_CLAUSE)
    if style:
        parts.append(f"Style: {style}")
    parts.append(catalog.NO_TEXT_CLAUSE)
    return _join(parts)


# Plain Faceless scenes have no camera move: the Ken Burns motion picks one.
_MOVE_FOR_MOTION = {"none": "static", "push_in": "push_in", "pull_out": "pull_out",
                    "pan_left": "pan_left", "pan_right": "pan_right"}


def camera_move(shot: dict) -> str:
    move = shot.get("camera_move")
    if move in catalog.CAMERA_MOVES:
        return move
    if shot.get("camera") == "handheld":
        return "handheld"
    return _MOVE_FOR_MOTION.get(shot.get("motion") or "", "static")


def _clip_body(scene: dict, style: str, register: str, *, seconds: float | None, part: int, parts: int,
               ends_on_frame: bool, hero_product: bool) -> list[str]:
    """Movement and tempo first, then framing, the action and its physics,
    the closing state, the look; narration is a separate track, so nobody
    speaks on screen."""
    shot = shot_of(scene)
    move = camera_move(shot)
    words = catalog.CAMERA_MOVES[move]
    if move not in ("static", "whip_pan", "rack_focus") and seconds:
        words += f" over {int(round(seconds))} seconds"
    direction = (shot.get("direction") or "").strip() or (shot.get("visual_prompt") or "").strip()
    if parts > 1 and part > 0:
        direction = f"The action continues: {direction}"
    camera = CAMERA_WORDS.get(shot.get("camera") or "medium", "medium shot")
    end_state = (shot.get("end_state") or "").strip()
    closing = ""
    if ends_on_frame:
        closing = "The shot ends exactly on the given last frame"
    elif end_state and part == parts - 1:
        closing = f"The shot ends on: {end_state}"
    look = catalog.REGISTER_WORDS.get((register or "").strip().lower(), "")
    return [
        words,
        camera[0].upper() + camera[1:],
        direction,
        "The product rests fixed in place, its label, shape and colour unchanged" if hero_product else "",
        "Movement has real weight and momentum; hair, cloth and objects react naturally",
        closing,
        f"Look: {style}" if style else "",
        look,
        "No one speaks, mouths closed",
        "No on-screen text",
    ]


def clip_prompt_image(scene: dict, style: str, part: int = 0, parts: int = 1, *, seconds: float | None = None,
                      register: str = "", ends_on_frame: bool = False, hero_product: bool = False) -> str:
    return _join(_clip_body(scene, style, register, seconds=seconds, part=part, parts=parts,
                            ends_on_frame=ends_on_frame, hero_product=hero_product))


def clip_prompt_reference(scene: dict, char_refs: list[tuple[str, int, int]], style: str,
                          has_start_image: bool, *, products: list[str] | None = None,
                          seconds: float | None = None, register: str = "", part: int = 0, parts: int = 1,
                          ends_on_frame: bool = False) -> str:
    """char_refs: (name, image count, video count) per character in order;
    ``products``: product names whose photos come before the characters."""
    notes, img, vid = [], 1, 1
    for name in products or []:
        notes.append(f"Image {img} is the product {name}")
        img += 1
    for name, images, videos in char_refs:
        if images == 1:
            notes.append(f"Image {img} is {name}")
        elif images > 1:
            notes.append(f"Images {img} to {img + images - 1} are {name}")
        img += images
        if videos:
            notes.append(f"Video {vid} shows how {name} moves")
            vid += videos
    parts_out = _clip_body(scene, style, register, seconds=seconds, part=part, parts=parts,
                           ends_on_frame=ends_on_frame, hero_product=False)
    head = notes + ["Keep each character consistent with their reference images"]
    if products:
        head.append(PRODUCT_CLAUSE)
    if has_start_image:
        # fal's reference-to-video takes image_url as the first frame (the
        # references keep the subjects consistent), so the promise holds.
        head.append("The video opens exactly on the given first frame")
    return _join([parts_out[0]] + head + parts_out[1:])


def thumbnail_prompt(base: str, chars: list, ref_groups: list[tuple[str, int]], style: str) -> str:
    clauses = [likeness_clause(c) for c in chars]
    missing = [c for c in clauses if c and c not in (base or "")]
    parts = missing + [
        base or "",
        "Thumbnail composition: one strong expressive subject, high contrast, sharp focus",
        "Leave the left third of the frame as clean, uncluttered background for a headline",
    ]
    if ref_groups:
        parts.append(_reference_note(ref_groups))
    if style:
        parts.append(f"Style: {style}")
    parts.append(catalog.NO_TEXT_CLAUSE)
    return _join(parts)


def sheet_prompt(char, ref_count: int, style: str) -> str:
    return _join([
        likeness_clause(char),
        f"Character reference sheet of {char.name}: front view, three quarter view, side profile and a full "
        "body view side by side, neutral pose, the same outfit in every view",
        "Plain light grey studio background, soft even light",
        _reference_note([(char.name, ref_count)]),
        f"Style: {style}" if style else "",
        catalog.NO_TEXT_CLAUSE,
    ])
