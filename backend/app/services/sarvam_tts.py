"""Sarvam AI text to speech: Bulbul v4 (bulbul:v4-flash) for voices in Indian
languages, next to ElevenLabs in Lip Sync and My Assets (app/services/assets.py).

REST, synchronous and fast (about a second for a sentence): POST
https://api.sarvam.ai/text-to-speech with the api-subscription-key header,
up to 2,500 characters, answering {"request_id", "audios": [base64]}. The key
is the owner's (APISettings.sarvam_api_key, API Keys page). The host is fixed,
so this is not a user-supplied URL fetch.

Each v4 voice belongs to one language, named <name>_<language>_<style>; the
language is taken from the voice, so a request cannot pair a voice with text
in a language it was not made for. The list is the one the API itself
reports (2026-10-28), less the two Assamese voices, which need beta access.
"""

from __future__ import annotations

import base64
import logging

import httpx

logger = logging.getLogger(__name__)

API_URL = "https://api.sarvam.ai/text-to-speech"
MODEL = "bulbul:v4-flash"
MODEL_LABEL = "Bulbul v4"
MAX_CHARS = 2500
PACE_MIN, PACE_MAX, PACE_DEFAULT = 0.5, 2.0, 1.0
SAMPLE_RATE = 24000
TIMEOUT_SECONDS = 60
DEFAULT_VOICE = "shubh_enhi_ads"
DEFAULT_LANGUAGE = "enhi"

# Voice language tag: (language_code sent to Sarvam, label). Hinglish voices
# take Hindi normalisation, as Sarvam's own examples do.
LANGUAGES: dict[str, tuple[str, str]] = {
    "hi": ("hi-IN", "Hindi"),
    "enhi": ("hi-IN", "Hinglish (Hindi and English)"),
    "en": ("en-IN", "English (India)"),
    "bn": ("bn-IN", "Bengali"),
    "gu": ("gu-IN", "Gujarati"),
    "kn": ("kn-IN", "Kannada"),
    "mr": ("mr-IN", "Marathi"),
    "pa": ("pa-IN", "Punjabi"),
    "ta": ("ta-IN", "Tamil"),
    "te": ("te-IN", "Telugu"),
}

VOICES_BY_LANGUAGE: dict[str, tuple[str, ...]] = {
    "hi": (
        "aayan_hi_conversational", "amit_hi_conversational", "ashutosh_hi_conversational",
        "kabir_hi_conversational", "kavya_hi_conversational", "manan_hi_conversational",
        "rahul_hi_conversational", "sumit_hi_conversational", "aditya_hi_conversational",
        "aditya_hi_sales", "anand_hi_documentary", "anand_hi_news", "aparna_hi_customer",
        "aparna_hi_kyc", "ashok_hi_character", "ashok_hi_news", "chhavi_hi_kids",
        "ishita_hi_ads", "ishita_hi_edtech", "ishita_hi_banking", "ishita_hi_ads_informal",
        "ishita_hi_devotional", "ishita_hi_numbers", "ishita_hi_social", "kunal_hi_kids",
        "mahesh_hi_documentary", "mani_hi_devotional", "mani_hi_conversational",
        "mohit_hi_conversational", "nachiket_hi_devotional", "priya_hi_recovery",
        "ratan_hi_latenight", "ratan_hi_customer_expressive", "ratan_hi_documentary",
        "ratan_hi_devotional", "ratan_hi_recovery", "ratan_hi_social", "ratan_hi_sports",
        "ratan_hi_latenight_warm", "rehan_hi_social", "ritu_hi_customer_utility",
        "ritu_hi_kids", "ritu_hi_conversation", "ritu_hi_customer", "ritu_hi_edtech",
        "ritu_hi_ads_formal", "ritu_hi_banking", "ritu_hi_ads_informal",
        "ritu_hi_insurance", "ritu_hi_edtech_bot", "ritu_hi_medical", "ritu_hi_sales",
        "ritu_hi_reels", "ritu_hi_social", "ritu_hi_customer_warm", "ritu_hi_social_lively",
        "roopa_hi_companion", "roopa_hi_narration", "roopa_hi_recovery", "roopa_hi_market",
        "roopa_hi_conversational", "sanchita_hi_assistant", "sanchita_hi_edtech",
        "sanchita_hi_banking", "sanchita_hi_feedback", "sanchita_hi_ads_formal",
        "sanchita_hi_ads_informal", "sanchita_hi_interview", "sanchita_hi_romantic",
        "sanchita_hi_market", "sanchita_hi_social", "sanchita_hi_kyc",
        "sarika_hi_conversation", "shalini_hi_companion", "shalini_hi_social",
        "shreya_hi_conversational", "shreya_hi_news", "shruti_hi_edtech",
        "shubh_hi_customer", "shubh_hi_ecomm", "shubh_hi_stories_mixed",
        "shubh_hi_devotional", "shubh_hi_ads", "shubh_hi_recovery",
        "shubh_hi_stories_dramatic", "simran_hi_assistant", "simran_hi_narration",
        "simran_hi_automobile", "simran_hi_conversation", "simran_hi_news_breaking",
        "simran_hi_social_energetic", "simran_hi_social_excited", "simran_hi_latenight",
        "simran_hi_news", "simran_hi_recovery", "simran_hi_sales", "suchitra_hi_ecomm",
        "suhani_hi_social", "sunny_hi_ads", "sunny_hi_reels", "tarun_hi_conversational",
        "tarun_hi_sales", "chaitra_hi_customer", "shilpa_hi_narration",
        "tanya_hi_narration", "aarti_hi_customer", "advait_hi_character", "aryaman_hi_ads",
        "chirag_hi_social", "girish_hi_devotional", "mukul_hi_ads", "mukul_hi_suspense",
        "suman_hi_companion", "vaibhav_hi_social", "vandana_hi_ecomm", "vipul_hi_social",
    ),
    "enhi": (
        "ishita_enhi_companion", "ishita_enhi_customer", "ishita_enhi_customer_expressive",
        "sanchita_enhi_companion", "shalini_enhi_companion", "shalini_enhi_customer",
        "shubh_enhi_companion", "shubh_enhi_ads", "shubh_enhi_banking",
        "simran_enhi_companion", "simran_enhi_customer", "simran_enhi_banking_expressive",
        "sunny_enhi_customer",
    ),
    "en": (
        "aditi_en_stories", "aparna_en_companion", "aparna_en_edtech", "ashwin_en_sports",
        "ashwin_en_sports_energetic", "chandrika_en_stories", "dev_en_recovery",
        "dev_en_conversational", "deven_en_conversation", "ishita_en_customer",
        "ishita_en_medical", "ishita_en_numbers", "ishita_en_social", "ishita_en_stories",
        "kalpit_en_edtech", "nachiket_en_ads", "neha_en_customer", "neha_en_latenight",
        "nupur_en_kids", "ojas_en_social", "ritu_en_edtech", "ritu_en_latenight",
        "ritu_en_medical", "ritu_en_reels", "rohan_en_recovery", "roopa_en_conversational",
        "rustom_en_suspense", "sanchita_en_companion", "sanchita_en_insurance",
        "sanchita_en_recovery", "sanchita_en_market", "sanchita_en_social",
        "shabana_en_edtech", "shalini_en_companion", "shalini_en_customer",
        "shubh_en_narration", "shubh_en_numbers", "shubh_en_ads", "shubh_en_recovery",
        "shubh_en_audiobook", "shubh_en_narration_gentle", "shubh_en_sports",
        "simran_en_narration", "simran_en_automobile", "simran_en_conversation",
        "simran_en_customer", "simran_en_edtech", "simran_en_edtech_bot", "simran_en_sales",
        "simran_en_recovery", "simran_en_ads", "simran_en_therapist", "sunny_en_social",
        "varun_en_ads", "varun_en_suspense", "zarina_en_conversation",
        "amelia_en_conversational", "sophia_en_conversational", "girish_en_documentary",
        "girish_en_devotional", "payal_en_edtech", "sarang_en_narration",
    ),
    "bn": (
        "arnab_bn_conversation", "roopa_bn_conversational", "bimal_bn_suspense",
    ),
    "gu": (
        "bhavik_gu_conversation", "pooja_gu_conversational", "pooja_gu_customer",
    ),
    "kn": (
        "chaitra_kn_conversation", "chaitra_kn_narration", "chetan_kn_conversation",
        "suchitra_kn_narration",
    ),
    "mr": (
        "ishita_mr_conversational", "mrunal_mr_narration", "neha_mr_narration",
        "nilesh_mr_conversation", "ritu_mr_insurance", "ritu_mr_narration",
        "rupali_mr_stories", "soham_mr_narration", "mukul_mr_stories",
    ),
    "pa": (
        "anand_pa_conversation", "anand_pa_customer", "harpreet_pa_narration",
        "jaspal_pa_banking",
    ),
    "ta": (
        "gokul_ta_narration", "aravind_ta_ads", "aravind_ta_suspense", "vijay_ta_narration",
    ),
    "te": (
        "kavitha_te_conversation", "kavitha_te_narration", "pooja_te_conversation",
        "tarun_te_narration",
    ),
}
VOICE_IDS = frozenset(v for voices in VOICES_BY_LANGUAGE.values() for v in voices)

# Speaker gender by first name, for the voice picker's filter. Names used for
# both (Suman, Harpreet, Mrunal) are left out rather than guessed.
_FEMALE = frozenset((
    "aarti", "aditi", "amelia", "aparna", "chaitra", "chandrika", "chhavi", "ishita", "kavitha",
    "kavya", "neha", "nupur", "payal", "pooja", "priya", "ritu", "roopa", "rupali", "sanchita",
    "sarika", "shabana", "shalini", "shilpa", "shreya", "shruti", "simran", "sophia", "suchitra",
    "suhani", "tanya", "vandana", "zarina",
))
_MALE = frozenset((
    "aayan", "aditya", "advait", "amit", "anand", "aravind", "arnab", "aryaman", "ashok",
    "ashutosh", "ashwin", "bhavik", "bimal", "chetan", "chirag", "dev", "deven", "girish", "gokul",
    "jaspal", "kabir", "kalpit", "kunal", "mahesh", "manan", "mani", "mohit", "mukul", "nachiket",
    "nilesh", "ojas", "rahul", "ratan", "rehan", "rohan", "rustom", "sarang", "shubh", "soham",
    "sumit", "sunny", "tarun", "vaibhav", "varun", "vijay", "vipul",
))


class SarvamError(RuntimeError):
    """Sarvam refused or failed; the message is safe to show (no key, no raw body)."""


def voice_language(voice: str) -> str | None:
    """The language tag of a v4 voice id, or None when the id is unknown."""
    if voice not in VOICE_IDS:
        return None
    return voice.split("_")[1]


def voice_label(voice: str) -> str:
    """shubh_enhi_customer_expressive is "Shubh, customer expressive"."""
    parts = voice.split("_")
    name = parts[0].capitalize()
    style = " ".join(parts[2:])
    return f"{name}, {style}" if style else name


def voice_gender(voice: str) -> str | None:
    name = voice.split("_")[0]
    return "female" if name in _FEMALE else "male" if name in _MALE else None


def voice_style(voice: str) -> str:
    """shubh_enhi_customer_expressive is "customer expressive"."""
    return " ".join(voice.split("_")[2:])


def catalog() -> dict:
    return {
        "languages": [{"id": tag, "code": code, "label": label} for tag, (code, label) in LANGUAGES.items()],
        "voices": [
            {"id": v, "label": voice_label(v), "language": tag, "gender": voice_gender(v), "style": voice_style(v)}
            for tag, voices in VOICES_BY_LANGUAGE.items() for v in voices
        ],
    }


def arguments(text: str, voice: str, pace: float | None) -> dict:
    """The request body; raises ValueError with a message fit for the user."""
    tag = voice_language(voice)
    if tag is None:
        raise ValueError("Unknown Sarvam voice. Pick one from the list.")
    value = PACE_DEFAULT if pace is None else float(pace)
    if not PACE_MIN <= value <= PACE_MAX:
        raise ValueError(f"Pace must be between {PACE_MIN} and {PACE_MAX}.")
    return {
        "text": text,
        "target_language_code": LANGUAGES[tag][0],
        "speaker": voice,
        "model": MODEL,
        "pace": round(value, 2),
        "speech_sample_rate": SAMPLE_RATE,
        "output_audio_codec": "mp3",
    }


async def synthesize(api_key: str, body: dict) -> bytes:
    """MP3 bytes for one request. Raises SarvamError."""
    headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(API_URL, headers=headers, json=body)
    except httpx.HTTPError as exc:
        logger.warning(f"Sarvam request failed: {type(exc).__name__}")
        raise SarvamError("The Sarvam voice service could not be reached") from exc
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code != 200:
        error = data.get("error") if isinstance(data, dict) else None
        code = (error or {}).get("code") if isinstance(error, dict) else None
        logger.warning(f"Sarvam answered {response.status_code} ({code}): {str((error or {}).get('message', ''))[:200]}")
        if response.status_code == 429 or code in ("insufficient_quota_error", "rate_limit_exceeded_error"):
            raise SarvamError("The Sarvam voice service is busy or out of quota. Try again shortly")
        if code in ("invalid_api_key_error", "authentication_error") or response.status_code == 403:
            raise SarvamError("The Sarvam voice service is not set up correctly")
        raise SarvamError("Sarvam could not voice this text")
    audios = data.get("audios") if isinstance(data, dict) else None
    if not audios or not isinstance(audios[0], str):
        raise SarvamError("Sarvam returned no audio")
    try:
        return b"".join(base64.b64decode(a, validate=True) for a in audios)
    except (ValueError, TypeError) as exc:
        raise SarvamError("Sarvam returned unreadable audio") from exc
