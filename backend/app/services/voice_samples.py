"""Voice samples for the voice pickers (Lip Sync, My Assets, Motion Graphics).

One short line per voice, in the voice's own language, made the first time
anyone asks for it and kept in storage after that, so each voice is paid for
once (21 ElevenLabs and about 220 Sarvam voices, a few cents in all). Samples
live under the uploads/ prefix.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from app.services import sarvam_tts
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

# Bump to remake every sample (new wording or settings).
SAMPLE_VERSION = "v1"

ELEVEN_TEXT = "Hi, I'm {name}. This is how I sound when I read your script and bring your video to life."

# Gender neutral wording: Hindi and Marathi verbs change with the speaker.
SARVAM_TEXT = {
    "hi": "नमस्ते, यह मेरी आवाज़ है। आपकी कहानी, आपका विज्ञापन या आपका वीडियो, अब मेरी आवाज़ में।",
    "enhi": "Hello! यह मेरी आवाज़ है। Your story, your ad, या आपका video, अब मेरी आवाज़ में।",
    "en": "Hello, this is my voice. Your story, your ad or your video, now in my voice.",
    "bn": "নমস্কার, এটা আমার কণ্ঠস্বর। আপনার গল্প, আপনার বিজ্ঞাপন বা আপনার ভিডিও, এখন আমার কণ্ঠে।",
    "gu": "નમસ્તે, આ મારો અવાજ છે. તમારી વાર્તા, તમારી જાહેરાત કે તમારો વીડિયો, હવે મારા અવાજમાં.",
    "kn": "ನಮಸ್ಕಾರ, ಇದು ನನ್ನ ಧ್ವನಿ. ನಿಮ್ಮ ಕಥೆ, ನಿಮ್ಮ ಜಾಹೀರಾತು ಅಥವಾ ನಿಮ್ಮ ವೀಡಿಯೊ, ಈಗ ನನ್ನ ಧ್ವನಿಯಲ್ಲಿ.",
    "mr": "नमस्कार, हा माझा आवाज आहे. तुमची गोष्ट, तुमची जाहिरात किंवा तुमचा व्हिडिओ, आता माझ्या आवाजात.",
    "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਇਹ ਮੇਰੀ ਆਵਾਜ਼ ਹੈ। ਤੁਹਾਡੀ ਕਹਾਣੀ, ਤੁਹਾਡਾ ਇਸ਼ਤਿਹਾਰ ਜਾਂ ਤੁਹਾਡੀ ਵੀਡੀਓ, ਹੁਣ ਮੇਰੀ ਆਵਾਜ਼ ਵਿੱਚ।",
    "ta": "வணக்கம், இது என் குரல். உங்கள் கதை, உங்கள் விளம்பரம் அல்லது உங்கள் வீடியோ, இப்போது என் குரலில்.",
    "te": "నమస్కారం, ఇది నా గొంతు. మీ కథ, మీ ప్రకటన లేదా మీ వీడియో, ఇప్పుడు నా గొంతులో.",
}


class VoiceSampleError(RuntimeError):
    """The sample could not be made; the message is safe to show."""


# Samples this worker knows exist (key -> URL), and one lock per key so two
# clicks in one worker do not pay twice.
_known: dict[str, str] = {}
_locks: dict[str, asyncio.Lock] = {}


def _filename(provider: str, voice: str) -> str:
    return f"voice_sample_{SAMPLE_VERSION}_{provider}_{voice}.mp3"


def _validate(provider: str, voice: str) -> None:
    from app.services.faceless.catalog import VOICE_IDS as ELEVEN_IDS

    if provider == "elevenlabs" and voice in ELEVEN_IDS:
        return
    if provider == "sarvam" and voice in sarvam_tts.VOICE_IDS:
        return
    raise VoiceSampleError("Unknown voice. Pick one from the list.")


async def _synthesize(db: Session, provider: str, voice: str) -> bytes:
    from app.services import assets
    from app.services.fal_keys import get_sync_client

    if provider == "elevenlabs":
        arguments = assets.voice_arguments(ELEVEN_TEXT.format(name=voice), voice, None)
        return await assets._elevenlabs_audio(get_sync_client(db), arguments)
    key = assets.sarvam_key(db)
    if not key:
        raise VoiceSampleError("Sarvam voices are not available right now.")
    text = SARVAM_TEXT.get(sarvam_tts.voice_language(voice) or "", SARVAM_TEXT["en"])
    return await sarvam_tts.synthesize(key, sarvam_tts.arguments(text, voice, None))


async def sample_url(db: Session, provider: str, voice: str) -> str:
    """The URL of the voice's sample, making it on first use."""
    _validate(provider, voice)
    name = _filename(provider, voice)
    if name in _known:
        return _known[name]
    storage = StorageService()
    lock = _locks.setdefault(name, asyncio.Lock())
    async with lock:
        if name in _known:
            return _known[name]
        if await storage.file_exists(name, "uploads"):
            url = storage.get_public_url(name, "uploads")
        else:
            try:
                audio = await _synthesize(db, provider, voice)
            except VoiceSampleError:
                raise
            except Exception as exc:
                logger.exception(f"Voice sample {provider}/{voice} failed: {type(exc).__name__}")
                raise VoiceSampleError("This voice sample is not available right now. Please try again later.") from exc
            url = await storage.upload_file(audio, name, "uploads", content_type="audio/mpeg")
            logger.info(f"Voice sample made: {provider}/{voice} ({len(audio)} bytes)")
        _known[name] = url
        return url
