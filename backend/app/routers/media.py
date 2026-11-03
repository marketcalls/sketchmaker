"""GET /static/{path}: stored media, for the signed-in owner only.

Not a public mount. <img> and <video> send the session cookie, and FileResponse
handles Range: a valid range gets 206, an out-of-bounds one gets 416.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.dependencies import CurrentUser
from app.services.storage_service import UnsafeMediaPath, safe_static_path

router = APIRouter()

# Types a browser can only display, never run. Anything else may carry script if it
# is opened on our origin, so it gets the sandbox and downloads instead of rendering.
_DISPLAY_PREFIXES = ("image/", "video/", "audio/")
SVG_TYPE = "image/svg+xml"

SANDBOX_CSP = "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'"
CACHE_CONTROL = "private, max-age=2592000, no-transform"


@router.api_route("/static/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def serve_media(path: str, _user: CurrentUser):
    try:
        file_path = safe_static_path(path)
    except UnsafeMediaPath:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    headers = {"Cache-Control": CACHE_CONTROL, "X-Content-Type-Options": "nosniff"}

    displayable = media_type.startswith(_DISPLAY_PREFIXES)
    if not displayable or media_type == SVG_TYPE:
        headers["Content-Security-Policy"] = SANDBOX_CSP
    if not displayable:
        headers["Content-Disposition"] = "attachment"

    return FileResponse(file_path, media_type=media_type, headers=headers)
