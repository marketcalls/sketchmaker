"""Quality checks: one vision read of a finished output against its brief.

A check sends the output (an image, or three frames of a clip) and its
references to the default LLM (APISettings, through
storyscript.llm.complete_json) with a numbered rubric, and stores a verdict:

    {verdict: "pass" | "warn" | "fail" | "unverified",
     lines: [{id, text, verdict, evidence}],
     defects: [{region, kind, severity, fix_instruction}],
     reasons: [sentences for people], model, checked_at, content_hash, kind}

The model only answers each line (pass, fail or unclear), transcribes the
lettering it sees and lists defects with a severity. The overall verdict is
computed here from those answers (compute_verdict), never taken from a model
score, and quoted text is compared in code with a normalised edit distance.
Lettering too small to read is "unverified", never a pass.

Checks are opt-in. The "qa:vision-check" key is the estimate shown next to the
toggle that asks for one; the spend itself is an LLM call, logged by litellm_client
into llm_usage. A check can come back "unverified" (no vision on the configured
model, the call failed, or the picture could not be judged). Nothing here
regenerates anything: a failed check is a badge with reasons, and the fix is an
action the user starts.

Rubric lines (scenario-refine-loop): pass/fail facts a viewer can check, never
taste words. Kinds of line: brief (Magic Prompt lines or the scene brief),
structure (bodies, hands, supported objects), artifacts (smears,
melted lettering, watermarks, blank frames), reference fidelity (one line per
reference, scenario-consistency) and placement (inside the format's safe area).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from app.services.pricing import QA_VISION_CHECK_KEY, usd_for

logger = logging.getLogger(__name__)

# Downscale before sending: 1024 px for a single image, 768 px each when the
# call carries several (references, clip frames).
SINGLE_SIDE = 1024
MULTI_SIDE = 768
MAX_REFERENCES = 4
MAX_TEXTS = 8
MAX_LINES = 6

PASS, WARN, FAIL, UNVERIFIED = "pass", "warn", "fail", "unverified"
VERDICTS = (PASS, WARN, FAIL, UNVERIFIED)

# /generate does not offer the toggle on the cheapest models: a check would be
# a large share of the image's price.
SKIP_MODELS = frozenset({
    "blackforestlabs/flux-3/klein/text-to-image",
    "fal-ai/z-image/turbo/lora",
})

# The fix for an image: an instruction edit of the kept image.
FIX_MODEL = "google/nano-banana-2.1/edit"

UNVERIFIED_NO_VISION = "The quality check needs an AI model that can see images, and none is set up right now."
UNVERIFIED_FAILED = "The quality check could not read this picture just now."
UNVERIFIED_UNREADABLE = "Some of the lettering is too small or blurred to read, so it could not be checked."


class CheckError(Exception):
    """A request for a check or a fix that cannot be served. The message is
    written for people."""


# ---------------------------------------------------------------------------
# What the model returns (validated and retried by complete_json)
# ---------------------------------------------------------------------------

class LineRead(BaseModel):
    id: str
    verdict: Literal["pass", "fail", "unclear"]
    evidence: str = Field(default="", max_length=400)


class DefectRead(BaseModel):
    region: str = Field(default="", max_length=200)
    kind: Literal["anatomy", "structure", "artifact", "text", "watermark", "blank",
                  "reference", "placement", "brief"]
    severity: Literal["minor", "major", "critical"]
    fix_instruction: str = Field(default="", max_length=400)


class Critique(BaseModel):
    lines: list[LineRead] = Field(default_factory=list)
    defects: list[DefectRead] = Field(default_factory=list, max_length=8)
    text_seen: list[str] = Field(default_factory=list, max_length=40)
    text_legible: bool = True


SYSTEM = """You are a strict quality inspector for AI generated pictures. You check a finished picture against a numbered checklist and report only what you can see. You never praise and never guess.

For every checklist line answer pass, fail or unclear:
- pass: you can see that the line holds.
- fail: you can see that it does not. Say what you see in a few words as the evidence.
- unclear: the picture is too small, blurred or ambiguous to tell. Never pass a line you cannot see.

Then list defects: concrete flaws a viewer would notice, each with where it is (the region, for example "left hand of the woman at frame right"), its kind, a severity and a one-sentence fix written as an edit request ("Redraw her left hand with five fingers around the cup").
Severity: critical when the picture cannot be used (blank or black, the wrong subject, a melted face, an extra limb on the main subject); major when a viewer notices it at a glance (an extra or missing finger, a warped hand, garbled lettering, a watermark, an object floating with nothing holding it); minor for small blemishes.
Kinds: anatomy, structure, artifact, text, watermark, blank, reference, placement, brief.

Lettering: transcribe every piece of text drawn in the picture exactly as it is drawn, letter by letter, misspellings included, one string per line of text, in text_seen. Never correct the spelling. When any lettering is too small or blurred to read, set text_legible to false.

Only the pictures named as being checked are judged. Reference pictures show what the subject must look like; they are not judged."""


@dataclass
class Rubric:
    """Checklist lines for one check: (id, text, weight) with weight "must"
    (a miss fails the check) or "should" (a miss is a warning)."""

    lines: list[tuple[str, str, str]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)

    def add(self, line_id: str, text: str, weight: str = "must") -> None:
        text = " ".join((text or "").split())[:400]
        if text and line_id not in {i for i, _, _ in self.lines}:
            self.lines.append((line_id, text, weight))


STRUCTURE = ("Every person and animal has a whole body: two arms and two legs attached to one body, five fingers "
             "on each visible hand, and every object rests on something that can hold it.")
ARTIFACTS = ("No smeared or melted areas, no garbled or half-formed lettering, no watermark or signature, and "
             "no blank, black or flat single-colour area where the picture should be.")
NO_TEXT = "The picture carries no lettering, captions, logos or watermark."

# Where a viewer's app covers the frame, by aspect.
SAFE_AREAS = {
    "9:16": "the main subject sits inside the middle of the frame, clear of the top tenth and the bottom fifth, "
            "where app buttons and captions sit",
    "16:9": "the main subject sits inside the frame, clear of the outer twentieth on every side",
    "1:1": "the main subject sits inside the frame, clear of the outer twentieth on every side",
    "4:5": "the main subject sits inside the frame, clear of the outer twentieth on every side",
}


# ---------------------------------------------------------------------------
# Quoted text and the edit distance
# ---------------------------------------------------------------------------

_QUOTED = (
    re.compile(r'"([^"\n]{1,120})"'),
    re.compile(r"“([^”\n]{1,120})”"),
    re.compile(r"«([^»\n]{1,120})»"),
)


def normalise_text(value: str) -> str:
    """Upper case, letters and digits of any script, single spaces."""
    value = unicodedata.normalize("NFKC", value or "").upper()
    value = re.sub(r"[\W_]+", " ", value)
    return " ".join(value.split())


def quoted_strings(prompt: str | None) -> list[str]:
    """The strings in double quotes that a prompt asks to appear in the
    picture, in order and without repeats. Closing instructions such as
    "no other text" are not copy."""
    found: list[tuple[int, str]] = []
    for pattern in _QUOTED:
        for m in pattern.finditer(prompt or ""):
            found.append((m.start(), m.group(1).strip()))
    out, seen = [], set()
    for _, text in sorted(found):
        norm = normalise_text(text)
        if not norm or norm in seen:
            continue
        if norm.startswith("NO ") and ("TEXT" in norm or "WORD" in norm):
            continue
        seen.add(norm)
        out.append(text)
    return out[:MAX_TEXTS]


def _best_match(needle: str, hay: str) -> tuple[int, str]:
    """(edit distance, closest substring) of ``needle`` against any substring
    of ``hay`` (free start and end), both normalised."""
    if not needle:
        return 0, ""
    if not hay:
        return len(needle), ""
    prev = [0] * (len(hay) + 1)
    prev_start = list(range(len(hay) + 1))
    for i in range(1, len(needle) + 1):
        cur = [i] + [0] * len(hay)
        cur_start = [0] + [0] * len(hay)
        for j in range(1, len(hay) + 1):
            cost = 0 if needle[i - 1] == hay[j - 1] else 1
            options = ((prev[j - 1] + cost, prev_start[j - 1]), (prev[j] + 1, prev_start[j]),
                       (cur[j - 1] + 1, cur_start[j - 1]))
            cur[j], cur_start[j] = min(options, key=lambda o: o[0])
        prev, prev_start = cur, cur_start
    end = min(range(len(hay) + 1), key=lambda j: prev[j])
    distance, start = prev[end], prev_start[end]
    # Widen to whole words, so the evidence shows the words as drawn.
    while start > 0 and hay[start - 1] != " ":
        start -= 1
    while end < len(hay) and hay[end] != " ":
        end += 1
    return distance, hay[start:end].strip()


def read_back(expected: str, seen: list[str], legible: bool) -> tuple[str, str]:
    """(line verdict, evidence) for one quoted string against the transcribed
    lettering. Exact after normalising is a pass; lettering too small to read
    is unverified, never a pass."""
    want = normalise_text(expected)
    hay = " ".join(normalise_text(s) for s in seen if s)
    distance, closest = _best_match(want, hay)
    if distance == 0:
        return PASS, f'Reads "{expected}".'
    if not legible:
        return UNVERIFIED, "Too small or blurred to read."
    if closest and distance / max(1, len(want)) <= 0.34:
        return FAIL, f'Reads "{closest}" instead of "{expected}".'
    return FAIL, f'"{expected}" is not in the picture.'


# ---------------------------------------------------------------------------
# The verdict, computed in code
# ---------------------------------------------------------------------------

_SEVERITY = {"critical": FAIL, "major": WARN, "minor": None}


def compute_verdict(rubric: Rubric, critique: Critique | None, *, code_defects: list[dict] | None = None,
                    reason: str | None = None) -> dict:
    """Lines and overall verdict from the model's answers.

    fail: a "must" line failed, a quoted string is misspelt or missing, or a
    critical defect. warn: a "should" line failed or a major defect.
    unverified: no answers at all, or a "must" line (or quoted string) could
    not be read and nothing failed. pass otherwise."""
    code_defects = list(code_defects or [])
    if critique is None:
        lines = [{"id": i, "text": t, "verdict": UNVERIFIED, "evidence": ""} for i, t, _ in rubric.lines]
        lines += [{"id": f"text{n}", "text": f'The text "{t}" is spelled exactly', "verdict": UNVERIFIED,
                   "evidence": ""} for n, t in enumerate(rubric.texts, start=1)]
        return {"verdict": UNVERIFIED, "lines": lines, "defects": code_defects,
                "reasons": [reason or UNVERIFIED_FAILED]}

    answers = {a.id.strip(): a for a in critique.lines}
    lines, must_unclear = [], False
    for line_id, text, weight in rubric.lines:
        answer = answers.get(line_id)
        if answer is None or answer.verdict == "unclear":
            verdict = UNVERIFIED
            must_unclear = must_unclear or weight == "must"
        elif answer.verdict == "pass":
            verdict = PASS
        else:
            verdict = FAIL if weight == "must" else WARN
        lines.append({"id": line_id, "text": text, "verdict": verdict,
                      "evidence": (answer.evidence if answer else "").strip()[:400]})
    for n, expected in enumerate(rubric.texts, start=1):
        verdict, evidence = read_back(expected, critique.text_seen, critique.text_legible)
        must_unclear = must_unclear or verdict == UNVERIFIED
        lines.append({"id": f"text{n}", "text": f'The text "{expected}" is spelled exactly', "verdict": verdict,
                      "evidence": evidence})

    defects = code_defects + [
        {"region": d.region.strip(), "kind": d.kind, "severity": d.severity,
         "fix_instruction": d.fix_instruction.strip()}
        for d in critique.defects
    ]
    outcomes = {ln["verdict"] for ln in lines} | {_SEVERITY.get(d["severity"]) for d in defects}
    if FAIL in outcomes:
        verdict = FAIL
    elif WARN in outcomes:
        verdict = WARN
    elif must_unclear:
        verdict = UNVERIFIED
    else:
        verdict = PASS

    reasons = []
    for ln in lines:
        if ln["verdict"] in (FAIL, WARN):
            reasons.append(f"{ln['text']}: {ln['evidence']}" if ln["evidence"] else ln["text"])
    for d in defects:
        if d["severity"] in ("critical", "major"):
            where = f" ({d['region']})" if d["region"] else ""
            reasons.append(f"{d['kind'].capitalize()} problem{where}: {d['fix_instruction'] or d['kind']}")
    if verdict == UNVERIFIED:
        reasons.append(UNVERIFIED_UNREADABLE if any(ln["id"].startswith("text") and ln["verdict"] == UNVERIFIED
                                                    for ln in lines) else UNVERIFIED_FAILED)
    return {"verdict": verdict, "lines": lines, "defects": defects, "reasons": reasons[:8]}


# ---------------------------------------------------------------------------
# Images for the call
# ---------------------------------------------------------------------------

def _prepare(blob: bytes, max_side: int) -> tuple[str, bool]:
    """(JPEG data URL, blank) for one image. Blank: one flat colour, which
    no model reading is needed to see."""
    from PIL import Image as PILImage, ImageStat

    with PILImage.open(io.BytesIO(blob)) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        spread = max(ImageStat.Stat(im.convert("L")).stddev or [0.0])
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), spread < 3.0


def content_hash(*blobs: bytes) -> str:
    h = hashlib.sha256()
    for blob in blobs:
        h.update(blob or b"")
    return h.hexdigest()[:32]


def _blank_defect(label: str) -> dict:
    return {"region": label, "kind": "blank", "severity": "critical",
            "fix_instruction": "The picture came back blank or a single flat colour; make it again."}


async def _critique(images: list[str], rubric: Rubric, context: str, *, user_id: int | None,
                    feature: str) -> tuple[Critique | None, str | None, str | None]:
    """(answers, model label, reason when there are none). Runs on its own
    database session: the LLM helpers commit (token usage), and a caller in
    the middle of a locked scheduler tick must not be committed by them."""
    from app.database import SessionLocal
    from app.services.storyscript import llm

    session = SessionLocal()
    label = None
    try:
        choice = llm.resolve_model(session)
        label = choice.label
        if not choice.supports_vision:
            return None, label, UNVERIFIED_NO_VISION
        checklist = "\n".join(f"[{line_id}] {text}" for line_id, text, _ in rubric.lines)
        prompt = (
            f"{context}\n\nChecklist:\n{checklist or '(no lines; list defects and transcribe the lettering only)'}\n\n"
            "Answer every checklist id above in lines, using exactly those ids."
        )
        wanted = {line_id for line_id, _, _ in rubric.lines}

        def validate(obj: Critique) -> list[str]:
            missing = wanted - {a.id.strip() for a in obj.lines}
            return [f"lines is missing the ids: {', '.join(sorted(missing))}"] if missing else []

        critique, choice = await llm.complete_json(
            session, system=SYSTEM, prompt=prompt, schema=Critique, feature=feature, validate=validate,
            max_tokens=4000, temperature=0.1, max_retries=1, user_id=user_id, choice=choice, images=images,
        )
        return critique, choice.label, None
    except Exception as exc:
        logger.warning(f"Quality check call failed ({label or 'no model'}): {type(exc).__name__}: {exc}")
        return None, label, UNVERIFIED_FAILED
    finally:
        session.close()


async def _run(kind: str, rubric: Rubric, context: str, checked: list[tuple[str, bytes]],
               references: list[tuple[str, bytes]], *, user_id: int | None) -> dict:
    """One check: prepare the pictures, call the model, compute the verdict."""
    side = SINGLE_SIDE if len(checked) == 1 and not references else MULTI_SIDE
    images, code_defects, names = [], [], []
    try:
        for label, blob in checked:
            url, blank = await asyncio.to_thread(_prepare, blob, side)
            images.append(url)
            names.append(f"image {len(images)} is {label} (being checked)")
            if blank:
                code_defects.append(_blank_defect(label))
        for label, blob in references[:MAX_REFERENCES]:
            try:
                url, _ = await asyncio.to_thread(_prepare, blob, MULTI_SIDE)
            except Exception:
                continue
            images.append(url)
            names.append(f"image {len(images)} is a reference showing {label}")
    except Exception as exc:
        logger.warning(f"Quality check: the picture could not be prepared: {type(exc).__name__}")
        critique, model, reason = None, None, UNVERIFIED_FAILED
    else:
        context = f"{context}\n\nPictures: " + "; ".join(names) + "."
        critique, model, reason = await _critique(images, rubric, context, user_id=user_id, feature=f"qa_{kind}")
    out = compute_verdict(rubric, critique, code_defects=code_defects, reason=reason)
    out.update({
        "kind": kind,
        "model": model,
        "checked_at": datetime.utcnow().isoformat(),
        "content_hash": content_hash(*(blob for _, blob in checked)),
    })
    return out


# ---------------------------------------------------------------------------
# One function per check kind
# ---------------------------------------------------------------------------

def _reference_lines(rubric: Rubric, references: list[tuple[str, bytes]], first_index: int) -> None:
    for n, (label, _) in enumerate(references[:MAX_REFERENCES]):
        what = ("same shape, colours, proportions and label" if label.startswith("the product")
                else "same face, hair, skin tone, build and clothing")
        rubric.add(f"ref{n + 1}", f"{label[:1].upper()}{label[1:]} matches reference image {first_index + n}: {what}.")


async def check_still(still: bytes, *, scene_text: str, cast: list[str], references: list[tuple[str, bytes]],
                      aspect: str | None, user_id: int | None) -> dict:
    """A Faceless storyboard still against its scene and the cast and product
    references, before any clip is made from it."""
    rubric = Rubric()
    if scene_text:
        rubric.add("brief", f"The picture shows this scene, its main subject and setting: {scene_text[:500]}",
                   "should")
    if cast:
        rubric.add("cast", f"The main characters visible are {', '.join(cast)} ({len(cast)} in all); "
                           "background extras do not count.", "should")
    rubric.add("structure", STRUCTURE, "should")
    rubric.add("artifacts", ARTIFACTS, "should")
    rubric.add("no_text", NO_TEXT, "should")
    if aspect in SAFE_AREAS:
        rubric.add("placement", f"In this {aspect} frame {SAFE_AREAS[aspect]}.", "should")
    _reference_lines(rubric, references, 2)
    return await _run("still", rubric, "Check a storyboard still for a video scene.", [("the still", still)],
                      references, user_id=user_id)


async def check_clip(frames: list[bytes], *, scene_text: str, references: list[tuple[str, bytes]],
                     user_id: int | None) -> dict:
    """A Faceless clip from its first, middle and last frames, against the
    approved references, in one call. Drift that appears and fades between
    the frames is not seen; this is a flag, never a retry."""
    rubric = Rubric()
    rubric.add("consistent", "The same people, objects and setting appear in every frame; no face, garment or "
                             "object changes shape, colour or identity between frames.")
    if scene_text:
        rubric.add("brief", f"The frames show this scene: {scene_text[:400]}", "should")
    rubric.add("structure", STRUCTURE, "should")
    rubric.add("artifacts", ARTIFACTS.replace("picture", "frame"), "should")
    count = len(frames)
    _reference_lines(rubric, references, count + 1)
    checked = [(f"frame {n + 1} of {count} of the clip", f) for n, f in enumerate(frames)]
    return await _run("clip", rubric, "Check frames taken from the start, middle and end of one video clip.",
                      checked, references, user_id=user_id)


async def check_text(image: bytes, *, prompt: str, user_id: int | None, texts: list[str] | None = None) -> dict:
    """Text read-back: every quoted string of the prompt, transcribed by the
    model and compared here letter by letter."""
    rubric = Rubric(texts=list(texts if texts is not None else quoted_strings(prompt))[:MAX_TEXTS])
    rubric.add("artifacts", ARTIFACTS, "should")
    return await _run("text", rubric, "Check the lettering of a generated picture.", [("the picture", image)], [],
                      user_id=user_id)


async def check_generated(image: bytes, *, prompt: str, lines: list[str], user_id: int | None) -> dict:
    """An opted-in /generate image: the Magic Prompt rubric lines (counts,
    left and right, attributes the user stated), structure, artifacts and the
    quoted text of the prompt."""
    rubric = Rubric(texts=quoted_strings(prompt))
    for n, line in enumerate(clean_lines(lines), start=1):
        rubric.add(f"brief{n}", line, "must")
    if not rubric.lines:
        rubric.add("brief", f"The picture shows what this prompt asks for: {(prompt or '')[:500]}", "should")
    rubric.add("structure", STRUCTURE, "should")
    rubric.add("artifacts", ARTIFACTS, "should")
    return await _run("generate", rubric, "Check a generated picture against what was asked for.",
                      [("the picture", image)], [], user_id=user_id)


PORTRAIT_REFUSAL = ("This photo will not lip sync well: it needs one large face looking toward the camera with the "
                    "mouth fully visible. Pick a closer, front-facing photo.")


async def check_portrait(image: bytes, *, user_id: int | None) -> dict:
    """Lip Sync pre-check: one large, frontal face with the mouth in view."""
    rubric = Rubric()
    rubric.add("one_face", "Exactly one human face is in the picture.")
    rubric.add("large", "That face is large: it takes up at least a tenth of the picture's height.")
    rubric.add("frontal", "The face looks toward the camera, turned less than about 45 degrees.")
    rubric.add("mouth", "The mouth and lips are fully visible, not covered by a hand, microphone, mask or hair.")
    return await _run("portrait", rubric, "Check a portrait photo that will be animated to speak.",
                      [("the portrait", image)], [], user_id=user_id)


def clean_lines(lines) -> list[str]:
    """Rubric lines from a client or Magic Prompt: short plain sentences, at
    most MAX_LINES."""
    out = []
    for line in lines or []:
        if not isinstance(line, str):
            continue
        line = " ".join(line.strip().lstrip("-*").split())[:200]
        if len(line) >= 6 and line not in out:
            out.append(line)
    return out[:MAX_LINES]


# ---------------------------------------------------------------------------
# Availability and price
# ---------------------------------------------------------------------------

def price() -> float:
    return usd_for(QA_VISION_CHECK_KEY)


def available(db) -> bool:
    """The default model can see images. The toggle is only offered when this
    holds, so a check that cannot run is never asked for."""
    from app.services.storyscript import llm

    try:
        return bool(llm.resolve_model(db).supports_vision)
    except Exception:
        return False


def view(quality: dict | None) -> dict | None:
    """What the browser gets: the verdict without the request."""
    if not isinstance(quality, dict):
        return None
    if quality.get("status") in ("pending", "running"):
        return {"status": "pending", "estimated_usd": quality.get("request", {}).get("estimated_usd")}
    if quality.get("verdict") not in VERDICTS:
        return None
    return {
        "status": "done",
        "verdict": quality["verdict"],
        "reasons": list(quality.get("reasons") or [])[:8],
        "lines": [{k: ln.get(k) for k in ("id", "text", "verdict", "evidence")} for ln in quality.get("lines") or []],
        "defects": list(quality.get("defects") or [])[:8],
        "kind": quality.get("kind"),
        "checked_at": quality.get("checked_at"),
        "estimated_usd": quality.get("estimated_usd"),
        "fixable": fix_targets(quality),
    }


# ---------------------------------------------------------------------------
# Opted-in checks of stored images (/generate and the explainer)
# ---------------------------------------------------------------------------

PENDING_WINDOW = timedelta(hours=2)
RUNNING_TIMEOUT = timedelta(minutes=10)
IMAGES_PER_TICK = 6


def pending(kind: str, *, prompt: str, lines: list[str] | None = None, estimated_usd: float | None = None) -> dict:
    """The quality value of an image that waits for its check."""
    return {
        "status": "pending",
        "requested_at": datetime.utcnow().isoformat(),
        "request": {"kind": kind, "prompt": (prompt or "")[:6000], "lines": clean_lines(lines),
                    "estimated_usd": estimated_usd},
    }


NO_QUOTED_TEXT = "There is no text in quotes in the prompt, so there was nothing to read back."


def nothing_to_check(kind: str, reason: str) -> dict:
    """An unverified verdict for a check that had nothing to read."""
    return {**compute_verdict(Rubric(), None, reason=reason), "kind": kind, "model": None, "estimated_usd": 0.0,
            "checked_at": datetime.utcnow().isoformat(), "content_hash": None}


def pending_from_job(job) -> dict | None:
    """A /generate job's opted-in check, for each image it stores."""
    request = getattr(job, "quality_check", None)
    if not isinstance(request, dict):
        return None
    return pending("generate", prompt=job.prompt or "", lines=request.get("lines"),
                   estimated_usd=request.get("estimated_usd"))


async def _check_stored_image(image) -> dict:
    from app.services.storage_service import storage_service

    request = (image.quality or {}).get("request") or {}
    blob = await storage_service.get_file_bytes(image.filename, "images", user_id=image.user_id)
    if not blob:
        return {**compute_verdict(Rubric(), None, reason=UNVERIFIED_FAILED), "kind": request.get("kind"),
                "checked_at": datetime.utcnow().isoformat(), "estimated_usd": 0.0}

    if request.get("kind") == "text":
        verdict = await check_text(blob, prompt=request.get("prompt") or "", user_id=image.user_id)
    else:
        verdict = await check_generated(blob, prompt=request.get("prompt") or "", lines=request.get("lines") or [],
                                        user_id=image.user_id)
    return {**verdict, "estimated_usd": 0.0 if verdict.get("verdict") == UNVERIFIED else price()}


def _set_quality(db, image_id: int, value: dict) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    from app.database import apply_row_lock
    from app.models.content import Image

    row = apply_row_lock(db.query(Image).filter(Image.id == image_id).populate_existing()).first()
    if row is not None:
        row.quality = value
        flag_modified(row, "quality")
    db.commit()


def process_pending_images(db, limit: int = IMAGES_PER_TICK) -> int:
    """Run the waiting checks of stored images (scheduler only). Each is
    claimed ("running") before its call, so a slow call is not started twice;
    a claim older than RUNNING_TIMEOUT belongs to a worker that died and ends
    unverified. Returns how many were checked."""
    from app.models.content import Image

    since = datetime.utcnow() - PENDING_WINDOW
    rows = (db.query(Image).filter(Image.quality.isnot(None), Image.created_at >= since)
            .order_by(Image.id).limit(200).all())
    done = 0
    for row in rows:
        q = row.quality if isinstance(row.quality, dict) else {}
        status = q.get("status")
        if status == "running":
            started = q.get("started_at") or ""
            if started and datetime.fromisoformat(started) < datetime.utcnow() - RUNNING_TIMEOUT:
                _set_quality(db, row.id, {**compute_verdict(Rubric(), None), "request": q.get("request"),
                                          "kind": (q.get("request") or {}).get("kind"), "estimated_usd": 0.0,
                                          "checked_at": datetime.utcnow().isoformat()})
            continue
        if status != "pending" or done >= limit:
            continue
        _set_quality(db, row.id, {**q, "status": "running", "started_at": datetime.utcnow().isoformat()})
        try:
            verdict = asyncio.run(_check_stored_image(row))
        except Exception:
            logger.exception(f"Quality check of image {row.id} failed")
            db.rollback()
            verdict = {**compute_verdict(Rubric(), None), "estimated_usd": 0.0,
                       "checked_at": datetime.utcnow().isoformat()}
        _set_quality(db, row.id, {**verdict, "request": q.get("request")})
        done += 1
    return done


def run_image_tick() -> None:
    """Scheduler entry point."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        process_pending_images(db)
    except Exception:
        db.rollback()
        logger.exception("Quality check tick failed")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fixes the user starts
# ---------------------------------------------------------------------------

def spelled(text: str) -> str:
    """ "Grand Opening" as G-r-a-n-d O-p-e-n-i-n-g."""
    return " ".join("-".join(word) for word in text.split())


def fix_targets(quality: dict | None) -> list[str]:
    """What a stored verdict can be fixed by: "spelling" when a quoted string
    failed, "defects" when a line failed or a defect carries a fix."""
    if not isinstance(quality, dict) or quality.get("verdict") not in (FAIL, WARN):
        return []
    out = []
    lines = quality.get("lines") or []
    if any(ln.get("id", "").startswith("text") and ln.get("verdict") == FAIL for ln in lines):
        out.append("spelling")
    if any(not ln.get("id", "").startswith("text") and ln.get("verdict") in (FAIL, WARN) for ln in lines) or any(
            d.get("fix_instruction") and d.get("severity") in ("critical", "major")
            for d in quality.get("defects") or []):
        out.append("defects")
    return out


KEEP = ("Change nothing else: keep the composition, the people, the colours, the light, the lettering style and "
        "every other word and part of the picture exactly as they are.")


def fix_instruction(quality: dict, target: str) -> str:
    """The edit prompt for a fix of the kept picture. Raises CheckError."""
    if target not in fix_targets(quality):
        raise CheckError("There is nothing of that kind to fix on this picture.")
    if target == "spelling":
        wrong = [ln for ln in quality.get("lines") or []
                 if ln.get("id", "").startswith("text") and ln.get("verdict") == FAIL]
        parts = []
        for ln in wrong:
            m = re.match(r'The text "(.*)" is spelled exactly$', ln.get("text") or "")
            if not m:
                continue
            word = m.group(1)
            parts.append(f'The text must read "{word}", spelled {spelled(word)}.')
        if not parts:
            raise CheckError("There is nothing of that kind to fix on this picture.")
        return " ".join(["Correct the lettering in this picture."] + parts[:MAX_TEXTS] + [KEEP])
    fixes = [d["fix_instruction"].rstrip(".") + "." for d in quality.get("defects") or []
             if d.get("fix_instruction") and d.get("severity") in ("critical", "major")]
    for ln in quality.get("lines") or []:
        if not ln.get("id", "").startswith("text") and ln.get("verdict") in (FAIL, WARN):
            fixes.append(f"Make this true: {ln.get('text', '').rstrip('.')}.")
    return " ".join(["Edit this picture."] + fixes[:4] + [KEEP])


def fix_resolution(width: int | None, height: int | None) -> str:
    """The edit resolution that keeps the kept picture's size."""
    side = max(int(width or 0), int(height or 0))
    if side > 2600:
        return "4k"
    if side > 1500:
        return "2k"
    return "1k"
