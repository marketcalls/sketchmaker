from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import Image

gallery_bp = Blueprint('gallery', __name__)

@gallery_bp.route('/gallery')
@login_required
def gallery():
    # Get all images for the current user
    images = Image.query.filter_by(user_id=current_user.id).order_by(Image.created_at.desc()).all()
    
    # Ensure dimensions are loaded for each image
    for image in images:
        image.get_dimensions()
    
    return render_template('gallery.html', images=images)
