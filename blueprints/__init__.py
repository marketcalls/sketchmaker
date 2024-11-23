from .auth import auth_bp
from .core import core_bp
from .generate import generate_bp
from .gallery import gallery_bp
from .download import download_bp
from .admin import admin
from .magix import magix_bp
from .training import training_bp
from .banner import banner
from .image_generator import image_generator_bp

__all__ = [
    'auth_bp',
    'core_bp',
    'generate_bp',
    'gallery_bp',
    'download_bp',
    'admin',
    'magix_bp',
    'training_bp',
    'banner',
    'image_generator_bp'
]
