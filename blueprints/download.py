from flask import Blueprint, send_file, abort, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import Image
from extensions import limiter, get_rate_limit_string
import os
import re

download_bp = Blueprint('download', __name__)

def sanitize_filename(filename):
    """Sanitize filename to prevent path traversal attacks"""
    # Remove any path components
    filename = os.path.basename(filename)
    # Use werkzeug's secure_filename
    filename = secure_filename(filename)
    # Additional validation: only allow alphanumeric, underscore, hyphen, and dot
    if not re.match(r'^[\w\-\.]+$', filename):
        return None
    return filename

@download_bp.route('/download/<filename>/<format>')
@limiter.limit(get_rate_limit_string())
@login_required
def download_image(filename, format):
    # Sanitize filename to prevent path traversal
    safe_filename = sanitize_filename(filename)
    if not safe_filename:
        abort(400)  # Bad request for invalid filename

    # Get base filename without extension
    base_filename = os.path.splitext(safe_filename)[0]

    # Validate format parameter
    allowed_formats = {'webp', 'jpeg', 'png'}
    format_lower = format.lower()
    if format_lower not in allowed_formats:
        abort(400)  # Bad request for invalid format

    # Get the image record from database - this ensures user owns the image
    image = Image.query.filter_by(filename=f"{base_filename}.png", user_id=current_user.id).first()

    if not image:
        abort(404)

    # Build filepath using current_app.root_path for safety
    filepath = os.path.join(current_app.root_path, 'static', 'images', f"{base_filename}.{format_lower}")

    # Verify the resolved path is within the expected directory (defense in depth)
    images_dir = os.path.realpath(os.path.join(current_app.root_path, 'static', 'images'))
    resolved_path = os.path.realpath(filepath)
    if not resolved_path.startswith(images_dir):
        abort(403)  # Forbidden - path traversal attempt

    if not os.path.exists(filepath):
        abort(404)

    # Set the appropriate mimetype
    mimetypes = {
        'webp': 'image/webp',
        'jpeg': 'image/jpeg',
        'png': 'image/png'
    }

    return send_file(
        filepath,
        mimetype=mimetypes.get(format_lower, 'image/png'),
        as_attachment=True,
        download_name=f"sketchmaker_{base_filename}.{format_lower}"
    )
