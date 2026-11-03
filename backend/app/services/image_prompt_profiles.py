"""What Magic Prompt (/generate) needs to know about the image it writes for.

The enhancer (app/clients/litellm_client.generate_prompt_for_image) is told
which model will render the prompt, the frame it renders into and, when the
user picked one, what the image is for, because a good prompt differs
between them: a small distilled model wants a short, plain brief; a
typography model wants every word of text quoted with its placement; a tall
9:16 frame wants a vertical composition with the key content clear of the
story and reel overlays.

clean_output() strips what language models wrap around a prompt (lead-ins,
quotes, headings, code fences), which image models would otherwise render
or be confused by. parse_directions() reads the several prompts a
"Directions" request asks for.
"""

from __future__ import annotations

import json
import re

# model id: (label, (min words, max words), notes for the prompt writer)
MODEL_PROFILES: dict[str, tuple[str, tuple[int, int], str]] = {
    "openai/gpt-image-2.5/sunburst/text-to-image": (
        "GPT Image 2.5",
        (80, 220),
        "Follows exact instructions and renders text cleanly, but past about seven distinct requirements some "
        "quietly drop: keep to about seven, the most important first. A detailed brief from the user is "
        "normalised, not embellished: refine it, and expand only a short, generic idea. Never add characters, "
        "brands, slogans or left and right placement the user did not imply. State the counts and positions "
        "the user gave explicitly.",
    ),
    "blackforestlabs/flux-3/text-to-image": (
        "FLUX 3",
        (80, 220),
        "Rewards concrete physical description in natural sentences. Put the subject and the single most "
        "important visual idea in the first sentence; detail that comes late gets less weight.",
    ),
    "blackforestlabs/flux-3/klein/text-to-image": (
        "FLUX 3 Klein",
        (50, 120),
        "A small, fast model: one clear subject, one light source, a simple setting. Short, plain sentences. "
        "Stacked secondary details get muddled, so keep only the ones that matter most.",
    ),
    "google/nano-banana-2.1": (
        "Nano Banana 2.1",
        (80, 220),
        "Understands scenes the way a photographer's brief describes them and handles text well. Write it as a "
        "clear brief: subject, action, setting, light, camera. Quote any wording exactly as it must read and "
        "say where each block sits.",
    ),
    "ideogram/v4.5": (
        "Ideogram 4.5",
        (60, 180),
        "A design and typography specialist: posters, covers, social graphics, logos, packaging. Quote every word "
        "that must appear, exactly, and say where it sits, how large it is relative to the rest, and the lettering "
        "(for example bold condensed sans serif, hand-painted script). Make the hierarchy visible through size, "
        "weight and position: the largest element, what sits beneath it, the small details. It cannot render a "
        "transparent background: when the user asks for one, describe a plain, even background in one solid "
        "colour instead.",
    ),
    "microsoft/mai-image-2.5": (
        "MAI Image 2.5",
        (80, 200),
        "Strong at photographic realism and at typography, its family trait: when the user wants words, quote "
        "them and give each block a role, a style and a place. Steering is positive only, so describe what is "
        "there rather than what is not. Lean on natural light, true materials and believable skin; avoid "
        "anything that pushes it towards a rendered or plastic look.",
    ),
    "xai/grok-imagine-image/v2.0/text-to-image": (
        "Grok Imagine 2.0",
        (30, 80),
        "Wants a short, concrete, literal brief: subject, setting, composition, light, finish, in one aesthetic. "
        "Quality adjectives and negatives are ignored, so state positives ('a clean empty background', not "
        "'no clutter'). Give each quoted string a role ('the title reads ...'). Small type blurs at the size "
        "this renders, so keep any words large and few.",
    ),
    "fal-ai/z-image/turbo/lora": (
        "Z-Image Turbo",
        (40, 90),
        "A fast distilled model: short, direct sentences, one subject, the essential setting and light only. "
        "If a LoRA is loaded, keep any trigger word, character name or style token the user wrote, spelled "
        "exactly, near the start.",
    ),
    "bytedance/seedream/v5/pro/text-to-image": (
        "Seedream 5 Pro",
        (100, 280),
        "Handles long, layered prompts with several elements. Give each element its own sentence with its "
        "position in the frame. Its letters are drawn, not typeset: keep in-image text to a few short strings "
        "at one or two sizes; paragraphs and many small labels turn into shapes.",
    ),
}
DEFAULT_PROFILE = ("the image model", (100, 250), "")

# How a prompt that carries words should end, per model. Grok invents extra
# labels unless told "no other text"; the others answer to the longer form.
TEXT_CLOSING = {"xai/grok-imagine-image/v2.0/text-to-image": "no other text"}
DEFAULT_TEXT_CLOSING = "no extra words, no duplicate text"


def text_closing(model: str | None) -> str:
    return TEXT_CLOSING.get(model or "", DEFAULT_TEXT_CLOSING)


def model_brief(model: str | None, lora: bool = False) -> str:
    """Lines telling the prompt writer which model renders the prompt."""
    label, (low, high), notes = MODEL_PROFILES.get(model or "", DEFAULT_PROFILE)
    lines = [f"Target model: {label}. Write {low} to {high} words."]
    if notes:
        lines.append(notes)
    lines.append(f'If the image carries words, end the prompt with "{text_closing(model)}".')
    if lora and model == "fal-ai/z-image/turbo/lora":
        lines.append("A LoRA is loaded for this generation.")
    return "\n".join(lines)


def _ratio(aspect_ratio: str | None) -> float | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*", aspect_ratio or "")
    if not match:
        return None
    w, h = float(match.group(1)), float(match.group(2))
    return w / h if w > 0 and h > 0 else None


def frame_brief(aspect_ratio: str | None) -> str:
    """How to compose for the frame the image renders into."""
    ratio = _ratio(aspect_ratio)
    if ratio is None:
        return ""
    label = aspect_ratio.strip()
    if ratio >= 1.9:
        # Very wide frames otherwise come back with black bars top and bottom.
        return (f"Frame: {label}, very wide. Compose horizontally like a cinema still or banner: the subject on one "
                "third, depth and context running across the frame, and a calm area on the other side. Say in the "
                "prompt that the image fills the frame edge to edge with no letterboxing.")
    if ratio >= 1.3:
        return (f"Frame: {label}, landscape. Place the subject on a third rather than dead centre and use the width "
                "for setting; if the image may carry text, keep one side quieter.")
    if ratio > 1.05:
        return f"Frame: {label}, gently landscape. A balanced composition with the subject slightly off centre."
    if ratio >= 0.95:
        return (f"Frame: {label}, square. A centred or symmetrical composition reads best; the subject should fill "
                "roughly half to two thirds of the frame.")
    if ratio >= 0.7:
        return (f"Frame: {label}, portrait. Compose vertically: the subject's full height or a head and shoulders "
                "crop, with headroom above.")
    # The 9:16 safe zone (story, reel and TikTok overlays), the same band
    # services/motion_graphics/design.py SAFE_ZONES composes video to.
    return (f"Frame: {label}, tall. Compose vertically, stacking the subject and setting from top to bottom. App "
            "buttons and captions cover the edges, so keep faces, words and key details inside the central band: "
            "clear of the top 14 percent and the bottom 35 percent, and in from each side by about a tenth.")


# Platform formats for the "Use for" picker on /generate
# (scenario-formats placement specs). id: (label, aspect ratio, exact export
# pixels or None, brief for the prompt writer). The export size is applied
# with Pillow by GET /generate/export/{image_id}; the image itself renders at
# the model's own size for the ratio.
PURPOSES: dict[str, tuple[str, str, tuple[int, int] | None, str]] = {
    "instagram_post": (
        "Instagram post", "4:5", None,
        "An Instagram feed post. The profile grid crops it toward a square, so keep the subject and any words "
        "centred, clear of the top and bottom tenth. The subject is unmistakable at a glance, with one dominant "
        "colour relationship.",
    ),
    "story_reel": (
        "Story or Reel", "9:16", None,
        "A story or reel cover. The subject and any words sit in the central band; the edges stay simple "
        "background.",
    ),
    "youtube_thumbnail": (
        "YouTube thumbnail", "16:9", (1280, 720),
        "A YouTube thumbnail, judged at a tenth of its size: one large, well lit subject, strong separation from "
        "a simpler background, and the bottom right corner kept clear, where the duration badge sits.",
    ),
    "pinterest": (
        "Pinterest pin", "2:3", None,
        "A Pinterest pin: a tall image that reads from top to bottom, the subject large, any words big enough "
        "to read in a narrow feed column.",
    ),
    "linkedin": (
        "LinkedIn post", "16:9", (1200, 627),
        "A LinkedIn feed image, cropped to 1.91:1 from this frame: keep the subject and any words away from the "
        "top and bottom twentieth, which the crop removes. Clean and professional.",
    ),
}


def purpose_brief(purpose: str | None) -> str:
    entry = PURPOSES.get(purpose or "")
    return f"Use: {entry[3]}" if entry else ""


def avoid_brief(avoid: str | None) -> str:
    """The negative-prompt text, turned into an instruction for positive wording.

    None of the /generate models takes a negative prompt, and naming a thing
    invites it, so the writer describes what is there instead.
    """
    text = re.sub(r"\s+", " ", (avoid or "")).strip()[:500]
    if not text:
        return ""
    return (f"The user wants to keep these out of the image: {text}. Do not name them in the prompt; describe "
            "what is there instead (for example 'an empty street' rather than 'no people').")


_QUOTED = re.compile(r'["“”«»][^"“”«»\n]{1,200}["“”«»]')


def has_quoted_text(prompt: str | None) -> bool:
    """True when the prompt carries quoted wording meant to appear in the image."""
    return bool(_QUOTED.search(prompt or ""))


_LEAD_IN = re.compile(
    r"^\s*(?:sure[,!.]?\s*)?(?:here(?:'s| is)\b[^\n:]*[:.]|(?:enhanced |image |final )?prompt\s*:)\s*",
    re.IGNORECASE,
)


def clean_output(text: str) -> str:
    """The prompt alone: no code fences, headings, lead-in or wrapping quotes."""
    out = (text or "").strip()
    out = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", out).strip()
    out = _LEAD_IN.sub("", out, count=1).strip()
    out = "\n".join(line for line in out.splitlines() if not re.match(r"^\s*#{1,6}\s", line)).strip()
    out = re.sub(r"^\*\*(.+?)\*\*$", r"\1", out, flags=re.MULTILINE)
    # Only a single wrapping pair: a prompt can open and close with quoted
    # on-image text ("SALE" ... "50% OFF"), which must stay.
    if len(out) >= 2 and out[0] == out[-1] and out[0] in "\"'" and out.count(out[0]) == 2:
        out = out[1:-1].strip()
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


DIRECTIONS_MIN = 2
DIRECTIONS_MAX = 4


def directions_brief(count: int) -> str:
    """The extra instruction for a Directions request: several prompts that
    differ along one named axis instead of one prompt repeated."""
    return (
        f"## Directions\nWrite {count} prompts instead of one. Choose one axis the request leaves open (for "
        "example the light, the vantage point, the medium, the moment, the setting) and name it. Every prompt "
        "keeps everything the user asked for and differs from the others only along that axis, at clearly "
        "different positions on it. Each prompt follows every rule above and stands on its own.\n"
        'Reply with JSON only, no code fence: {"axis": "<the axis in a few words>", "prompts": ["...", "..."]}'
    )


def parse_directions(text: str, count: int) -> tuple[str, list[str]] | None:
    """(axis, prompts) from a Directions reply, or None when it is unusable."""
    raw = (text or "").strip()
    raw = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    prompts = [clean_output(p) for p in data.get("prompts") or [] if isinstance(p, str) and p.strip()]
    prompts = [p for p in prompts if p][:count]
    if len(prompts) < min(count, DIRECTIONS_MIN):
        return None
    axis = data.get("axis") if isinstance(data.get("axis"), str) else ""
    return re.sub(r"\s+", " ", axis).strip()[:80], prompts
