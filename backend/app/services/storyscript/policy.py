"""Policy data and detectors shared by compliance, characters and packaging.

Keyword detection is deliberately simple and deterministic: it is a guard
that points a human at a problem, not a classifier. Lists cover the cases the
research calls out (YouTube inauthentic content clarification of July 2026,
TikTok and Instagram AI labels, EU AI Act Art. 50, California SB 942).
"""

from __future__ import annotations

import re
from typing import Iterable

from .models import CharacterBrief, PlatformDisclosure, Script, Template

COPYRIGHTED_CHARACTERS = (
    "mickey mouse", "minnie mouse", "donald duck", "goofy", "elsa", "olaf", "simba", "buzz lightyear",
    "lightning mcqueen", "shrek", "spider-man", "spiderman", "spider man", "batman", "superman",
    "wonder woman", "iron man", "captain america", "the hulk", "wolverine", "deadpool", "the joker",
    "harley quinn", "harry potter", "hermione", "dumbledore", "voldemort", "gandalf", "frodo",
    "darth vader", "yoda", "luke skywalker", "baby yoda", "grogu", "pikachu", "pokemon", "super mario",
    "mario bros", "luigi", "princess peach", "bowser", "sonic the hedgehog", "zelda", "kirby",
    "spongebob", "patrick star", "bugs bunny", "daffy duck", "tom and jerry", "scooby doo",
    "scooby-doo", "garfield", "snoopy", "peppa pig", "bluey", "paw patrol", "dora the explorer",
    "barbie", "hello kitty", "homer simpson", "bart simpson", "rick and morty", "naruto", "goku",
    "luffy", "totoro", "optimus prime", "godzilla", "james bond", "minions", "shrek", "stitch",
    "moana", "winnie the pooh", "paddington", "thomas the tank engine", "cocomelon", "sesame street",
    "elmo", "kermit", "teenage mutant ninja turtles", "transformers", "master chief", "lara croft",
)

BRANDS = (
    "coca-cola", "coca cola", "pepsi", "nike", "adidas", "mcdonald's", "mcdonalds",
    "starbucks", "disney", "marvel", "netflix", "google", "youtube", "tiktok", "instagram",
    "facebook", "apple logo", "iphone", "macbook", "samsung", "tesla", "amazon logo", "gucci", "louis vuitton",
    "chanel", "rolex", "ferrari", "lamborghini", "porsche", "lego", "red bull", "monster energy",
    "nintendo", "playstation", "xbox", "microsoft", "openai", "chatgpt", "uber", "airbnb", "ikea",
    "walmart", "burger king", "kfc", "gatorade", "nestle", "spotify",
)

# Very prominent people. Not exhaustive: the cast flags and the vision bible
# carry the general case.
PUBLIC_FIGURES = (
    "donald trump", "trump", "joe biden", "biden", "barack obama", "obama", "kamala harris",
    "elon musk", "musk", "taylor swift", "narendra modi", "modi", "vladimir putin", "putin",
    "volodymyr zelensky", "zelensky", "xi jinping", "king charles", "pope leo", "pope francis",
    "mark zuckerberg", "zuckerberg", "jeff bezos", "bezos", "bill gates", "kim kardashian",
    "cristiano ronaldo", "ronaldo", "lionel messi", "messi", "mrbeast", "mr beast", "oprah",
    "beyonce", "rihanna", "kanye west", "shah rukh khan", "virat kohli", "sam altman",
    "keir starmer", "emmanuel macron", "macron", "rishi sunak", "justin bieber", "selena gomez",
    "lebron james", "michael jordan", "tom cruise", "dwayne johnson", "ariana grande",
)

DEATH_WORDS = ("died", "dies", "dead", "death", "killed", "passed away", "funeral", "murdered",
               "assassinated", "overdose", "suicide")
EVENT_WORDS = ("arrested", "charged", "indicted", "scandal", "divorce", "affair", "resigns",
               "resigned", "announces", "announced", "confesses", "admits", "leaked", "caught")
DISASTER_WORDS = ("earthquake", "tsunami", "explosion", "terror attack", "plane crash", "air crash",
                  "flood", "wildfire", "mass shooting", "shooting", "bombing", "hurricane",
                  "derailment", "building collapse", "outbreak", "pandemic", "meltdown")
ENDORSE_WORDS = ("recommend", "recommends", "endorse", "endorses", "sponsored", "use this",
                 "uses this", "buy", "buying", "download", "sign up", "link in bio", "promo code",
                 "my favorite product", "swears by", "approved by")

EXPERT_PERSONA = ("doctor", "dr.", "physician", "surgeon", "nurse", "pharmacist", "therapist",
                  "psychiatrist", "nutritionist", "dietitian", "lawyer", "attorney", "solicitor",
                  "judge", "financial advisor", "financial adviser", "investment advisor",
                  "wealth manager", "stock expert", "trader", "accountant", "tax advisor",
                  "political analyst", "politician", "senator", "minister")
ADVICE_WORDS = ("you should", "you must", "i recommend", "i advise", "my advice", "take this",
                "stop taking", "dosage", "milligrams", "invest in", "buy this stock", "sell your",
                "guaranteed returns", "vote for", "vote against", "sue them", "you can sue",
                "do not pay", "cure", "cures", "treatment for", "diagnose")
HEALTH_FIN_POL_WORDS = ("medication", "medicine", "supplement", "diagnosis", "symptom", "disease",
                        "stock", "crypto", "bitcoin", "invest", "portfolio", "tax", "lawsuit",
                        "election", "candidate", "ballot", "party")

# Strong distress blocks animal comedy; mild peril is a warning.
ANIMAL_DISTRESS = ("injured", "injury", "bleeding", "blood", "trapped", "drowning", "drown",
                   "abandoned", "starving", "hurt", "abuse", "abused", "kicked", "beaten", "terrified",
                   "attacked", "dying", "crying in pain", "burned", "electrocuted", "hit by a car",
                   "run over", "wounded", "in pain", "suffering")
ANIMAL_PERIL = ("panicking", "panic", "chased by", "rescue", "rescued", "whimpering", "shivering",
                "cage", "caged", "stuck in", "falls from", "fell from", "scared", "frightened",
                "danger", "peril", "cliff edge")
SHOCK_WORDS = ("gore", "gory", "corpse", "dead body", "decapitated", "mutilated", "dismembered",
               "entrails", "vomit", "graphic violence", "torture", "self harm")
KIDS_UNSAFE = ("kill", "killed", "blood", "gun", "guns", "weapon", "knife", "die", "dies", "death",
               "scary", "terrifying", "kiss", "kissing", "sexy", "alcohol", "beer", "wine",
               "cigarette", "smoking", "drugs", "drunk", "swear", "damn", "hell")
CRIME_WORDS = ("murder", "murdered", "homicide", "killed", "kidnapping", "kidnapped", "robbery",
               "assault", "arrested", "convicted", "trial", "suspect", "victim", "serial killer")
REAL_CLAIM_PHRASES = ("true story", "this really happened", "based on real events", "based on a true",
                      "real footage", "actual footage", "this is real", "really happened")

ANIMAL_SPECIES_HINT = ("dog", "cat", "monkey", "bird", "horse", "cow", "pig", "goat", "duck",
                       "rabbit", "bear", "lion", "tiger", "elephant", "panda", "fox", "parrot",
                       "hamster", "penguin", "otter", "animal", "puppy", "kitten", "capybara")


def _pattern(words: Iterable[str]) -> re.Pattern:
    alts = sorted({re.escape(w) for w in words}, key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(alts) + r")(?![a-z0-9])", re.I)


_P = {
    "copyright": _pattern(COPYRIGHTED_CHARACTERS),
    "brand": _pattern(BRANDS),
    "public": _pattern(PUBLIC_FIGURES),
    "death": _pattern(DEATH_WORDS),
    "event": _pattern(EVENT_WORDS),
    "disaster": _pattern(DISASTER_WORDS),
    "endorse": _pattern(ENDORSE_WORDS),
    "expert": _pattern(EXPERT_PERSONA),
    "advice": _pattern(ADVICE_WORDS),
    "hfp": _pattern(HEALTH_FIN_POL_WORDS),
    "animal_distress": _pattern(ANIMAL_DISTRESS),
    "animal_peril": _pattern(ANIMAL_PERIL),
    "shock": _pattern(SHOCK_WORDS),
    "kids": _pattern(KIDS_UNSAFE),
    "crime": _pattern(CRIME_WORDS),
    "real_claim": _pattern(REAL_CLAIM_PHRASES),
    "animal": _pattern(ANIMAL_SPECIES_HINT),
}


def find(kind: str, text: str) -> list[str]:
    """Distinct matches of one detector in text, lower-cased, in order."""
    seen: list[str] = []
    for m in _P[kind].finditer(text or ""):
        w = m.group(0).lower()
        if w not in seen:
            seen.append(w)
    return seen


def has(kind: str, text: str) -> bool:
    return bool(_P[kind].search(text or ""))


def is_animal(c: CharacterBrief) -> bool:
    sp = (c.species or "").lower()
    if sp and sp != "human":
        return True
    return has("animal", f"{c.role} {c.personality}")


def is_realistic(script: Script, template: Template | None, cast: list[CharacterBrief]) -> bool:
    """Would a viewer take it for real footage of real people, places or events?"""
    if template is not None and template.realistic:
        return True
    style = (script.visual_style or "").lower()
    if any(w in style for w in ("photoreal", "realism", "realistic", "documentary footage")):
        return True
    return any(c.is_real_person for c in cast)


def disclosure_advice(script: Script, template: Template | None,
                      cast: list[CharacterBrief]) -> list[PlatformDisclosure]:
    realistic = is_realistic(script, template, cast)
    music = script.music is not None
    out = [
        PlatformDisclosure(
            platform="youtube", required=realistic or music,
            label="Altered or synthetic content" if realistic else
                  ("Altered or synthetic content (AI music)" if music else "None required"),
            reason=("Realistic people, places or events made with AI must be disclosed in YouTube Studio."
                    if realistic else
                    "YouTube asks for disclosure of AI-generated music; clearly animated visuals are exempt."
                    if music else "Clearly animated content does not need the label."),
        ),
        PlatformDisclosure(
            platform="tiktok", required=realistic,
            label="AI-generated content label",
            reason=("TikTok requires the AI-generated label on realistic AI content; private people's "
                    "likeness is not allowed." if realistic else
                    "Recommended for AI content; required only when it looks realistic."),
        ),
        PlatformDisclosure(
            platform="instagram", required=realistic,
            label="AI info label",
            reason=("Meta labels realistic AI images and video; mark it when posting. A recurring AI "
                    "character run as its own profile needs an AI persona label from 31 August 2026."
                    if realistic else
                    "Recommended. A recurring AI character run as its own profile needs an AI persona "
                    "label from 31 August 2026."),
        ),
    ]
    return out


def disclosure_line(script: Script, template: Template | None, cast: list[CharacterBrief]) -> str:
    realistic = is_realistic(script, template, cast)
    parts = ["Made with AI: visuals, voice and music are AI generated."]
    if realistic:
        parts.append("This video contains realistic synthetic content.")
    if script.dramatization_label:
        parts.append(script.dramatization_label)
    return " ".join(parts)
