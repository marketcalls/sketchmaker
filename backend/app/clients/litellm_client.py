"""LiteLLM client for unified LLM access."""

import logging
import os
import re

# Before importing litellm: in its default mode it loads the nearest .env into
# os.environ, and every subprocess would inherit what is in there.
os.environ["LITELLM_MODE"] = "PRODUCTION"

import litellm  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.models.api import APISettings, APIProvider  # noqa: E402

# Configure LiteLLM
litellm.drop_params = True  # Drop unsupported params instead of erroring
litellm.suppress_debug_info = True  # its help text goes to stdout, past the log redaction


# Provider prefixes for LiteLLM
logger = logging.getLogger(__name__)

PROVIDER_PREFIXES = {
    "OpenAI": "openai/",
    "Anthropic": "anthropic/",
    "Google Gemini": "gemini/",
    "Groq": "groq/",
    "xAI": "xai/",
    "Cerebras": "cerebras/",
    "OpenRouter": "openrouter/",
    # OpenAI-compatible endpoints route through LiteLLM's openai/ path and
    # supply their own api_base, taken from the provider row.
    "Baseten": "openai/",
}

# Providers whose endpoint lives somewhere other than the vendor default. The
# address is stored on the provider row by the seed.
OPENAI_COMPATIBLE_DEFAULTS = {
    "Baseten": "https://inference.baseten.co/v1",
}


def _estimated_usd(provider_name: str, model_name: str, input_tokens: int, output_tokens: int) -> float | None:
    """litellm's price for these tokens, or None when it does not know the model."""
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=f"{get_model_prefix(provider_name)}{model_name}",
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        return round(float(prompt_cost) + float(completion_cost), 6)
    except Exception:
        return None


def record_token_usage(db: Session, response, provider_name: str, model_name: str,
                       feature: str = "other", user_id: int | None = None) -> None:
    """Record what a call cost in tokens, and in USD where the price is known. Never
    raises. This is the only record of LLM spending: callers must not also call
    usage.record_usage.

    Accounting must not be able to break the feature it is measuring, so every
    failure here is swallowed. A missing row is a gap in a report; an exception
    is a broken generation.
    """
    try:
        from app.models.llm_usage import LLMUsage

        usage = getattr(response, "usage", None)
        if usage is None:
            return
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        db.add(LLMUsage(
            user_id=user_id,
            feature=feature,
            provider=provider_name,
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_usd=_estimated_usd(provider_name, model_name, input_tokens, output_tokens),
        ))
        db.commit()
    except Exception as exc:
        logger.warning(f"Could not record token usage: {type(exc).__name__}: {exc}")
        try:
            db.rollback()
        except Exception:
            pass


def get_provider_base_url(provider_name: str, db: Session) -> str | None:
    """The API endpoint for a provider, if it is not the vendor default."""
    provider = db.query(APIProvider).filter(APIProvider.name == provider_name).first()
    configured = (getattr(provider, "base_url", None) or "").strip()
    return configured or OPENAI_COMPATIBLE_DEFAULTS.get(provider_name)

# Model families that only accept the default temperature. Verified against a
# live OpenAI 400 on gpt-5.6-luna; applies to the whole GPT-5 line.
NO_TEMPERATURE_FAMILIES = ("gpt-5",)

# Reasoning models that need special handling
REASONING_MODELS = {
    "o1",
    "o1-mini",
    "o1-preview",
    "o3",
    "o3-mini",
    "gpt-oss-120b",
}


LLM_KEY_REJECTED = "Your language model provider rejected the API key. Check it in Settings, under API keys."


def is_llm_auth_error(exc: BaseException) -> bool:
    """The provider refused the stored key, as opposed to any other failure."""
    return isinstance(exc, litellm.AuthenticationError)


def get_api_settings(db: Session) -> APISettings:
    """Get API settings from database."""
    settings = db.query(APISettings).first()
    if not settings:
        raise ValueError("API settings not configured")
    return settings


def get_provider_api_key(provider_name: str, db: Session) -> str | None:
    """Get API key for a specific provider."""
    settings = get_api_settings(db)
    return settings.get_provider_key(provider_name)


def get_model_prefix(provider_name: str) -> str:
    """Get the LiteLLM prefix for a provider."""
    return PROVIDER_PREFIXES.get(provider_name, "")


def resolve_fallback_model(db: Session, exclude: tuple[str, str] | None = None):
    """Return (model_name, provider_name) for the configured backup model.

    Returns None when no fallback is set, when it is incomplete, or when it
    resolves to the model that just failed — retrying the same model on the same
    provider would only repeat the failure.
    """
    from app.models.api import AIModel, APIProvider

    settings = get_api_settings(db)
    if not settings or not settings.fallback_model_id:
        return None

    model = db.query(AIModel).filter(AIModel.id == settings.fallback_model_id).first()
    if not model:
        return None

    provider = db.query(APIProvider).filter(APIProvider.id == model.provider_id).first()
    if not provider:
        return None

    if exclude and (model.name, provider.name) == exclude:
        return None

    return model.name, provider.name


def is_reasoning_model(model_name: str) -> bool:
    """Check if a model is a reasoning model."""
    model_lower = model_name.lower()
    return any(rm in model_lower for rm in REASONING_MODELS)


def supports_temperature(model_name: str) -> bool:
    """Whether a model accepts a custom ``temperature``.

    The GPT-5 family rejects anything other than the default:

        Unsupported value: 'temperature' does not support 0 with this model.
        Only the default (1) value is supported.

    Sending it is a hard 400, so the parameter has to be omitted rather than
    merely adjusted. litellm.drop_params does not save us here — it only strips
    parameters it knows are unsupported, and it has no capability data for the
    newest model ids.
    """
    model_lower = model_name.lower()
    if is_reasoning_model(model_name):
        return False
    return not any(family in model_lower for family in NO_TEMPERATURE_FAMILIES)


async def generate_completion(
    prompt: str,
    model_name: str,
    provider_name: str,
    db: Session,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    system_prompt: str | None = None,
    feature: str = "other",
    user_id: int | None = None,
) -> str:
    """Generate a completion using LiteLLM."""
    # Get API key
    api_key = get_provider_api_key(provider_name, db)
    if not api_key:
        raise ValueError(f"API key not configured for {provider_name}")

    # Build model string with prefix
    prefix = get_model_prefix(provider_name)
    full_model_name = f"{prefix}{model_name}"

    # Build messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Build kwargs based on model type
    kwargs = {
        "model": full_model_name,
        "messages": messages,
        "max_tokens": max_tokens,
        "api_key": api_key,
    }

    # An OpenAI-compatible provider is the openai/ path pointed elsewhere.
    base_url = get_provider_base_url(provider_name, db)
    if base_url:
        kwargs["api_base"] = base_url

    # Handle reasoning models differently
    if is_reasoning_model(model_name):
        # Reasoning models don't support temperature
        if provider_name in ("OpenAI", "Groq", "Cerebras"):
            kwargs["reasoning_effort"] = "medium"
    elif supports_temperature(model_name):
        kwargs["temperature"] = temperature

    # Make the API call, falling back to the configured backup model if the
    # primary fails. Every LLM path in the app routes through this function, so
    # this is the single place failover needs to live.
    try:
        response = await litellm.acompletion(**kwargs)
        record_token_usage(db, response, provider_name, model_name, feature, user_id)
        return response.choices[0].message.content
    except Exception as primary_error:
        fallback = resolve_fallback_model(db, exclude=(model_name, provider_name))
        if not fallback:
            logger.error(
                f"LLM call failed on {provider_name}/{model_name} and no fallback "
                f"is configured: {type(primary_error).__name__}"
            )
            raise

        fb_model, fb_provider = fallback
        logger.warning(
            f"LLM call failed on {provider_name}/{model_name} "
            f"({type(primary_error).__name__}); retrying on fallback "
            f"{fb_provider}/{fb_model}"
        )

        fb_key = get_provider_api_key(fb_provider, db)
        if not fb_key:
            logger.error(f"Fallback provider {fb_provider} has no API key configured")
            raise primary_error

        fb_kwargs = dict(kwargs)
        fb_kwargs["model"] = f"{get_model_prefix(fb_provider)}{fb_model}"
        fb_kwargs["api_key"] = fb_key

        # The endpoint belongs to the primary, not the request. Carrying it over
        # would post the fallback provider's key to the primary's host — an
        # OpenAI key sent to inference.baseten.co, which fails and leaks the key
        # to a third party on the way. Recompute it for the fallback instead.
        fb_kwargs.pop("api_base", None)
        fb_base_url = get_provider_base_url(fb_provider, db)
        if fb_base_url:
            fb_kwargs["api_base"] = fb_base_url

        # Reasoning-model handling differs per model, so recompute it rather than
        # carrying the primary's parameters across to a different family.
        fb_kwargs.pop("reasoning_effort", None)
        fb_kwargs.pop("temperature", None)
        if is_reasoning_model(fb_model):
            if fb_provider in ("OpenAI", "Groq", "Cerebras"):
                fb_kwargs["reasoning_effort"] = "medium"
        elif supports_temperature(fb_model):
            fb_kwargs["temperature"] = temperature

        try:
            response = await litellm.acompletion(**fb_kwargs)
        except Exception as fallback_error:
            # Surface the original failure: the primary is what the operator
            # configured, and its error is the more useful diagnostic.
            logger.error(
                f"Fallback {fb_provider}/{fb_model} also failed: "
                f"{type(fallback_error).__name__}"
            )
            raise primary_error

        logger.info(f"Fallback {fb_provider}/{fb_model} succeeded")
        # Attributed to the model that actually did the work, not the one asked.
        record_token_usage(db, response, fb_provider, fb_model, feature, user_id)
        return response.choices[0].message.content


def _model_kwargs(kwargs: dict, model_name: str, provider_name: str, db: Session, temperature: float) -> dict:
    """Model, key, endpoint and temperature rules for one provider, as
    generate_completion applies them. Raises ValueError for a missing key."""
    api_key = get_provider_api_key(provider_name, db)
    if not api_key:
        raise ValueError(f"API key not configured for {provider_name}")
    out = dict(kwargs)
    out["model"] = f"{get_model_prefix(provider_name)}{model_name}"
    out["api_key"] = api_key
    for key in ("api_base", "reasoning_effort", "temperature"):
        out.pop(key, None)
    base_url = get_provider_base_url(provider_name, db)
    if base_url:
        out["api_base"] = base_url
    if is_reasoning_model(model_name):
        if provider_name in ("OpenAI", "Groq", "Cerebras"):
            out["reasoning_effort"] = "medium"
    elif supports_temperature(model_name):
        out["temperature"] = temperature
    return out


def _estimated_usage(messages: list[dict], text: str):
    """Rough token counts (4 characters a token) for a stream that reported none."""
    from types import SimpleNamespace

    prompt_chars = sum(len(m.get("content") or "") for m in messages)
    return SimpleNamespace(prompt_tokens=prompt_chars // 4, completion_tokens=len(text) // 4)


async def _stream_one(kwargs: dict, db: Session, provider_name: str, model_name: str,
                      feature: str, user_id: int | None):
    """Text deltas of one streamed call; token usage is recorded when it ends."""
    from types import SimpleNamespace

    response = await litellm.acompletion(**kwargs, stream=True, stream_options={"include_usage": True})
    usage = None
    produced: list[str] = []
    try:
        async for chunk in response:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            choices = getattr(chunk, "choices", None) or []
            delta = getattr(choices[0], "delta", None) if choices else None
            text = getattr(delta, "content", None) if delta is not None else None
            if text:
                produced.append(text)
                yield text
    finally:
        # Accounting must never break the turn: record_token_usage swallows its
        # own errors, and a provider that sends no usage gets an estimate.
        if usage is None and produced:
            usage = _estimated_usage(kwargs.get("messages") or [], "".join(produced))
        if usage is not None:
            record_token_usage(db, SimpleNamespace(usage=usage), provider_name, model_name, feature, user_id)


async def stream_completion(
    prompt: str,
    model_name: str,
    provider_name: str,
    db: Session,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    system_prompt: str | None = None,
    feature: str = "other",
    user_id: int | None = None,
):
    """Stream a completion as text deltas (an async generator of str).

    Same model, key and parameter handling as generate_completion. The backup
    model takes over only when the primary fails before its first token: once
    text has been shown to someone, switching models would splice two answers.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    base = {"messages": messages, "max_tokens": max_tokens}
    kwargs = _model_kwargs(base, model_name, provider_name, db, temperature)

    started = False
    try:
        async for text in _stream_one(kwargs, db, provider_name, model_name, feature, user_id):
            started = True
            yield text
        return
    except Exception as primary_error:
        if started:
            logger.error(f"LLM stream failed part way on {provider_name}/{model_name}: {type(primary_error).__name__}")
            raise
        fallback = resolve_fallback_model(db, exclude=(model_name, provider_name))
        if not fallback:
            logger.error(
                f"LLM stream failed on {provider_name}/{model_name} and no fallback "
                f"is configured: {type(primary_error).__name__}"
            )
            raise
        fb_model, fb_provider = fallback
        logger.warning(
            f"LLM stream failed on {provider_name}/{model_name} "
            f"({type(primary_error).__name__}); retrying on fallback {fb_provider}/{fb_model}"
        )
        try:
            # The endpoint and parameters are recomputed for the fallback, never
            # carried over (see generate_completion).
            fb_kwargs = _model_kwargs(base, fb_model, fb_provider, db, temperature)
        except ValueError:
            logger.error(f"Fallback provider {fb_provider} has no API key configured")
            raise primary_error
        error = primary_error

    started = False
    try:
        async for text in _stream_one(fb_kwargs, db, fb_provider, fb_model, feature, user_id):
            started = True
            yield text
    except Exception as fallback_error:
        logger.error(f"Fallback {fb_provider}/{fb_model} stream also failed: {type(fallback_error).__name__}")
        if started:
            raise
        # The primary is what the operator configured; its error is the more useful one.
        raise error
    logger.info(f"Fallback {fb_provider}/{fb_model} succeeded")


def build_advanced_settings_context(advanced: dict | None) -> str:
    """Build context string from advanced settings."""
    if not advanced:
        return ""

    parts = []

    if advanced.get("style"):
        parts.append(f"ARTISTIC STYLE: {advanced['style']}")

    if advanced.get("color_palette"):
        colors = ", ".join(advanced["color_palette"])
        parts.append(f"COLOR PALETTE: {colors}")

    if advanced.get("lighting"):
        parts.append(f"LIGHTING: {advanced['lighting']}")

    if advanced.get("mood"):
        parts.append(f"MOOD/ATMOSPHERE: {advanced['mood']}")

    if advanced.get("composition"):
        parts.append(f"COMPOSITION: {advanced['composition']}")

    if advanced.get("time_of_day"):
        parts.append(f"TIME OF DAY: {advanced['time_of_day']}")

    if advanced.get("weather"):
        parts.append(f"WEATHER/ENVIRONMENT: {advanced['weather']}")

    if advanced.get("quality"):
        parts.append(f"QUALITY LEVEL: {advanced['quality']}")

    # Camera settings
    camera = advanced.get("camera")
    if camera:
        camera_parts = []
        if camera.get("angle"):
            camera_parts.append(f"angle: {camera['angle']}")
        if camera.get("distance"):
            camera_parts.append(f"shot: {camera['distance']}")
        if camera.get("lens"):
            camera_parts.append(f"lens: {camera['lens']}")
        if camera_parts:
            parts.append(f"CAMERA: {', '.join(camera_parts)}")

    return "\n".join(parts)


async def generate_prompt_for_image(
    topic: str,
    model_name: str,
    provider_name: str,
    db: Session,
    art_style: str | None = None,
    advanced_settings: dict | None = None,
    target_model: str | None = None,
    aspect_ratio: str | None = None,
    lora: bool = False,
    purpose: str | None = None,
    avoid: str | None = None,
    directions: int = 0,
    with_checks: bool = False,
) -> tuple[str, dict]:
    """Generate an enhanced, detailed image prompt from a topic.

    This function transforms simple user ideas into comprehensive,
    professional-quality prompts optimized for AI image generation.
    ``purpose`` is a PURPOSES id ("Use for"), ``avoid`` the negative-prompt
    text (rewritten as positive description), and ``directions`` (2 to 4)
    asks for that many prompts along one named axis, returned in
    settings_applied["directions"] with the first as the prompt.
    ``with_checks`` (one prompt only, not with Directions) also asks, in the
    same call, for 3 to 6 checkable rubric lines for the quality check
    (app/services/quality_gate.py), returned in settings_applied["checks"];
    a reply without them still returns the prompt.

    Returns:
        tuple: (enhanced_prompt, settings_applied_dict)
    """

    system_prompt = """You write prompts for modern image models. Your output is
fed straight to the model, so it is the prompt itself and nothing else.

## What changed, and why this matters

Prompts written for 2023-era models do not work well now. Two habits to drop:

- Quality incantations. "8K, ultra HD, masterpiece, award-winning, trending on
  artstation, highly detailed" did something for old models. Current models
  were trained on captioned photographs and reward description, not adjectives
  about quality. These tokens now spend attention and buy nothing.
- Comma-separated keyword lists. Current models parse natural language. Write
  sentences a photo editor would write, not tags.

What works instead is specific, observable description: what is physically
there, what it is made of, where the light comes from, what the camera is
doing. Tested side by side, a described scene reproduces the requested glaze,
garment, prop and light direction; a keyword list produces a generic version of
the same idea.

## The rule that matters most

ANYTHING YOU DO NOT STATE, THE MODEL INVENTS.

So never drop an attribute the user gave you. If they said Japanese, elderly,
left-handed, red dress, rainy, 1970s, that attribute must survive into your
prompt in plain words. Losing one is the single most common way an enhanced
prompt disappoints: the user asked for a Japanese ceramicist, the prompt said
"an elderly man", and the model produced a European one. Their words are
requirements, not inspiration.

## Precision: the details that ruin an image when left vague

- Counts. Say exactly how many: "two women", "three ceramic cups", never
  "some" or "a few". Models miscount whatever is not pinned down.
- Positions. Use the viewer's left and right, foreground and background, and
  say who is where when there is more than one person or object.
- Hands and bodies. When hands matter, say what each hand is doing and holding;
  an idle hand is where anatomy errors appear.
- Describe what is there, not what is absent. "An empty street at dawn" works;
  "a street with no people" often adds people, because naming a thing invites
  it. The only exception is exact text, below.
- No contradictions. Do not ask for golden hour and overcast light, or a
  minimal scene full of props. When two settings conflict, keep the one the
  user stated most specifically.

## When the user already wrote a full prompt

If the input is already a detailed prompt (several sentences, or specific
light, camera and setting), refine it rather than replace it: keep their
structure, wording and every choice, sharpen anything vague, fill in only
what is missing (often light direction, lens, materials), and remove quality
incantations. Do not change their subject, style or composition.

## Language

Write the prompt in English, which every model understands best, whatever
language the user wrote in. Text that must appear in the image stays exactly
as the user wrote it, in its own script, inside double quotes.

## How to build the prompt

Open with one sentence naming the subject and what they are doing, carrying
every attribute the user specified. Then add, in prose:

- The subject in detail: age, build, expression, posture, where the eyes go.
  Clothing by fabric and condition, not just colour: "linen worn thin at the
  elbows", "a jacket creased across the back from sitting".
- Materials and surfaces. This is where realism lives. Crackle in a glaze,
  grain in timber, scuffing on leather, condensation on glass, dust on matte
  plastic.
- Light: one clear source, its direction, its quality, what it does to the
  subject. "Late afternoon sun through a window at frame left, raking across
  his face so the far cheek falls into shadow." Direction and consequence beat
  naming a lighting style.
- The setting: three or four concrete objects placed relative to the subject,
  not a vague location.
- Camera as fact, not decoration: lens length, aperture, where focus falls,
  what falls away. "85mm at f/2, focus on the rim, the shelving behind
  dissolving."
- Colour as a short palette of named colours actually present.

## Length and the target model

Follow the word range given for the target model in the request: small fast
models lose the thread in long prompts, large ones reward them. Every
sentence must add a fact the model can render. A long prompt of vague praise
is worse than a short prompt of specifics; do not pad to reach a length.
Compose for the frame the request names.

The rendering notes are for you, not the image model: use them to decide
what goes where, then describe the result in visual terms ("her face and the
book sit in the middle of the tall frame"). Never repeat them: no aspect
ratios, word counts, model names, platforms, overlays, safe zones,
percentages of the frame, "the eye reads", "optimized for" or other
instructions in the prompt. The only exception is a phrase a note tells you
to put in the prompt, such as the closing words for text.

## What makes an image travel

An image spreads when it can be read instantly and still rewards a second look.
Build in as many of these as the subject honestly allows. Do not force them onto
a brief that does not want them, and never let them override what the user
asked for.

- One subject, unmistakable. A viewer scrolling gives an image a fraction of a
  second. If the eye has to hunt for the point, it moves on. Decide what the
  eye lands on first and make everything else quieter.
- A moment, not a pose. The instant before something lands, or just after.
  A held breath, a hand halfway to a face, steam still rising. A scene caught
  mid-event implies a story and the viewer finishes it themselves.
- One thing that should not be there. An anomaly, a juxtaposition, a scale that
  does not add up. The pattern break is what stops the scroll.
- A real expression. Specific and slightly ambiguous beats broadly happy or
  broadly sad. Describe the eyes and mouth separately, and let them disagree:
  a smile that has not reached the eyes reads as human, a symmetrical grin
  reads as stock.
- Scale that surprises. Something small against something vast, stated as a
  proportion the viewer can check ("the cup is the size of her palm", "the
  lighthouse stands no taller than the wave behind it"), never with intensity
  words such as huge, massive, giant or oversized.
- One dominant colour relationship against a restrained ground, so the image
  holds its shape as a small square in a feed.
- A vantage point people do not usually get: from below, from directly above,
  from inside the thing.
- One detail so specific it could only have been observed. A chipped rim, a
  price sticker half peeled, tan lines, a repair. Specificity is what separates
  an image that looks made from one that looks found.

Legibility comes first. Anything that only works at full size is wasted on a
feed: strong silhouette, clear separation between subject and background, and
no important detail so small it dissolves.

## By purpose

PHOTOGRAPHY AND PORTRAITS: real lens and aperture, real light. Skin keeps its
texture: pores, fine lines, stray hairs. Avoid airbrushed perfection unless
asked.

NATURE AND LANDSCAPE: name the species, rock, weather and season. Give the
light a time of day and the air a condition (haze, humidity, cold clarity).
Scale cues make a landscape read as vast.

YOUTUBE THUMBNAILS: professional, not shouty. One clear subject filling much of
the frame, face large and well lit if a person is present, with a genuine
readable expression rather than an exaggerated open mouth. Strong figure to
ground separation: subject lit brighter than a simplified, darker background so
it survives being shown at the size of a thumbnail. Leave one uncluttered
region for a text overlay and say where it is. High colour contrast between
subject and background, saturated but not radioactive. No fake red circles or
arrows, no distorted shock faces. Think a well-art-directed magazine cover
rather than tabloid.

INSTAGRAM AND SOCIAL: composed for a small square or vertical crop, subject
unmistakable at a glance, one dominant colour relationship, generous negative
space.

PRESENTATIONS AND SLIDES: clean and uncluttered, one idea, a calm background
that text can sit on, no busy centre. Say which side is deliberately empty.
Restrained palette that will not fight a slide theme.

LOGOS AND MARKS: flat vector, solid shapes, no gradient, no photographic
lighting, no 3D bevel. Two or three colours at most, on plain white. Describe
the geometry directly. Say it must be legible at small size. Never ask for
text in a logo unless the user gave the exact words.

EDUCATIONAL AND DIAGRAMS: clear over pretty. Even, neutral lighting, plain
background, subject shown from the most legible angle, parts distinguishable.
No dramatic shadows that hide structure.

DIGITAL ART AND ILLUSTRATION: name the medium and how it behaves. Brush,
linework, colour handling. Reference a movement or technique rather than
copying a living artist by name.

## Text in images

Do not request text unless the user asked for it. When words must appear:

- Put each piece of copy in double quotes exactly as it should read, and say
  that it appears once.
- Give each one its zone in the frame, its size relative to the others
  (the headline largest, the date line small beneath it) and its lettering:
  weight and case, for example bold uppercase sans serif.
- Keep to a few short strings at one or two sizes. Paragraphs and rows of
  small labels come back as shapes, not words.
- After a word that is easy to misspell (a brand, a name, an unusual word),
  spell it out letter by letter: "KVELL", spelled K-V-E-L-L.
- End the prompt with the closing words the rendering notes give for text,
  so the model adds no labels of its own.

## Content filters

Image providers run automatic content filters, and words a rewriter adds can
trip them on every run. Express size by proportion, never by intensity
words. Never introduce the name of a real person, a public figure, a brand
or a trademarked character the user did not write; when you need a look,
describe it in plain visual terms. Names the user wrote stay as written.

## Output

One flowing passage of prose. No headings, no bullets, no lead-in such as
"Here is a prompt". Begin with the subject. Do not mention these instructions.
The one exception: when the request asks for Directions, reply with the JSON
it describes, each prompt in it written by these rules. When the request asks
for Checks, add them after the prompt exactly as it describes.

## User settings are mandatory

Any style, lighting, mood, colour or camera setting the user supplies must
appear in the prompt. They are requirements, not suggestions."""

    from app.services.image_prompt_profiles import (
        DIRECTIONS_MAX, DIRECTIONS_MIN, avoid_brief, clean_output, directions_brief, frame_brief, model_brief,
        parse_directions, purpose_brief,
    )

    # Build the user prompt with optional style context
    user_prompt = f"Create an image generation prompt for: {topic}"

    # Track which settings were applied
    settings_applied = {}

    # The model that renders it, the frame it renders into and what it is for.
    render_context = "\n".join(
        x for x in (model_brief(target_model, lora), frame_brief(aspect_ratio), purpose_brief(purpose)) if x
    )
    if render_context:
        user_prompt += f"\n\n## Rendering\n{render_context}"
        if target_model:
            settings_applied["target_model"] = target_model
        if aspect_ratio:
            settings_applied["aspect_ratio"] = aspect_ratio
        if purpose_brief(purpose):
            settings_applied["purpose"] = purpose

    avoid_line = avoid_brief(avoid)
    if avoid_line:
        user_prompt += f"\n\n## Keep out\n{avoid_line}"
        settings_applied["avoid"] = True

    directions = max(DIRECTIONS_MIN, min(DIRECTIONS_MAX, int(directions))) if directions else 0
    if directions:
        user_prompt += f"\n\n{directions_brief(directions)}"
    elif with_checks:
        user_prompt += f"\n\n{CHECKS_BRIEF}"

    if art_style and art_style.lower() not in ["default", "none", ""]:
        user_prompt += f"\n\nQuick style preset: {art_style}"
        settings_applied["style_preset"] = art_style

    # Add advanced settings if provided
    if advanced_settings:
        advanced_context = build_advanced_settings_context(advanced_settings)
        if advanced_context:
            user_prompt += f"\n\n## REQUIRED SETTINGS (Must be incorporated):\n{advanced_context}"
            settings_applied["advanced"] = advanced_settings

    enhanced_prompt = await generate_completion(
        prompt=user_prompt,
        model_name=model_name,
        provider_name=provider_name,
        db=db,
        # Room for a 500-word prompt without truncation; the old 1000 cut long
        # scenes off mid-sentence. Directions write several prompts.
        max_tokens=2400 + 1200 * max(0, directions - 1),
        # Lower than before: the user's attributes must survive, and the
        # model guidance is a constraint, not a suggestion.
        temperature=0.7,
        system_prompt=system_prompt,
        feature="image_prompt",
    )

    if directions:
        parsed = parse_directions(enhanced_prompt, directions)
        if parsed is None:
            # One prompt for every image, as before Directions existed.
            logger.warning("Magic Prompt directions reply could not be read; using it as one prompt")
            prompt = clean_output(enhanced_prompt)
            if prompt.lstrip().startswith("{"):
                raise ValueError("Magic Prompt returned no usable prompt")
            settings_applied["directions"] = {"axis": "", "prompts": [prompt]}
            return prompt, settings_applied
        axis, prompts = parsed
        settings_applied["directions"] = {"axis": axis, "prompts": prompts}
        return prompts[0], settings_applied

    if with_checks:
        enhanced_prompt, checks = split_checks(enhanced_prompt)
        if checks:
            settings_applied["checks"] = checks
    return clean_output(enhanced_prompt), settings_applied


# Rubric lines for an opted-in quality check, asked for in the Magic Prompt
# call itself (scenario-refine-loop: pass/fail facts, never taste words).
CHECKS_BRIEF = """## Checks
After the prompt, write one line that reads exactly CHECKS: and under it 3 to 6 lines, each starting with "- ". Each line is one fact a viewer can check as true or false in the finished picture: an exact count, who or what is at the viewer's left or right, each quoted text exactly as it must read, or an attribute the user stated (age, colour, clothing, setting). No taste words such as beautiful or striking. These lines are not part of the prompt."""

_CHECKS_MARK = re.compile(r"^\s*\**\s*CHECKS\s*:?\s*\**\s*$", re.MULTILINE | re.IGNORECASE)


def split_checks(reply: str) -> tuple[str, list[str]]:
    """(prompt, rubric lines) of a Magic Prompt reply that may end with a
    CHECKS: block. Without the block the reply is returned whole."""
    text = reply or ""
    m = _CHECKS_MARK.search(text)
    if not m:
        return text, []
    lines = []
    for line in text[m.end():].splitlines():
        line = line.strip()
        if not line:
            continue
        if not re.match(r"^[-*\u2022]\s+|^\d+[.)]\s+", line):
            break
        line = re.sub(r"^[-*\u2022]\s+|^\d+[.)]\s+", "", line).strip()
        if line:
            lines.append(line[:200])
    return text[:m.start()].rstrip(), lines[:6]


async def enhance_magix_prompt(
    user_prompt: str,
    mode: str,
    model_name: str,
    provider_name: str,
    db: Session,
    num_images: int = 1,
    edit_history: list[dict] | None = None,
) -> dict:
    """Enhance a user's Magix prompt by understanding their intent.

    This function focuses on understanding WHAT the user wants to change/create,
    while the mode template provides HOW to achieve it photographically.

    The output will be MERGED with mode-specific expert settings.

    Args:
        user_prompt: The user's text description of what they want
        mode: The portrait mode (studio_portrait, cinematic, etc.)
        model_name: LLM model to use for enhancement
        provider_name: LLM provider name
        db: Database session
        num_images: Number of input images (affects combination instructions)
        edit_history: List of previous edits for context (iterative editing)

    Returns:
        dict: User intent JSON to be merged with mode template
    """
    import json

    system_prompt = """You are MagixIntentParser, an AI that understands user requests for portrait photo editing.

## YOUR ROLE
Parse user prompts to understand WHAT they want to CHANGE - and critically, what to PRESERVE.
This is for ITERATIVE EDITING where users make small changes to an existing image.
Focus on understanding the MINIMAL change requested while preserving everything else.

## CORE PRINCIPLES
1. **Minimal Change**: Only change what the user explicitly requests
2. **Maximum Preservation**: Everything NOT mentioned must be preserved exactly
3. **Identity Sacred**: Face, body shape, skin tone MUST always be preserved
4. **Context Aware**: Detect if this is a targeted edit (change X) vs full transformation

## EDIT TYPE DETECTION
- "change X to Y", "make X green", "add sunglasses" = TARGETED EDIT (preserve almost everything)
- "put me on a beach", "transform into..." = SCENE CHANGE (preserve identity, change scene)
- No specific change mentioned = STYLE APPLICATION (apply mode style, preserve identity)

## OUTPUT JSON SCHEMA
Respond ONLY with valid JSON (no markdown, no explanation):

{
  "edit_type": "targeted_edit | scene_change | style_application",

  "specific_changes": [
    {
      "what_to_change": "exact element to modify (e.g., 't-shirt', 'background', 'hair color')",
      "change_to": "what it should become (e.g., 'green t-shirt', 'beach background')",
      "change_description": "detailed description of the change"
    }
  ],
  "NOTE": "If user requests MULTIPLE changes (e.g., 'change X AND do Y'), include ALL changes in the array above",

  "scene_override": {
    "location": "specific place/setting (or null to KEEP ORIGINAL)",
    "environment": "outdoor/indoor/studio (or null to KEEP ORIGINAL)",
    "time_of_day": "if mentioned (or null to KEEP ORIGINAL)",
    "weather": "if mentioned (or null to KEEP ORIGINAL)",
    "background_elements": ["specific elements (empty list = KEEP ORIGINAL)"]
  },

  "subject_direction": {
    "pose": "change if requested (or 'PRESERVE_ORIGINAL')",
    "expression": "change if requested (or 'PRESERVE_ORIGINAL')",
    "gaze": "change if requested (or 'PRESERVE_ORIGINAL')",
    "action": "change if requested (or 'PRESERVE_ORIGINAL')"
  },

  "framing_override": {
    "shot_type": "change if requested (or null to KEEP ORIGINAL)",
    "composition_notes": "any specific framing requests"
  },

  "appearance_changes": {
    "clothing": "ONLY if user wants to change clothes, otherwise 'PRESERVE_ORIGINAL'",
    "clothing_color": "specific color if mentioned",
    "hair": "ONLY if user wants to change hair, otherwise 'PRESERVE_ORIGINAL'",
    "accessories": "add/remove ONLY if mentioned, otherwise 'PRESERVE_ORIGINAL'"
  },

  "preserve_from_original": [
    "ALWAYS include: face, facial features, identity, skin tone, body shape",
    "Add everything NOT being changed"
  ],

  "preservation_priority": "CRITICAL - This is iterative editing. ONLY modify what user explicitly requested. Keep EVERYTHING else identical to input image."
}

## GUIDELINES FOR TARGETED EDITS
- "change t-shirt to green" → preserve_from_original: ["face", "identity", "pose", "background", "hair", "pants", "shoes", "expression", "lighting", "composition"]
- "add sunglasses" → preserve_from_original: ["face", "identity", "clothing", "pose", "background", "hair", "expression", "everything except eyes area"]
- "change background to beach" → preserve_from_original: ["face", "identity", "clothing", "pose", "hair", "expression", "body position", "lighting on subject"]

## CRITICAL RULES
- If user says "change X" → ONLY X changes, EVERYTHING else stays identical
- Always include comprehensive preserve_from_original list
- For targeted_edit type, preservation is CRITICAL
- Face and identity MUST always be in preserve_from_original"""

    # Build the user message with edit history context
    history_context = ""
    if edit_history and len(edit_history) > 0:
        history_lines = []
        for i, edit in enumerate(edit_history, 1):
            history_lines.append(f"{i}. \"{edit.get('prompt', '')}\"")
        history_context = f"""
## PREVIOUS EDITS APPLIED (the current image already has these changes):
{chr(10).join(history_lines)}

IMPORTANT: The current image ALREADY reflects all the above edits. Your job is to understand the NEW edit request and determine what ADDITIONAL changes to make while preserving what was already done.
"""

    # Product mode edits a product photo: there is no face to keep.
    product_note = (
        "\nThis is a PRODUCT photo, not a portrait: preserve the product's shape, proportions, colours and label "
        "instead of a face, and never list face or identity.\n"
        if mode == "product" else ""
    )
    user_message = f"""Portrait Mode: {mode}
Number of input images: {num_images}
{product_note}{history_context}
User's NEW request: "{user_prompt if user_prompt else "Create a professional portrait"}"

Parse this request and extract the user's intent:
1. What specific changes do they want NOW?
2. If they mention multiple changes (e.g., "change X AND do Y"), capture ALL of them
3. What should be preserved from the current image?

Output ONLY the JSON structure."""

    try:
        result = await generate_completion(
            prompt=user_message,
            model_name=model_name,
            provider_name=provider_name,
            db=db,
            max_tokens=1500,
            temperature=0.2,  # Low temperature for consistency
            system_prompt=system_prompt,
            feature="magix",
        )

        # Parse JSON response
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()

        user_intent = json.loads(cleaned)
        logger.debug(f"[Magix] Parsed user intent: {list(user_intent.keys())}")
        return user_intent

    except (json.JSONDecodeError, Exception) as e:
        # Return a basic structure if parsing fails
        logger.warning(f"[Magix] Intent parsing failed: {e}")
        return {
            "scene_override": {"location": None},
            "subject_direction": {"pose": "natural from image"},
            "framing_override": {"shot_type": None},
            "appearance_changes": {},
            "additional_requirements": [user_prompt] if user_prompt else [],
            "preserve_from_original": ["face", "identity", "facial features"]
        }


async def enhance_tryon_prompt(
    user_prompt: str,
    mode: str,
    model_name: str,
    provider_name: str,
    db: Session,
) -> dict:
    """Enhance a user's Virtual Try-On prompt by understanding their intent.

    This function focuses on understanding WHAT the user wants for the try-on,
    while the mode template provides the scene, lighting, and style settings.

    The output will be MERGED with mode-specific expert settings.

    Args:
        user_prompt: The user's text description of what they want
        mode: The try-on style mode (natural, professional, glamour, etc.)
        model_name: LLM model to use for enhancement
        provider_name: LLM provider name
        db: Database session

    Returns:
        dict: User intent JSON to be merged with mode template
    """
    import json

    system_prompt = """You are TryOnIntentParser, an AI that understands user requests for virtual try-on clothing visualization.

## YOUR ROLE
Parse user prompts to understand HOW they want the outfit to look on them.
You do NOT define technical photography settings (those come from expert templates).
Focus ONLY on understanding the user's creative intent for the try-on.

## CORE PRINCIPLES
1. **Extract Intent**: Understand what setting, pose, and style the user wants
2. **Preserve Identity**: The person's body and face must be preserved exactly
3. **Focus on Fit**: How the garment should fit and drape on the body
4. **Be Specific**: Convert vague requests into specific, actionable descriptions

## OUTPUT JSON SCHEMA
Respond ONLY with valid JSON (no markdown, no explanation):

{
  "scene_override": {
    "location": "specific place/setting user requested (or null if not specified)",
    "environment": "outdoor/indoor/studio - based on user request",
    "time_of_day": "if mentioned (morning/afternoon/sunset/night/etc)",
    "weather": "if mentioned (sunny/cloudy/rainy/etc)",
    "background_elements": ["specific elements user wants in background"]
  },

  "pose_direction": {
    "body_pose": "standing/sitting/walking/posing - what user requested",
    "arm_position": "how arms should be positioned if specified",
    "body_angle": "front/side/three-quarter view if specified",
    "action": "what the subject is doing if specified"
  },

  "garment_fit": {
    "fit_style": "fitted/loose/flowing/tight - if user specified",
    "drape": "how the fabric should fall",
    "adjustments": "any specific fit adjustments mentioned"
  },

  "styling_additions": {
    "accessories": "accessories to add with the outfit",
    "shoes": "footwear if mentioned",
    "styling_notes": "any overall styling direction"
  },

  "atmosphere_override": {
    "mood": "what mood/vibe user wants",
    "lighting_feel": "natural/dramatic/soft - general feel requested",
    "color_tone": "warm/cool/neutral color preference"
  },

  "additional_requirements": ["any other specific requests from user"],

  "preserve_from_original": ["list of things to keep unchanged from person image"]
}

## GUIDELINES
- If user mentions a location → extract it to scene_override.location
- If user mentions fit preferences → extract to garment_fit
- If user doesn't mention something → set it to null or use appropriate default
- Always include body proportions, face in preserve_from_original
- Focus on making the outfit look natural and realistic on the person"""

    # Build the user message
    user_message = f"""Try-On Style: {mode}

User's request: "{user_prompt if user_prompt else "Create a natural virtual try-on"}"

Parse this request and extract the user's intent. What scene, pose, fit, and atmosphere do they want?
Output ONLY the JSON structure."""

    try:
        result = await generate_completion(
            prompt=user_message,
            model_name=model_name,
            provider_name=provider_name,
            db=db,
            max_tokens=1500,
            temperature=0.2,  # Low temperature for consistency
            system_prompt=system_prompt,
            feature="tryon_prompt",
        )

        # Parse JSON response
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()

        user_intent = json.loads(cleaned)
        logger.debug(f"[VirtualTryOn] Parsed user intent: {list(user_intent.keys())}")
        return user_intent

    except (json.JSONDecodeError, Exception) as e:
        # Return a basic structure if parsing fails
        logger.warning(f"[VirtualTryOn] Intent parsing failed: {e}")
        return {
            "scene_override": {"location": None},
            "pose_direction": {"body_pose": "natural standing"},
            "garment_fit": {"fit_style": "natural"},
            "styling_additions": {},
            "atmosphere_override": {},
            "additional_requirements": [user_prompt] if user_prompt else [],
            "preserve_from_original": ["body proportions", "face", "identity", "skin tone"]
        }


def merge_tryon_intent_with_template(user_intent: dict, mode: str = "natural", prompt: str | None = None,
                                     use_dress_background: bool = False) -> str:
    """The try-on prompt with the LLM-parsed intent applied, as plain sentences.

    The parsed scene, pose, fit, styling and atmosphere replace the mode's
    single choices; image 1 stays the person and image 2 lends the garment
    only (app/services/edit_prompts.py).
    """
    from app.services.edit_prompts import build_tryon_prompt

    return build_tryon_prompt(mode, prompt, use_dress_background, user_intent or {})


def merge_user_intent_with_template(user_intent: dict, mode: str = "studio_portrait", prompt: str | None = None,
                                    mode_options: dict | None = None,
                                    image_roles: list[str] | None = None) -> str:
    """The Magix prompt with the LLM-parsed intent applied, as plain sentences.

    A targeted edit drops the mode template: "Change only X to Y. Keep A, B,
    C exactly.", with the keep list written out again on every iteration.
    Scene changes and style applications keep the mode's single choices and
    override what the user asked about (app/services/edit_prompts.py).
    """
    from app.services.edit_prompts import magix_prompt_from_intent

    return magix_prompt_from_intent(user_intent or {}, mode, prompt, mode_options, image_roles)
