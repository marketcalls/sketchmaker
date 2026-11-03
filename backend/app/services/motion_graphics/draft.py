"""Brief to spec with the platform LLM (storyscript's complete_json path:
APISettings default provider and model, schema in the prompt, validation
errors fed back for up to two retries).

The model picks a template and style (unless the user fixed them) and fills
the typed slots within their limits. It never invents data: when the user
pasted a table, the table is attached as is and the model only writes the
words around it; numbers in slots must come from the brief. Sources are
taken from the brief; a data video without one is flagged for the user.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.services.storyscript.llm import complete_json

from .data import parse_csv, validate_table
from .design import STYLES
from .spec import TEMPLATES, DataTable, Scene, Spec, normalize, validate


class DraftScene(BaseModel):
    type: str
    slots: dict[str, Any] = Field(default_factory=dict)
    voiceover: Optional[str] = None


class DraftOut(BaseModel):
    template_id: str
    style_id: str
    title: str = Field(max_length=120)
    scenes: list[DraftScene] = Field(min_length=1, max_length=20)
    source: Optional[str] = None
    music_mood: Optional[str] = None
    notes: Optional[str] = None


def _catalog_text(template_id: Optional[str]) -> str:
    lines = []
    for t in TEMPLATES.values():
        if template_id and t.id != template_id:
            continue
        lines.append(f"TEMPLATE {t.id} ({t.name}): {t.description} Aspects {', '.join(t.aspects)}; "
                     f"length {t.length[0]} to {t.length[1]} s; data: {t.data_kind or 'none'}; "
                     f"source required: {t.requires_source}.")
        for st in t.scene_types:
            slots = []
            for s in st.slots:
                lim = []
                if s.max_chars:
                    lim.append(f"max {s.max_chars} chars")
                if s.max_words:
                    lim.append(f"max {s.max_words} words")
                if s.item_fields:
                    lim.append("list of {" + ", ".join(f.key for f in s.item_fields) + "}")
                if s.choices:
                    lim.append("one of " + "/".join(s.choices))
                slots.append(f"{s.key}:{s.kind}{'*' if s.required else ''}" + (f" ({'; '.join(lim)})" if lim else ""))
            lines.append(f"  scene '{st.type}' x{st.min_count}..{st.max_count}: " + ", ".join(slots))
    lines.append("SHARED scene 'end_card' x0..1: headline:text* (max 48 chars), cta:text (max 24), url:text")
    return "\n".join(lines)


SYSTEM = """You are a senior motion designer and editor writing short animated text and data videos.
Pick the best template and style for the brief, then fill every scene's slots.
Rules:
- Obey every slot limit (characters and words). Hooks are at most 7 words and state the payoff.
- Plain words on screen. No emoji, no hashtags, no em dashes or en dashes.
- Never invent statistics, quotes or sources. Numbers in slots must appear in the brief or the data.
  If a data template needs numbers the brief does not give, choose a text template instead.
- source: the publisher or dataset named in the brief, else null.
- Kinetic quotes: only quote the person the brief names; split the quote into beats of 1 to 6 words, mark 1 or 2 emphasis words per beat.
- voiceover (optional, per scene): a short spoken line that adds context instead of reading the screen verbatim; null when silent.
- Images are uploaded by the user later; for listicle items you may write an image_prompt describing a clean photo or illustration.
- style_id is one of: {styles}.
- music_mood is one of: uplifting, documentary, epic, lofi, playful, suspense, melancholy, none.
"""


async def draft_spec(db, *, brief: str, template_id: Optional[str] = None, style_id: Optional[str] = None,
                     data_csv: Optional[str] = None, length_seconds: Optional[int] = None, aspect: str = "9:16",
                     seed: Optional[int] = None, voiceover: bool = False, user_id: Optional[int] = None) -> tuple[Spec, dict]:
    """(spec, info) where info = {template_id, style_id, music_mood, notes, validation}."""
    table = parse_csv(data_csv) if data_csv else None
    data_hint = ""
    if table and table.get("rows"):
        preview = [table["columns"]] + table["rows"][:8]
        data_hint = ("\nThe user attached this table (it will be used as is; do not repeat its numbers, "
                     "write titles, notes and takeaways around it):\n" + json.dumps(preview)[:3000])
    fixed = ""
    if template_id:
        fixed += f"\nUse template_id '{template_id}'."
    if style_id:
        fixed += f"\nUse style_id '{style_id}'."
    target = f"\nTarget length about {length_seconds} seconds." if length_seconds else ""
    vo = "\nWrite a voiceover line for each spoken scene." if voiceover else "\nLeave voiceover null."
    prompt = (f"BRIEF:\n{brief.strip()[:4000]}\n\nAspect {aspect}.{target}{fixed}{vo}{data_hint}\n\n"
              f"CATALOG:\n{_catalog_text(template_id)}")
    system = SYSTEM.replace("{styles}", ", ".join(STYLES))

    def check(out: DraftOut) -> list[str]:
        problems = []
        tid = template_id or out.template_id
        if tid not in TEMPLATES:
            return [f"template_id must be one of {', '.join(TEMPLATES)}"]
        if out.style_id not in STYLES and not style_id:
            problems.append(f"style_id must be one of {', '.join(STYLES)}")
        spec = _to_spec(out, tid, style_id, table, seed)
        rep = validate(spec)
        for e in rep["errors"]:
            if e.get("slot") in ("data", "source"):
                continue
            problems.append(e["message"])
        return problems[:12]

    out, choice = await complete_json(db, system=system, prompt=prompt, schema=DraftOut, feature="motion_graphics_draft",
                                      validate=check, temperature=0.7, user_id=user_id, max_tokens=4096)
    tid = template_id or out.template_id
    spec = _to_spec(out, tid, style_id, table, seed)
    rep = validate(spec)
    info = {"template_id": tid, "style_id": spec.style_id, "music_mood": out.music_mood, "notes": out.notes,
            "model": choice.label, "validation": rep}
    return spec, info


def _to_spec(out: DraftOut, tid: str, style_id: Optional[str], table: Optional[dict], seed: Optional[int]) -> Spec:
    tpl = TEMPLATES[tid]
    scenes = []
    for s in out.scenes:
        if tpl.scene_type(s.type) is None:
            continue
        slots = {k: v for k, v in (s.slots or {}).items() if v not in (None, "")}
        # The model's output is untrusted: an upload reference it invents
        # never resolves (ids are looked up in the project's own uploads), and
        # over-long text is cut to the spec's hard bounds instead of failing.
        scenes.append(Scene(type=s.type[:30], slots=slots, voiceover=(s.voiceover or "")[:2000] or None))
    data = DataTable(**table) if table and table.get("rows") else None
    if data is None and tpl.sample_data and tpl.data_kind in ("race", "series", "tickers"):
        data = None
    spec = Spec(template_id=tid, style_id=style_id or (out.style_id if out.style_id in STYLES else tpl.default_style),
                title=out.title[:120], scenes=scenes[:24], data=data, source=((out.source or "")[:160] or None),
                **({"seed": seed} if seed else {}))
    return normalize(spec)


def data_report(kind: Optional[str], csv_text: str) -> dict:
    table = parse_csv(csv_text)
    view = validate_table(kind, table) if kind else {"ok": True, "problems": [], "warnings": []}
    return {"table": table, "view": view}
