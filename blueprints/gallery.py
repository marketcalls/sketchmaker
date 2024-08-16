from flask import Blueprint, render_template, current_app
import os

gallery_bp = Blueprint('gallery', __name__)

@gallery_bp.route('/gallery')
def gallery():
    image_folder = os.path.join(current_app.root_path, 'static', 'images')
    images = [f for f in os.listdir(image_folder) if f.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]
    return render_template('gallery.html', images=images)

@gallery_bp.route('/image/<filename>')
def image(filename):
    return render_template('image.html', filename=filename)