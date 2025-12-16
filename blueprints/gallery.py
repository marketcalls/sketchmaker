from flask import Blueprint, render_template, abort, jsonify, request
from flask_login import login_required, current_user
from models import Image, db
from extensions import limiter, get_rate_limit_string
import markdown2
import os

gallery_bp = Blueprint('gallery', __name__)

# Number of images to load per page
IMAGES_PER_PAGE = 20

@gallery_bp.route('/gallery')
@limiter.limit(get_rate_limit_string())
@login_required
def view_gallery():
    # Get total count for initial render
    total_images = Image.query.filter_by(user_id=current_user.id).count()

    return render_template('gallery.html', total_images=total_images, images_per_page=IMAGES_PER_PAGE)

@gallery_bp.route('/api/gallery/images')
@limiter.limit(get_rate_limit_string())
@login_required
def get_gallery_images():
    """API endpoint for paginated gallery images"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', IMAGES_PER_PAGE, type=int)

    # Limit per_page to prevent abuse
    per_page = min(per_page, 50)

    # Get paginated images
    pagination = Image.query.filter_by(user_id=current_user.id)\
                           .order_by(Image.created_at.desc())\
                           .paginate(page=page, per_page=per_page, error_out=False)

    images_data = []
    for image in pagination.items:
        images_data.append({
            'id': image.id,
            'url': image.get_url(),
            'thumbnail_url': image.get_thumbnail_url() if hasattr(image, 'get_thumbnail_url') else image.get_url(),
            'prompt': image.prompt[:100] + '...' if image.prompt and len(image.prompt) > 100 else image.prompt,
            'created_at': image.created_at.isoformat() if image.created_at else None,
            'width': image.width,
            'height': image.height
        })

    return jsonify({
        'images': images_data,
        'page': page,
        'per_page': per_page,
        'total': pagination.total,
        'pages': pagination.pages,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev
    })

@gallery_bp.route('/gallery/<int:image_id>')
@limiter.limit(get_rate_limit_string())
@login_required
def view_image(image_id):
    # Get the specific image and verify ownership
    image = Image.query.get_or_404(image_id)
    if image.user_id != current_user.id:
        abort(403)  # Forbidden if not owner
    
    return render_template('image.html', image=image)

@gallery_bp.route('/gallery/<int:image_id>/delete', methods=['POST'])
@login_required
def delete_image(image_id):
    # Get the specific image and verify ownership
    image = Image.query.get_or_404(image_id)
    if image.user_id != current_user.id:
        abort(403)  # Forbidden if not owner
    
    try:
        # Delete the actual image files (both PNG and WebP versions)
        base_filename = os.path.splitext(image.filename)[0]
        png_path = os.path.join('static', 'images', f'{base_filename}.png')
        webp_path = os.path.join('static', 'images', f'{base_filename}.webp')
        
        # Try to delete both file versions if they exist
        if os.path.exists(png_path):
            os.remove(png_path)
        if os.path.exists(webp_path):
            os.remove(webp_path)
        
        # Delete the database entry
        db.session.delete(image)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Image deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# Register markdown filter for all templates using this blueprint
@gallery_bp.app_template_filter('markdown')
def markdown_filter(text):
    return markdown2.markdown(text)
