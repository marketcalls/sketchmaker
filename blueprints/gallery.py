from flask import Blueprint, render_template
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
    
    # Create markdown filter
    def markdown_filter(text):
        return markdown2.markdown(text)
    
    # Register markdown filter for the template
    view_gallery.markdown = markdown_filter
    
    return render_template('gallery.html', 
                         images=images,
                         markdown=markdown_filter)

# Register markdown filter for all templates using this blueprint
@gallery_bp.app_template_filter('markdown')
def markdown_filter(text):
    return markdown2.markdown(text)
