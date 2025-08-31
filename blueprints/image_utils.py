"""
Image Utility Blueprint
Provides image optimization endpoints for various services
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required
from services.image_optimizer import ImageOptimizer
from extensions import limiter

image_utils_bp = Blueprint('image_utils', __name__)

@image_utils_bp.route('/api/utils/optimize-image', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def optimize_image():
    """
    Optimize a single image for a specific service.
    
    Request body:
    {
        "image": "base64 or data URL",
        "service": "fal|magix|training|thumbnail",
        "config": {  // optional custom config
            "max_width": 1536,
            "max_height": 1536,
            "quality": 85,
            "max_file_size_mb": 4
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'image' not in data:
            return jsonify({'error': 'No image provided'}), 400
        
        image_data = data['image']
        service = data.get('service', 'fal')
        custom_config = data.get('config', None)
        
        # Optimize the image
        optimized_image, metadata = ImageOptimizer.optimize_image(
            image_data=image_data,
            service=service,
            custom_config=custom_config
        )
        
        return jsonify({
            'success': True,
            'optimized_image': optimized_image,
            'metadata': metadata
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@image_utils_bp.route('/api/utils/batch-optimize', methods=['POST'])
@limiter.limit("10 per minute")
@login_required
def batch_optimize():
    """
    Optimize multiple images at once.
    
    Request body:
    {
        "images": ["base64 or data URL", ...],
        "service": "fal|magix|training|thumbnail",
        "config": { ... }  // optional
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'images' not in data:
            return jsonify({'error': 'No images provided'}), 400
        
        images = data['images']
        service = data.get('service', 'fal')
        custom_config = data.get('config', None)
        
        if not isinstance(images, list):
            return jsonify({'error': 'Images must be an array'}), 400
        
        if len(images) > 10:
            return jsonify({'error': 'Maximum 10 images per batch'}), 400
        
        # Optimize all images
        results = ImageOptimizer.batch_optimize(
            images=images,
            service=service,
            custom_config=custom_config
        )
        
        # Format response
        optimized_images = []
        for optimized_data, metadata in results:
            optimized_images.append({
                'image': optimized_data,
                'metadata': metadata
            })
        
        return jsonify({
            'success': True,
            'optimized_images': optimized_images,
            'total_processed': len(optimized_images)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@image_utils_bp.route('/api/utils/image-info', methods=['POST'])
@limiter.limit("50 per minute")
@login_required
def get_image_info():
    """
    Get information about an image without optimizing it.
    
    Request body:
    {
        "image": "base64 or data URL"
    }
    """
    try:
        from PIL import Image
        import io
        import base64
        
        data = request.get_json()
        
        if not data or 'image' not in data:
            return jsonify({'error': 'No image provided'}), 400
        
        image_data = data['image']
        
        # Parse image data
        if image_data.startswith('data:'):
            header, data_part = image_data.split(',', 1)
            image_bytes = base64.b64decode(data_part)
        else:
            image_bytes = base64.b64decode(image_data)
        
        # Open with PIL to get info
        img = Image.open(io.BytesIO(image_bytes))
        
        # Calculate file size
        file_size_bytes = len(image_bytes)
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        # Get image info
        info = {
            'width': img.width,
            'height': img.height,
            'format': img.format,
            'mode': img.mode,
            'file_size_bytes': file_size_bytes,
            'file_size_mb': round(file_size_mb, 2),
            'megapixels': round((img.width * img.height) / 1000000, 2),
            'aspect_ratio': round(img.width / img.height, 2) if img.height > 0 else 0,
            'needs_optimization': file_size_mb > 2 or img.width > 1920 or img.height > 1920
        }
        
        # Check for EXIF orientation
        try:
            exif = img._getexif()
            if exif and 274 in exif:  # Orientation tag
                info['has_orientation_data'] = True
                info['orientation'] = exif[274]
            else:
                info['has_orientation_data'] = False
        except:
            info['has_orientation_data'] = False
        
        return jsonify({
            'success': True,
            'info': info
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@image_utils_bp.route('/api/utils/optimization-preview', methods=['POST'])
@limiter.limit("20 per minute")
@login_required
def optimization_preview():
    """
    Preview what the optimization would do without actually optimizing.
    Useful for showing users the expected results.
    
    Request body:
    {
        "image": "base64 or data URL",
        "service": "fal|magix|training|thumbnail"
    }
    """
    try:
        from PIL import Image
        import io
        import base64
        
        data = request.get_json()
        
        if not data or 'image' not in data:
            return jsonify({'error': 'No image provided'}), 400
        
        image_data = data['image']
        service = data.get('service', 'fal')
        
        # Parse image to get current stats
        if image_data.startswith('data:'):
            header, data_part = image_data.split(',', 1)
            image_bytes = base64.b64decode(data_part)
        else:
            image_bytes = base64.b64decode(image_data)
        
        img = Image.open(io.BytesIO(image_bytes))
        
        # Get service configuration
        config = ImageOptimizer.SERVICE_CONFIGS.get(
            service,
            {
                'max_width': ImageOptimizer.DEFAULT_MAX_WIDTH,
                'max_height': ImageOptimizer.DEFAULT_MAX_HEIGHT,
                'quality': ImageOptimizer.DEFAULT_QUALITY,
                'max_file_size_mb': ImageOptimizer.DEFAULT_MAX_FILE_SIZE_MB
            }
        )
        
        # Calculate expected dimensions
        max_width = config['max_width']
        max_height = config['max_height']
        
        if img.width > max_width or img.height > max_height:
            ratio = min(max_width / img.width, max_height / img.height)
            new_width = int(img.width * ratio)
            new_height = int(img.height * ratio)
            will_resize = True
        else:
            new_width = img.width
            new_height = img.height
            will_resize = False
        
        # Estimate compressed size (rough estimate)
        current_size_mb = len(image_bytes) / (1024 * 1024)
        if will_resize:
            size_reduction = (new_width * new_height) / (img.width * img.height)
        else:
            size_reduction = 1.0
        
        # Factor in quality compression
        quality_factor = config['quality'] / 100
        estimated_size_mb = current_size_mb * size_reduction * quality_factor * 0.7  # 0.7 is a rough JPEG compression factor
        
        preview = {
            'current': {
                'width': img.width,
                'height': img.height,
                'size_mb': round(current_size_mb, 2),
                'format': img.format or 'Unknown'
            },
            'optimized': {
                'width': new_width,
                'height': new_height,
                'estimated_size_mb': round(estimated_size_mb, 2),
                'format': 'JPEG',
                'quality': config['quality']
            },
            'savings': {
                'size_reduction_percent': round((1 - estimated_size_mb / current_size_mb) * 100, 1),
                'will_resize': will_resize,
                'dimension_change': f"{img.width}x{img.height} → {new_width}x{new_height}" if will_resize else "No change"
            },
            'service_config': config
        }
        
        return jsonify({
            'success': True,
            'preview': preview
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500