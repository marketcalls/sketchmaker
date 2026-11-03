"""compliance_check: deterministic policy flags for a script and its cast.

Severity: ``block`` stops paid steps and publishing until fixed, ``warn``
needs a human decision, ``info`` is advice (mostly platform disclosure).
"""

from __future__ import annotations

import re

from . import policy
from .models import CharacterBrief, ComplianceFlag, Scene, Script, Template
from .templates import STOCK_VOICES, get_template

_SEVERITY_ORDER = {"block": 0, "warn": 1, "info": 2}


def _as_script(script) -> Script:
    if isinstance(script, Script):
        return script
    if isinstance(script, dict):
        return Script.model_validate(script)
    return Script.model_validate(script, from_attributes=True)


def _as_cast(cast) -> list[CharacterBrief]:
    out = []
    for c in cast or []:
        if isinstance(c, CharacterBrief):
            out.append(c)
        elif isinstance(c, dict):
            out.append(CharacterBrief.model_validate(c))
        else:
            out.append(CharacterBrief.model_validate(c, from_attributes=True))
    return out


def _spoken(s: Scene) -> str:
    return " ".join([s.narration] + [d.text for d in s.dialogue])


def _scene_text(s: Scene) -> str:
    return " ".join([_spoken(s), s.on_screen_text or "", s.shot.direction or ""])


def _bible_flag(c: CharacterBrief, kind: str, threshold: float = 0.5) -> float:
    if not c.bible:
        return 0.0
    best = 0.0
    for f in c.bible.safety_flags:
        if f.kind == kind and f.confidence >= threshold:
            best = max(best, f.confidence)
    return best


def compliance_check(script, cast) -> list[ComplianceFlag]:
    """Policy flags for a script, most severe first.

    ``script`` is a Script (or its dict); ``cast`` a list of CharacterBrief
    (or dicts or ORM rows) for the characters the script may use.
    """
    s = _as_script(script)
    cast_l = _as_cast(cast)
    try:
        tpl: Template | None = get_template(s.template_id)
    except KeyError:
        tpl = None
    flags: list[ComplianceFlag] = []

    def add(code, severity, message, advice="", scene_id=None, character_id=None, platform=None):
        flags.append(ComplianceFlag(code=code, severity=severity, message=message, advice=advice,
                                    scene_id=scene_id, character_id=character_id, platform=platform))

    by_id = {c.id: c for c in cast_l}
    in_script = set(s.cast_ids) | {cid for sc in s.scenes for cid in sc.shot.characters} | {
        d.character_id for sc in s.scenes for d in sc.dialogue}
    used_cast = [c for c in cast_l if c.id in in_script] or cast_l
    all_text = " ".join([s.title, s.logline, s.premise, s.outcome, s.ending_line, s.outro_title]
                        + [_scene_text(sc) for sc in s.scenes])
    sourced_scene_ids = {sc.id for sc in s.scenes if sc.sources}

    # 1. Real people: likeness without consent; minors; public figures.
    for c in used_cast:
        looks_real = c.is_real_person or _bible_flag(c, "real_person", 0.6) > 0
        if c.is_real_person and not (c.is_user_self or c.consent_attested):
            add("likeness_without_consent", "block",
                f"{c.name} is built from a real person with no consent on file.",
                "Attest consent from the person (scope and revocation) or replace the character.",
                character_id=c.id)
        elif looks_real and not c.is_real_person:
            add("possible_real_person", "warn",
                f"{c.name}'s reference images look like a real person.",
                "If this is a real person, mark it and attest consent; otherwise use a clearly fictional design.",
                character_id=c.id)
        elif c.is_real_person:
            add("real_person_consented", "info",
                f"{c.name} is a real person with consent on file.",
                "Realistic depictions need the altered or synthetic disclosure.", character_id=c.id)

        minor = c.is_minor or _bible_flag(c, "possible_minor") > 0
        if minor and looks_real:
            add("real_minor_likeness", "block",
                f"{c.name} may be a real minor.",
                "Do not build characters from photos of real children.", character_id=c.id)
        elif minor:
            add("minor_character", "warn",
                f"{c.name} may be a minor.",
                "Keep the story age appropriate: no romance, violence or peril involving the character.",
                character_id=c.id)

        if _bible_flag(c, "copyrighted_character") > 0 or policy.has("copyright", f"{c.name} {c.role}"):
            add("copyrighted_character", "block",
                f"{c.name} looks like or is named after a copyrighted character.",
                "Use an original character design and name.", character_id=c.id)

        public = c.is_public_figure or _bible_flag(c, "public_figure") > 0
        if public:
            lines = " ".join(_scene_text(sc) for sc in s.scenes
                             if c.id in sc.shot.characters or any(d.character_id == c.id for d in sc.dialogue))
            if policy.has("endorse", lines):
                add("public_figure_endorsement", "block",
                    f"{c.name} is a public figure shown endorsing something.",
                    "Public figures can never appear to endorse a product, service or cause.",
                    character_id=c.id)
            if policy.has("death", lines) or policy.has("event", lines):
                add("public_figure_fake_event", "block",
                    f"{c.name} is a public figure placed in an event (death, arrest, scandal or announcement).",
                    "Never invent events involving real public figures.", character_id=c.id)
            add("public_figure_in_cast", "warn",
                f"{c.name} is or resembles a public figure.",
                "Only with documented consent, and never in endorsements or invented events.",
                character_id=c.id)

    # 2. Public figures named in the text.
    for sc in s.scenes:
        text = _scene_text(sc)
        names = policy.find("public", text)
        if not names:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for name in names:
            near = " ".join(x for x in sentences if name in x.lower())
            if policy.has("death", near) and sc.id not in sourced_scene_ids:
                add("fake_celebrity_death", "block",
                    f"A death or killing is tied to {name.title()} without a cited source.",
                    "Never depict or claim a real person's death unless it is reported fact with a source.",
                    scene_id=sc.id)
            elif policy.has("endorse", near):
                add("public_figure_endorsement", "block",
                    f"{name.title()} appears to endorse something.",
                    "Remove the endorsement.", scene_id=sc.id)
            elif policy.has("event", near) and sc.id not in sourced_scene_ids:
                add("public_figure_fake_event", "block",
                    f"An unsourced event is tied to {name.title()}.",
                    "Cite a provided fact or remove the claim.", scene_id=sc.id)
            elif name in (sc.shot.direction or "").lower():
                add("public_figure_depicted", "warn",
                    f"{name.title()} is depicted in the visuals.",
                    "Do not depict real public figures; show places or objects instead.", scene_id=sc.id)

    # 3. Disasters: fabricated or realistic without context.
    realistic = policy.is_realistic(s, tpl, cast_l)
    for sc in s.scenes:
        if not policy.has("disaster", _scene_text(sc)):
            continue
        if s.fact_mode and sc.id not in sourced_scene_ids:
            add("unsourced_disaster", "block",
                "A disaster is described without a cited source.",
                "Cite a provided fact or remove it. Fake disasters are not allowed.", scene_id=sc.id)
        elif not s.fact_mode and realistic:
            add("realistic_fictional_disaster", "warn",
                "A realistic looking fictional disaster may be taken as real.",
                "Use a stylized look or add a clear fiction label.", scene_id=sc.id)

    # 4. AI expert personas giving health, legal, finance or political advice.
    experts = [c for c in used_cast if policy.has("expert", f"{c.role} {c.personality} {c.name}")]
    narrator_expert = re.search(r"\b(?:as an?|i am an?|i'm an?)\s+(?:doctor|physician|nurse|lawyer|attorney|"
                                r"financial (?:advisor|adviser)|therapist|pharmacist|accountant)\b",
                                all_text, re.I)
    for sc in s.scenes:
        for c in experts:
            said = " ".join(d.text for d in sc.dialogue if d.character_id == c.id)
            if said and policy.has("advice", said):
                add("expert_persona_advice", "block",
                    f"{c.name} is presented as an expert ({c.role or 'expert'}) and gives advice.",
                    "AI personas must not pose as doctors, lawyers, financial or political experts giving advice.",
                    scene_id=sc.id, character_id=c.id)
        if narrator_expert and policy.has("advice", sc.narration):
            add("expert_persona_advice", "block",
                "The narrator claims an expert identity and gives advice.",
                "Remove the expert claim and the advice.", scene_id=sc.id)
        elif policy.has("advice", _spoken(sc)) and policy.has("hfp", _spoken(sc)):
            add("advice_content", "warn",
                "The script gives health, legal, financial or political advice.",
                "Keep it general information, add a not-advice note, and never frame it as expert advice.",
                scene_id=sc.id)
    for c in experts:
        if not any(f.code == "expert_persona_advice" and f.character_id == c.id for f in flags):
            add("expert_persona", "warn",
                f"{c.name} is framed as an expert ({c.role or 'expert'}).",
                "Fine as a story role; never let the character give real advice.", character_id=c.id)

    # 5. Animal distress, peril and shock.
    animal_cast = [c for c in used_cast if policy.is_animal(c)]
    animal_tpl = tpl is not None and tpl.id == "animal_comedy"
    for sc in s.scenes:
        text = _scene_text(sc)
        has_animal = animal_tpl or bool(animal_cast) or policy.has("animal", text)
        if has_animal and policy.has("animal_distress", text):
            add("animal_distress", "block" if animal_tpl else "warn",
                "An animal is shown in distress or harm: " + ", ".join(policy.find("animal_distress", text)) + ".",
                "Animal distress formats fail platform policy. Keep the humor in absurdity, never suffering.",
                scene_id=sc.id)
        elif has_animal and policy.has("animal_peril", text):
            add("animal_peril", "warn" if animal_tpl else "info",
                "An animal may appear to be in peril: " + ", ".join(policy.find("animal_peril", text)) + ".",
                "Make sure the animal is never frightened or in danger on screen.", scene_id=sc.id)
        if policy.has("shock", text):
            add("shock_content", "block" if (tpl and tpl.kids_safe) else "warn",
                "Shock or gore content: " + ", ".join(policy.find("shock", text)) + ".",
                "Shock formats fail platform policy; imply, do not show.", scene_id=sc.id)

    # 6. Kids content.
    if tpl is not None and tpl.kids_safe:
        add("made_for_kids", "info",
            "This template is kids safe; it may be made for kids under COPPA rules.",
            "If the audience is children, mark it made for kids on YouTube (comments and personalized ads are off). "
            "AI kids cartoons are under scrutiny: keep real story and variety.")
        for sc in s.scenes:
            bad = policy.find("kids", _scene_text(sc))
            if bad:
                add("kids_unsafe_content", "warn",
                    "Words not suited to a kids safe template: " + ", ".join(bad) + ".",
                    "Rewrite the scene for young audiences.", scene_id=sc.id)

    # 7. Copyrighted characters and brands in the text and visuals.
    for sc in s.scenes:
        vis = sc.shot.direction or ""
        spoken = _spoken(sc) + " " + (sc.on_screen_text or "")
        for name in policy.find("copyright", vis):
            add("copyrighted_character", "block", f"The visuals show {name.title()}, a copyrighted character.",
                "Replace it with an original character.", scene_id=sc.id)
        for name in policy.find("copyright", spoken):
            if name not in vis.lower():
                add("copyrighted_reference", "warn", f"The script names {name.title()}.",
                    "Mentions can be fine as commentary, but do not build the story around it.", scene_id=sc.id)
        for name in policy.find("brand", vis):
            add("brand_in_visuals", "warn", f"The visuals mention the brand {name.title()}.",
                "Logos and brands are never drawn; describe a generic product.", scene_id=sc.id)
    for name in policy.find("copyright", s.title):
        add("copyrighted_title", "warn", f"The title uses {name.title()}.", "Use an original title.")

    # 8. Real crime and fact mode.
    if s.fact_mode and (s.needs_facts or not s.facts):
        add("fact_mode_missing_facts", "block",
            "This template requires sourced facts and none were provided.",
            "Add facts with sources, answer the scene questions, and redraft before voicing.")
    if tpl is not None and tpl.id == "true_crime_sourced" and not s.facts:
        add("real_crime_without_sources", "block",
            "True crime must be a real, sourced case.", "Provide the case record and sources.")
    for sc in s.scenes:
        if sc.questions:
            add("open_fact_questions", "warn", f"{len(sc.questions)} open fact question(s) in this scene.",
                "Answer them with sourced facts before voicing.", scene_id=sc.id)
        if s.fact_mode and sc.notes and "without a cited fact" in sc.notes:
            add("unsourced_claim", "warn", "A specific number has no cited fact.",
                "Cite a provided fact or remove the number.", scene_id=sc.id)
        if not s.fact_mode and policy.has("crime", _spoken(sc)) and realistic:
            add("realistic_crime_fiction", "warn",
                "Realistic crime content without sources may be taken as a real case.",
                "Add a fiction label or use a stylized look.", scene_id=sc.id)

    # 9. Dramatization labels and fiction presented as real.
    if tpl is not None and tpl.dramatization_label and not s.dramatization_label:
        add("missing_dramatization_label", "warn",
            "The dramatization or fiction label is missing.",
            f"Show this card at the start: {tpl.dramatization_label}")
    elif s.dramatization_label:
        add("dramatization_label", "info", "Show the dramatization card at the start and in the description.",
            s.dramatization_label)
    if (tpl is not None and not tpl.fact_mode) and policy.has("real_claim", all_text):
        add("fiction_presented_as_real", "block",
            "Fiction is presented as a true story.",
            "Remove claims like 'true story' or 'this really happened' from fiction.")
    if s.fact_mode and realistic and not s.dramatization_label:
        add("missing_dramatization_label", "warn",
            "Realistic recreations of real events need a dramatization label.",
            "Add a card: Dramatization. Illustrations are not real images of the people or events.")

    # 10. Voices.
    if s.narrator_voice and s.narrator_voice not in STOCK_VOICES:
        add("custom_voice", "info", "The narrator uses a custom voice.",
            "Voice clones are allowed for your own voice only.")
    for c in used_cast:
        if c.voice_id and c.voice_id not in STOCK_VOICES and not c.is_user_self:
            add("custom_character_voice", "warn",
                f"{c.name} uses a custom voice.",
                "Only stock voices or your own cloned voice are allowed.", character_id=c.id)

    # 11. Platform disclosure advice.
    for d in policy.disclosure_advice(s, tpl, cast_l):
        add(f"disclosure_{d.platform}", "warn" if d.required else "info",
            f"{d.platform.title()}: {d.label}." if d.required else f"{d.platform.title()}: {d.reason}",
            d.reason if d.required else "", platform=d.platform)
    add("ai_provenance", "info",
        "EU AI Act Art. 50 (from 2 August 2026) and California SB 942 expect AI content to be marked.",
        "Keep the AI disclosure line in the description and the export's content credentials.",
        platform="all")

    # De-duplicate (same code, scene and character) and order by severity.
    seen = set()
    unique: list[ComplianceFlag] = []
    for f in flags:
        key = (f.code, f.scene_id, f.character_id, f.message)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    unique.sort(key=lambda f: _SEVERITY_ORDER[f.severity])
    return unique
