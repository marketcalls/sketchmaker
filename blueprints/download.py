from flask import Blueprint, send_file, abort
from flask_login import login_required, current_user
from models import Image
import os

download_bp = Blueprint('download', __name__)

@download_bp.route('/download/<filename>/<format>')
@login_required
def download_image(filename, format):
    # Get base filename without extension
    base_filename = os.path.splitext(filename)[0]
    
    # Get the image record from database
    image = Image.query.filter_by(filename=f"{base_filename}.png", user_id=current_user.id).first()
    
    if not image:
        abort(404)
    
    # Determine the file path based on format
    if format.lower() == 'webp':
        filepath = os.path.join('sketchmaker', 'static', 'images', f"{base_filename}.webp")
    elif format.lower() == 'jpeg':
        filepath = os.path.join('sketchmaker', 'static', 'images', f"{base_filename}.jpeg")
    else:  # default to PNG
        filepath = os.path.join('sketchmaker', 'static', 'images', f"{base_filename}.png")
    
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
        mimetype=mimetypes.get(format.lower(), 'image/png'),
        as_attachment=True,
        download_name=f"sketchmaker_{base_filename}.{format.lower()}"
    )
