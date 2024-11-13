from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user
from models import Image
import markdown2

gallery_bp = Blueprint('gallery', __name__)

@gallery_bp.route('/gallery')
@login_required
def view_gallery():
    # Get user's images ordered by creation date (newest first)
    images = Image.query.filter_by(user_id=current_user.id)\
                       .order_by(Image.created_at.desc())\
                       .all()
    
    return render_template('gallery.html', images=images)

@gallery_bp.route('/gallery/<int:image_id>')
@login_required
def view_image(image_id):
    # Get the specific image and verify ownership
    image = Image.query.get_or_404(image_id)
    if image.user_id != current_user.id:
        abort(403)  # Forbidden if not owner
    
    return render_template('image.html', image=image)

# Register markdown filter for all templates using this blueprint
@gallery_bp.app_template_filter('markdown')
def markdown_filter(text):
    return markdown2.markdown(text)
