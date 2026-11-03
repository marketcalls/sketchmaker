"""Plan checks: problems in a StoryDoc that a video model or an ad review
would catch later, found before anyone spends money on it.

``lint`` returns plain sentences, each starting with ``LINT_PREFIX``.
``apply_lint`` runs after every director turn and every hand edit: it drops
the checks of the last run from ``open_questions`` and adds the current
ones, so a fixed problem disappears and nothing is listed twice. The
director's own questions come first and keep their place.
"""

from __future__ import annotations

import re

from .models import AD_PLACEMENTS, AD_WORD_BUDGETS, MAX_QUESTIONS, Shot, StoryDoc

LINT_PREFIX = "Plan check: "
WORDS_PER_SECOND = 2.5
MAX_IDENTITIES = 2
MAX_WARNINGS = 6
# Seconds an ad's shots may differ from its placement length.
RUNTIME_TOLERANCE = 0.5

_CTA_PURPOSES = ("cta", "call_to_action", "brand", "end_card", "endcard", "packshot", "pack_shot", "close")


def _words(text: str) -> int:
    return len(re.findall(r"[\w'’-]+", text or ""))


def spoken_words(shot: Shot) -> int:
    """Words spoken in a shot: its dialogue and its voiceover."""
    return sum(_words(d.line) for d in shot.dialogue) + _words(shot.voiceover)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


def _ends_on_cta(doc: StoryDoc) -> bool:
    scenes = [s for s in doc.scenes if s.shots]
    if not scenes:
        return True
    scene, shot = scenes[-1], scenes[-1].shots[-1]
    purpose = _slug(scene.purpose)
    if any(p in purpose for p in _CTA_PURPOSES):
        return True
    cta = (doc.ad.cta if doc.ad else "").strip().lower()
    if not cta:
        return False
    spoken = " ".join([shot.on_screen_text, shot.voiceover] + [d.line for d in shot.dialogue]).lower()
    return cta in spoken


def lint(doc: StoryDoc) -> list[str]:
    """The plan checks that apply to ``doc`` now, at most MAX_WARNINGS."""
    out: list[str] = []
    shots = doc.all_shots()
    for _, shot in shots:
        words = spoken_words(shot)
        fits = int(WORDS_PER_SECOND * shot.duration_seconds)
        if words > fits + 1:
            out.append(f"Shot {shot.id} has {words} spoken words in {shot.duration_seconds:g} seconds; about "
                       f"{fits} fit at a natural pace. Trim the line or lengthen the shot.")
        if len(shot.characters) > MAX_IDENTITIES:
            out.append(f"Shot {shot.id} has {len(shot.characters)} characters in frame. Video models keep at most "
                       f"two faces consistent, so split the shot or keep the extras unnamed.")
        if shot.b_roll and shot.dialogue:
            out.append(f"Shot {shot.id} is B-roll but has dialogue to lip sync. Move the line to voiceover or "
                       f"onto a shot of the speaker.")

    if doc.format == "ad" and shots:
        if not any(shot.type == "insert" or shot.props for _, shot in shots):
            out.append("This ad has no insert or hero shot of the product. Add one that shows it clearly.")
        if not _ends_on_cta(doc):
            out.append("This ad does not end on the call to action. Close on the brand beat with the CTA "
                       "in the last shot.")
        target = doc.target_seconds
        if target not in AD_PLACEMENTS and target != 60:
            out.append(f"Ad placements run exactly 6, 15 or 30 seconds; this ad is set to {target}.")
        runtime = doc.total_seconds()
        if abs(runtime - target) > RUNTIME_TOLERANCE:
            out.append(f"The shots add up to {runtime:g} seconds but the ad runs {target}. Make them add "
                       f"up exactly.")
        budget = AD_WORD_BUDGETS.get(target)
        words = sum(spoken_words(shot) for _, shot in shots)
        if budget and words > budget[1] + max(2, budget[1] // 10):
            out.append(f"The ad has {words} spoken words; a {target} second spot holds about {budget[0]} to "
                       f"{budget[1]}. Cut the script.")

    unique: list[str] = []
    for sentence in out:
        line = LINT_PREFIX + sentence
        if line not in unique:
            unique.append(line)
    return unique[:MAX_WARNINGS]


def apply_lint(doc: StoryDoc) -> StoryDoc:
    """``doc`` with the current plan checks in ``open_questions`` (see the module docstring)."""
    kept = [q for q in doc.open_questions if not q.startswith(LINT_PREFIX)]
    found = lint(doc)
    merged: list[str] = []
    for q in kept[:max(0, MAX_QUESTIONS - len(found))] + found:
        if q not in merged:
            merged.append(q)
    doc.open_questions = merged[:MAX_QUESTIONS]
    return doc
