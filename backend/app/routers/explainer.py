"""
Explainer Tool: generate professional visual content using OpenAI GPT Image 2.5
(Sunburst) via fal.

Sunburst is OpenAI's precision tuning of GPT Image 2.5: it plans the layout
before drawing, holds dense copy, numbers and diagram geometry, and edits
with up to 4 reference images and an optional mask through the /edit
endpoint for brand-consistent variants. This module is the
explainer/infographic/PPT/SaaS-visual workhorse.
"""

import logging
import re
import uuid
from typing import Optional, List, Literal
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.dependencies import CurrentUser, DbSession
from app.models.content import Image
from app.models.api import APISettings, APIProvider, AIModel
from app.schemas.image import ImageResponse
from app.clients.fal_client import EXPLAINER_TEXT_MODEL, generate_explainer_image, validate_url
from app.clients.litellm_client import generate_completion
from app.services.pricing import explainer_resolution, explainer_usd
from app.services.usage import record_usage
from app.services import quality_gate

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# CONTENT TEMPLATES — visual content types the explainer can produce
# =============================================================================

CONTENT_TEMPLATES = {
    # --- Educational / Explainer family --------------------------------------
    "concept": {
        "name": "Concept Explainer",
        "description": "Educational breakdowns of complex topics for learners",
        "icon": "lightbulb",
        "audience": "students, learners, self-taught readers",
        "intent": "Explain a single concept end-to-end with visual scaffolding",
        "must_include": [
            "Central concept tile with bold headline",
            "4-6 supporting components with named icons",
            "Short captions under each component (under 12 words)",
            "Connector lines/arrows showing relationships",
            "Legend or key in a corner if symbols repeat",
        ],
    },
    "infographic": {
        "name": "Infographic",
        "description": "Statistic-driven visualization with hero numbers and icons",
        "icon": "chart-bar",
        "audience": "general public, social audiences, report readers",
        "intent": "Present statistics, comparisons, and takeaways at a glance",
        "must_include": [
            "Hero stat block (one number you remember)",
            "3-5 supporting stats each with its own tile and icon",
            "Source attribution row at the bottom",
            "Coherent color-coded categories",
            "Small chart element (bar/donut/line) where useful",
        ],
    },
    "flowchart": {
        "name": "Flowchart",
        "description": "Process flows, decision trees, and step diagrams",
        "icon": "share-nodes",
        "audience": "engineers, ops teams, learners walking through a process",
        "intent": "Encode a step-by-step or branching process visually",
        "must_include": [
            "Clear START and END nodes",
            "Diamond decision nodes with labeled YES/NO branches",
            "Process boxes with action verbs as labels",
            "Arrows showing direction; no orphan boxes",
            "Color band per stage if the flow is long",
        ],
    },
    "mindmap": {
        "name": "Mind Map",
        "description": "Hierarchical concept map with branches",
        "icon": "layout-grid",
        "audience": "learners brainstorming, knowledge mappers",
        "intent": "Show a central concept exploding into related sub-concepts",
        "must_include": [
            "Central topic node, visually heaviest",
            "4-7 first-level branches radiating outward",
            "Sub-branches no deeper than 2 levels",
            "Color per branch, kept consistent on its sub-nodes",
            "Small icon glyph on each node",
        ],
    },
    "timeline": {
        "name": "Timeline",
        "description": "Chronological events on a milestone track",
        "icon": "clock",
        "audience": "history readers, product/company storytelling",
        "intent": "Walk a viewer through events in order",
        "must_include": [
            "Single horizontal or vertical track spine",
            "Date labels in monospace or numeric font",
            "Event title + 1-line description per milestone",
            "Icon or thumbnail per event",
            "Visual distinction for 'most important' milestone(s)",
        ],
    },
    "comparison": {
        "name": "Comparison Chart",
        "description": "Side-by-side comparisons, pros/cons matrices",
        "icon": "code-compare",
        "audience": "decision-makers, buyers, evaluators",
        "intent": "Help the viewer pick between options",
        "must_include": [
            "Two or three columns with clear headers (logo or name)",
            "Vertical attribute list (rows) with label column on left",
            "Checkmarks, X marks, or numeric scores per cell",
            "Colored highlight on the recommended column",
            "Summary verdict band at the bottom",
        ],
    },
    "architecture": {
        "name": "Architecture Diagram",
        "description": "System architectures, data flows, technical stacks",
        "icon": "boxes",
        "audience": "engineers, architects, technical reviewers",
        "intent": "Show how components connect and data flows",
        "must_include": [
            "Layered grouping (frontend / backend / data / infra)",
            "Component boxes labeled with technology names",
            "Directional arrows for request/response/data flow",
            "Subtle dashed grid for alignment (do not draw the grid itself)",
            "Legend explaining color or arrow conventions",
        ],
    },
    "pitchdeck": {
        "name": "Pitch Deck Slide",
        "description": "Investor-style slide for startups and product launches",
        "icon": "presentation",
        "audience": "investors, executives, pitch reviewers",
        "intent": "Sell a single idea on a single slide",
        "must_include": [
            "Bold headline statement (under 8 words)",
            "Hero metric or product visual",
            "Supporting bullet/stat row of 2-3 items",
            "Brand-leaning palette and clean type",
            "Subtle company/page footer",
        ],
    },

    # --- Professional / Productivity family ----------------------------------
    "ppt_slide": {
        "name": "Presentation Slide",
        "description": "16:9 PPT/Keynote slide for talks and webinars",
        "icon": "presentation",
        "audience": "speakers, internal teams, learners watching a deck",
        "intent": "One slide that conveys one idea cleanly",
        "must_include": [
            "Concise title (max 7 words) at the top",
            "Single hero visual or 3-up content row",
            "Generous padding; no edge-to-edge text",
            "Footer line with section/page hint",
            "Consistent corner branding placeholder",
        ],
    },
    "educational_poster": {
        "name": "Educational Poster",
        "description": "Classroom-ready poster summarizing a topic",
        "icon": "lightbulb",
        "audience": "K-12 / college students, teachers",
        "intent": "Summarize a topic so a student can revise from one image",
        "must_include": [
            "Big subject heading at the top",
            "Sectioned body with 4-6 mini-cards",
            "Definitions, formulas, or laws called out in tinted boxes",
            "A small worked example or diagram",
            "Encouraging tone, friendly icons, readable serif/sans pairing",
        ],
    },
    "cheatsheet": {
        "name": "Cheat Sheet",
        "description": "Dense reference card packed with syntax/keys/recipes",
        "icon": "layout-grid",
        "audience": "developers, power users, exam-takers",
        "intent": "Maximize information density without becoming illegible",
        "must_include": [
            "Multi-column grid (3-4 columns)",
            "Section headers with subtle dividers",
            "Monospace code snippets for technical content",
            "Inline keyboard-key glyphs where relevant",
            "Tight spacing, consistent baseline grid",
        ],
    },
    "saas_landing_hero": {
        "name": "SaaS Landing Hero",
        "description": "Top-of-fold hero composition for a SaaS startup",
        "icon": "boxes",
        "audience": "early-stage founders, marketing teams",
        "intent": "Communicate value prop + show product in one frame",
        "must_include": [
            "Strong headline + subhead pair",
            "Primary CTA button with explicit label",
            "Product screenshot/mockup floating to one side",
            "Soft gradient or mesh background",
            "Trust row (logos / star rating / metric strip)",
        ],
    },
    "dashboard_mockup": {
        "name": "Dashboard Mockup",
        "description": "Analytics or admin dashboard UI mockup",
        "icon": "chart-bar",
        "audience": "PMs, designers, founders pitching tooling",
        "intent": "Render a believable product UI with real-looking data",
        "must_include": [
            "Left sidebar with iconified nav",
            "Top bar with search + user avatar",
            "Grid of KPI cards (4 across) with sparklines",
            "Primary chart panel (line or area)",
            "Secondary widgets: table, donut, recent-activity list",
        ],
    },
    "social_card": {
        "name": "Social Share Card",
        "description": "Branded post for LinkedIn / X / Instagram",
        "icon": "share-nodes",
        "audience": "founders posting, content marketers",
        "intent": "Stop the scroll, communicate one idea",
        "must_include": [
            "Hook line in display type (under 12 words)",
            "Subline or attribution",
            "Author/brand mark with avatar circle",
            "Background that contrasts with text",
            "Single decorative element (shape, gradient, icon)",
        ],
    },
    "stat_callout": {
        "name": "Statistic Callout",
        "description": "Single hero stat with supporting context",
        "icon": "chart-bar",
        "audience": "report readers, social audiences",
        "intent": "One number, one story",
        "must_include": [
            "Massive numeric figure (display weight)",
            "Unit / label directly under the figure",
            "One-sentence context line",
            "Source attribution in small caps",
            "One coherent accent color",
        ],
    },
}


# =============================================================================
# VISUAL STYLES — design language modifiers
# =============================================================================

VISUAL_STYLES = {
    # --- Existing tonal styles ------------------------------------------------
    "professional": {
        "name": "Professional",
        "description": "Clean, corporate, minimal",
        "prompt_modifier": (
            "professional corporate visual style, clean lines, restrained palette of "
            "navy/charcoal/white with one accent color, generous whitespace, "
            "Inter or Söhne-style sans-serif typography, no decorative flourishes"
        ),
    },
    "modern": {
        "name": "Modern",
        "description": "Sleek and contemporary",
        "prompt_modifier": (
            "modern sleek visual style, soft gradients, rounded geometry, "
            "subtle drop shadows, balanced negative space, geometric sans-serif type"
        ),
    },
    "creative": {
        "name": "Creative",
        "description": "Artistic and visually striking",
        "prompt_modifier": (
            "creative bold visual style, asymmetric composition, vibrant accent colors, "
            "playful illustrative motifs, layered shapes, expressive typography pairing"
        ),
    },
    "minimal": {
        "name": "Minimal",
        "description": "Quiet, elegant, lots of breathing room",
        "prompt_modifier": (
            "minimalist visual style, expansive whitespace, hairline strokes, "
            "two-color palette, single typeface, no decorative ornament"
        ),
    },
    "tech": {
        "name": "Tech",
        "description": "Digital, dark, futuristic",
        "prompt_modifier": (
            "tech / cyberpunk visual style, near-black background, neon accent gradients, "
            "monospace numerals, subtle grid lines, glow on data points, no chromatic aberration"
        ),
    },
    "educational": {
        "name": "Educational",
        "description": "Clear, friendly classroom feel",
        "prompt_modifier": (
            "educational visual style, friendly rounded sans-serif type, soft pastel palette, "
            "hand-drawn-style icons, clear visual hierarchy, no clutter"
        ),
    },

    # --- New SaaS / startup / editorial styles -------------------------------
    "saas_startup": {
        "name": "SaaS Startup",
        "description": "Linear/Vercel/Stripe-grade product aesthetic",
        "prompt_modifier": (
            "modern SaaS startup aesthetic in the visual register of Linear, Vercel and Stripe: "
            "off-white or near-black background, single hero gradient (indigo to violet OR teal to lime), "
            "Inter/Söhne typography, ultra-tight kerning on display text, "
            "subtle 1px hairline borders on cards, "
            "rounded-2xl corners, soft long shadows, no stock-photo people"
        ),
    },
    "premium_dark": {
        "name": "Premium Dark",
        "description": "Dark-mode editorial with neon highlights",
        "prompt_modifier": (
            "premium dark-mode editorial style, near-black #0B0B10 background, "
            "high-contrast white display type, single neon accent (electric violet or chartreuse), "
            "subtle noise texture, refined micro-typography, no harsh saturated rainbow"
        ),
    },
    "editorial": {
        "name": "Editorial",
        "description": "Magazine-grade typographic layout",
        "prompt_modifier": (
            "editorial magazine layout style, serif display headline paired with sans body, "
            "strong typographic hierarchy, generous gutters, multi-column grid, "
            "muted paper-white background, restrained two-color palette"
        ),
    },
    "brutalist": {
        "name": "Brutalist",
        "description": "Raw, high-contrast, opinionated",
        "prompt_modifier": (
            "brutalist visual style, raw high-contrast composition, oversized type, "
            "flat saturated primary colors, hard 4px black borders, no gradients, "
            "intentional asymmetry, mono labels"
        ),
    },
    "glassmorphism": {
        "name": "Glassmorphism",
        "description": "Frosted glass cards over a vivid mesh",
        "prompt_modifier": (
            "glassmorphism visual style, frosted translucent panels with 24px blur and 1px white inner stroke, "
            "vivid blurred mesh-gradient background (magenta/azure/lime), "
            "soft drop shadows under each card, crisp legible white type"
        ),
    },
    "neumorphic": {
        "name": "Neumorphic",
        "description": "Soft shadows, monochrome surfaces",
        "prompt_modifier": (
            "soft neumorphic visual style, single off-white or warm-grey surface, "
            "elements appearing to extrude with paired light/dark shadows, "
            "no harsh borders, restrained accent color used only on active states"
        ),
    },
    "pitch_premium": {
        "name": "Pitch Premium",
        "description": "Y Combinator / a16z investor-deck polish",
        "prompt_modifier": (
            "premium investor-pitch slide aesthetic, off-white background, "
            "single bold accent color, very large display headline, "
            "one hero stat or product render, restrained iconography, "
            "subtle bottom-right page mark"
        ),
    },
    "isometric": {
        "name": "Isometric Vector",
        "description": "30-degree axonometric vector illustration",
        "prompt_modifier": (
            "isometric vector illustration style, 30-degree axonometric projection, "
            "flat-shaded geometry with two-tone faces, no outlines, "
            "warm pastel palette, soft drop shadows under each element"
        ),
    },
    "blueprint": {
        "name": "Blueprint",
        "description": "Engineering blueprint / schematic",
        "prompt_modifier": (
            "engineering blueprint style, deep blue background with white/cyan technical linework, "
            "monospaced annotations, dimension lines and tick marks, dashed reference lines, "
            "subtle grid"
        ),
    },
}


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


class ExplainerRequest(BaseModel):
    """Schema for explainer generation."""

    topic: str = Field(..., min_length=1, max_length=20000)
    content_type: str = Field(default="concept")
    style: str = Field(default="saas_startup")
    aspect_ratio: str = Field(default="16:9")
    resolution: str = Field(default="2K")
    # Literal, not str: the value ends up in the stored filename.
    output_format: Literal["png", "jpeg", "webp"] = Field(default="png")
    enhance_prompt: bool = Field(default=False)
    # Edit-mode inputs (optional). If non-empty, routes to the GPT Image 2.5 edit endpoint.
    reference_image_urls: List[str] = Field(default_factory=list, max_length=4)
    mask_url: Optional[str] = None
    # Opt-in spelling check of the quoted copy (app/services/quality_gate.py),
    # run once the image is stored.
    quality_check: bool = False


class EnhanceRequest(BaseModel):
    """Request to enhance an explainer prompt."""

    prompt: str = Field(..., min_length=1, max_length=10000)
    content_type: str = Field(default="concept")
    style: str = Field(default="saas_startup")
    aspect_ratio: Optional[str] = "16:9"


class EnhanceResponse(BaseModel):
    """Response with enhanced prompt."""

    enhanced_prompt: str
    original_prompt: str


class ReferenceUploadResponse(BaseModel):
    """Response after uploading a reference image."""

    url: str
    filename: str
    file_size_bytes: int


# =============================================================================
# PROMPT ENHANCEMENT: a short, ranked brief for GPT Image 2.5 Sunburst
# =============================================================================

# GPT Image 2.5 follows exact instructions, but past about seven distinct
# requirements some quietly drop, and a long brief is normalised rather than
# followed line by line. So the brief is short, ranked, and holds only what
# the user gave or the layout needs: no invented figures, logos or footers.
ENHANCER_SYSTEM_PROMPT = """You are a senior visual designer writing the brief for an explainer image. It goes straight to OpenAI's GPT Image 2.5, an image model that plans the layout before drawing and renders text well, but quietly drops requirements past about seven.

Write one passage of plain prose, 150 to 350 words, no headings, no bullets, no labels. Open with the kind of image and its use (for example "a 16:9 infographic explaining how vaccines train the immune system"). Then give at most seven requirements, the most important first:

1. The layout: the regions and where each block sits (top band, left column, centred diagram).
2. The headline and every other piece of copy, each in straight double quotes exactly as it must read, with its zone, its size relative to the rest, and its weight and case. Say each appears once. Spell any unusual word letter by letter after it.
3. The diagram, chart or illustration, and what it shows.
4. The palette as three or four named colours or hex codes, and the background.
5. The typeface style (for example a geometric sans serif, bold for the headline).
6. Icons or graphic motifs, only where they carry meaning.
7. Anything else the user asked for.

Use only content the user gave. Never invent statistics, sample values, quotes, names, dates, logos, logo placeholders, footers or source attributions: when the user gave no numbers, show the idea without numbers. Keep the copy to a few short strings at one or two sizes; paragraphs and rows of tiny labels come back as shapes. Describe what is there rather than listing what is not. End with "no extra words, no duplicate text".
"""


async def enhance_prompt_with_ai(
    prompt: str,
    content_type: str,
    style: str,
    db,
    aspect_ratio: str = "16:9",
) -> str:
    """Enhance the user's prompt for GPT Image 2.5 via the default LLM."""
    content_info = CONTENT_TEMPLATES.get(content_type, CONTENT_TEMPLATES["concept"])
    style_info = VISUAL_STYLES.get(style, VISUAL_STYLES["saas_startup"])

    structure_lines = "\n".join(f"- {item}" for item in _structure_items(content_info))

    user_content = f"""Write the brief for this explainer image.

THE USER'S IDEA (all the content there is):
\"\"\"
{prompt}
\"\"\"

KIND OF IMAGE: {content_info['name']}, {content_info['intent']}
AUDIENCE: {content_info['audience']}
FRAME: {aspect_ratio}

USUAL STRUCTURE (use only the parts the user's content supports):
{structure_lines}

VISUAL STYLE: {style_info['name']}. {style_info['prompt_modifier']}

Write the brief now: 150 to 350 words, at most seven requirements, the most important first. Output the brief only, no preamble.
"""

    try:
        api_settings = db.query(APISettings).first()
        if not api_settings or not api_settings.default_provider_id or not api_settings.default_model_id:
            logger.debug("No API settings configured for prompt enhancement")
            return prompt

        provider = db.query(APIProvider).filter(APIProvider.id == api_settings.default_provider_id).first()
        model = db.query(AIModel).filter(AIModel.id == api_settings.default_model_id).first()
        if not provider or not model:
            logger.debug("Default provider or model not found")
            return prompt

        enhanced = await generate_completion(
            prompt=user_content,
            model_name=model.name,
            provider_name=provider.name,
            db=db,
            max_tokens=1500,
            temperature=0.6,
            system_prompt=ENHANCER_SYSTEM_PROMPT,
        )
        return enhanced.strip()
    except Exception as e:
        logger.warning(f"Error enhancing prompt: {str(e)}")
        return prompt


# Template items that need words or marks only the user can supply. Without
# them the model invents a source, a company name or a logo.
_INVENTED_ITEM = re.compile(r"attribution|footer|branding|placeholder|logo|sample|source", re.IGNORECASE)


def _structure_items(content_info: dict) -> list[str]:
    return [item for item in content_info["must_include"] if not _INVENTED_ITEM.search(item)]


def build_generation_prompt(prompt: str, content_type: str, style: str) -> str:
    """A short, ranked prompt when AI enhancement is OFF: the kind of image,
    the user's topic, the usual structure and the style, without the LLM
    round trip."""
    content_info = CONTENT_TEMPLATES.get(content_type, CONTENT_TEMPLATES["concept"])
    style_info = VISUAL_STYLES.get(style, VISUAL_STYLES["saas_startup"])

    structure = "; ".join(_structure_items(content_info))

    return (
        f"Create a {content_info['name'].lower()} ({content_info['intent']}). "
        f"Topic: {prompt}\n\n"
        f"Layout: {structure}.\n\n"
        f"Visual style: {style_info['prompt_modifier']}.\n\n"
        "Use only the facts and wording in the topic; spell every word exactly. "
        "Keep the text to a few short lines at one or two sizes. No extra words, no duplicate text."
    )


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.get("/templates")
async def get_templates():
    """Return content templates and visual styles available to the UI."""
    return {
        "templates": CONTENT_TEMPLATES,
        "styles": VISUAL_STYLES,
    }


@router.post("/upload-reference", response_model=ReferenceUploadResponse)
async def upload_reference_image(
    current_user: CurrentUser,
    image: UploadFile = File(...),
):
    """Upload a reference image for GPT Image 2.5 edit mode.

    Returns a URL the frontend can pass back in `reference_image_urls`.
    Up to 4 references are allowed per generation.
    """
    from app.services.storage_service import storage_service

    content = await image.read()
    file_size = len(content)

    max_size = 25 * 1024 * 1024  # 25MB
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
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
    filename = f"explainer_ref_{uuid.uuid4()}{ext}"

    url = await storage_service.upload_file(
        file_data=content,
        filename=filename,
        storage_type="uploads",
        content_type=image.content_type,
        user_id=current_user.id,
    )

    return ReferenceUploadResponse(url=url, filename=filename, file_size_bytes=file_size)


@router.post("/enhance", response_model=EnhanceResponse)
async def enhance_prompt(
    body: EnhanceRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Enhance a brief idea into a short, ranked brief for GPT Image 2.5."""
    enhanced = await enhance_prompt_with_ai(
        prompt=body.prompt,
        content_type=body.content_type,
        style=body.style,
        db=db,
        aspect_ratio=body.aspect_ratio or "16:9",
    )
    return EnhanceResponse(enhanced_prompt=enhanced, original_prompt=body.prompt)


@router.post("/generate", response_model=ImageResponse)
async def generate_explainer(
    body: ExplainerRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Generate an explainer image with OpenAI GPT Image 2.5 (Sunburst).

    Routes automatically:
      - With reference_image_urls: the GPT Image 2.5 edit endpoint
        (brand-consistent variants, character/style transfer, infographic
        remixes), with the optional mask.
      - Without references: GPT Image 2.5 text-to-image.

    Quality is fixed at "high" and num_images at 1 (product decision).
    """
    # Validate references early (cheap fail before the provider call)
    refs = [u for u in body.reference_image_urls if u]
    if len(refs) > 4:
        raise HTTPException(status_code=400, detail="Up to 4 reference images allowed")

    # Priced per image by resolution, with its own price when references send
    # the request to the edit endpoint (app/services/pricing.py). The
    # resolution is normalised the way generate_explainer_image renders it.
    resolution = explainer_resolution(body.resolution)
    estimated_usd = explainer_usd(resolution, with_references=bool(refs))
    if body.quality_check and not quality_gate.available(db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The spelling check is not available right now. Turn it off to create the visual without it.",
        )
    for ref in refs:
        ok, err = validate_url(ref, allow_data_urls=False)
        if not ok:
            logger.warning(f"Explainer reference image URL rejected for user {current_user.id}: {err}")
            raise HTTPException(status_code=400, detail="A reference image could not be used. Upload it again and retry.")
    if body.mask_url:
        ok, err = validate_url(body.mask_url, allow_data_urls=False)
        if not ok:
            logger.warning(f"Explainer mask URL rejected for user {current_user.id}: {err}")
            raise HTTPException(status_code=400, detail="The mask could not be used. Draw it again and retry.")

    # Build or enhance the prompt
    if body.enhance_prompt:
        final_prompt = await enhance_prompt_with_ai(
            prompt=body.topic,
            content_type=body.content_type,
            style=body.style,
            db=db,
            aspect_ratio=body.aspect_ratio,
        )
    else:
        final_prompt = build_generation_prompt(
            prompt=body.topic,
            content_type=body.content_type,
            style=body.style,
        )

    try:
        result = await generate_explainer_image(
            prompt=final_prompt,
            db=db,
            aspect_ratio=body.aspect_ratio,
            resolution=resolution,
            output_format=body.output_format,
            user_id=current_user.id,
            reference_image_urls=refs,
            mask_url=body.mask_url,
        )

        model_name = result.get("endpoint") or EXPLAINER_TEXT_MODEL

        image = Image(
            filename=result["filename"],
            prompt=body.topic,
            magic_prompt=final_prompt if body.enhance_prompt else None,
            art_style=f"explainer_{body.content_type}_{body.style}",
            width=result.get("width", 1024),
            height=result.get("height", 1024),
            model=model_name,
            aspect_ratio=body.aspect_ratio,
            user_id=current_user.id,
        )
        if body.quality_check:
            # Read back after the response, in the scheduler. With no quoted
            # copy there is nothing to read back.
            if quality_gate.quoted_strings(final_prompt):
                image.quality = quality_gate.pending("text", prompt=final_prompt, estimated_usd=quality_gate.price())
            else:
                image.quality = quality_gate.nothing_to_check("text", quality_gate.NO_QUOTED_TEXT)
        db.add(image)

        record_usage(
            db,
            feature="explainers",
            usd=estimated_usd,
            model=model_name,
            units=1,
            unit="image",
            detail={
                "content_type": body.content_type,
                "style": body.style,
                "topic": body.topic[:200],
                "enhanced": body.enhance_prompt,
                "aspect_ratio": body.aspect_ratio,
                "resolution": resolution,
                "edit_mode": bool(refs),
                "num_references": len(refs),
            },
        )
        db.commit()
        db.refresh(image)

        return ImageResponse.from_orm_with_urls(image)

    except ValueError:
        logger.exception(f"Explainer generation failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="We could not create this visual. Please try again.",
        )
    except Exception:
        logger.exception(f"Explainer generation failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We could not create this visual right now. Please try again in a moment.",
        )
