"""Deterministic text helpers: TTS safety, word budgets, audio tags, prompts.

The writing rules come from the story-telling project: spell numbers as words;
no hyphens, ampersands, brackets, emoji or bullet characters; sentences under
about 25 words; 24 to 32 words per narrated scene; about 165 words a minute.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Numbers as words (English). Other languages keep digits and let Eleven v4's
# text normalization read them, since a wrong spelled-out number is worse.
# --------------------------------------------------------------------------

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
         "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_SCALES = [(10 ** 12, "trillion"), (10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")]
_ORDINAL_IRREGULAR = {"one": "first", "two": "second", "three": "third", "five": "fifth",
                      "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}


def _under_100(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def _under_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{_ONES[hundreds]} hundred")
    if rest:
        parts.append(_under_100(rest))
    return " ".join(parts) if parts else "zero"


def int_to_words(n: int) -> str:
    """Cardinal number in words: 1200 -> 'one thousand two hundred'."""
    if n < 0:
        return "minus " + int_to_words(-n)
    if n < 1000:
        return _under_1000(n)
    for value, name in _SCALES:
        if n >= value:
            head, rest = divmod(n, value)
            out = f"{int_to_words(head)} {name}"
            return out + (f" {int_to_words(rest)}" if rest else "")
    return _under_1000(n)


def year_to_words(n: int) -> str:
    """Years read the way people say them: 1947 -> 'nineteen forty seven'."""
    if 2000 <= n <= 2009:
        return int_to_words(n)
    if 1100 <= n <= 2099 and n % 100 == 0 and n % 1000 != 0:
        return f"{_under_100(n // 100)} hundred"
    if 1100 <= n <= 2099:
        hi, lo = divmod(n, 100)
        lo_words = _under_100(lo) if lo >= 10 else f"oh {_ONES[lo]}"
        return f"{_under_100(hi)} {lo_words}"
    return int_to_words(n)


def ordinal_words(n: int) -> str:
    words = int_to_words(n).split()
    last = words[-1]
    if last in _ORDINAL_IRREGULAR:
        words[-1] = _ORDINAL_IRREGULAR[last]
    elif last.endswith("y"):
        words[-1] = last[:-1] + "ieth"
    else:
        words[-1] = last + "th"
    return " ".join(words)


def number_to_words(token: str) -> str:
    """'1,200' -> 'one thousand two hundred'; '3.5' -> 'three point five'."""
    token = token.replace(",", "")
    if "." in token:
        whole, frac = token.split(".", 1)
        head = int_to_words(int(whole)) if whole else "zero"
        return head + " point " + " ".join(_ONES[int(d)] for d in frac if d.isdigit())
    return int_to_words(int(token))


_CURRENCY = {"$": ("dollar", "dollars"), "\u00a3": ("pound", "pounds"),
             "\u20ac": ("euro", "euros"), "\u20b9": ("rupee", "rupees"), "\u00a5": ("yen", "yen")}
_MAGNITUDE = {"k": "thousand", "m": "million", "bn": "billion", "b": "billion", "t": "trillion"}

_RE_CURRENCY = re.compile(r"([$\u00a3\u20ac\u20b9\u00a5])\s?(\d[\d,]*(?:\.\d+)?)(?:\s?(bn|[kmbt])\b)?", re.I)
_RE_PERCENT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s?%")
_RE_ORDINAL = re.compile(r"\b(\d+)(st|nd|rd|th)\b", re.I)
_RE_DECADE = re.compile(r"\b(1[1-9]|20)(\d0)'?s\b")
_RE_YEAR = re.compile(r"\b(1[1-9]\d\d|20\d\d)\b")
_RE_MAGNITUDE = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s?(bn|[kmbt])\b", re.I)
_RE_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_RE_RANGE = re.compile(r"(\d)\s?[-\u2013\u2014]\s?(\d)")


def _decade_words(m: re.Match) -> str:
    year = int(m.group(1) + m.group(2))
    words = year_to_words(year).split()
    last = words[-1]
    if last.endswith("y"):
        words[-1] = last[:-1] + "ies"
    elif last == "hundred":
        words[-1] = "hundreds"
    else:
        words[-1] = last + "s"
    return " ".join(words)


def spell_numbers(text: str) -> str:
    """Replace every digit run in English text with words."""
    def cur(m: re.Match) -> str:
        sym, num, mag = m.group(1), m.group(2), (m.group(3) or "").lower()
        singular, plural = _CURRENCY[sym]
        words = number_to_words(num)
        if mag:
            return f"{words} {_MAGNITUDE[mag]} {plural}"
        return f"{words} {singular if words == 'one' else plural}"

    text = _RE_RANGE.sub(r"\1 to \2", text)
    text = _RE_CURRENCY.sub(cur, text)
    text = _RE_PERCENT.sub(lambda m: f"{number_to_words(m.group(1))} percent", text)
    text = _RE_ORDINAL.sub(lambda m: ordinal_words(int(m.group(1))), text)
    text = _RE_DECADE.sub(_decade_words, text)
    text = _RE_MAGNITUDE.sub(
        lambda m: f"{number_to_words(m.group(1))} {_MAGNITUDE[m.group(2).lower()]}", text)
    text = _RE_YEAR.sub(lambda m: year_to_words(int(m.group(1))), text)
    text = _RE_NUMBER.sub(lambda m: number_to_words(m.group(0)), text)
    return text


# --------------------------------------------------------------------------
# TTS sanitizer
# --------------------------------------------------------------------------

_SYMBOL_WORDS = {"&": " and ", "+": " plus ", "=": " equals ", "@": " at ", "#": " number ",
                 "%": " percent "}
_RE_BRACKETED = re.compile(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|<[^>]*>")
_RE_URL = re.compile(r"https?://\S+|www\.\S+")
_RE_SPACES = re.compile(r"\s+")
_RE_SENTENCE = re.compile(r"(?<=[.!?])\s+")
MAX_SENTENCE_WORDS = 25


def _strip_emoji_and_symbols(text: str, keep_currency: bool = False) -> str:
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat == "Sc" and keep_currency:
            out.append(ch)
        elif cat in ("So", "Sk", "Sc", "Sm", "Cs", "Co", "Cn") or (cat.startswith("C") and ch not in "\n\t"):
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _split_long_sentence(sentence: str, limit: int = MAX_SENTENCE_WORDS) -> list[str]:
    words = sentence.split()
    if len(words) <= limit:
        return [sentence]
    # Prefer a comma or a conjunction near the middle.
    mid = len(words) // 2
    best = None
    for offset in range(0, mid):
        for i in (mid - offset, mid + offset):
            if 4 <= i < len(words) - 3:
                w = words[i - 1]
                if w.endswith((",", ";", ":")) or words[i].lower() in ("and", "but", "so", "because", "while", "then"):
                    best = i
                    break
        if best:
            break
    if best is None:
        best = mid
    first = " ".join(words[:best]).rstrip(",;:")
    second_words = words[best:]
    if second_words[0].lower() in ("and", "but", "so", "then") and len(second_words) > 4:
        second_words = second_words[1:]
    second = " ".join(second_words)
    first = first if first.endswith((".", "!", "?")) else first + "."
    second = second[0].upper() + second[1:] if second else second
    return _split_long_sentence(first, limit) + _split_long_sentence(second, limit)


def tts_safe(text: str, language: str = "en", *, provider: str = "elevenlabs", keep_tags: bool = False) -> str:
    """Make a line safe and natural for Eleven v4.

    Removes bracketed asides, URLs, emoji, bullets, hyphens, slashes and
    ampersands; spells numbers in English; splits sentences longer than about
    25 words; normalizes whitespace and quotes. Ellipses stay for ElevenLabs,
    which reads them as a trailing pause; other providers (Sarvam) get a full
    stop. With ``keep_tags`` a known audio tag that opens a sentence is kept
    (see limit_audio_tags for the per-line cap); every other bracket goes.
    """
    if not text:
        return ""
    if keep_tags:
        parts = _split_at_tags(unicodedata.normalize("NFKC", text))
        if any(tag for tag, _ in parts):
            out = []
            for tag, chunk in parts:
                clean = tts_safe(chunk, language, provider=provider)
                if clean:
                    out.append(f"[{tag}] {clean}" if tag else clean)
            return " ".join(out)
    t = unicodedata.normalize("NFKC", text)
    t = _RE_URL.sub(" ", t)
    t = _RE_BRACKETED.sub(" ", t)
    t = t.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    t = t.replace('"', "")
    # Bullets and list markers at line starts.
    t = re.sub(r"(?m)^\s*(?:[-*\u2022\u25cf\u25aa\u2023\u2043]|\d+[.)])\s+", "", t)
    if language == "en":
        t = spell_numbers(t)
    for sym, word in _SYMBOL_WORDS.items():
        t = t.replace(sym, word)
    # Dashes of every kind and slashes become pauses or spaces.
    t = re.sub(r"\s[-\u2010-\u2015]+\s", ", ", t)
    t = re.sub(r"[\u2010-\u2015]", ", ", t)
    t = re.sub(r"(?<=\w)-(?=\w)", " ", t)
    t = t.replace("-", " ").replace("/", " or ").replace("\\", " ")
    t = t.replace("*", " ").replace("_", " ").replace("~", " ").replace("|", " ").replace("^", " ")
    t = re.sub(r"\.{3,}|\u2026", "..." if provider == "elevenlabs" else ".", t)
    t = _strip_emoji_and_symbols(t, keep_currency=language != "en")
    t = _RE_SPACES.sub(" ", t).strip()
    t = re.sub(r"\s+([,.!?;:])", r"\1", t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"([.!?])\s*,", r"\1", t)
    t = re.sub(r"^[,.;:\s]+", "", t)
    if not t:
        return ""
    sentences = [s for s in _RE_SENTENCE.split(t) if s.strip()]
    out: list[str] = []
    for s in sentences:
        out.extend(_split_long_sentence(s.strip()))
    t = " ".join(out)
    if t and t[-1] not in ".!?":
        t += "."
    return t


def sentence_lengths(text: str) -> list[int]:
    return [len(s.split()) for s in _RE_SENTENCE.split(text.strip()) if s.strip()]


def is_tts_safe(text: str, language: str = "en") -> bool:
    text = _RE_TAG.sub(lambda m: " " if _tag_at_boundary(text, m) else m.group(0), text or "")
    if language == "en" and re.search(r"\d", text):
        return False
    if re.search(r"[&\[\]{}()<>*#@/\\|~^_\u2010-\u2015-]", text):
        return False
    return all(n <= MAX_SENTENCE_WORDS + 3 for n in sentence_lengths(text))


def word_count(text: str) -> int:
    return len(text.split()) if text else 0


# --------------------------------------------------------------------------
# Eleven v4 audio tags
# --------------------------------------------------------------------------

# Tags documented for Eleven v3 and v4 audio tags (voice delivery and emotion).
# The model reads unknown tags aloud on some voices, so anything outside this
# list is mapped to the nearest safe tag or dropped.
SAFE_AUDIO_TAGS = (
    "whispering", "whispers", "excited", "sad", "angry", "happy", "curious",
    "sarcastic", "thoughtful", "surprised", "mischievously", "sighs", "exhales",
    "laughs", "crying", "shouting", "calm", "nervous",
)

_TAG_ALIASES = {
    "whisper": "whispering", "whispered": "whispering", "softly": "whispering", "quietly": "whispering",
    "excitedly": "excited", "thrilled": "excited", "joyful": "happy", "cheerful": "happy",
    "sadly": "sad", "tearful": "crying", "sobbing": "crying", "cries": "crying",
    "angrily": "angry", "furious": "angry", "mad": "angry",
    "laughing": "laughs", "chuckles": "laughs", "giggles": "laughs",
    "sigh": "sighs", "sighing": "sighs", "shout": "shouting", "yelling": "shouting", "yells": "shouting",
    "scared": "nervous", "afraid": "nervous", "anxious": "nervous", "fearful": "nervous", "worried": "nervous",
    "shocked": "surprised", "gasps": "surprised", "puzzled": "curious", "wondering": "curious",
    "mocking": "sarcastic", "dry": "sarcastic", "deadpan": "sarcastic", "reflective": "thoughtful",
    "serene": "calm", "gentle": "calm", "playful": "mischievously", "mischievous": "mischievously",
}


def normalize_audio_tag(tag: str | None) -> str | None:
    if not tag:
        return None
    t = tag.strip().strip("[]").strip().lower()
    if t in SAFE_AUDIO_TAGS:
        return t
    return _TAG_ALIASES.get(t)


# At most two tags per line (Eleven v4 reads a line with more as overacted),
# each opening a sentence: the line's emotion field plus one inline tag.
MAX_AUDIO_TAGS = 2
_RE_TAG = re.compile(r"\[([^\[\]]{1,40})\]")


def _tag_at_boundary(text: str, m: re.Match) -> bool:
    before = text[: m.start()].rstrip()
    return (not before or before[-1] in ".!?") and normalize_audio_tag(m.group(1)) is not None


def _split_at_tags(text: str) -> list[tuple[str | None, str]]:
    """(tag, text) chunks: a known tag that opens a sentence starts a chunk."""
    out: list[tuple[str | None, str]] = []
    tag, last = None, 0
    for m in _RE_TAG.finditer(text):
        if not _tag_at_boundary(text, m):
            continue
        if text[last:m.start()].strip() or tag:
            out.append((tag, text[last:m.start()]))
        tag, last = normalize_audio_tag(m.group(1)), m.end()
    out.append((tag, text[last:]))
    return out


def limit_audio_tags(text: str, leading: str | None = None, max_tags: int = MAX_AUDIO_TAGS) -> str:
    """The line as sent to Eleven v4 after its ``leading`` (emotion) tag:
    known tags that open a sentence are kept, up to ``max_tags`` per line
    counting the leading one; every other bracketed word is removed, so the
    voice never reads an unknown tag aloud."""
    budget = max_tags - (1 if leading else 0)
    kept = 0

    def repl(m: re.Match) -> str:
        nonlocal kept
        if _tag_at_boundary(text, m) and kept < budget:
            kept += 1
            return f"[{normalize_audio_tag(m.group(1))}]"
        return " "

    return _RE_SPACES.sub(" ", _RE_TAG.sub(repl, text or "")).strip()


# --------------------------------------------------------------------------
# Budgets
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class WordBudget:
    target: int
    minimum: int
    maximum: int
    scenes: int
    words_per_scene: int | None
    images_per_scene: int


def word_budget(length_seconds: float, wpm: int, words_per_scene: int | None,
                shots_per_minute: float, outro_seconds: float = 0.0) -> WordBudget:
    """Words and scenes for a runtime.

    Narrated templates: words = speaking seconds x wpm / 60 (30 s at 165 wpm
    gives about 82, the story-telling project's 80 to 90), and scenes =
    words / words_per_scene so each scene holds 24 to 32 words. The template's
    shots per minute then sets how many stills a scene cycles through.

    Dialogue-led templates (words_per_scene None): scenes come straight from
    shots per minute (one shot per scene), words from the same wpm.
    """
    speaking = max(5.0, length_seconds - outro_seconds)
    target = int(round(speaking * wpm / 60.0))
    if words_per_scene:
        scenes = max(2, int(round(target / words_per_scene)))
        scene_seconds = speaking / scenes
        images = max(1, min(4, int(round(shots_per_minute * scene_seconds / 60.0))))
    else:
        scenes = max(3, int(round(speaking / 60.0 * shots_per_minute)))
        images = 1
    return WordBudget(
        target=target,
        minimum=int(math.floor(target * 0.92)),
        maximum=int(math.ceil(target * 1.08)),
        scenes=scenes,
        words_per_scene=words_per_scene,
        images_per_scene=images,
    )


def seconds_for_words(words: int, wpm: int) -> float:
    return round(words * 60.0 / max(60, wpm), 2)


# --------------------------------------------------------------------------
# Visual prompts
# --------------------------------------------------------------------------

# Art style words the LLM tends to add. The house style is appended by the
# app, so these would fight it.
_STYLE_WORDS = [
    "photorealistic", "photo realistic", "hyperrealistic", "hyper realistic", "realistic",
    "cinematic", "anime", "manga", "cartoon", "pixar", "disney", "ghibli", "studio ghibli",
    "3d render", "3d", "cgi", "unreal engine", "octane render", "octane", "watercolor",
    "oil painting", "painterly", "illustration", "illustrated", "digital art", "concept art",
    "claymation", "stylized", "comic book", "graphic novel", "pencil sketch", "sketch",
    "vector art", "low poly", "pixel art", "8k", "4k", "hdr", "ultra detailed", "highly detailed",
    "masterpiece", "trending on artstation", "artstation", "film grain", "bokeh", "35mm",
    "art style", "in the style of",
]
_RE_STYLE = re.compile(r"(?i)\b(?:" + "|".join(re.escape(w) for w in sorted(_STYLE_WORDS, key=len, reverse=True)) + r")\b")
_RE_TEXT_WORDS = re.compile(
    r"(?i)[^.,;]*\b(?:text|caption|subtitle|lettering|logo|watermark|signage|sign that reads|"
    r"words?|written|title card|headline)\b[^.,;]*[.,;]?")


def strip_style_words(direction: str) -> str:
    out = _RE_STYLE.sub("", direction or "")
    out = _RE_TEXT_WORDS.sub("", out)
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",\s*,+", ",", out)
    out = re.sub(r"[\s,;:]+([.!?])", r"\1", out)
    out = re.sub(r"^[\s,;:.]+", "", out)
    # "Cinematic shot of X" leaves "shot of X" behind.
    out = re.sub(r"(?i)^(?:an?\s+)?(?:shot|image|picture|photo|render|frame)\b\s*(?:of\s+)?[,:]?\s*", "", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,;")
    if out:
        out = out[0].upper() + out[1:]
    return out


def compose_visual_prompt(clauses: list[str], direction: str) -> str:
    """Each present character's likeness clause verbatim, then the direction."""
    parts = [c.strip() for c in clauses if c and c.strip()]
    d = strip_style_words(direction)
    if d:
        parts.append(d)
    out = " ".join(p if p.endswith((".", "!", "?")) else p + "." for p in parts)
    return out.strip()


def image_prompt(visual_prompt: str, house_style: str) -> str:
    """The final string sent to the image model: prompt, then the house style."""
    vp = visual_prompt.strip()
    if vp and not vp.endswith("."):
        vp += "."
    return f"{vp} {house_style.strip()}".strip()


# --------------------------------------------------------------------------
# Similarity features (cheap, deterministic)
# --------------------------------------------------------------------------

_STOP = frozenset(
    "a an the and or but if then so of to in on at by for with from as is are was were be been "
    "it its this that these those he she they them his her their you your we our i me my not no "
    "do does did has have had will would can could just than into out up down over very".split())
_RE_WORD = re.compile(r"[a-z0-9']+")


def normalize_tokens(text: str) -> list[str]:
    toks = _RE_WORD.findall((text or "").lower())
    out = []
    for w in toks:
        if w in _STOP or len(w) < 2:
            continue
        for suf in ("ing", "ed", "es", "s"):
            if len(w) > 4 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


def ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def containment(a: set, b: set) -> float:
    """Share of the smaller set found in the larger one."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def text_similarity(a: str, b: str) -> float:
    """Blend of unigram and bigram overlap on normalized tokens, 0..1."""
    ta, tb = normalize_tokens(a), normalize_tokens(b)
    uni = jaccard(set(ta), set(tb))
    bi = jaccard(ngrams(ta, 2), ngrams(tb, 2))
    return round(0.5 * uni + 0.5 * bi, 4) if (ta and tb) else 0.0


def sequence_similarity(a: list[str], b: list[str]) -> float:
    """Normalized Levenshtein similarity between two label sequences."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return 1.0 - prev[-1] / max(len(a), len(b))


def title_pattern(title: str) -> str:
    """Shape of a title: content words become W, numbers N, keeps function words."""
    toks = re.findall(r"[A-Za-z0-9']+|[?!:.]", title or "")
    out = []
    for t in toks:
        low = t.lower()
        if t.isdigit():
            out.append("N")
        elif low in _STOP or t in "?!:.":
            out.append(low)
        else:
            out.append("W")
    collapsed: list[str] = []
    for t in out:
        if t == "W" and collapsed and collapsed[-1] == "W":
            continue
        collapsed.append(t)
    return " ".join(collapsed)
