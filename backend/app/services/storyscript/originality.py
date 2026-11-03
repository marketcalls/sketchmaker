"""originality_check: compare a script with the channel's or series' last N.

Cheap deterministic features only (no LLM): normalized n-gram overlap on the
premise, outcome and narration, edit-distance similarity on the beat sequence
and shot list, and title shape. YouTube's July 2026 inauthentic content
clarification fails "same situation, same outcome" character repeats, so that
case is flagged explicitly.
"""

from __future__ import annotations

from typing import Any

from .models import OriginalityMatch, OriginalityReport
from .templates import get_template
from .text import (
    containment, ngrams, normalize_tokens, sequence_similarity, text_similarity, title_pattern,
)

# Feature weights (renormalized over the features both scripts have).
WEIGHTS = {
    "premise": 0.25,
    "outcome": 0.20,
    "narration": 0.20,
    "beats": 0.10,
    "shots": 0.10,
    "title": 0.10,
    "visuals": 0.05,
}
SAME_SITUATION = 0.35
SAME_OUTCOME = 0.35


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class _Features:
    def __init__(self, src: Any):
        scenes = _get(src, "scenes") or []
        self.title = (_get(src, "title") or "").strip()
        self.situation = (_get(src, "situation") or "").strip()
        self.premise = " ".join(x for x in [_get(src, "premise") or "", _get(src, "logline") or "",
                                            self.situation] if x).strip()
        last = scenes[-1] if scenes else None
        last_narr = (_get(last, "narration") or "") if last is not None else ""
        self.outcome = " ".join(x for x in [_get(src, "outcome") or "", _get(src, "ending_line") or "",
                                            last_narr] if x).strip()
        self.outcome_core = (_get(src, "outcome") or "").strip() or self.outcome
        self.hook = (_get(src, "hook_formula") or "").strip()
        spoken, visuals, beats, shots = [], [], [], []
        for sc in scenes:
            spoken.append(_get(sc, "narration") or "")
            for d in _get(sc, "dialogue") or []:
                spoken.append(_get(d, "text") or "")
            shot = _get(sc, "shot") or {}
            visuals.append(_get(shot, "direction") or "")
            beats.append(str(_get(sc, "beat") or ""))
            chars = ",".join(sorted(_get(shot, "characters") or []))
            shots.append(f"{_get(shot, 'camera') or ''}:{_get(shot, 'kind') or ''}:{chars}")
        self.spoken_tokens = normalize_tokens(" ".join(spoken))
        self.visual_tokens = normalize_tokens(" ".join(visuals))
        self.beats = [b for b in beats if b]
        self.shots = shots
        self.template_id = _get(src, "template_id") or ""


def _compare(a: _Features, b: _Features) -> dict[str, float]:
    f: dict[str, float] = {}
    if a.premise and b.premise:
        sim = text_similarity(a.premise, b.premise)
        if a.situation and b.situation and a.situation.lower() == b.situation.lower():
            sim = max(sim, 0.6)
        f["premise"] = sim
    if a.outcome_core and b.outcome_core:
        f["outcome"] = max(text_similarity(a.outcome_core, b.outcome_core),
                           0.8 * text_similarity(a.outcome, b.outcome))
    if a.spoken_tokens and b.spoken_tokens:
        f["narration"] = round(max(containment(ngrams(a.spoken_tokens, 3), ngrams(b.spoken_tokens, 3)),
                                   0.6 * containment(ngrams(a.spoken_tokens, 2), ngrams(b.spoken_tokens, 2))), 4)
    if a.beats and b.beats:
        seq = sequence_similarity(a.beats, b.beats)
        # Same template means same beat ids by design; that alone is a consistent
        # format, not a repeat. Weight it with the hook formula.
        hook_same = 1.0 if (a.hook and a.hook == b.hook) else 0.0
        f["beats"] = round(0.6 * seq + 0.4 * hook_same, 4) if a.hook and b.hook else round(seq, 4)
    if a.shots and b.shots:
        f["shots"] = round(sequence_similarity(a.shots, b.shots), 4)
    if a.title and b.title:
        f["title"] = round(0.5 * sequence_similarity(title_pattern(a.title).split(), title_pattern(b.title).split())
                           + 0.5 * text_similarity(a.title, b.title), 4)
    if a.visual_tokens and b.visual_tokens:
        f["visuals"] = round(containment(ngrams(a.visual_tokens, 2), ngrams(b.visual_tokens, 2)), 4)
    return f


def _weighted(f: dict[str, float]) -> float:
    total = sum(WEIGHTS[k] for k in f)
    if not total:
        return 0.0
    return sum(WEIGHTS[k] * v for k, v in f.items()) / total


def _shared_phrases(a: _Features, b: _Features, limit: int = 3) -> list[str]:
    common = ngrams(a.spoken_tokens, 4) & ngrams(b.spoken_tokens, 4)
    return [" ".join(g) for g in sorted(common)[:limit]]


def originality_check(script, previous_scripts) -> OriginalityReport:
    """Score 0 to 100 (100 = original) against previous scripts.

    ``previous_scripts`` is newest last or in any order: Scripts, their dicts,
    or lighter dicts with only title, premise and outcome (EpisodeSummary).
    """
    cur = _Features(script)
    prev = list(previous_scripts or [])
    if not prev:
        return OriginalityReport(score=100, verdict="original", compared=0,
                                 findings=["Nothing to compare with yet."])

    matches: list[tuple[float, int, dict[str, float], _Features]] = []
    for i, p in enumerate(prev):
        pf = _Features(p)
        feats = _compare(cur, pf)
        matches.append((_weighted(feats), i, feats, pf))
    matches.sort(key=lambda m: m[0], reverse=True)

    top_sim = matches[0][0]
    # Repetition across many episodes also counts, not just the single closest.
    top3 = [m[0] for m in matches[:3]]
    blended = 0.75 * top_sim + 0.25 * (sum(top3) / len(top3))
    score = int(round(100 * (1 - blended)))

    findings: list[str] = []
    suggestions: list[str] = []
    ssso_hits = []
    for sim, i, feats, pf in matches:
        name = pf.title or f"script {i + 1}"
        if feats.get("premise", 0) >= SAME_SITUATION and feats.get("outcome", 0) >= SAME_OUTCOME:
            ssso_hits.append(name)
    ssso = bool(ssso_hits)
    if ssso:
        score = min(score, 35)
        findings.append("Same situation, same outcome as: " + "; ".join(ssso_hits[:3])
                        + ". YouTube treats this repeat pattern as inauthentic content.")

    sim, i, feats, pf = matches[0]
    name = pf.title or f"script {i + 1}"
    if feats.get("premise", 0) >= SAME_SITUATION:
        findings.append(f"Premise is {int(feats['premise'] * 100)} percent similar to '{name}'.")
        suggestions.append("Put the characters in a different situation: a new place, a new goal or a new antagonist.")
    if feats.get("outcome", 0) >= SAME_OUTCOME:
        findings.append(f"Outcome is {int(feats['outcome'] * 100)} percent similar to '{name}'.")
        suggestions.append("End differently: flip who wins, add a cost, or leave a new open question.")
    if feats.get("narration", 0) >= 0.2:
        phrases = _shared_phrases(cur, pf)
        findings.append(f"Narration reuses {int(feats['narration'] * 100)} percent of phrases from '{name}'"
                        + (": " + "; ".join(phrases) if phrases else "."))
        suggestions.append("Rewrite repeated lines in fresh words; keep only the series catchphrase.")
    if feats.get("shots", 0) >= 0.7:
        findings.append(f"Shot list is {int(feats['shots'] * 100)} percent the same as '{name}'.")
        suggestions.append("Redraft with a new seed or change camera and framing on several scenes.")
    if feats.get("title", 0) >= 0.7:
        findings.append(f"Title follows the same pattern as '{name}'.")
        suggestions.append("Use a different title formula from the template.")

    hooks = [m[3].hook for m in matches if m[3].hook]
    if cur.hook and hooks:
        same_hook = sum(1 for h in hooks if h == cur.hook)
        if same_hook >= max(2, len(hooks) // 2 + 1):
            findings.append(f"Same hook formula as {same_hook} of the last {len(hooks)} scripts.")
            suggestions.append("Open with a different hook formula.")

    # Suggest unused archetypes from the template's variation pools.
    try:
        tpl = get_template(cur.template_id) if cur.template_id else None
    except KeyError:
        tpl = None
    if tpl and (ssso or feats.get("premise", 0) >= SAME_SITUATION):
        used = {m[3].situation.lower() for m in matches if m[3].situation} | {cur.situation.lower()}
        fresh = [x for x in tpl.situations if x.lower() not in used][:3]
        if fresh:
            suggestions.append("Unused situations for this template: " + "; ".join(fresh) + ".")
    if tpl and (ssso or feats.get("outcome", 0) >= SAME_OUTCOME):
        used_o = " ".join(m[3].outcome_core.lower() for m in matches)
        fresh_o = [x for x in tpl.outcomes if x.lower() not in used_o][:3]
        if fresh_o:
            suggestions.append("Outcome ideas not used recently: " + "; ".join(fresh_o) + ".")

    score = max(0, min(100, score))
    verdict = "original" if score >= 70 and not ssso else ("similar" if score >= 45 and not ssso else "repetitive")
    if not findings:
        findings.append("No close match in the compared scripts.")
    closest = [
        OriginalityMatch(title=m[3].title, index=m[1], similarity=round(m[0], 4), features=m[2])
        for m in matches[:3]
    ]
    # Keep suggestions unique and in order.
    seen, uniq = set(), []
    for s_ in suggestions:
        if s_ not in seen:
            seen.add(s_)
            uniq.append(s_)
    return OriginalityReport(score=score, verdict=verdict, same_situation_same_outcome=ssso,
                             compared=len(prev), closest=closest, findings=findings, suggestions=uniq)

