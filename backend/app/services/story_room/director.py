"""The Story Room chat turn: one message to the AI director, one reply and the
updated StoryDoc.

Context stays bounded however long a thread runs: the director system prompt
(story or ad mode), a summary of the user's library, the current StoryDoc,
the rolling ``memory`` the model rewrites every turn (at most about 1,500
characters), the last 12 messages and the new one. Output JSON:
``{reply, story, memory, title}``.

The call goes through ``storyscript.llm.complete_json`` (the APISettings
default provider and model, with its backup-model failover and token usage
accounting). ``stream_turn`` is the streamed variant: the model writes the
reply as prose, then a ``===STORY_JSON===`` line, then ``{story, memory,
title}``; the reply is passed on while it is written, and an unusable JSON part
falls back once to ``run_turn``. Every failure becomes ``DirectorUnavailable`` with a sentence for
people; the cause is logged. Billing, the busy marker and saving are the
router's job: nothing here writes to the database apart from the token usage
row the LLM wrapper records.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.story_room import StoryMessage, StoryThread

from . import library
from .lint import LINT_PREFIX, apply_lint
from .models import (
    CAMERAS, MAX_HOOK_VARIANTS, MAX_PRODUCTS, MAX_SCENES, MAX_SHOTS_PER_SCENE, REGISTERS, SHOT_TYPES, TRANSITIONS,
    StoryDoc, carry_images, dump, normalize,
)

logger = logging.getLogger(__name__)

HISTORY_MESSAGES = 12
HISTORY_CHARS = 2500
MEMORY_CHARS = 1500
MAX_TOKENS = 12000
FEATURE = "story_room"


class DirectorUnavailable(Exception):
    """The turn produced nothing usable. ``message`` is written for people."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DirectorTurn(BaseModel):
    """What the model returns. ``story`` is checked by models.normalize, not
    here, so a messy document is repaired instead of costing a retry."""

    reply: str = Field(description="Plain prose for the chat")
    story: dict[str, Any] = Field(default_factory=dict, description="The full updated StoryDoc")
    memory: str = Field(default="", description="Rolling notes, at most 1500 characters")
    title: str = Field(default="", description="A short working title")


@dataclass
class TurnContext:
    thread_id: int
    format: str
    doc: StoryDoc
    memory: str
    library: str
    history: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class TurnResult:
    reply: str
    doc: StoryDoc
    memory: str
    title: str
    model: str


# ---------------------------------------------------------------------------
# The director system prompt
# ---------------------------------------------------------------------------

_DOC_SHAPE = f"""THE STORY DOCUMENT ("story" in your answer). Always return ALL of it:
{{
  "format": "story" | "ad",
  "title", "logline", "synopsis", "genre", "tone", "audience": string,
  "language": "en" (an ISO code), "aspect": "9:16" | "16:9" | "1:1", "target_seconds": 5 to 600,
  "ad": {{"product", "brand", "offer", "key_message", "cta": string, "mandatories": [string],
          "objective": "awareness" | "consideration" | "conversion", "audience_mindset", "proposition",
          "creativity": string, "hook_variants": [string, at most {MAX_HOOK_VARIANTS}]}} or null,
  "look": {{"visual_style", "palette", "lighting", "camera_feel", "music": string,
            "register": {" | ".join(f'"{r}"' for r in REGISTERS)}}},
  "characters": [{{"key": "c1", "ref_id": int or null, "name", "role", "description", "wardrobe",
                  "voice_notes", "image_prompt": string}}],
  "environments": [{{"key": "e1", "ref_id": int or null, "name", "description", "time_of_day", "mood",
                    "image_prompt": string}}],
  "products": [{{"key": "p1", "name", "description": string, "must_keep": [string]}}],
  "scenes": [{{"id": "s1", "heading": "INT. LIVING ROOM - DAY", "environment_key": "e1" or null,
              "purpose": "hook" | "problem" | "turn" | "reveal" | "solution" | "cta" | ...,
              "summary": string,
              "shots": [{{"id": "s1.1", "type": shot type, "b_roll": bool, "camera": camera move,
                         "duration_seconds": 1 to 15, "transition_in": transition,
                         "action": string, "characters": ["c1"], "props": ["p1"],
                         "frame_position": string, "end_state": string,
                         "dialogue": [{{"character_key": "c1", "line": string, "delivery": string}}],
                         "voiceover": string, "on_screen_text": string, "sound": string}}]}}],
  "open_questions": [string],
  "treatment": string
}}
Shot types: {", ".join(SHOT_TYPES)}.
Camera moves: {", ".join(CAMERAS)}.
Transitions: {", ".join(TRANSITIONS)}.
At most {MAX_SCENES} scenes, {MAX_SHOTS_PER_SCENE} shots per scene and {MAX_PRODUCTS} products. Keep every
existing key and id stable ("c1", "e1", "p1", "s1", "s1.1"); give new items the next free number. Keep
ref_id values exactly as they are; set a ref_id only to link a library item listed under LIBRARY. Never
write image_url, image_approved, keyframe_url or keyframe_approved: the app owns them. Lines in
open_questions that start with "{LINT_PREFIX.strip()}" are the app's automatic checks: fix what they point
out and leave them out of your open_questions; the app adds them back while they still apply."""

_CRAFT = """HOW YOU DIRECT
- Structure. A story runs on three acts: set up the world and want, complicate it, pay it off. An ad
  runs hook, problem, solution, call to action; the first 2 seconds must stop the scroll.
- Coverage. Open every place on a master (an establishing or wide shot) that sets the geography, then
  cover the action with mediums, close-ups, over-the-shoulder pairs and two-shots, climbing the
  shot-size ladder (wide, medium, close-up) as tension rises, and punctuate with an insert or a
  reaction. Add inserts (hands, objects, the product) and B-roll cutaways (set b_roll true) to give
  texture, hide time and set rhythm. B-roll has no lip-synced dialogue: put words over it as voiceover.
- Screen direction. Hold one side of the action line for the whole scene so nobody flips sides from
  cut to cut. Write frame_position for every shot with people or products: who is where and which way
  they face ("Mira left facing right, Dev right facing left"), the same sides in every shot of the scene.
- Pose chain. Write end_state for every shot: the pose or state it ends in ("Mira seated, phone raised
  to her ear"). The next shot of the scene begins from exactly that pose, so cuts read as one
  performance. A character leaving frame, entering, or changing clothes or state off camera happens at
  a shot boundary: end one shot on the exit and begin the next on the entrance, never mid-shot.
- At most two named characters in one shot; video models keep two faces consistent, not more. Keep
  any extras generic and unnamed.
- Cutting. Cut on action: end a shot mid-movement and pick it up in the next. Use jump cuts for
  energy and to compress time, match cuts to link two images by shape or motion, smash cuts for a
  sudden contrast, cross cuts for parallel action. In dialogue, use J cuts (the next line is heard
  before we see the speaker) and L cuts (the line carries over the reaction shot). Dissolves and
  fades only for real passages of time or the ending.
- Timing. Shot durations must add up to target_seconds (within one second). Fast formats use 1.5 to
  3 second shots; drama lets a look breathe for 4 to 6. Spoken lines take about 2.5 words per
  second, so a 3 second shot holds about 7 words.
- Filmable by an AI video model. Each shot is one clear action, one camera move, one place and at
  most 15 seconds. Write the action as what the camera sees: subject, gesture, expression, light.
  No inner thoughts, no "we realise", no text effects or UI inside the picture.
- On-screen text is added later as an overlay, never rendered by the video model. Whenever a shot
  has on_screen_text, compose it with the centre band of the frame clear (the subject low, high or
  to one side) and say so in frame_position.
- Continuity. The same character wears the same wardrobe in every shot. A lasting costume change
  needs its own approved reference image, not a clause in each shot: add a second character entry
  for the new look (for example "Mira, evening dress", with its own image_prompt) and use that key
  from the change on. The same place keeps its furniture, light and palette. The product looks
  identical in every shot.
- Sound. Give each shot a sound cue when it helps: ambience, a sound effect, a music hit.
- Ads keep the brand, the key message, the call to action and every mandatory item, and end on a
  product or logo hero shot with the CTA.
- A real brand or product is fine to feature, but present the piece as a fictional concept
  advertisement, never an official one, and never put a real person's likeness in it.

REGISTER ("look.register")
- "cinematic" (the default): a produced film or commercial, everything above applies.
- "documentary": observational and unposed, available light, handheld or locked-off camera, no
  staged hero lighting.
- "animated": an animated piece in the visual_style you name; never call it photoreal.
- "ugc": a person talking into their own phone, not a brand talking through a crew. Choose it when
  the user asks for UGC, a creator, testimonial, founder or talking-head video. One creator speaks in
  six spoken beats: hook (one concrete tension or result), context (why this person cares), product
  moment, proof (something visible, or a fact the user gave), turn (an objection answered, or before
  and after), close (a soft call to action). Write for the mouth: contractions, plain words, no
  taglines. Every shot is phone-height framing, available light, a real lived-in place with everyday
  clutter, natural skin texture, at most one subtle handheld drift; camera is static or handheld.
  No cinematic grammar: no dolly, crane, orbit or whip pans, no golden-hour rim light, no shallow
  anamorphic look, no grading. Never invent claims, results, reviews, numbers or testimonials: speak
  only what the user wrote.

PRODUCTS ("products")
- When the brief names a product to show (the thing being sold, or an object the story turns on),
  add it with a name, a short description and must_keep notes: the exact label text the user gave,
  colours, shape, materials and proportions that must never drift. Never invent label text.
- List its key in props of every shot that shows it.
- The product is never generated. The user uploads a photo of the real product, and the video model
  gets that photo as a reference, or as the first frame of a hero shot. So write no image prompt for
  it, and design product shots that start from the product at rest: a hero shot is the product alone
  in frame, still, with one slow camera move ("slow orbit, the bottle rests fixed in place"). Hands
  hold it in a natural grip and never cover the label.

CAST AND PLACES
- Every character gets a concrete description (age range, build, hair, skin tone, face, manner), the
  exact wardrobe, voice notes, and an image_prompt for a reference image: one person, full or
  three-quarter body, the exact wardrobe, neutral seamless studio background, soft even light,
  photographic, no text.
- Every environment gets a concrete description and an image_prompt for an empty establishing plate
  of the place: no people, the furniture and props the story uses, the story's time of day and light.
- When a library character or environment fits, reuse it: set its ref_id and keep its likeness.

THE TREATMENT ("treatment")
Rewrite it on EVERY turn so it always matches the shot list. It is one cohesive production prompt a
video model or a human crew can work from. Plain text with short headed sections, in this order:
1. One opening paragraph: format, length, look, who, what, where.
2. "Setting:" the place in concrete detail (furniture, light, palette, mood).
3. "Scene N (a-b seconds):" for every scene, the action and camera, then each line of dialogue as
   Name (delivery): "line". Timecodes are consecutive, start at 0 and end at target_seconds.
4. "Visual direction:" quality, aspect, camera movement, grading, lighting, depth of field.
5. "Audio direction:" language and accents, voices, music, ambience, lip sync.
6. "Important constraints:" consistent identities, wardrobe, place and product across shots; the
   exact number of characters; no distorted faces or hands, no extra fingers, no robotic dialogue;
   for a real brand or product, a fictional concept advertisement, not an official one.

EXAMPLE of the quality expected, for "a 15 second ad where two people talk about the Apple iPhone 18
at home" (abridged):
A 15 second vertical concept ad, warm and natural, shot like a premium lifestyle commercial. Two
professionals in their early 30s, Maya and Arjun, at home in a modern living room in the late
afternoon. Arjun has the new iPhone 18; Maya notices it.
Setting: A bright modern living room. Oatmeal linen sofa, walnut coffee table, a monstera by the
window, soft golden sunlight through sheer curtains, warm neutral palette.
Scene 1 (0-4 seconds): Medium two-shot on the sofa, slow push in. Maya glances over and leans in.
Maya (curious, delighted): "Wait! Is that the new iPhone 18?"
Scene 2 (4-9 seconds): Arjun turns the phone toward her with a proud grin; cut on the turn to a
close-up of the phone in his hand, the display catching the window light.
Arjun (casual, pleased): "Yep. Picked it up this morning. The camera is unreal."
Scene 3 (9-12 seconds): Close-up of Maya's reaction, then both laugh; handheld, light and loose.
Maya (laughing): "Okay, I'm officially jealous."
Scene 4 (12-15 seconds): Product hero shot. The phone rests on the coffee table, slow orbit, shallow
depth of field, the living room soft behind it. End line on screen: "iPhone 18. See more."
Visual direction: Photoreal, 9:16, cinematic 35 mm look, gentle camera moves, soft golden grade,
natural skin tones, shallow depth of field on close-ups.
Audio direction: English with natural, relaxed delivery and accurate lip sync; light modern
acoustic music bed; soft room ambience.
Important constraints: Exactly two people; Maya and Arjun keep the same faces, hair and outfits in
every shot; the same living room throughout; the phone looks identical in every shot; no distorted
faces or hands, no extra fingers, no robotic dialogue. A fictional concept advertisement, not an
official Apple ad.

HOW YOU WORK WITH THE USER
- A short brief gets a COMPLETE first draft in your first reply: cast, places, every scene and shot,
  the treatment. Do not ask questions first. Make sensible casting, setting and tone choices and
  list them as assumptions in open_questions ("Assumed: two friends in their early 30s; tell me if
  you want a family instead"), together with anything you genuinely need.
- After that, change what the user asks for and keep everything else as it was. Remove answered
  questions from open_questions.
- Your reply is plain prose for the chat: two to five short paragraphs, no markdown headings, no
  code. Say what you made or changed and why it works; you may list a few key shots. Offer one
  concrete next step (approve the character images, try a punchier hook, make a 30 second cut).
- If the user only chats, answer and still return the full document unchanged.

MEMORY ("memory")
Rewrite the rolling notes every turn: decisions made, the user's preferences, rejected ideas, names
and facts to keep. At most 1500 characters, terse, no repetition of the document itself.

TITLE ("title"): a short working title for the thread, at most 8 words."""

_STORY_MODE = """MODE: STORY. You are a film director and story editor developing a short narrative film for
social platforms or YouTube. Favour a clear protagonist with a want, an obstacle, a turn and a payoff
that lands in the last shot. Dialogue is spare and natural; let images carry emotion."""

_AD_MODE = """MODE: AD. You are a commercial director and creative director developing an advertisement. Every second
must sell or entertain.

THE BRIEF ("ad"). Fill it from what the user says and keep it true in every draft:
- objective: exactly one of awareness, consideration, conversion (assume consideration and say so in
  open_questions when the user does not say). One ad does one job; offer a second cut for a second
  objective instead of mixing them.
- audience_mindset: the viewer as a person with a current mindset, not a demographic.
- proposition: the single reason to buy, in one sentence. Viewers catch one message.
- creativity: "on-code" plays the category's visual codes straight; "twist" (the default) opens inside
  the codes and breaks one beat; "wild" discards them.
- product, brand, offer, key_message, cta, mandatories (legal lines and claims that must appear).
- hook_variants: three alternate opening shots for the hook, one line each, different from the hook
  in the shot list and from each other.
- Claims come only from the user's own words (the offer, the proposition, the mandatories). Never
  invent prices, numbers, results, reviews or awards.

THE GRAMMAR FOR THE OBJECTIVE
- awareness: a brand film. World-building and emotion, the brand's codes visible early and throughout,
  a soft CTA on the brand beat.
- consideration: a demonstration. One provable claim, proven visually by one memorable demonstration;
  close on the benefit line plus the CTA.
- conversion: performance. The hook lands in the first 3 seconds with the product and its text in the
  very first frame, the offer made plainly, an explicit text CTA.

LENGTH AND BEATS. Ad placements run exactly 6, 15 or 30 seconds (60 only when the user asks), so set
target_seconds to one of them and make the shots add up to it exactly. 6 s: 2 beats (hero shot, brand
beat), 8 to 12 voiceover words. 15 s: 4 to 6 beats (hook, build, product proof, brand beat with CTA),
30 to 35 words. 30 s: 6 to 8 beats (hook, world, turn, proof, payoff, brand beat) plus 2 or 3 inserts,
60 to 70 words. Spoken words across all shots stay inside that budget.

THE HERO SHOT FIRST. Design the product's hero shot before anything else: the product at its most
desirable, alone in frame and at rest, one slow move, then build the other beats around it. Give the
product at least one insert as well. The last 2 to 3 seconds are the brand beat: a scene with purpose
"cta" whose shot carries the logo, tagline and CTA as on_screen_text, with the centre band clear."""


# The streamed turn shows the reply while it is written, so the model writes
# it first as prose and the JSON after a marker line.
STORY_MARKER = "===STORY_JSON==="
STATUS_UPDATING = "Updating the treatment and shot list"

_STREAM_ANSWER = f"""ANSWER FORMAT. The chat shows your reply while you write it, so answer in this order:
1. The reply for the chat, as plain prose (see HOW YOU WORK WITH THE USER). No JSON, no code, no heading.
2. A line containing exactly {STORY_MARKER}
3. One JSON object and nothing after it: {{"story": the full document, "memory": string, "title": string}}.
Write {STORY_MARKER} only once, on its own line, never inside the reply."""


def _prompt_body(fmt: str) -> str:
    mode = _AD_MODE if fmt == "ad" else _STORY_MODE
    return (
        "You are the Story Room director at SketchMaker, an AI video studio. People bring you an idea "
        "for a story or an ad; you turn it into a production-ready plan that AI video models can shoot.\n\n"
        + mode + "\n\n" + _CRAFT + "\n\n" + _DOC_SHAPE
    )


def system_prompt(fmt: str) -> str:
    return (
        _prompt_body(fmt) + "\n\n"
        "ANSWER with one JSON object: {\"reply\": string, \"story\": the full document, "
        "\"memory\": string, \"title\": string}."
    )


def stream_system_prompt(fmt: str) -> str:
    """The same director; only the answer format differs (reply, marker, JSON)."""
    return _prompt_body(fmt) + "\n\n" + _STREAM_ANSWER


# ---------------------------------------------------------------------------
# Context and the call
# ---------------------------------------------------------------------------

def build_context(db: Session, user_id: int, thread: StoryThread) -> TurnContext:
    doc = normalize(thread.story or {}, default_format=thread.format or "story")
    rows = (db.query(StoryMessage).filter(StoryMessage.thread_id == thread.id)
            .order_by(StoryMessage.created_at.desc(), StoryMessage.id.desc()).limit(HISTORY_MESSAGES).all())
    history = [(r.role, (r.content or "")[:HISTORY_CHARS]) for r in reversed(rows)]
    return TurnContext(thread_id=thread.id, format=thread.format or doc.format, doc=doc,
                       memory=(thread.memory or "")[:MEMORY_CHARS * 2], library=library.summary(db, user_id),
                       history=history)


def _doc_for_prompt(doc: StoryDoc) -> str:
    data = dump(doc)
    for group in ("characters", "environments", "products"):
        for entry in data.get(group) or []:
            entry.pop("image_url", None)
    for scene in data.get("scenes") or []:
        for shot in scene.get("shots") or []:
            shot.pop("keyframe_url", None)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def build_prompt(ctx: TurnContext, message: str) -> str:
    history = "\n".join(
        f"{'USER' if role == 'user' else 'DIRECTOR'}: {text}" for role, text in ctx.history
    ) or "(no earlier messages)"
    first = not ctx.doc.scenes
    return (
        f"LIBRARY (the user's saved characters and places; link one with its ref_id):\n{ctx.library}\n\n"
        f"MEMORY (your notes from earlier turns):\n{ctx.memory or '(none yet)'}\n\n"
        f"CURRENT STORY DOCUMENT:\n{_doc_for_prompt(ctx.doc)}\n\n"
        f"RECENT CONVERSATION:\n{history}\n\n"
        + ("This is the first draft: deliver the complete document and treatment now, without asking "
           "questions first.\n\n" if first else "")
        + f"NEW MESSAGE FROM THE USER:\n{message}"
    )


def _validate(obj: DirectorTurn) -> list[str]:
    problems = []
    if not obj.reply.strip():
        problems.append("reply must not be empty")
    if not isinstance(obj.story, dict) or not obj.story:
        problems.append("story must be the full document object")
    return problems


def merge(ctx: TurnContext, story: dict) -> StoryDoc:
    """The model's document over the current one (top-level fields it left out
    are kept), normalized, with server-owned image fields and lost ref_ids
    carried over by key."""
    base = dump(ctx.doc)
    base.update({k: v for k, v in (story or {}).items() if k in StoryDoc.model_fields})
    doc = normalize(base, default_format=ctx.format)
    old_cast = {c.key: c for c in ctx.doc.characters}
    old_env = {e.key: e for e in ctx.doc.environments}
    for entry in doc.characters:
        if entry.ref_id is None and entry.key in old_cast:
            entry.ref_id = old_cast[entry.key].ref_id
    for entry in doc.environments:
        if entry.ref_id is None and entry.key in old_env:
            entry.ref_id = old_env[entry.key].ref_id
    return carry_images(ctx.doc, doc)


async def run_turn(db: Session, ctx: TurnContext, message: str, user_id: int) -> TurnResult:
    """Ask the director. ``db`` is only used for the model settings and the
    token usage row; pass a session with no open transaction of the caller's."""
    from app.services.storyscript import llm
    from app.services.storyscript.errors import InvalidLLMOutput, LLMCallFailed, LLMNotConfigured, StoryScriptError

    try:
        obj, choice = await llm.complete_json(
            db, system=system_prompt(ctx.format), prompt=build_prompt(ctx, message), schema=DirectorTurn,
            feature=FEATURE, validate=_validate, max_tokens=MAX_TOKENS, temperature=0.8, max_retries=1,
            user_id=user_id,
        )
    except LLMNotConfigured:
        logger.exception(f"Story Room thread {ctx.thread_id}: no LLM is configured")
        raise DirectorUnavailable("The story director is not available right now. Please try again later.")
    except InvalidLLMOutput as exc:
        logger.warning(f"Story Room thread {ctx.thread_id}: unusable director output ({exc.last_error[:300]})")
        raise DirectorUnavailable("The director's answer could not be used. Please try again.")
    except LLMCallFailed:
        logger.exception(f"Story Room thread {ctx.thread_id}: the director call failed")
        raise DirectorUnavailable("The story director could not be reached. Please try again in a moment.")
    except StoryScriptError:
        logger.exception(f"Story Room thread {ctx.thread_id}: the director call failed")
        raise DirectorUnavailable("The story director could not be reached. Please try again in a moment.")
    try:
        return _result(ctx, obj, choice.label)
    except Exception:
        logger.exception(f"Story Room thread {ctx.thread_id}: the director's document could not be repaired")
        raise DirectorUnavailable("The director's answer could not be used. Please try again.")


def _result(ctx: TurnContext, obj: DirectorTurn, model: str) -> TurnResult:
    """The merged document with the plan checks applied, memory and title capped."""
    doc = apply_lint(merge(ctx, obj.story))
    memory = (obj.memory or ctx.memory or "").strip()
    if len(memory) > MEMORY_CHARS:
        memory = memory[:MEMORY_CHARS].rsplit(" ", 1)[0]
    title = (obj.title or doc.title or "").strip()[:200]
    return TurnResult(reply=obj.reply.strip()[:20000], doc=doc, memory=memory, title=title, model=model)


def _held_back(text: str) -> int:
    """How many characters at the end of ``text`` could be the start of the
    marker, so they are not shown until the next chunk settles it."""
    for k in range(min(len(STORY_MARKER) - 1, len(text)), 0, -1):
        if text.endswith(STORY_MARKER[:k]):
            return k
    return 0


def _mend_json(text: str) -> str:
    """Fix the slips a model makes without the provider's JSON mode: a comma
    before ``}`` or ``]``, and raw line breaks or tabs inside strings. Only
    characters outside strings are dropped, so string content is kept."""
    out: list[str] = []
    in_str = escaped = False
    for i, ch in enumerate(text):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            elif ch in "\n\r\t":
                out.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[ch])
                continue
            out.append(ch)
            continue
        if ch == '"':
            in_str = True
        elif ch == ",":
            rest = text[i + 1:].lstrip()
            if rest[:1] in ("}", "]"):
                continue
        out.append(ch)
    return "".join(out)


def _load_streamed_json(raw_json: str) -> Any:
    """The JSON part of a streamed answer, mended once if it does not parse."""
    from app.services.storyscript.llm import extract_json

    try:
        return extract_json(raw_json)
    except json.JSONDecodeError as exc:
        around = exc.doc[max(0, exc.pos - 80):exc.pos + 40].replace("\n", " ")
        try:
            data = extract_json(_mend_json(raw_json))
        except json.JSONDecodeError:
            logger.warning(f"Story Room streamed JSON did not parse near: {around!r}")
            raise
        logger.info(f"Story Room streamed JSON mended near: {around!r}")
        return data


def _parse_streamed(ctx: TurnContext, reply: str, raw_json: str, model: str) -> TurnResult:
    """The streamed answer as a TurnResult; ValueError when it cannot be used."""
    data = _load_streamed_json(raw_json)
    if not isinstance(data, dict):
        raise ValueError("The JSON part is not an object")
    if "reply" in data and not reply:
        # The model ignored the format and wrote the whole turn as one object.
        reply = str(data.get("reply") or "")
    obj = DirectorTurn.model_validate({"reply": reply, **{k: data[k] for k in ("story", "memory", "title") if k in data}})
    problems = _validate(obj)
    if problems:
        raise ValueError("; ".join(problems))
    return _result(ctx, obj, model)


async def stream_turn(db: Session, ctx: TurnContext, message: str, user_id: int):
    """Ask the director with a streamed answer. Yields ``(kind, payload)``:

    - ``("delta", text)``: reply text as it is written (never the marker);
    - ``("status", text)``: once the reply is complete and the document is being written;
    - ``("replace", text)``: the reply from the non-streamed fallback, which replaces what was shown;
    - ``("result", TurnResult)``: last.

    An answer whose JSON part is missing or unusable falls back once to
    ``run_turn`` (JSON mode with validation and a retry). Failures raise
    DirectorUnavailable with the same sentences as run_turn. ``db`` is used as
    in run_turn.
    """
    from app.clients.litellm_client import stream_completion
    from app.services.storyscript import llm
    from app.services.storyscript.errors import LLMNotConfigured

    try:
        choice = llm.resolve_model(db)
    except LLMNotConfigured:
        logger.exception(f"Story Room thread {ctx.thread_id}: no LLM is configured")
        raise DirectorUnavailable("The story director is not available right now. Please try again later.")

    text = ""
    shown = 0           # characters of the reply already sent as deltas
    marker_at = -1
    as_json = None      # the answer opened with JSON instead of prose: show nothing of it
    try:
        async for piece in stream_completion(
            prompt=build_prompt(ctx, message), model_name=choice.model, provider_name=choice.provider, db=db,
            max_tokens=MAX_TOKENS, temperature=0.8, system_prompt=stream_system_prompt(ctx.format),
            feature=FEATURE, user_id=user_id,
        ):
            text += piece
            if marker_at >= 0:
                continue
            if as_json is None and text.strip():
                as_json = text.lstrip()[0] in "{`"
            found = text.find(STORY_MARKER, max(0, shown - len(STORY_MARKER)))
            if found >= 0:
                marker_at = found
                if not as_json and text[shown:found].rstrip():
                    yield ("delta", text[shown:found].rstrip())
                shown = found
                yield ("status", STATUS_UPDATING)
            elif not as_json:
                safe = len(text) - _held_back(text)
                if safe > shown:
                    yield ("delta", text[shown:safe])
                    shown = safe
    except ValueError:
        # generate_completion's convention: a missing key or settings row.
        logger.exception(f"Story Room thread {ctx.thread_id}: the director is not configured")
        raise DirectorUnavailable(
            "The story director needs a language model key. Add one in Settings, under API keys, "
            "or choose another model under AI model."
        )
    except Exception as exc:
        logger.exception(f"Story Room thread {ctx.thread_id}: the streamed director call failed")
        from app.clients.litellm_client import LLM_KEY_REJECTED, is_llm_auth_error

        if is_llm_auth_error(exc):
            raise DirectorUnavailable(LLM_KEY_REJECTED)
        raise DirectorUnavailable("The story director could not be reached. Please try again in a moment.")

    try:
        if marker_at >= 0:
            reply = "" if as_json else text[:marker_at].strip()
            result = _parse_streamed(ctx, reply, text[marker_at + len(STORY_MARKER):], choice.label)
        elif as_json:
            result = _parse_streamed(ctx, "", text, choice.label)
        else:
            raise ValueError("The answer has no story marker")
    except Exception as exc:
        logger.warning(f"Story Room thread {ctx.thread_id}: streamed answer unusable "
                       f"({type(exc).__name__}: {str(exc)[:200]}), asking again without streaming")
        if marker_at < 0:
            yield ("status", STATUS_UPDATING)
        result = await run_turn(db, ctx, message, user_id)
        yield ("replace", result.reply)
        yield ("result", result)
        return
    if as_json:
        yield ("replace", result.reply)
    yield ("result", result)
