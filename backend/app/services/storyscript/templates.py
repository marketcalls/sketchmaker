"""Template catalogue: 6 story-telling formats and 10 viral templates.

Data lives in code so it ships with the release and is versioned with the
engine that reads it. Beat timings are fractions of the runtime and are built
contiguously by ``_beats`` so they always cover 0.0 to 1.0 exactly.

Sources: the story-telling project's writing rules and per-format scene jobs,
and the 2025 to 2026 viral faceless research (beats with timings, retention
heuristics, policy). See docs/STUDIO_ARCHITECTURE.md section 2.
"""

from __future__ import annotations

from functools import lru_cache

from .models import Beat, LengthRange, MusicPlan, MusicSection, Template, VoiceStyle

# Appended to every house style. Text is rendered by the app, never by the
# image model: generated lettering is misspelled and cannot be translated.
NO_TEXT_CLAUSE = "no text, no lettering, no logos, no watermark"

# The voices every faceless channel already uses. Never suggested.
OVERUSED_VOICES = ("Rachel", "Brian", "Adam")

# Stock Eleven v4 voices on fal (verified 2026-10-25).
STOCK_VOICES = (
    "Aria", "Roger", "Sarah", "Laura", "Charlie", "George", "Callum", "River",
    "Liam", "Charlotte", "Alice", "Matilda", "Will", "Jessica", "Eric", "Chris",
    "Brian", "Daniel", "Lily", "Bill", "Rachel",
)

SHORTS_MAX_SECONDS = 180
LONG_MAX_SECONDS = 900


def _style(body: str) -> str:
    return f"{body}, {NO_TEXT_CLAUSE}"


def _beats(spec: list[tuple]) -> list[Beat]:
    """Build contiguous beats from (id, name, end_fraction, job[, rehook[, silence]])."""
    out: list[Beat] = []
    start = 0.0
    for row in spec:
        bid, name, end, job = row[0], row[1], row[2], row[3]
        rehook = row[4] if len(row) > 4 else False
        silence = row[5] if len(row) > 5 else 0.0
        out.append(Beat(id=bid, name=name, start=round(start, 4), end=round(end, 4),
                        job=job, rehook=rehook, silence_after=silence))
        start = end
    out[-1].end = 1.0
    return out


def _music(mood: str, pos: list[str], neg: list[str], sections: list[tuple]) -> MusicPlan:
    return MusicPlan(
        mood=mood,
        positive_global_styles=pos,
        negative_global_styles=neg + ["vocals", "lyrics"],
        sections=[
            MusicSection(section_name=n, fraction=f, positive_local_styles=p,
                         negative_local_styles=q)
            for (n, f, p, q) in sections
        ],
    )


_SHORT_ASPECTS = ["9:16", "1:1", "4:5", "16:9"]
_LONG_ASPECTS = ["16:9", "9:16"]

_FORMAT_STYLE = _style(
    "painterly digital illustration, cinematic composition, soft volumetric light, "
    "rich filmic color grade, consistent character design, clean readable silhouettes"
)

_NARRATOR = VoiceStyle(
    wpm=165, stability=0.5, similarity_boost=0.75,
    description="Conversational, warm, spoken out loud, not read",
    suggested_voices=["Daniel", "Matilda", "Callum", "Lily"],
)

_SHORT_MUSIC = _music(
    "light pulse", ["modern underscore", "soft percussion", "steady pulse"],
    ["harsh distortion"],
    [("intro", 0.15, ["sparse", "curious"], []),
     ("body", 0.7, ["building", "driving"], []),
     ("outro", 0.15, ["resolve", "soft landing"], [])],
)


def _build() -> list[Template]:
    t: list[Template] = []

    # ------------------------------------------------------------------
    # The 6 story-telling formats (narrated, 24 to 32 words per scene)
    # ------------------------------------------------------------------
    t.append(Template(
        id="biography", name="Biography",
        pitch="One life in a minute: the end state first, then how they got there.",
        niche="people and history", kind="format",
        aspects=_SHORT_ASPECTS, default_aspect="9:16",
        length=LengthRange(min_seconds=30, default_seconds=60, max_seconds=180), shorts=True,
        beats=_beats([
            ("hook", "Hook: end state", 1 / 6, "Open on where they ended up, the single most striking fact."),
            ("origin", "Origin", 2 / 6, "Where they started, one concrete detail."),
            ("first_move", "First move", 3 / 6, "The first decision that set things in motion."),
            ("setback", "Setback", 4 / 6, "The low point. No stat card here.", True),
            ("big_win", "Big win", 5 / 6, "The breakthrough, with its one number on a stat card."),
            ("landing", "Where it landed", 1.0, "Where it all landed, and what it means now."),
        ]),
        hook_formulas=[
            "Open on the end state: who they became, then ask how.",
            "A bold claim about the person, proven by the rest of the video.",
            "In medias res at the moment everything changed.",
        ],
        rehook_seconds=[18, 42], rehook_every_seconds=30,
        ending="payoff", ending_note="Land the payoff, then a three to five word outro title.",
        shots_per_minute=10, words_per_scene=28, dialogue_mode="narration",
        visual_style=_FORMAT_STYLE, realistic=False, voice=_NARRATOR, music=_SHORT_MUSIC,
        caption_preset="bold_pop", fact_mode=True, stat_cards=True, clip_share=0.15,
        policy_notes=[
            "Every claim comes from the provided facts, dates carry their source.",
            "Depict real people as illustrated, never photoreal, unless consent is attested.",
        ],
        title_formulas=["How {subject} went from {start} to {end}", "The {subject} story nobody tells",
                        "{subject}: the moment everything changed"],
        description_formula="One line on the end state, then the turning point.",
        tags=["biography", "history", "true story"],
        situations=["the unlikely origin", "the setback that almost ended it", "the rival who shaped them",
                    "the one decision", "the forgotten early failure"],
        outcomes=["vindicated late", "triumph with a cost", "legacy bigger than the person", "quiet ending"],
    ))

    t.append(Template(
        id="explainer", name="Explainer",
        pitch="A symptom everyone has seen, named and taken apart in a minute.",
        niche="education", kind="format",
        aspects=_SHORT_ASPECTS, default_aspect="9:16",
        length=LengthRange(min_seconds=30, default_seconds=60, max_seconds=600), shorts=False,
        beats=_beats([
            ("symptom", "Symptom", 1 / 6, "The everyday thing the viewer has noticed."),
            ("name_it", "Name it", 2 / 6, "Give the thing its name."),
            ("mechanism_1", "Mechanism one", 3 / 6, "The first half of how it works.", True),
            ("mechanism_2", "Mechanism two", 4 / 6, "The second half, one idea only."),
            ("what_changes", "What changes", 5 / 6, "What this changes for the viewer."),
            ("what_to_do", "What to do", 1.0, "One clear action or takeaway."),
        ]),
        hook_formulas=["Point at something the viewer saw today and ask why.",
                       "State the counterintuitive answer first.",
                       "Pattern interrupt: a wrong but common explanation, then stop it."],
        rehook_seconds=[18, 42], rehook_every_seconds=60,
        ending="payoff", ending_note="End on the action, then a short outro title.",
        shots_per_minute=10, words_per_scene=28, dialogue_mode="narration",
        visual_style=_FORMAT_STYLE, voice=_NARRATOR, music=_SHORT_MUSIC,
        caption_preset="bold_pop", fact_mode=False, stat_cards=True, clip_share=0.15,
        policy_notes=["No health, legal or financial advice framed as an expert persona."],
        title_formulas=["Why {topic} happens", "{topic}, explained in a minute", "The real reason {topic}"],
        description_formula="The question in one line, then the answer teaser.",
        tags=["explainer", "learn", "science"],
        situations=["everyday annoyance", "hidden system", "common misconception", "surprising origin"],
        outcomes=["simple fix", "it is a feature not a bug", "you have been doing it wrong", "nobody fully knows"],
    ))

    t.append(Template(
        id="reel", name="Reel",
        pitch="Thirty seconds: a hook, the evidence, a turn and a follow.",
        niche="general", kind="format",
        aspects=_SHORT_ASPECTS, default_aspect="9:16",
        length=LengthRange(min_seconds=15, default_seconds=30, max_seconds=60), shorts=True,
        beats=_beats([
            ("hook", "Hook", 1 / 3, "The single most striking fact or claim."),
            ("evidence", "Evidence", 2 / 3, "Why it is true, one concrete proof."),
            ("turn", "Turn and follow", 1.0, "The twist, then a reason to follow."),
        ]),
        hook_formulas=["Bold claim in the first sentence.", "Curiosity gap: name the payoff, withhold it.",
                       "Pattern interrupt: start mid sentence on the surprising part."],
        rehook_seconds=[18], rehook_every_seconds=None,
        ending="loop", ending_note="Last line flows back into the first.",
        shots_per_minute=12, words_per_scene=28, dialogue_mode="narration",
        visual_style=_FORMAT_STYLE, voice=_NARRATOR, music=_SHORT_MUSIC,
        caption_preset="bold_pop", fact_mode=False, stat_cards=True, clip_share=0.25,
        title_formulas=["{topic} in 30 seconds", "Wait for the turn: {topic}", "Nobody expects this about {topic}"],
        tags=["shorts", "reels"],
        situations=["surprising fact", "quick story", "hot take", "before and after"],
        outcomes=["reversal", "confirmation with a twist", "open question"],
    ))

    t.append(Template(
        id="listicle", name="Listicle",
        pitch="A countdown with equal beats, each item a number on a stat card.",
        niche="general", kind="format",
        aspects=_SHORT_ASPECTS, default_aspect="9:16",
        length=LengthRange(min_seconds=30, default_seconds=60, max_seconds=180), shorts=True,
        beats=_beats([
            ("intro", "Intro", 0.12, "Promise the list and its best item."),
            ("item_1", "Item one", 0.296, "Item one, one idea, its number on the stat card."),
            ("item_2", "Item two", 0.472, "Item two, same length as the others."),
            ("item_3", "Item three", 0.648, "Item three, re-hook: the best is still coming.", True),
            ("item_4", "Item four", 0.824, "Item four."),
            ("item_5", "Item five", 0.94, "The best item, as promised."),
            ("closer", "Closer", 1.0, "Short closer that invites a comment."),
        ]),
        hook_formulas=["Promise the most surprising item first, deliver it last.",
                       "Number plus stakes: five things that change how you see the topic."],
        rehook_seconds=[20, 40], rehook_every_seconds=30,
        ending="payoff", ending_note="Equal scene lengths. Item numbers go on the stat card.",
        shots_per_minute=10, words_per_scene=26, dialogue_mode="narration",
        visual_style=_FORMAT_STYLE, voice=_NARRATOR, music=_SHORT_MUSIC,
        caption_preset="bold_pop", fact_mode=False, stat_cards=True, clip_share=0.1,
        policy_notes=["Generic top ten content is saturated: every item needs a specific, surprising angle."],
        title_formulas=["{number} {topic} facts that sound fake", "{number} things about {topic} nobody told you",
                        "Ranking {topic}: number one surprised me"],
        tags=["top 5", "facts", "list"],
        situations=["ranked countdown", "myths versus facts list", "hidden gems", "things that changed history"],
        outcomes=["the best saved for last", "a surprise wildcard", "the viewer picks"],
    ))

    t.append(Template(
        id="news", name="News",
        pitch="What happened, the number, why, who it hits, what next. Every claim dated.",
        niche="news", kind="format",
        aspects=_SHORT_ASPECTS, default_aspect="9:16",
        length=LengthRange(min_seconds=30, default_seconds=45, max_seconds=180), shorts=True,
        beats=_beats([
            ("what_happened", "What happened", 0.2, "The event in one sentence, dated."),
            ("the_number", "The number", 0.4, "The key number, on the stat card, with its source."),
            ("background", "Background", 0.6, "The context that makes it matter.", True),
            ("who_affected", "Who is affected", 0.8, "Who this lands on."),
            ("what_next", "What next", 1.0, "What happens next, with its date if known."),
        ]),
        hook_formulas=["Lead with the event and the date.", "Lead with the number, then what it measures."],
        rehook_seconds=[20, 40], rehook_every_seconds=30,
        ending="payoff", ending_note="End on what happens next, never on speculation.",
        shots_per_minute=10, words_per_scene=28, dialogue_mode="narration",
        visual_style=_FORMAT_STYLE, voice=_NARRATOR.model_copy(update={"wpm": 160}),
        music=_music("neutral news bed", ["minimal pulse", "neutral"], ["dramatic"],
                     [("main", 1.0, ["steady"], [])]),
        caption_preset="bold_pop", fact_mode=True, stat_cards=True, clip_share=0.1,
        policy_notes=[
            "Every claim is dated and taken from the provided facts.",
            "Realistic depictions of real events need the altered or synthetic disclosure.",
            "Never fabricate disasters, deaths or statements.",
        ],
        title_formulas=["{topic}: what happened and what is next", "{topic} explained in 45 seconds",
                        "Why {topic} matters"],
        tags=["news", "update"],
        situations=["breaking update", "policy change", "market move", "local story with wide impact"],
        outcomes=["what to watch next", "open question", "known next date"],
        dramatization_label="Illustrations are dramatizations. Sources in the description.",
    ))

    t.append(Template(
        id="myth_buster", name="Myth buster",
        pitch="The belief, why it spread, the correction with proof, what to do instead.",
        niche="education", kind="format",
        aspects=_SHORT_ASPECTS, default_aspect="9:16",
        length=LengthRange(min_seconds=30, default_seconds=45, max_seconds=180), shorts=True,
        beats=_beats([
            ("belief", "The belief", 0.2, "State the myth as people say it."),
            ("why_spread", "Why it spread", 0.4, "Why it sounds right."),
            ("correction", "Correction", 0.6, "The correction, one number on the stat card.", True),
            ("evidence", "Evidence", 0.8, "The proof, with its source."),
            ("what_to_do", "What to do", 1.0, "What to do instead."),
        ]),
        hook_formulas=["Quote the myth, then: that is wrong.", "Ask the viewer if they believe it, then flip it."],
        rehook_seconds=[20, 40], rehook_every_seconds=30,
        ending="payoff", ending_note="End on the action, not on the myth.",
        shots_per_minute=10, words_per_scene=28, dialogue_mode="narration",
        visual_style=_FORMAT_STYLE, voice=_NARRATOR, music=_SHORT_MUSIC,
        caption_preset="bold_pop", fact_mode=True, stat_cards=True, clip_share=0.1,
        policy_notes=["Corrections must cite a provided fact.",
                      "No health, legal or financial advice framed as an expert persona."],
        title_formulas=["{topic} is a myth", "Stop believing {topic}", "The truth about {topic}"],
        tags=["myth", "facts", "debunk"],
        situations=["health myth", "history myth", "science myth", "money myth"],
        outcomes=["myth fully false", "half true", "true for a different reason"],
    ))

    # ------------------------------------------------------------------
    # The 10 viral templates
    # ------------------------------------------------------------------
    t.append(Template(
        id="micro_drama", name="Micro drama",
        pitch="A recurring cast, a confrontation in the first second, a cliffhanger and a vote.",
        niche="drama series", kind="viral",
        aspects=["9:16", "4:5", "1:1"], default_aspect="9:16",
        length=LengthRange(min_seconds=45, default_seconds=75, max_seconds=180), shorts=True,
        beats=_beats([
            ("cold_open", "Cold open", 0.025, "Drop into a confrontation mid line, no setup."),
            ("recap", "Recap", 0.11, "One line that tells a new viewer who wants what."),
            ("turn_1", "Escalation turn one", 0.26, "First turn: the stakes rise."),
            ("turn_2", "Escalation turn two", 0.41, "Second turn: someone lies or is caught.", True),
            ("turn_3", "Escalation turn three", 0.56, "Third turn: the worst possible moment."),
            ("reveal", "Reveal", 0.83, "The reveal that reframes the episode.", True),
            ("cliffhanger", "Cliffhanger and vote", 1.0, "Freeze on a choice and ask viewers to vote."),
        ]),
        hook_formulas=["In medias res: a slap, a shout or a slammed door, mid sentence.",
                       "A line of dialogue that is a threat or a confession.",
                       "Stakes up front: someone is about to lose everything."],
        rehook_seconds=[17, 42], rehook_every_seconds=30,
        ending="cliffhanger_vote",
        ending_note="End on an unresolved choice with two options; the vote prompt names both.",
        shots_per_minute=15, words_per_scene=None, dialogue_mode="mixed",
        visual_style=_style("stylized 3D animation, soft clay textures, expressive faces, "
                            "dramatic rim light, shallow depth of field, consistent character design"),
        realistic=False,
        voice=VoiceStyle(wpm=160, stability=0.35, description="Character voices with a light narrator",
                         suggested_voices=["Charlotte", "Callum", "Jessica", "Liam", "Alice", "Eric"]),
        music=_music("tense melodrama", ["dramatic strings", "pulsing synth", "tension"], ["happy", "upbeat"],
                     [("tension", 0.55, ["low", "suspense"], []),
                      ("reveal", 0.3, ["swell", "impact"], []),
                      ("cliff", 0.15, ["suspended", "unresolved"], ["resolution"])]),
        caption_preset="karaoke_box", fact_mode=False, stat_cards=False, clip_share=0.35,
        policy_notes=[
            "Each episode needs a new situation and a new outcome; same situation, same outcome repeats fail YouTube's inauthentic content policy.",
            "Stylized, clearly animated look; no real people without consent.",
        ],
        title_formulas=["{character} {turn}... Part {episode}", "She thought no one would find out (Part {episode})",
                        "Who should {character} choose? Episode {episode}"],
        description_formula="One line that restates the cliffhanger, then the vote question.",
        tags=["micro drama", "ai series", "story", "drama"],
        situations=["a secret is overheard", "a gift reaches the wrong person", "a rival arrives uninvited",
                    "a lie is about to be exposed", "a choice between two people", "a mistaken identity",
                    "a stolen idea", "a lost relative returns", "a wedding is interrupted", "a will is read"],
        outcomes=["the underdog wins at a cost", "the villain turns out to be someone else", "an alliance forms",
                  "the plan backfires", "a sacrifice", "a second secret is revealed", "someone walks away"],
    ))

    t.append(Template(
        id="historical_pov", name="Historical POV",
        pitch="POV: you wake up in another century, six sensory beats that get darker, then a twist.",
        niche="history", kind="viral",
        aspects=["9:16", "4:5", "1:1"], default_aspect="9:16",
        length=LengthRange(min_seconds=30, default_seconds=50, max_seconds=90), shorts=True,
        beats=_beats([
            ("pov_hook", "POV hook", 0.06, "POV: you wake up in a year and place. Second person."),
            ("sense_1", "Sense one", 0.18, "A sensory detail: what you see first."),
            ("sense_2", "Sense two", 0.30, "What you smell or hear."),
            ("sense_3", "Sense three", 0.42, "What you eat or wear.", True),
            ("sense_4", "Sense four", 0.54, "Work or danger, slightly darker."),
            ("sense_5", "Sense five", 0.66, "Darker: illness, law or punishment."),
            ("sense_6", "Sense six", 0.78, "Darkest detail."),
            ("twist", "Twist fact", 0.92, "The twist fact that recontextualizes everything."),
            ("loop", "Loop line", 1.0, "A line that leads back into the opening."),
        ]),
        hook_formulas=["POV: you wake up in {year}, {place}.", "POV: you are a {role} in {year}."],
        rehook_seconds=[18, 40], rehook_every_seconds=None,
        ending="loop", ending_note="The last sentence flows into the first, POV restart.",
        # Six sensory beats of about six seconds: scenes come from the shot
        # cadence (about 14 words each), not from the 28-word narrated rule.
        shots_per_minute=11, words_per_scene=None, dialogue_mode="narration",
        visual_style=_style("first person cinematic realism, period accurate details, natural light, "
                            "handheld camera feel, film grain, muted earthy palette"),
        realistic=True,
        voice=VoiceStyle(wpm=150, stability=0.6, description="Calm, second person, intimate",
                         suggested_voices=["Callum", "Matilda", "Will", "Alice"]),
        music=_music("period ambient", ["ambient drone", "period instruments", "sparse"], ["modern beats"],
                     [("dawn", 0.4, ["soft"], []), ("dark", 0.5, ["ominous", "low"], []),
                      ("twist", 0.1, ["sting"], [])]),
        caption_preset="bold_pop", fact_mode=False, stat_cards=False, clip_share=0.3,
        policy_notes=["Historical details should come from provided facts when given; flag invented specifics.",
                      "Realistic recreations of real places and events need the altered or synthetic disclosure."],
        title_formulas=["POV: you wake up in {topic}", "POV: you live in {topic}", "You would not survive {topic}"],
        tags=["pov", "history", "historical"],
        situations=["ancient city", "medieval village", "industrial factory town", "sea voyage",
                    "royal court", "plague year", "frontier settlement"],
        outcomes=["you would not last a week", "surprisingly modern twist", "the twist is about you"],
    ))

    t.append(Template(
        id="sleep_history", name="Sleep history",
        pitch="A slow, soft walk through daily life in another era, made to fall asleep to.",
        niche="history, sleep", kind="viral",
        aspects=["16:9"], default_aspect="16:9",
        length=LengthRange(min_seconds=300, default_seconds=600, max_seconds=900), shorts=False,
        beats=_beats([
            ("arrival", "Arrival", 0.10, "Settle the listener in a place and time, gently."),
            ("morning", "Morning", 0.30, "Morning routines, slow sensory detail."),
            ("work", "Work and trade", 0.50, "How people worked, without tension."),
            ("evening", "Evening", 0.72, "Meals, family, small comforts."),
            ("night", "Night", 0.92, "The world going quiet."),
            ("drift", "Drift off", 1.0, "Softer and slower, an invitation to sleep."),
        ]),
        hook_formulas=["Tonight, we travel to {place}, in the year {year}.",
                       "Get comfortable. We are going back to {place}."],
        rehook_seconds=[], rehook_every_seconds=None,
        ending="payoff", ending_note="No re-hooks, no cliffhanger. Fade softly.",
        shots_per_minute=3, words_per_scene=32, dialogue_mode="narration",
        visual_style=_style("soft painterly oil illustration, warm low light, gentle haze, "
                            "calm composition, muted palette"),
        realistic=False,
        voice=VoiceStyle(wpm=128, stability=0.75, description="Soft, slow, unhurried",
                         suggested_voices=["Lily", "Bill", "Matilda", "George"]),
        music=_music("sleep ambient", ["ambient pads", "soft piano", "slow"], ["drums", "percussion", "loud"],
                     [("settle", 0.2, ["warm"], []), ("drift", 0.8, ["very soft", "sparse"], [])]),
        caption_preset="serif_story", fact_mode=True, stat_cards=False, clip_share=0.0,
        policy_notes=["Historical claims come from provided facts.",
                      "Up to 15 minutes in this release; longer runs need chaptered music (one track tops out at 10 minutes)."],
        title_formulas=["Daily life in {topic}, a history to fall asleep to",
                        "A quiet night in {topic}", "Fall asleep in {topic}"],
        tags=["sleep", "history", "relaxing", "asmr history"],
        situations=["a market town", "a monastery", "a harbor", "a farmhouse", "a desert caravan", "a winter castle"],
        outcomes=["the town falls asleep", "a festival night", "a quiet winter"],
        # Made to fall asleep to: slow dissolves, never a hard cut.
        transition="crossfade",
    ))

    t.append(Template(
        id="mythology_documentary", name="Mythology documentary",
        pitch="A long-form myth told in medias res, re-hooks every three minutes, climax at 80 percent.",
        niche="mythology, history", kind="viral",
        aspects=["16:9"], default_aspect="16:9",
        length=LengthRange(min_seconds=300, default_seconds=720, max_seconds=900), shorts=False,
        beats=_beats([
            ("cold_open", "In medias res", 0.05, "Start at the most dramatic moment, then pull back."),
            ("world", "The world", 0.20, "The world and the gods or heroes in it."),
            ("rising", "Rising conflict", 0.45, "The conflict grows; open a question you answer later.", True),
            ("complication", "Complication", 0.65, "The cost of the conflict appears.", True),
            ("crisis", "Crisis", 0.80, "Everything is lost or about to be.", True),
            ("climax", "Climax", 0.90, "The climax at about 80 percent."),
            ("meaning", "Aftermath and meaning", 1.0, "What the myth meant to the people who told it; abrupt satisfying end."),
        ]),
        hook_formulas=["In medias res: the climactic moment, then: but how did it come to this?",
                       "A question no one in the myth could answer."],
        rehook_seconds=[180, 360, 540], rehook_every_seconds=180,
        ending="payoff", ending_note="Abrupt, satisfying end. No long goodbye.",
        shots_per_minute=5, words_per_scene=28, dialogue_mode="narration",
        visual_style=_style("epic painterly concept art, dramatic chiaroscuro, volumetric god rays, "
                            "rich mythic palette, cinematic wide compositions"),
        realistic=False,
        voice=VoiceStyle(wpm=145, stability=0.6, description="Deep, measured narrator",
                         suggested_voices=["Daniel", "George", "Bill", "Callum"]),
        music=_music("orchestral epic", ["orchestral", "choir pads", "cinematic"], ["electronic"],
                     [("opening", 0.1, ["dramatic"], []), ("world", 0.3, ["mysterious"], []),
                      ("conflict", 0.4, ["building", "percussion"], []), ("climax", 0.1, ["epic"], []),
                      ("resolve", 0.1, ["reflective"], [])]),
        caption_preset="serif_story", fact_mode=True, stat_cards=False, clip_share=0.15,
        policy_notes=["Sources are the myth texts the user provided (for example a translation and line).",
                      "Mark interpretation as interpretation."],
        title_formulas=["The myth of {topic}, the full story", "{topic}: the darkest myth you never heard",
                        "Why the ancients feared {topic}"],
        tags=["mythology", "documentary", "legends"],
        situations=["a god's betrayal", "a hero's impossible task", "a monster's origin",
                    "a war between gods", "a forbidden love", "the end of the world"],
        outcomes=["tragic fall", "costly victory", "transformation", "cyclical return"],
    ))

    t.append(Template(
        id="original_horror", name="Original horror",
        pitch="Original fiction: an unsettling detail, silence, a twist at 85 percent, an ambiguous end.",
        niche="horror fiction", kind="viral",
        aspects=["16:9", "9:16"], default_aspect="16:9",
        length=LengthRange(min_seconds=45, default_seconds=600, max_seconds=900), shorts=False,
        beats=_beats([
            ("detail", "Unsettling detail", 0.05, "One small wrong detail, no explanation."),
            ("normal", "Normal life", 0.20, "Ordinary life, with one more wrong thing."),
            ("wrongness", "First wrongness", 0.40, "The first undeniable wrongness.", True, 1.5),
            ("escalation", "Escalation", 0.60, "It escalates; silence beats between lines.", True, 1.5),
            ("investigation", "Investigation", 0.75, "The narrator looks for answers."),
            ("confrontation", "Confrontation", 0.85, "Face to face with it."),
            ("twist", "Twist", 0.93, "The twist at about 85 percent.", False, 2.0),
            ("ambiguous", "Ambiguous end", 1.0, "End unresolved, one last image."),
        ]),
        hook_formulas=["A small, specific wrong detail stated flatly.", "A rule the narrator was told never to break."],
        rehook_seconds=[20, 45, 180, 360], rehook_every_seconds=150,
        ending="payoff", ending_note="Ambiguous: never fully explain it.",
        shots_per_minute=5, words_per_scene=28, dialogue_mode="narration",
        visual_style=_style("dark atmospheric illustration, deep shadows, cold desaturated palette, "
                            "fog, single practical light source, unsettling negative space"),
        realistic=False,
        voice=VoiceStyle(wpm=140, stability=0.55, description="Low, close, restrained",
                         suggested_voices=["Callum", "Charlotte", "Bill", "River"]),
        music=_music("dread ambient", ["dark ambient", "drones", "sparse"], ["melody", "upbeat"],
                     [("unease", 0.4, ["low drone"], []), ("dread", 0.45, ["tension"], []),
                      ("twist", 0.15, ["silence", "single tone"], [])]),
        caption_preset="minimal_lower", fact_mode=False, stat_cards=False, clip_share=0.15,
        policy_notes=["Original fiction only, never presented as real or as a true story.",
                      "No real places, people or crimes as the source of the horror.",
                      "No gore or shock imagery."],
        title_formulas=["I should not have {action}", "The {object} in my {place}",
                        "Never {rule} after midnight"],
        description_formula="One unsettling line, then a fiction label.",
        tags=["horror", "scary story", "fiction"],
        situations=["a house that adds a room", "a voice on an old recording", "a neighbor who never sleeps",
                    "a road that loops", "a rule at a night job", "a photo with one extra person"],
        outcomes=["it was the narrator all along", "it follows the viewer", "it never left",
                  "nothing is explained", "the rule was a lie"],
        dramatization_label="Fiction. Not based on real events.",
    ))

    t.append(Template(
        id="business_story", name="Business story",
        pitch="A company in one shocking number, its rise, its fall and the lesson, told by a mascot.",
        niche="business", kind="viral",
        aspects=["16:9", "9:16"], default_aspect="16:9",
        length=LengthRange(min_seconds=60, default_seconds=600, max_seconds=900), shorts=False,
        beats=_beats([
            ("number", "Shocking number", 0.06, "The shocking number, on the stat card, with its source."),
            ("origin", "Origin", 0.20, "Where it started."),
            ("rise", "Rise", 0.45, "How it grew, one mechanism per scene.", True),
            ("peak", "Peak", 0.55, "The peak, with its number."),
            ("fall", "Fall", 0.80, "What went wrong.", True),
            ("lesson", "Lesson", 1.0, "The lesson, stated plainly; not investment advice."),
        ]),
        hook_formulas=["Lead with a number that sounds impossible.", "Lead with the collapse, then rewind."],
        rehook_seconds=[20, 45, 180, 360], rehook_every_seconds=180,
        ending="payoff", ending_note="The lesson, then an abrupt end.",
        shots_per_minute=6, words_per_scene=28, dialogue_mode="narration",
        visual_style=_style("clean stylized 3D, bright studio lighting, playful mascot character, "
                            "simple bold shapes, isometric business scenes"),
        realistic=False,
        voice=VoiceStyle(wpm=160, stability=0.45, description="Energetic, clear storyteller",
                         suggested_voices=["Eric", "Jessica", "Chris", "Liam"]),
        music=_music("corporate tension", ["modern underscore", "pulse", "synth"], ["sad piano"],
                     [("hook", 0.1, ["impact"], []), ("rise", 0.45, ["building"], []),
                      ("fall", 0.3, ["darker"], []), ("lesson", 0.15, ["resolve"], [])]),
        caption_preset="bold_pop", fact_mode=True, stat_cards=True, clip_share=0.15,
        policy_notes=["Every number comes from a provided fact with its source and date.",
                      "No investment advice; the mascot is a storyteller, not a financial advisor.",
                      "Company names may be said; logos are never drawn."],
        title_formulas=["How {topic} lost {number}", "The rise and fall of {topic}", "{topic}: the mistake that cost everything"],
        tags=["business", "case study", "startup"],
        situations=["overnight boom", "slow empire", "fraud unravels", "one bad bet", "copycat war"],
        outcomes=["collapse", "comeback", "acquired", "still standing but shrunk"],
    ))

    t.append(Template(
        id="what_if", name="What if",
        pitch="What if the impossible happened: impact by 15 s, effects by 35 s, an extreme end, a reality check.",
        niche="science, speculation", kind="viral",
        aspects=["9:16", "4:5", "1:1", "16:9"], default_aspect="9:16",
        length=LengthRange(min_seconds=30, default_seconds=55, max_seconds=90), shorts=True,
        beats=_beats([
            ("hook", "Hook", 0.055, "What if, in one line."),
            ("impact", "Immediate impact", 0.27, "The first thing that happens."),
            ("second_order", "Second order effects", 0.64, "What that causes next, two or three steps.", True),
            ("extreme", "Extreme conclusion", 0.91, "Where it ends up at the extreme."),
            ("reality", "Reality check and loop", 1.0, "Bring it back to reality, loop to the start."),
        ]),
        hook_formulas=["What if {premise}?", "In three seconds, {premise}. Here is what happens next."],
        rehook_seconds=[17, 40], rehook_every_seconds=None,
        ending="loop", ending_note="Reality check line that leads back into the question.",
        shots_per_minute=12, words_per_scene=26, dialogue_mode="narration",
        visual_style=_style("stylized 3D explainer, bold simple shapes, bright saturated palette, "
                            "playful exaggeration, clean backgrounds"),
        realistic=False,
        voice=VoiceStyle(wpm=165, stability=0.45, description="Curious, energetic",
                         suggested_voices=["Liam", "Jessica", "Charlie", "Aria"]),
        music=_music("curious pulse", ["quirky", "pizzicato", "light electronic"], ["sad"],
                     [("hook", 0.1, ["sparse"], []), ("build", 0.8, ["building"], []), ("loop", 0.1, ["light"], [])]),
        caption_preset="bold_pop", fact_mode=False, stat_cards=True, clip_share=0.25,
        policy_notes=["Speculation must be framed as speculation; the reality check is grounded."],
        title_formulas=["What if {topic}?", "What happens if {topic}", "{topic} for one day"],
        tags=["what if", "science", "hypothetical"],
        situations=["physics changes", "a species vanishes", "a planet event", "a human ability", "a technology disappears"],
        outcomes=["total collapse", "surprisingly fine", "humans adapt", "it already happened once"],
    ))

    t.append(Template(
        id="faith_story", name="Faith story",
        pitch="A scripture-faithful story with its references in the script, told with reverence.",
        niche="faith", kind="viral",
        aspects=["16:9", "9:16"], default_aspect="16:9",
        length=LengthRange(min_seconds=45, default_seconds=600, max_seconds=900), shorts=False,
        beats=_beats([
            ("opening", "Opening", 0.05, "The moment the story turns on, with its reference."),
            ("setting", "Setting", 0.20, "Who, where and when, as the text tells it."),
            ("calling", "Calling or conflict", 0.45, "The calling or conflict.", True),
            ("trial", "Trial", 0.70, "The trial or test.", True),
            ("turning", "Turning point", 0.85, "The turning point, quoted from the text."),
            ("resolution", "Resolution", 0.95, "How the text resolves it."),
            ("reflection", "Reflection", 1.0, "A short reflection and the reference to read."),
        ]),
        hook_formulas=["Open at the turning moment, cite book chapter and verse.",
                       "A question the story answers, then the reference."],
        rehook_seconds=[20, 45, 180, 360], rehook_every_seconds=180,
        ending="payoff", ending_note="Close with the reference so viewers can read it.",
        shots_per_minute=5, words_per_scene=28, dialogue_mode="narration",
        visual_style=_style("reverent painterly illustration, warm golden light, soft focus, "
                            "historically grounded clothing and settings"),
        realistic=False,
        voice=VoiceStyle(wpm=140, stability=0.65, description="Reverent, warm, unhurried",
                         suggested_voices=["George", "Matilda", "Daniel", "Alice"]),
        music=_music("reverent", ["soft strings", "choir pads", "piano"], ["drums", "electronic"],
                     [("opening", 0.2, ["gentle"], []), ("story", 0.6, ["warm", "building"], []),
                      ("reflection", 0.2, ["peaceful"], [])]),
        caption_preset="serif_story", fact_mode=True, stat_cards=False, clip_share=0.1,
        policy_notes=["Stay scripture-faithful: no invented events, words or miracles.",
                      "Cite references (book, chapter, verse) as sources; quotes come from the provided translation.",
                      "Depict sacred figures respectfully; follow the tradition's norms on depiction."],
        title_formulas=["The story of {topic}, as the scripture tells it", "{topic}: what really happened",
                        "Why {topic} still matters"],
        tags=["faith", "bible story", "scripture"],
        situations=["a calling", "a test of faith", "an exile", "a reconciliation", "a miracle as recorded"],
        outcomes=["faith rewarded", "humility learned", "a promise kept", "a warning heeded"],
    ))

    t.append(Template(
        id="animal_comedy", name="Animal comedy",
        pitch="An absurd animal setup, two escalations and a payoff in the last two seconds, then loop.",
        niche="comedy, animals", kind="viral",
        aspects=["9:16", "1:1", "4:5"], default_aspect="9:16",
        length=LengthRange(min_seconds=15, default_seconds=25, max_seconds=45), shorts=True,
        beats=_beats([
            ("setup", "Absurd setup", 0.30, "An animal doing something absurdly human."),
            ("escalate_1", "Escalation one", 0.60, "It gets sillier."),
            ("escalate_2", "Escalation two", 0.92, "Peak silliness, no danger."),
            ("payoff", "Payoff", 1.0, "The punchline in the last two seconds, loops to the start."),
        ]),
        hook_formulas=["An animal mid human task, already failing.", "A deadpan line from the animal."],
        rehook_seconds=[], rehook_every_seconds=None,
        ending="loop", ending_note="Payoff in the final two seconds; last frame matches the first.",
        shots_per_minute=18, words_per_scene=None, dialogue_mode="mixed",
        visual_style=_style("bright stylized 3D animation, soft rounded shapes, expressive cartoon animals, "
                            "sunny lighting, playful colors"),
        realistic=False,
        voice=VoiceStyle(wpm=165, stability=0.3, description="Comic character voices, deadpan narrator",
                         suggested_voices=["Charlie", "Laura", "Will", "Jessica"]),
        music=_music("playful", ["bouncy", "pizzicato", "comedic"], ["sad", "tense"],
                     [("setup", 0.3, ["light"], []), ("build", 0.6, ["bouncy"], []), ("button", 0.1, ["sting"], [])]),
        caption_preset="karaoke_box", fact_mode=False, kids_safe=True, stat_cards=False, clip_share=0.4,
        policy_notes=["No distress, peril, injury, fear or harm to any animal, even as a joke.",
                      "No shock content; humor comes from absurdity, not suffering.",
                      "Clearly animated style, never realistic footage of animals."],
        title_formulas=["{character} tries {topic}", "When the {character} {action}", "{character} was not ready"],
        tags=["funny animals", "comedy", "animation"],
        situations=["a job interview", "a cooking show", "a gym session", "a group photo", "a talent show",
                    "a tech support call", "a family dinner"],
        outcomes=["deadpan reversal", "wins by accident", "outsmarts the human", "the tiny one steals the show"],
    ))

    t.append(Template(
        id="true_crime_sourced", name="True crime (sourced)",
        pitch="A real, sourced case told with care: every claim cited, dramatizations labeled.",
        niche="true crime", kind="viral",
        aspects=["16:9"], default_aspect="16:9",
        length=LengthRange(min_seconds=300, default_seconds=720, max_seconds=900), shorts=False,
        beats=_beats([
            ("cold_open", "Cold open", 0.04, "The moment the case broke, sourced."),
            ("lives", "The people", 0.15, "Who the people were, with respect for victims."),
            ("event", "The event", 0.30, "What happened, from the record.", True),
            ("investigation", "Investigation", 0.55, "How investigators worked it.", True),
            ("breakthrough", "Breakthrough", 0.70, "The break in the case."),
            ("outcome", "Outcome", 0.85, "Charges, trial and verdict, as recorded.", True),
            ("aftermath", "Aftermath", 1.0, "What remains unresolved, and where to learn more."),
        ]),
        hook_formulas=["Open on a documented detail that does not add up.", "Open on the date and the first call."],
        rehook_seconds=[20, 45, 180, 360, 540], rehook_every_seconds=180,
        ending="payoff", ending_note="End on the documented outcome; no speculation presented as fact.",
        shots_per_minute=5, words_per_scene=28, dialogue_mode="narration",
        visual_style=_style("dark graphic novel illustration, moody shadows, muted palette, "
                            "evocative objects and places, faces in shadow or silhouette"),
        realistic=False,
        voice=VoiceStyle(wpm=150, stability=0.6, description="Grave, careful, factual",
                         suggested_voices=["Daniel", "Charlotte", "Roger", "Alice"]),
        music=_music("investigative", ["dark ambient", "pulse", "piano"], ["upbeat"],
                     [("open", 0.1, ["tension"], []), ("story", 0.75, ["low", "steady"], []),
                      ("end", 0.15, ["somber"], [])]),
        caption_preset="minimal_lower", fact_mode=True, stat_cards=True, clip_share=0.05,
        policy_notes=["Real cases only, every claim from a provided source with its date.",
                      "Dramatized scenes are labeled as dramatizations.",
                      "No graphic violence or gore; never show real victims' faces.",
                      "Do not name uncharged suspects; respect victims and families."],
        title_formulas=["The case of {topic}", "{topic}: what the records show", "The {topic} case, start to finish"],
        tags=["true crime", "case", "documentary"],
        situations=["cold case reopened", "wrongful conviction", "disappearance", "fraud", "heist"],
        outcomes=["solved", "unsolved", "overturned", "partial justice"],
        dramatization_label="Dramatization. Illustrations are not real images of the people or events.",
    ))
    return t


@lru_cache(maxsize=1)
def _catalogue() -> dict[str, Template]:
    return {tpl.id: tpl for tpl in _build()}


def list_templates() -> list[Template]:
    """Every template, formats first, as fresh copies (callers may mutate them)."""
    return [tpl.model_copy(deep=True) for tpl in _catalogue().values()]


def get_template(template_id: str) -> Template:
    """One template by id. Raises KeyError for an unknown id."""
    tpl = _catalogue().get(template_id)
    if tpl is None:
        raise KeyError(f"Unknown template: {template_id}")
    return tpl.model_copy(deep=True)


def max_length_for(template: Template, aspect: str) -> int:
    """Longest allowed runtime: template max, capped at 180 s for anything but 16:9."""
    cap = LONG_MAX_SECONDS if aspect == "16:9" else SHORTS_MAX_SECONDS
    if template.shorts:
        cap = min(cap, SHORTS_MAX_SECONDS)
    return min(template.length.max_seconds, cap)


def rehook_times(template: Template, length_seconds: float) -> list[float]:
    """Absolute re-hook times inside the runtime (never in the last 10 percent)."""
    limit = length_seconds * 0.9
    times = [t for t in template.rehook_seconds if 3.0 < t < limit]
    if template.rehook_every_seconds:
        last = max(template.rehook_seconds) if template.rehook_seconds else 0.0
        t = last + template.rehook_every_seconds
        while t < limit:
            times.append(t)
            t += template.rehook_every_seconds
    return sorted(set(round(x, 2) for x in times))
