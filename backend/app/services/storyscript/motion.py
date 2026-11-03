"""motion_graphics_draft: delegates to /motion-graphics.

The signature is fixed by docs/STUDIO_ARCHITECTURE.md section 2. The work is
done by app.services.motion_graphics.draft.draft_spec (same LLM path as the
rest of the script engine); this wrapper returns the storyscript MotionSpec
shape (elements are the motion graphics scenes, data the attached table).
"""

from __future__ import annotations

from .models import MotionSpec


async def motion_graphics_draft(db, *, template_id, brief, data=None, length_seconds,
                                aspect) -> MotionSpec:
    """Draft a motion graphics spec (kinetic type, stats, charts)."""
    from app.services.motion_graphics.draft import draft_spec
    from app.services.motion_graphics.spec import TEMPLATES

    from .errors import StoryScriptInputError

    if template_id and template_id not in TEMPLATES:
        raise StoryScriptInputError(f"Unknown motion graphics template '{template_id}'")
    if not (brief or "").strip():
        raise StoryScriptInputError("A brief is required")

    spec, _info = await draft_spec(db, brief=brief, template_id=template_id or None,
                                   data_csv=data if isinstance(data, str) else None,
                                   length_seconds=length_seconds, aspect=aspect)
    return MotionSpec(
        template_id=spec.template_id,
        aspect=aspect,
        length_seconds=int(length_seconds),
        elements=[s.model_dump() for s in spec.scenes],
        data=spec.data.model_dump() if spec.data else None,
    )
