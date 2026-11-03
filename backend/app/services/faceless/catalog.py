"""Static catalogues and limits for Faceless Studio.

Prices are never here: every amount comes from app/services/pricing.py.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

TTS_ENDPOINT = "elevenlabs/tts/eleven-v4"
MUSIC_ENDPOINT = "fal-ai/elevenlabs/music"
H3_FAMILY = "h3-max"

DEFAULT_EDIT_MODEL = "google/nano-banana-2.1/edit"
DEFAULT_T2I_MODEL = "blackforestlabs/flux-3/klein/text-to-image"
STILL_RESOLUTIONS = ("1k", "2k")
DEFAULT_STILL_RESOLUTION = "1k"
CLIP_RESOLUTIONS = ("480p", "768p", "1080p")
DEFAULT_CLIP_RESOLUTION = "768p"
CLIP_MODES = ("image", "reference")    # image-to-video from the still, or reference-to-video
DEFAULT_CLIP_MODE = "image"
CLIP_MIN_SECONDS = 2
CLIP_MAX_SECONDS = 15
# A scene longer than one clip is split into parts (default at most two).
# The storyboard then makes one still more than there are parts: part k runs
# from still k to still k+1, so the parts join on a frame both share.
DEFAULT_MAX_CLIPS_PER_SCENE = 2
# Character reference images sent per character (sheet first, then references).
REFS_PER_CHARACTER = 3
H3_MAX_REFERENCE_IMAGES = 9

# ---------------------------------------------------------------------------
# Formats and limits
# ---------------------------------------------------------------------------

ASPECTS = ("9:16", "16:9", "1:1", "4:5")
# Output frame sizes per render resolution.
FRAME_SIZES = {
    "1080p": {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)},
    "720p": {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (720, 720), "4:5": (720, 900)},
}
RENDER_RESOLUTIONS = tuple(FRAME_SIZES)
DEFAULT_RENDER_RESOLUTION = "1080p"
# Aspect sent to image and video models (4:5 is generated at 3:4 and cropped).
MODEL_ASPECT = {"9:16": "9:16", "16:9": "16:9", "1:1": "1:1", "4:5": "3:4"}
SAFE_ZONE = {"9:16": "shorts", "16:9": "youtube", "1:1": "reels", "4:5": "reels"}

MIN_LENGTH_SECONDS = 15
MAX_LENGTH_SECONDS = {"16:9": 900, "9:16": 180, "1:1": 180, "4:5": 180}
# Measured narration may run this much over MAX_LENGTH_SECONDS; beyond it no
# provider step (and no render) is planned.
LENGTH_TOLERANCE = 0.10
MAX_SCENES = 120
# Script limits checked on every save (drafts, edits, revisions, restores):
# numbers that drive timing and pricing must be finite and in range, and text
# is bounded so a saved script cannot balloon the database or a render.
MAX_SCRIPT_JSON_BYTES = 600_000
MAX_SCENE_SECONDS = 300.0       # an unvoiced scene's planned duration
MAX_SILENCE_SECONDS = 10.0
MAX_NARRATION_CHARS = 5000
MAX_DIALOGUE_LINES = 30
MAX_LINE_CHARS = 2000
MAX_ON_SCREEN_TEXT = 300
MAX_PROMPT_CHARS = 4000
MAX_SCRIPT_SPOKEN_CHARS = 120_000
MAX_CAST = 6
MAX_CHARACTER_MEDIA = 12
MAX_SCENE_MEDIA_PER_SCENE = 1

IMAGE_UPLOAD_MAX_BYTES = 25 * 1024 * 1024
VIDEO_UPLOAD_MAX_BYTES = 100 * 1024 * 1024
CHARACTER_VIDEO_MAX_SECONDS = 60.0
SCENE_VIDEO_MAX_SECONDS = 180.0
VIDEO_MIN_SECONDS = 1.0
# H3 Max reference videos must be 2 to 15 s each.
REFERENCE_VIDEO_MIN_SECONDS = 2.0
REFERENCE_VIDEO_MAX_SECONDS = 15.0
FRAMES_PER_CHARACTER_VIDEO = 3

# Narration pace used before the voices exist (estimates only).
ESTIMATE_WPM = 165
LINE_PAUSE_SECONDS = 0.25
SCENE_TAIL_SECONDS = 0.35
MIN_SCENE_SECONDS = 1.5
OUTRO_SECONDS = 92 / 30  # 92 frames at 30 fps, silent outro card
TITLE_CARD_SECONDS = 2.6
# Ads: the brand beat (CTA, offer, logo) takes the last 2 to 3 seconds and
# the whole piece is fitted to the placement length. The end card gives way
# down to AD_END_CARD_MIN_SECONDS when narration needs the room.
AD_END_CARD_SECONDS = 2.5
AD_END_CARD_MIN_SECONDS = 1.5
AD_MIN_SCENE_SECONDS = 1.0
# J cut: the scene's voice starts this long before its picture. L cut: the
# picture changes this long before the previous scene's voice ends.
SPLIT_EDIT_SECONDS = 0.4
# A clip up to this much shorter than its slot plays slightly slower to fill
# it (speed 0.9 and above reads as natural); a larger gap holds the last
# frame under a slow push-in. Never a frozen frame.
CLIP_MIN_SPEED = 0.9

# Voice take check (free, after each clip is stored): a take outside this
# pace, or with a pause longer than VOICE_MAX_PAUSE_SECONDS, is flagged for
# the user, who may re-voice it (a normal voice line). Never re-run on its own.
VOICE_WPM_RANGE = (120, 210)
VOICE_MAX_PAUSE_SECONDS = 1.5
VOICE_CHECK_MIN_WORDS = 6   # shorter lines have no meaningful pace

# Clip prompts: one camera move, its tempo first (ShotPlan.camera_move).
CAMERA_MOVES = {
    "static": "Static camera, locked shot",
    "push_in": "Slow push-in toward the subject",
    "pull_out": "Slow pull-back reveal",
    "pan_left": "Slow pan left",
    "pan_right": "Slow pan right",
    "tilt_up": "Slow tilt up",
    "tilt_down": "Slow tilt down",
    "tracking": "Smooth tracking shot that follows the subject at walking pace",
    "handheld": "Subtle handheld drift",
    "orbit": "Slow orbit around the subject",
    "crane_up": "Slow crane up",
    "whip_pan": "Fast whip pan",
    "rack_focus": "Static camera, slow rack focus from the foreground to the subject",
}
# Look register (Story Room Look.register) as clip prompt words.
REGISTER_WORDS = {
    "cinematic": "Cinematic film look, shallow depth of field, motivated light",
    "ugc": "Handheld phone footage, natural light, authentic and unpolished",
    "documentary": "Observational documentary footage, available light",
    "animated": "Animated, the style of the first frame held throughout",
}

# Hourly caps, runaway-spend guards (counted in faceless_activity).
DRAFTS_PER_HOUR = 20
REVISIONS_PER_HOUR = 60
BIBLES_PER_HOUR = 20
PACKAGES_PER_HOUR = 20
STEP_RUNS_PER_HOUR = 60

# Provider request handling (scheduler).
MAX_IN_FLIGHT_PER_RUN = 6
ITEM_TIMEOUT_SECONDS = 2 * 3600
MAX_POLL_ERRORS = 20
MAX_RESULT_ERRORS = 3
RENDER_MAX_ATTEMPTS = 2

# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------

CONSENT_TEXT_VERSION = "2026-10-25"
CONSENT_TEXT = (
    "I confirm that this character is based on me, or on a real person who has given me "
    "explicit permission to create AI images, video and stories with their likeness. I "
    "will not use this character to impersonate, deceive, endorse products or events the "
    "person has not approved, or depict a minor. I can revoke this at any time, which stops "
    "all further generation with this character."
)
CONSENT_RELATIONSHIPS = ("self", "with_permission")

# ---------------------------------------------------------------------------
# Voices (Eleven v4 stock voices; voice cloning is not offered)
# ---------------------------------------------------------------------------

VOICES = [
    {"id": "Aria", "gender": "female", "accent": "American", "tone": "expressive, middle aged"},
    {"id": "Roger", "gender": "male", "accent": "American", "tone": "confident, casual"},
    {"id": "Sarah", "gender": "female", "accent": "American", "tone": "soft, news"},
    {"id": "Laura", "gender": "female", "accent": "American", "tone": "upbeat, young"},
    {"id": "Charlie", "gender": "male", "accent": "Australian", "tone": "natural, conversational"},
    {"id": "George", "gender": "male", "accent": "British", "tone": "warm, storyteller"},
    {"id": "Callum", "gender": "male", "accent": "Transatlantic", "tone": "intense, character"},
    {"id": "River", "gender": "neutral", "accent": "American", "tone": "calm, confident"},
    {"id": "Liam", "gender": "male", "accent": "American", "tone": "articulate, young"},
    {"id": "Charlotte", "gender": "female", "accent": "Swedish", "tone": "sensual, character"},
    {"id": "Alice", "gender": "female", "accent": "British", "tone": "confident, educational"},
    {"id": "Matilda", "gender": "female", "accent": "American", "tone": "friendly, warm"},
    {"id": "Will", "gender": "male", "accent": "American", "tone": "friendly, young"},
    {"id": "Jessica", "gender": "female", "accent": "American", "tone": "expressive, young"},
    {"id": "Eric", "gender": "male", "accent": "American", "tone": "friendly, middle aged"},
    {"id": "Chris", "gender": "male", "accent": "American", "tone": "casual, conversational"},
    {"id": "Brian", "gender": "male", "accent": "American", "tone": "deep, narration"},
    {"id": "Daniel", "gender": "male", "accent": "British", "tone": "authoritative, documentary"},
    {"id": "Lily", "gender": "female", "accent": "British", "tone": "warm, narration"},
    {"id": "Bill", "gender": "male", "accent": "American", "tone": "trustworthy, older"},
    {"id": "Rachel", "gender": "female", "accent": "American", "tone": "calm, the provider default"},
]
VOICE_IDS = {v["id"] for v in VOICES}
DEFAULT_NARRATOR_VOICE = "Daniel"
DEFAULT_STABILITY = 0.5
DEFAULT_SIMILARITY = 0.75

# ---------------------------------------------------------------------------
# Music moods (ElevenLabs Music composition plan styles; instrumental default)
# ---------------------------------------------------------------------------

# Each mood names a tempo range (and a key where it shapes the colour), which
# ElevenLabs Music follows far more reliably than adjectives alone; both are
# appended to the positive styles (see _with_tempo) so every caller that
# sends a mood's styles, /motion-graphics included, gets them.
MUSIC_MOODS = [
    {"id": "template", "label": "Template default", "positive": [], "negative": []},
    {"id": "suspense", "label": "Suspense", "positive": ["tense cinematic underscore", "pulsing low strings", "sparse percussion"], "negative": ["upbeat pop", "vocals"], "bpm": (90, 100), "key": "D minor"},
    {"id": "uplifting", "label": "Uplifting", "positive": ["uplifting cinematic", "warm piano", "building strings"], "negative": ["dark", "vocals"], "bpm": (100, 116), "key": "D major"},
    {"id": "melancholy", "label": "Melancholy", "positive": ["melancholic piano", "soft strings", "slow tempo"], "negative": ["drums", "vocals"], "bpm": (60, 72), "key": "A minor"},
    {"id": "epic", "label": "Epic orchestral", "positive": ["epic orchestral", "taiko drums", "brass swells"], "negative": ["lofi", "vocals"], "bpm": (80, 95), "key": "C minor"},
    {"id": "documentary", "label": "Documentary", "positive": ["documentary underscore", "ambient textures", "light pulse"], "negative": ["heavy drums", "vocals"], "bpm": (85, 100)},
    {"id": "lofi", "label": "Lo-fi calm", "positive": ["lofi hip hop", "mellow keys", "vinyl texture"], "negative": ["aggressive", "vocals"], "bpm": (70, 85)},
    {"id": "dark_ambient", "label": "Dark ambient", "positive": ["dark ambient drones", "distant metallic hits", "unsettling textures"], "negative": ["happy", "vocals"], "bpm": (60, 75), "key": "E minor"},
    {"id": "playful", "label": "Playful", "positive": ["playful pizzicato", "quirky percussion", "light woodwinds"], "negative": ["dark", "vocals"], "bpm": (110, 125), "key": "F major"},
    {"id": "sleep", "label": "Sleep and calm", "positive": ["ambient pads", "slow evolving drones", "very soft piano"], "negative": ["drums", "percussion", "vocals"], "bpm": (50, 60)},
    {"id": "none", "label": "No music", "positive": [], "negative": []},
]


def _with_tempo(mood: dict) -> dict:
    bpm = mood.get("bpm")
    extra = [f"{bpm[0]} to {bpm[1]} BPM"] if bpm else []
    if mood.get("key"):
        extra.append(f"in {mood['key']}")
    return {**mood, "positive": list(mood["positive"]) + extra}


MUSIC_MOODS = [_with_tempo(m) for m in MUSIC_MOODS]
MUSIC_MOOD_IDS = {m["id"] for m in MUSIC_MOODS}

# ---------------------------------------------------------------------------
# Captions (render engine presets)
# ---------------------------------------------------------------------------

CAPTION_STYLES = [
    {"id": "bold_pop", "label": "Bold pop", "description": "Word by word, heavy outline, the current word pops."},
    {"id": "karaoke_box", "label": "Karaoke box", "description": "Short groups with a highlight box moving over each word."},
    {"id": "minimal_lower", "label": "Minimal lower", "description": "Small clean lines low in the frame, for long-form."},
    {"id": "serif_story", "label": "Serif story", "description": "Elegant serif groups for calm storytelling."},
    {"id": "none", "label": "No captions", "description": "Voice only."},
]
CAPTION_STYLE_IDS = {c["id"] for c in CAPTION_STYLES}

# ---------------------------------------------------------------------------
# Visual styles (appended to every image prompt; "template" keeps the
# template's house style)
# ---------------------------------------------------------------------------

STYLES = [
    {"id": "template", "label": "Template default", "prompt": ""},
    {"id": "cinematic", "label": "Cinematic realism", "prompt": "cinematic film still, natural light, shallow depth of field, 35mm, rich color grade"},
    {"id": "stylized_3d", "label": "Stylized 3D", "prompt": "stylized 3D animation, soft global illumination, expressive proportions, clean materials"},
    {"id": "claymation", "label": "Claymation", "prompt": "claymation stop motion, handmade clay textures, miniature set, soft studio light"},
    {"id": "anime", "label": "Anime", "prompt": "anime key visual, clean line art, cel shading, vivid sky"},
    {"id": "painterly", "label": "Painterly", "prompt": "painterly digital painting, visible brush strokes, warm muted palette"},
    {"id": "watercolor", "label": "Watercolor storybook", "prompt": "watercolor storybook illustration, soft edges, paper texture"},
    {"id": "comic", "label": "Comic", "prompt": "graphic novel panel, bold ink lines, halftone shading"},
    {"id": "noir", "label": "Noir", "prompt": "black and white film noir, hard shadows, venetian blind light"},
    {"id": "documentary", "label": "Documentary photo", "prompt": "documentary photograph, available light, candid composition, fine grain"},
]
STYLE_PROMPTS = {s["id"]: s["prompt"] for s in STYLES}

NO_TEXT_CLAUSE = "No text, captions, numbers, logos, signage or watermarks."

STEPS = ("storyboard", "clips", "voice", "music", "render", "thumbnails")
