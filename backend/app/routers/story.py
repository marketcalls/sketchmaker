"""Story generation routes - text, image, reference and keyframes to video.

MiniMax H3 Max is the default model family; Seedance 2.5, Kling v4, FLUX 3 Max
and Gemini Omni Flash 1.1 are the alternatives (see STORY_VIDEO_MODELS in
app/clients/fal_client.py).
Stories are priced per second of video by family and resolution, plus H3 Max
reference tokens beyond the included allowance; Kling v4 and Seedance with
reference videos are priced on the input plus the output length
(app/services/pricing.py).
"""

import hashlib
import hmac
import uuid
import math
import random
import asyncio
import logging
import re
from datetime import datetime
from fastapi.concurrency import run_in_threadpool
from fastapi import APIRouter, HTTPException, status, UploadFile, File

from app.dependencies import CurrentUser, DbSession
from app.models.content import Video, StoryGenerationJob
from app.models.api import APISettings, APIProvider, AIModel
from app.schemas.story import (
    EnhancePromptRequest,
    EnhancePromptResponse,
    CreateStoryRequest,
    StoryJobResponse,
    StoryStatusResponse,
    StoryVideoResponse,
    StoryResultResponse,
    StoryGalleryResponse,
)
from app.clients.fal_client import (
    SUBTITLE_MODEL,
    get_story_generation_status,
    get_story_generation_result,
    download_and_save_video,
    submit_subtitle_generation,
    get_subtitle_generation_status,
    get_subtitle_generation_result,
    STORY_VIDEO_MODELS,
    DEFAULT_STORY_VIDEO_MODEL,
    resolve_story_options,
    build_story_arguments,
    submit_story_job,
    story_actual_usd,
    story_family_for_endpoint,
    story_model_for_job,
    story_usd_cost,
    story_video_input_seconds,
    subtitle_usd,
    is_content_policy_error,
    job_error_code,
    CONTENT_FILTER_ERROR,
)
from app.services.job_state import (
    CLAIMABLE_STATUSES,
    claim_job,
    JOB_HANDED_BACK,
    fail_claimed_job,
    lock_job,
)
from app.config import settings
from app.services.pricing import STORY_PROMPT_ENHANCE_KEY, usd_for
from app.services.usage import record_usage

logger = logging.getLogger(__name__)

router = APIRouter()


# Reference videos are priced on their length (H3 Max reference tokens, the
# Kling v4 and Seedance video-reference rates). The upload measures it and
# signs it into the stored filename, so /generate can trust it without
# downloading the file again: story_ref_<uuid>-d<centiseconds>-<signature>.
# Anything else (an external URL, an older upload) is estimated at the maximum.
_SIGNED_STORY_REF = re.compile(r"story_ref_([0-9a-f]{32})-d(\d{1,9})-([0-9a-f]{16})\.(?:mp4|mov)$")
STORY_VIDEO_UPLOAD_MAX_BYTES = 50 * 1024 * 1024


def _story_ref_signature(user_id: int, token: str, centis: int) -> str:
    message = f"story-ref-duration:{user_id}:{token}:{centis}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()[:16]


def signed_story_ref_filename(user_id: int, duration_seconds: float, ext: str) -> str:
    token = uuid.uuid4().hex
    centis = int(math.ceil(duration_seconds * 100))
    return f"story_ref_{token}-d{centis}-{_story_ref_signature(user_id, token, centis)}{ext}"


def story_ref_duration_from_url(url: str | None, user_id: int) -> float | None:
    """The length measured at upload, if ``url`` is this user's signed reference video."""
    from urllib.parse import urlparse

    name = (urlparse(url or "").path or "").rsplit("/", 1)[-1]
    match = _SIGNED_STORY_REF.search(name)
    if not match:
        return None
    token, centis, signature = match.group(1), int(match.group(2)), match.group(3)
    if not hmac.compare_digest(signature, _story_ref_signature(user_id, token, centis)):
        return None
    return centis / 100.0


async def add_subtitles_to_video(
    video_url: str,
    job: StoryGenerationJob,
    db,
) -> dict:
    """Add subtitles to a story video as a second stage.

    Uses all subtitle settings from the job, matching FAL auto-subtitle API.
    Returns the subtitled video result from FAL or raises an exception.
    """
    logger.info(f"Adding subtitles to story video: {job.job_id}")

    try:
        # Get background_color - handle "none" specially
        bg_color = job.subtitle_background_color or "none"
        background_color = None if bg_color in ("none", "transparent") else bg_color

        # Submit subtitle generation job with all FAL API parameters
        subtitle_result = await run_in_threadpool(
            submit_subtitle_generation,
            video_url=video_url,
            db=db,
            font_color=job.subtitle_font_color or "white",
            stroke_color=job.subtitle_stroke_color or "black",
            highlight_color=job.subtitle_highlight_color or "purple",
            background_color=background_color,
            position=job.subtitle_position or "bottom",
            font_size=job.subtitle_font_size or 100,
            font_name=job.subtitle_font_name or "Montserrat",
            font_weight=job.subtitle_font_weight or "bold",
            stroke_width=job.subtitle_stroke_width or 3,
            y_offset=job.subtitle_y_offset or 75,
            words_per_subtitle=job.subtitle_words_per_subtitle or 3,
            enable_animation=bool(job.subtitle_enable_animation),
            language=job.subtitle_language or "en",
        )

        subtitle_request_id = subtitle_result["request_id"]
        logger.info(f"Subtitle job submitted: {subtitle_request_id}")

        # Poll for completion (max 5 minutes)
        max_attempts = 60  # 60 * 5 seconds = 5 minutes
        for attempt in range(max_attempts):
            status = await run_in_threadpool(get_subtitle_generation_status, subtitle_request_id, db)

            if status.get("completed"):
                logger.info(f"Subtitle generation completed for story: {job.job_id}")
                # Get the result
                result = await run_in_threadpool(get_subtitle_generation_result, subtitle_request_id, db)
                return result

            if status.get("status") == "error" or "error" in str(status).lower():
                error_msg = status.get("error", "Subtitle generation failed")
                logger.error(f"Subtitle generation failed: {error_msg}")
                raise Exception(f"Subtitle generation failed: {error_msg}")

            # Wait before next poll. asyncio, not time.sleep: this runs on the
            # request's event loop, and a blocking sleep would stall every other
            # request on this worker for up to five minutes.
            await asyncio.sleep(5)

        raise Exception("Subtitle generation timed out after 5 minutes")

    except Exception as e:
        logger.error(f"Failed to add subtitles to story: {e}")
        raise


# What the prompt enhancer tells the LLM about each Stories model family.
STORY_ENHANCER_PROFILES = {
    "h3-max": "a fast AI video generation model with strong prompt adherence, refined aesthetics, native sound, and director-level camera control",
    "seedance-2.5": "an advanced AI video generation model with native audio, real-world physics simulation, lip-sync, and director-level camera control",
    "kling-v4": "an advanced AI video generation model with strong motion realism, real-world physics, consistent characters, and director-level camera control",
    "flux-3-max": "an advanced AI video generation model with native audio, rich photographic detail, real-world physics, and director-level camera control",
    "omni-flash": "Google's multimodal AI video model with synchronized native audio, real-world knowledge and physics, and cinematic camera control described in natural language",
}


class StoryEnhanceUnavailable(Exception):
    """The enhancer produced nothing (no model configured, or the call failed)."""


# Content type direction for the enhancer. Each keeps one dominant camera
# move per clip: a single generated clip is one continuous take, so cuts and
# stacked moves ("360 reveal plus macro") come back as wobble and flicker.
STORY_CONTENT_INSTRUCTIONS = {
    "cinematic": "Create a Hollywood blockbuster scene with dramatic lighting, depth of field, film grain, and one deliberate professional camera move. Think Nolan, Villeneuve, Deakins, or Lubezki-level cinematography.",
    "pixar": "Create a Pixar/Disney-quality 3D animated scene with vibrant colors, expressive cartoon characters, smooth rounded shapes, warm lighting, and heartfelt storytelling. Think Toy Story, Inside Out, Coco: family-friendly, emotionally rich, playful yet cinematic.",
    "anime": "Create a Japanese anime-style scene with dynamic action lines, expressive eyes, vivid colors, dramatic speed lines, and cinematic anime composition. Think Studio Ghibli, Makoto Shinkai, or shonen battle sequences.",
    "marvel": "Create a superhero-style action scene with epic wide shots, dramatic hero poses, energy effects, one sweeping camera move, and blockbuster intensity, with original characters only.",
    "fantasy": "Create an epic fantasy scene with magical lighting, mythical creatures, enchanted landscapes, dramatic weather, and otherworldly atmosphere. Think Lord of the Rings, Game of Thrones, or Studio Ghibli fantasy worlds.",
    "horror": "Create a suspenseful horror/thriller scene with moody shadows, unsettling angles, fog, flickering light, a slow reveal, and tension-building camera work. Think elevated horror, like Ari Aster, Jordan Peele, or classic Hitchcock.",
    "reel": "Create a vertical, attention-grabbing moment for Instagram Reels or TikTok: a strong hook in the first second, energetic subject motion and one fast camera move, all in one continuous take.",
    "story": "Create an engaging narrative moment that captures emotion and draws viewers in immediately. Think opening scene of a film.",
    "ad": "Create a premium, polished advertisement scene with product-hero lighting, one smooth camera reveal, and aspirational atmosphere.",
    "meme": "Create a humorous, exaggerated, or absurd scene with comedic timing, visual punch, and unexpected moments.",
    "vlog": "Create a personal, authentic-feeling scene with natural lighting, handheld energy, and a documentary intimacy.",
    "narration": "Create a cinematic scene with voiceover-friendly visuals: sweeping landscapes, atmospheric details, and a dramatic slow reveal.",
    "music": "Create a music video scene with rhythmic subject motion, dramatic lighting changes, stylized color grading, and performance energy.",
    "documentary": "Create a documentary-style scene with observational camera work, natural lighting, real-world textures, and journalistic composition. Think nature documentary or social storytelling.",
    "product": "Create a sleek product showcase: one slow, smooth camera move around the product, premium material textures, and an aspirational lifestyle context. Think Apple keynote or luxury brand commercial.",
}

# Spoken lines are sized to the clip: about 2.5 words per second.
STORY_WORDS_PER_SECOND = 2.5
# Past this length a clip gets time-coded beats, one action each.
STORY_BEATS_AFTER_SECONDS = 10


def _clip_seconds(duration: str | None, family_cfg: dict) -> int | None:
    """Seconds of the clip the prompt is for, or None when unknown ("auto")."""
    value = duration if duration not in (None, "") else family_cfg["default_duration"]
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _beat_marks(seconds: int) -> str:
    """Beat boundaries for a long clip, e.g. "0-4s, 4-8s, 8-12s"."""
    count = max(2, min(5, round(seconds / 4)))
    step = seconds / count
    marks = [round(i * step) for i in range(count)] + [seconds]
    return ", ".join(f"{marks[i]}-{marks[i + 1]}s" for i in range(count))


def build_enhancer_system_prompt(
    family: str,
    content_type: str | None = None,
    mode: str | None = None,
    duration: str | None = None,
    aspect_ratio: str | None = None,
    frames: str | None = None,
    reference_tags: list[str] | None = None,
    generate_audio: bool | None = None,
) -> str:
    """The prompt enhancer's instructions for one clip.

    Text-to-video gets the whole shot. Over a supplied start or end frame
    (or keyframes) the image already fixes the look, so only motion, camera
    and timing are written. In reference mode the subjects are named by their
    reference tags, never re-described. One dominant camera move per clip
    (bracket commands on H3 Max); clips over 10 seconds get time-coded
    beats. With sound, dialogue is a named speaker, a delivery verb and a
    quoted line sized to the clip, and the audio line names only what should
    be heard: an exclusion such as "no music" is what audio filters read.
    """
    family_cfg = STORY_VIDEO_MODELS[family]
    model_label = family_cfg["label"]
    model_profile = STORY_ENHANCER_PROFILES.get(family, STORY_ENHANCER_PROFILES[DEFAULT_STORY_VIDEO_MODEL])
    mode = mode if mode in ("text-to-video", "image-to-video", "reference-to-video", "keyframes") else "text-to-video"
    if family_cfg.get("native_audio"):
        has_audio = True
    else:
        has_audio = bool(family_cfg["audio"]) and generate_audio is not False
    brackets = family == "h3-max"
    seconds = _clip_seconds(duration, family_cfg)
    long_clip = seconds is not None and seconds > STORY_BEATS_AFTER_SECONDS

    content_instruction = STORY_CONTENT_INSTRUCTIONS.get(content_type or "", "")

    clip_facts = []
    clip_facts.append(f"{seconds} seconds" if seconds else "length chosen by the model (keep it to one beat)")
    if aspect_ratio and aspect_ratio not in ("auto", "adaptive"):
        clip_facts.append(f"{aspect_ratio} frame")

    # What the prompt describes depends on what the user already supplied.
    if mode == "image-to-video":
        which = {"start": "opening frame", "end": "closing frame", "both": "opening and closing frames"}.get(
            frames or "start", "opening frame"
        )
        task = (
            f"The user supplied the {which} as an image. The image already fixes the subject, wardrobe, setting, "
            "light and style. Write ONLY the motion, the camera and the timing: what moves and how, the one camera "
            "move, and how the shot "
            + ("travels from the first frame to the last." if frames == "both" else
               "arrives at the closing frame." if frames == "end" else "continues from the opening frame.")
            + " Never re-describe what the image shows; refer to it as 'the subject' or by role."
        )
    elif mode == "keyframes":
        task = (
            "The user supplied keyframe images pinned to times in the clip. They fix the look. Write ONLY the motion "
            "and camera that carry the shot from one keyframe to the next. Never re-describe what the images show."
        )
    elif mode == "reference-to-video":
        tags = [t for t in (reference_tags or []) if t]
        tag_text = ", ".join(tags) if tags else "Image 1, Image 2 and so on"
        task = (
            f"The user supplied reference uploads named {tag_text}. References carry identity and look, not the "
            "opening moment. Name each subject by its tag, for example 'the character from "
            f"{tags[0] if tags else 'Image 1'}', and never re-describe its face, body, outfit or colors. Say what each "
            "tag supplies and what it does not (for example 'take only the jacket from Image 2'). Spend the words on "
            "action, setting, camera and sound."
        )
        if any(t.lower().lstrip("@<").startswith("audio") for t in tags):
            task += " Bind every audio tag to a role in words, such as 'Audio 1 is her own voice, lip-synced'."
    else:
        task = (
            "Write the full shot in this order: shot size, setting, the subject and one action, one named camera "
            "move, the light source, the style."
        )

    if brackets:
        camera_rule = (
            "- Camera: open with ONE bracketed camera command such as [Push in], [Pull out], [Pan left], "
            "[Tracking shot] or [Static shot]; at most 2 or 3 motion cues in the whole prompt. Lock statics "
            "explicitly when the camera should not move."
        )
    else:
        camera_rule = (
            "- Camera: exactly ONE dominant, named camera move per clip (for example 'slow dolly-in' or "
            "'tracking shot follows her'). Never stack moves or write cuts: the clip is one continuous take."
        )

    if long_clip:
        timing_rule = (
            f"- Timing: this clip runs {seconds} seconds, so write time-coded beats, one action per beat "
            f"({_beat_marks(seconds)}), the last ending at {seconds}s, all one continuous take."
        )
    else:
        timing_rule = "- Timing: one continuous beat; complex scenes hold together best near 5 seconds."

    if has_audio:
        words = round(STORY_WORDS_PER_SECOND * seconds) if seconds else 15
        audio_rules = (
            f"- Dialogue (only if the scene needs it): name the speaker, give a delivery verb, then the quoted "
            f"line, e.g. Maya whispers: \"We made it.\" At most {words} spoken words in total for this clip.\n"
            "- End with one audio line that names only sounds the scene itself makes, positively, e.g. "
            "\"Audio: rain on the umbrella, distant traffic, footsteps on wet asphalt.\" Never name a sound to "
            "leave out (no \"no music\"), and never name a music genre or instrument.\n"
            "- Close with: No subtitles, no on-screen text."
        )
    else:
        audio_rules = (
            "- This model renders the picture only: no dialogue, voice-over or sound descriptions; carry the "
            "mood through action, expression and framing.\n"
            "- Close with: No subtitles, no on-screen text."
        )

    move = "[Push in] " if brackets else ""
    dolly = "" if brackets else " Slow dolly-in as she stops under a flickering sign."
    stop = " She stops under a flickering sign." if brackets else ""
    speaker = "The subject" if mode in ("image-to-video", "keyframes") else "The woman"
    dialogue = f' {speaker} says softly: "Almost home."' if has_audio else ""
    audio_line = " Audio: rain on her umbrella, distant traffic, her footsteps on wet asphalt." if has_audio else ""
    if mode in ("image-to-video", "keyframes"):
        example = (
            f"{move}The subject lowers the umbrella and looks up as the rain eases; the coat settles and droplets "
            f"slide off the brim.{'' if brackets else ' Slow push-in, ending on a close-up of her face.'}"
            f"{dialogue}{audio_line} No subtitles, no on-screen text."
        )
    elif mode == "reference-to-video":
        tags = [t for t in (reference_tags or []) if t] or ["Image 1"]
        example = (
            f"{move}The character from {tags[0]} walks through a rain-soaked night market, umbrella in hand, "
            f"neon reflected in the puddles around her.{dolly}{stop} Cool blue street light with warm red rim "
            f"light, cinematic film grain.{dialogue}{audio_line} No subtitles, no on-screen text."
        )
    else:
        example = (
            f"{move}Wide shot of a rain-soaked Tokyo street at night, neon signs reflected in the puddles. A woman "
            f"in a red raincoat walks toward the camera, umbrella in hand, steam rising from a manhole beside her."
            f"{dolly}{stop} Cool blue street light with warm red rim light from the neon, cinematic film grain."
            f"{dialogue}{audio_line} No subtitles, no on-screen text."
        )
    if long_clip:
        example = (
            "(For a long clip, the same shot as beats: \"0-4s: ... 4-8s: ... 8-12s: ...\", each beat one action, "
            "the camera move carried through.)\n" + example
        )

    return f"""You are a film director writing the prompt for one video clip on {model_label}, {model_profile}.

CLIP: {', '.join(clip_facts)}.
{f"CONTENT TYPE: {content_instruction}" if content_instruction else ""}

YOUR TASK: {task}

RULES:
{camera_rule}
{timing_rule}
- Write natural sentences, not tag lists. Named moves and concrete light sources survive generation; mood words do not.
- Describe size by proportion ("as tall as her shoulder"), not intensity words such as huge, massive or oversized.
- No real people, celebrities or comparisons to them, and no trademarked characters or logos; describe character types instead.
- No text overlays, captions, watermarks or UI elements in the picture.
{audio_rules}

EXAMPLE OUTPUT:
{example}

OUTPUT: Return ONLY the prompt. No explanations, headings or quotes around it."""


async def enhance_story_prompt(
    topic: str,
    style: str | None,
    content_type: str | None,
    db,
    video_model: str | None = None,
    strict: bool = False,
    mode: str | None = None,
    duration: str | None = None,
    aspect_ratio: str | None = None,
    frames: str | None = None,
    reference_tags: list[str] | None = None,
    generate_audio: bool | None = None,
) -> str:
    """Enhance a story prompt using LLM for Hollywood-director quality video generation.

    The instructions follow the clip (build_enhancer_system_prompt): the
    model family, the mode and what was supplied, the length and the sound.

    ``strict``: raise StoryEnhanceUnavailable instead of returning the topic
    unchanged when nothing could be generated (the paid endpoint refunds then).
    """
    from app.clients.litellm_client import generate_completion

    family = video_model if video_model in STORY_VIDEO_MODELS else DEFAULT_STORY_VIDEO_MODEL

    # Get API settings
    api_settings = db.query(APISettings).first()
    if not api_settings or not api_settings.default_provider_id or not api_settings.default_model_id:
        logger.warning("Story prompt enhancement skipped: No default provider/model configured")
        if strict:
            raise StoryEnhanceUnavailable()
        return topic  # Return original if no API configured

    # Get provider and model
    provider = db.query(APIProvider).filter(APIProvider.id == api_settings.default_provider_id).first()
    model = db.query(AIModel).filter(AIModel.id == api_settings.default_model_id).first()

    if not provider or not model:
        logger.warning("Story prompt enhancement skipped: Provider or model not found")
        if strict:
            raise StoryEnhanceUnavailable()
        return topic

    system_prompt = build_enhancer_system_prompt(
        family,
        content_type=content_type,
        mode=mode,
        duration=duration,
        aspect_ratio=aspect_ratio,
        frames=frames,
        reference_tags=reference_tags,
        generate_audio=generate_audio,
    )
    style_instruction = f"\nVisual style: {style}" if style else ""

    try:
        enhanced = await generate_completion(
            prompt=f"Direct this video clip:{style_instruction}\n\nConcept: {topic}",
            model_name=model.name,
            provider_name=provider.name,
            db=db,
            max_tokens=700,
            temperature=0.8,
            system_prompt=system_prompt,
        )
        enhanced = (enhanced or "").strip()
        if not enhanced and strict:
            raise StoryEnhanceUnavailable()
        return enhanced or topic
    except StoryEnhanceUnavailable:
        raise
    except Exception as e:
        logger.error(f"Story prompt enhancement failed: {e}")
        if strict:
            raise StoryEnhanceUnavailable() from e
        return topic  # Return original if enhancement fails


@router.post("/enhance-prompt", response_model=EnhancePromptResponse)
async def enhance_prompt_endpoint(
    body: EnhancePromptRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Enhance a story prompt using AI for better video generation.

    Takes a simple idea and turns it into a prompt for the clip described by
    the request (model, mode and supplied frames or references, length,
    aspect, sound).
    """
    try:
        enhanced = await enhance_story_prompt(
            topic=body.topic,
            style=body.style,
            content_type=body.content_type,
            db=db,
            video_model=body.video_model,
            strict=True,
            mode=body.mode,
            duration=body.duration,
            aspect_ratio=body.aspect_ratio,
            frames=body.frames,
            reference_tags=body.reference_tags,
            generate_audio=body.generate_audio,
        )

        return EnhancePromptResponse(
            original_prompt=body.topic,
            enhanced_prompt=enhanced,
            estimated_usd=usd_for(STORY_PROMPT_ENHANCE_KEY),
        )

    except StoryEnhanceUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The prompt enhancer is not available right now. Please try again.",
        )
    except Exception:
        logger.exception("Story prompt enhancement failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The prompt could not be enhanced right now. Please try again.",
        )


@router.post("/upload-image")
async def upload_story_image(
    current_user: CurrentUser,
    db: DbSession,
    image: UploadFile = File(...),
):
    """Upload a source image for image-to-video story generation.

    The story video models need hosted URLs for source, reference and keyframe images.
    This endpoint uploads the image and returns a publicly accessible URL.

    Maximum file size: 25MB (the models accept up to 30MB)
    Supported formats: JPEG, PNG, WebP
    """
    from app.services.storage_service import storage_service

    max_size = 25 * 1024 * 1024  # 25MB
    content = await image.read(max_size + 1)
    file_size = len(content)

    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image file too large. Maximum size is 25MB",
        )

    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if image.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image format. Allowed: JPEG, PNG, WebP",
        )

    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    ext = ext_map.get(image.content_type, ".jpg")
    filename = f"story_src_{uuid.uuid4()}{ext}"

    url = await storage_service.upload_file(
        file_data=content,
        filename=filename,
        storage_type="uploads",
        content_type=image.content_type,
        user_id=current_user.id,
    )

    logger.info(f"Story source image uploaded: {filename} ({file_size / 1024:.2f} KB)")

    return {
        "url": url,
        "filename": filename,
        "file_size_bytes": file_size,
        "message": "Image uploaded successfully",
    }


@router.post("/upload-video")
async def upload_story_video(
    current_user: CurrentUser,
    db: DbSession,
    video: UploadFile = File(...),
):
    """Upload a reference video for reference-to-video mode.

    Maximum file size: 50MB
    Supported formats: MP4, MOV
    """
    from app.services.storage_service import storage_service

    max_size = STORY_VIDEO_UPLOAD_MAX_BYTES
    content = await video.read(max_size + 1)
    file_size = len(content)

    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Video file too large. Maximum size is 50MB",
        )

    allowed_types = {"video/mp4", "video/quicktime"}
    if video.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported video format. Allowed: MP4, MOV",
        )

    ext_map = {"video/mp4": ".mp4", "video/quicktime": ".mov"}
    ext = ext_map.get(video.content_type, ".mp4")
    # Measure the length for the reference price; only a real measurement is
    # signed into the filename.
    from app.routers.video import _probe_upload_duration

    measured = await run_in_threadpool(_probe_upload_duration, content, ext)
    if measured:
        filename = signed_story_ref_filename(current_user.id, measured, ext)
    else:
        filename = f"story_ref_{uuid.uuid4()}{ext}"

    url = await storage_service.upload_file(
        file_data=content,
        filename=filename,
        storage_type="uploads",
        content_type=video.content_type,
        user_id=current_user.id,
    )

    logger.info(f"Story reference video uploaded: {filename} ({file_size / 1024 / 1024:.2f} MB)")

    return {
        "url": url,
        "filename": filename,
        "file_size_bytes": file_size,
        "duration_seconds": measured,
        "message": "Video uploaded successfully",
    }


@router.post("/upload-audio")
async def upload_story_audio(
    current_user: CurrentUser,
    db: DbSession,
    audio: UploadFile = File(...),
):
    """Upload a reference audio for reference-to-video mode.

    Maximum file size: 15MB
    Supported formats: MP3, WAV
    """
    from app.services.storage_service import storage_service

    max_size = 15 * 1024 * 1024  # 15MB
    content = await audio.read(max_size + 1)
    file_size = len(content)

    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file too large. Maximum size is 15MB",
        )

    allowed_types = {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp3"}
    if audio.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported audio format. Allowed: MP3, WAV",
        )

    ext_map = {"audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav"}
    ext = ext_map.get(audio.content_type, ".mp3")
    filename = f"story_ref_{uuid.uuid4()}{ext}"

    url = await storage_service.upload_file(
        file_data=content,
        filename=filename,
        storage_type="uploads",
        content_type=audio.content_type,
        user_id=current_user.id,
    )

    logger.info(f"Story reference audio uploaded: {filename} ({file_size / 1024:.2f} KB)")

    return {
        "url": url,
        "filename": filename,
        "file_size_bytes": file_size,
        "message": "Audio uploaded successfully",
    }


@router.post("/generate", response_model=StoryJobResponse)
async def generate_story_endpoint(
    body: CreateStoryRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Submit an async story generation job.

    video_model picks the family (Seedance 2.5 by default, Kling v4, FLUX 3
    Max); every option is validated against it (400 on a mismatch).

    Returns a job_id immediately. Poll /story/status/{job_id} for progress,
    then fetch results from /story/result/{job_id} when complete.

    Cost: the family's per-second price at the chosen resolution times the
    duration. "auto" is estimated at the family's longest auto length and
    recorded on the real length when the job finishes.
    """
    # Validate every option against the chosen model family and build the fal
    # arguments. ValueError carries a message fit for the user.
    job_id = str(uuid.uuid4())
    end_user_id = str(current_user.id)
    try:
        options = resolve_story_options(
            video_model=body.video_model,
            mode=body.mode,
            duration=body.duration,
            resolution=body.resolution,
            aspect_ratio=body.aspect_ratio,
        )
        family_cfg = STORY_VIDEO_MODELS[options["family"]]
        # Seedance never received the seed (kept on the job as before); H3 Max
        # and FLUX 3 Max are sent it; Kling v4 has no seed. A final render
        # passes its preview's seed, which only families that take one use.
        seed = None
        if family_cfg["seed"] and body.seed is not None:
            seed = body.seed
        elif family_cfg["seed"] or options["family"] == "seedance-2.5":
            seed = random.randint(0, 2147483647)
        keyframes = [kf.model_dump() for kf in body.keyframes] if body.keyframes else None
        arguments = build_story_arguments(
            options,
            prompt=body.prompt,
            generate_audio=body.generate_audio,
            image_url=body.image_url,
            end_image_url=body.end_image_url,
            image_urls=body.image_urls,
            video_urls=body.video_urls,
            audio_urls=body.audio_urls,
            keyframes=keyframes,
            end_user_id=end_user_id,
            seed=seed,
            target_audio_url=body.target_audio_url,
            # The model may rewrite only the user's own raw text; an enhanced
            # prompt is already engineered and must arrive as written.
            prompt_expansion=not body.original_prompt,
        )
        # Reference inputs as sent (a reference-mode start image counts as an
        # image), for the families that price reference tokens.
        ref_fields = family_cfg.get("reference_fields") or {}
        ref_images = len(arguments.get(ref_fields.get("images", ""), []) or [])
        if family_cfg.get("reference_start_field") and arguments.get(family_cfg["reference_start_field"]):
            ref_images += 1
        ref_videos = list(arguments.get(ref_fields.get("videos", ""), []) or [])
        # Measured lengths of this user's signed uploads; None assumes the maximum.
        video_seconds = [story_ref_duration_from_url(url, current_user.id) for url in ref_videos]
        estimated_usd = story_usd_cost(
            options["family"],
            options["resolution"],
            options["duration"],
            mode=options["mode"],
            image_count=ref_images,
            video_count=len(ref_videos),
            audio_count=len(arguments.get(ref_fields.get("audios", ""), []) or []),
            video_seconds=video_seconds,
        )
        video_input_seconds = (
            story_video_input_seconds(options["family"], len(ref_videos), video_seconds)
            if options["mode"] == "reference-to-video" else 0
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    try:
        # Blocking network calls: off the event loop.
        request_id = await run_in_threadpool(submit_story_job, options["endpoint"], arguments, db)

        # Create job record
        duration_int = 0 if options["duration"] == "auto" else int(options["duration"])
        first_image = body.image_url
        if options["mode"] == "keyframes" and arguments.get("keyframes"):
            first_image = arguments["keyframes"][0]["image_url"]

        job = StoryGenerationJob(
            job_id=job_id,
            request_id=request_id,
            user_id=current_user.id,
            prompt=body.prompt,
            original_prompt=body.original_prompt,
            enhanced_prompt=body.prompt if body.original_prompt else None,
            mode=options["mode"],
            model=options["endpoint"],
            image_url=first_image,
            duration_seconds=duration_int,
            resolution=options["resolution"],
            # Kling image-to-video takes no aspect ratio: it follows the image.
            aspect_ratio=options["aspect_ratio"] or "auto",
            seed=seed,
            # Subtitle settings
            add_subtitles=1 if body.add_subtitles else 0,
            subtitle_font_color=body.subtitle_font_color,
            subtitle_stroke_color=body.subtitle_stroke_color,
            subtitle_highlight_color=body.subtitle_highlight_color,
            subtitle_background_color=body.subtitle_background_color,
            subtitle_position=body.subtitle_position,
            subtitle_font_size=body.subtitle_font_size,
            subtitle_font_name=body.subtitle_font_name,
            subtitle_font_weight=body.subtitle_font_weight,
            subtitle_stroke_width=body.subtitle_stroke_width,
            subtitle_y_offset=body.subtitle_y_offset,
            subtitle_words_per_subtitle=body.subtitle_words_per_subtitle,
            subtitle_enable_animation=1 if body.subtitle_enable_animation else 0,
            subtitle_language=body.subtitle_language,
            status="pending",
            estimated_usd=estimated_usd,
            # The reference video length the estimate was priced on, for an
            # "auto" length (story_actual_usd).
            result={"pricing": {"video_input_seconds": video_input_seconds}} if video_input_seconds else None,
        )
        db.add(job)
        db.commit()

        logger.info(f"Story generation job submitted: {job_id}")

        return StoryJobResponse(
            job_id=job_id,
            status="pending",
            message="Story generation job submitted. Poll /story/status/{job_id} for progress.",
        )

    except ValueError as e:
        # Options were validated above; this comes from fal or the database.
        logger.error(f"Story generation submit rejected: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This video request could not be accepted. Check the inputs and try again.",
        )
    except Exception as e:
        logger.error(f"Story generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We could not start this video right now. Please try again in a moment.",
        )


@router.get("/status/{job_id}", response_model=StoryStatusResponse)
async def get_story_job_status(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get status of a story generation job."""
    job = db.query(StoryGenerationJob).filter(
        StoryGenerationJob.job_id == job_id,
        StoryGenerationJob.user_id == current_user.id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Return cached status if truly completed
    if job.status == "completed" and job.result and job.result.get("video_id"):
        return StoryStatusResponse(
            job_id=job.job_id,
            status="completed",
            progress=100,
            logs=job.logs.split("\n") if job.logs else None,
            error=job.error,
            error_code=job_error_code(job.error),
            created_at=job.created_at,
            started_at=job.started_at,
        )

    # Return failed status
    if job.status == "failed":
        return StoryStatusResponse(
            job_id=job.job_id,
            status="failed",
            progress=0,
            logs=job.logs.split("\n") if job.logs else None,
            error=job.error,
            error_code=job_error_code(job.error),
            created_at=job.created_at,
            started_at=job.started_at,
        )

    # If processing, return current status
    if job.status == "processing":
        return StoryStatusResponse(
            job_id=job.job_id,
            status="processing",
            progress=job.progress or 75,
            logs=job.logs.split("\n") if job.logs else None,
            error=job.error,
            error_code=job_error_code(job.error),
            created_at=job.created_at,
            started_at=job.started_at,
        )

    # Determine FAL model based on whether this is image-to-video
    fal_model = story_model_for_job(job)

    # Poll FAL for current status
    try:
        fal_status = await run_in_threadpool(get_story_generation_status, job.request_id, db, model=fal_model)

        # Re-read under the row lock: the job may have been claimed while fal
        # answered, and a stale write would make it claimable again.
        job = lock_job(db, StoryGenerationJob, job.id)
        if job.status not in CLAIMABLE_STATUSES:
            db.rollback()
            fal_status = {"status": job.status, "logs": fal_status.get("logs")}
        elif fal_status.get("completed"):
            if job.status == "pending":
                job.status = "in_progress"
            job.progress = 90
            if not job.started_at:
                job.started_at = datetime.utcnow()
        elif fal_status.get("in_progress"):
            job.status = "in_progress"
            job.progress = 50
            if not job.started_at:
                job.started_at = datetime.utcnow()
        elif fal_status.get("status") == "error":
            job.status = "failed"
            job.error = fal_status.get("error")

        # Store logs
        if fal_status.get("logs"):
            job.logs = "\n".join(fal_status["logs"])

        db.commit()

        # Return status - use "ready" when FAL is complete but video not yet processed
        if fal_status.get("completed"):
            response_status = "ready"
            response_progress = 95
        else:
            response_status = job.status
            response_progress = job.progress or 0

        return StoryStatusResponse(
            job_id=job.job_id,
            status=response_status,
            progress=response_progress,
            logs=fal_status.get("logs"),
            error=job.error,
            error_code=job_error_code(job.error),
            created_at=job.created_at,
            started_at=job.started_at,
        )

    except Exception as e:
        logger.error(f"Failed to get story job status: {e}", exc_info=True)
        return StoryStatusResponse(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress or 0,
            error="We could not check this video just now. It is still running, so please check again in a moment.",
            created_at=job.created_at,
            started_at=job.started_at,
        )


@router.get("/result/{job_id}", response_model=StoryResultResponse)
async def get_story_job_result(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get result of a completed story generation job.

    Downloads the video from FAL, saves it locally, creates a Video record
    and records what it cost.
    """
    # No row lock: it would be held across the fal calls below. The job is
    # claimed atomically (claim_job) once fal reports it finished.
    job = db.query(StoryGenerationJob).filter(
        StoryGenerationJob.job_id == job_id,
        StoryGenerationJob.user_id == current_user.id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # GUARD 1: Return cached result if already processed
    if job.result and job.result.get("video_id"):
        video_id = job.result.get("video_id")
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            return StoryResultResponse(
                job_id=job.job_id,
                status="completed",
                video=StoryVideoResponse.from_orm_with_urls(video),
                estimated_usd=job.estimated_usd or 0,
                completed_at=job.completed_at,
            )

    # GUARD 2: If job is being processed, don't interfere
    if job.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is currently being processed. Please try again in a few seconds.",
        )

    if job.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=job.error or "Story generation failed",
        )

    # Determine FAL model based on whether this is image-to-video
    fal_model = story_model_for_job(job)

    # Check if job is complete with FAL
    fal_status = await run_in_threadpool(get_story_generation_status, job.request_id, db, model=fal_model)
    if not fal_status.get("completed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job not complete. Current status: {fal_status.get('status', 'unknown')}",
        )

    # Claim the job: only one caller (this endpoint or the scheduler) may
    # download and store it.
    if not claim_job(db, StoryGenerationJob, job.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is currently being processed. Please try again in a few seconds.",
        )
    db.refresh(job)

    try:
        # Fetch result from FAL
        fal_result = await run_in_threadpool(get_story_generation_result, job.request_id, db, model=fal_model)

        # Download and save video
        video_data = await download_and_save_video(fal_result, user_id=job.user_id)

        # Price on the generated clip, before subtitles replace it: fixed
        # lengths keep the estimate, "auto" follows the real length.
        usd, billed_seconds = story_actual_usd(job, fal_result, video_data.get("duration_seconds"))

        # STAGE 2: Add subtitles if enabled
        subtitles_added_successfully = False
        if job.add_subtitles:
            logger.info(f"Story {job.job_id}: Adding subtitles (stage 2)")
            job.progress = 80
            db.commit()

            try:
                from app.services.storage_service import storage_service

                # fal's own copy of the clip: it needs no upload.
                video_url = fal_result["video"]["url"]

                # Add subtitles to the video
                subtitle_result = await add_subtitles_to_video(video_url, job, db)

                # Download the subtitled video and replace original
                subtitled_video_data = await download_and_save_video(subtitle_result, user_id=job.user_id)

                # Only delete original after confirming subtitled video was saved
                original_filename = video_data["filename"]
                original_thumbnail = video_data.get("thumbnail_filename")

                # Use subtitled video data
                video_data = subtitled_video_data
                subtitles_added_successfully = True
                logger.info(f"Story {job.job_id}: Subtitles added successfully")

                # Now safe to delete original video file (without subtitles)
                try:
                    await storage_service.delete_file(original_filename, "videos", user_id=job.user_id)
                    if original_thumbnail:
                        await storage_service.delete_file(original_thumbnail, "thumbnails", user_id=job.user_id)
                except Exception as del_err:
                    logger.warning(f"Failed to delete original video: {del_err}")

            except Exception as subtitle_error:
                logger.error(f"Story {job.job_id}: Subtitle generation failed: {subtitle_error}")
                # Continue with the original video (without subtitles)
                # subtitles_added_successfully remains False - has_subtitles will be 0

        # GUARD 3: Re-check job hasn't been processed while downloading
        db.refresh(job)
        if job.result and job.result.get("video_id"):
            video = db.query(Video).filter(Video.id == job.result["video_id"]).first()
            if video:
                return StoryResultResponse(
                    job_id=job.job_id,
                    status="completed",
                    video=StoryVideoResponse.from_orm_with_urls(video),
                    estimated_usd=job.estimated_usd or 0,
                    completed_at=job.completed_at,
                )

        # Save video to database with story-specific fields
        video = Video(
            filename=video_data["filename"],
            thumbnail_filename=video_data.get("thumbnail_filename"),
            prompt=job.prompt,
            original_prompt=job.original_prompt,
            video_type="story",
            has_subtitles=1 if subtitles_added_successfully else 0,
            duration_seconds=video_data.get("duration_seconds"),
            width=video_data.get("width"),
            height=video_data.get("height"),
            fps=video_data.get("fps"),
            file_size_bytes=video_data.get("file_size_bytes"),
            model=story_model_for_job(job),
            seed=job.seed,  # Store seed for reproducibility
            user_id=current_user.id,
        )
        db.add(video)
        db.flush()

        record_usage(
            db,
            feature="story",
            usd=usd,
            model=story_model_for_job(job),
            units=billed_seconds,
            unit="second",
            job_type="story",
            job_id=job.job_id,
            detail={
                "aspect_ratio": job.aspect_ratio,
                "has_subtitles": subtitles_added_successfully,
                "video_model": story_family_for_endpoint(story_model_for_job(job)),
                "resolution": job.resolution,
                "reference_tokens": fal_result.get("reference_tokens") if isinstance(fal_result, dict) else None,
                "source": "result_endpoint",
            },
        )
        if subtitles_added_successfully:
            # Stage 2 is a fal job of its own.
            record_usage(
                db,
                feature="subtitle",
                usd=subtitle_usd(video_data.get("duration_seconds")),
                model=SUBTITLE_MODEL,
                job_type="story",
                job_id=job.job_id,
                detail={"source": "result_endpoint"},
            )

        # Update job
        job.status = "completed"
        job.progress = 100
        job.estimated_usd = usd
        job.completed_at = datetime.utcnow()
        job.result = {"video_id": video.id}

        db.commit()

        logger.info(f"Story generation completed: {job_id}")

        return StoryResultResponse(
            job_id=job.job_id,
            status="completed",
            video=StoryVideoResponse.from_orm_with_urls(video),
            estimated_usd=usd,
            completed_at=job.completed_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Story processing failed: {e}", exc_info=True)
        if is_content_policy_error(e):
            # fal finished the request with a moderation refusal: nothing to
            # save; a same-model retry is refused again.
            fail_claimed_job(db, StoryGenerationJob, job.id, CONTENT_FILTER_ERROR)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=CONTENT_FILTER_ERROR)
        message = "We could not save this video. Please try generating it again."
        failed = fail_claimed_job(db, StoryGenerationJob, job.id, message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message if failed else JOB_HANDED_BACK,
        )


@router.get("/gallery", response_model=StoryGalleryResponse)
async def get_story_gallery(
    current_user: CurrentUser,
    db: DbSession,
    page: int = 1,
    page_size: int = 20,
):
    """Get user's generated story videos.

    Returns paginated list of story videos (video_type='story').
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    if page_size > 100:
        page_size = 100

    # Count total story videos for user
    total = db.query(Video).filter(
        Video.user_id == current_user.id,
        Video.video_type == "story",
    ).count()

    total_pages = math.ceil(total / page_size) if total > 0 else 1
    offset = (page - 1) * page_size

    # Get paginated videos
    videos = db.query(Video).filter(
        Video.user_id == current_user.id,
        Video.video_type == "story",
    ).order_by(Video.created_at.desc()).offset(offset).limit(page_size).all()

    return StoryGalleryResponse(
        videos=[StoryVideoResponse.from_orm_with_urls(v) for v in videos],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.delete("/{video_id}")
async def delete_story(
    video_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Delete a story video and its stored files."""
    from app.services.storage_service import storage_service

    video = db.query(Video).filter(
        Video.id == video_id,
        Video.user_id == current_user.id,
        Video.video_type == "story",
    ).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story video not found",
        )

    filename, thumbnail = video.filename, video.thumbnail_filename

    # Database first, then storage (best effort)
    db.delete(video)
    db.commit()

    try:
        await storage_service.delete_file(filename, "videos", user_id=current_user.id)
        if thumbnail:
            await storage_service.delete_file(thumbnail, "thumbnails", user_id=current_user.id)
    except Exception as e:
        logger.warning(f"Failed to delete story files: {e}")

    return {"status": "ok", "message": "Story deleted"}


@router.get("/{video_id}/download")
async def download_story(
    video_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get download URL for a story video."""
    video = db.query(Video).filter(
        Video.id == video_id,
        Video.user_id == current_user.id,
        Video.video_type == "story",
    ).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story video not found",
        )

    return {
        "download_url": video.get_url(),
        "filename": video.filename,
    }
