"""
Image Optimization Service
A modular service for optimizing images before processing.
Handles resizing, compression, and format conversion.
"""

from PIL import Image
import io
import base64
from typing import Tuple, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class ImageOptimizer:
    """
    Image optimization service for reducing file sizes and dimensions
    while maintaining quality for AI processing.
    """
    
    # Default settings - can be overridden per use case
    DEFAULT_MAX_WIDTH = 1920
    DEFAULT_MAX_HEIGHT = 1920
    DEFAULT_QUALITY = 85
    DEFAULT_MAX_FILE_SIZE_MB = 5
    
    # Specific settings for different services
    SERVICE_CONFIGS = {
        'fal': {
            'max_width': 1536,
            'max_height': 1536,
            'quality': 85,
            'max_file_size_mb': 4,
            'format': 'JPEG'
        },
        'magix': {
            'max_width': 1536,
            'max_height': 1536,
            'quality': 90,
            'max_file_size_mb': 4,
            'format': 'JPEG'
        },
        'training': {
            'max_width': 1024,
            'max_height': 1024,
            'quality': 95,
            'max_file_size_mb': 3,
            'format': 'JPEG'
        },
        'thumbnail': {
            'max_width': 512,
            'max_height': 512,
            'quality': 80,
            'max_file_size_mb': 1,
            'format': 'JPEG'
        }
    }
    
    @classmethod
    def optimize_image(
        cls,
        image_data: str,
        service: str = 'fal',
        custom_config: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Optimize an image for a specific service.
        
        Args:
            image_data: Base64 encoded image data or data URL
            service: Service name for specific optimization settings
            custom_config: Optional custom configuration to override defaults
            
        Returns:
            Tuple of (optimized_image_data, metadata)
        """
        try:
            # Get configuration
            config = cls._get_config(service, custom_config)
            
            # Parse image data
            image_bytes = cls._parse_image_data(image_data)
            
            # Open image with PIL
            img = Image.open(io.BytesIO(image_bytes))
            original_format = img.format
            original_size = len(image_bytes)
            original_dimensions = img.size
            
            # Convert RGBA to RGB if needed (for JPEG)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create a white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Fix orientation based on EXIF data (important for iPhone images)
            img = cls._fix_orientation(img)
            
            # Resize if needed
            img, was_resized = cls._resize_image(img, config)
            
            # Compress and convert format
            optimized_bytes = cls._compress_image(img, config)
            
            # Further compress if still too large
            quality = config['quality']
            max_size_bytes = config['max_file_size_mb'] * 1024 * 1024
            
            while len(optimized_bytes) > max_size_bytes and quality > 60:
                quality -= 5
                optimized_bytes = cls._compress_image(img, {**config, 'quality': quality})
            
            # If still too large, resize more aggressively
            if len(optimized_bytes) > max_size_bytes:
                scale_factor = 0.8
                while len(optimized_bytes) > max_size_bytes and scale_factor > 0.3:
                    new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
                    temp_img = img.resize(new_size, Image.Resampling.LANCZOS)
                    optimized_bytes = cls._compress_image(temp_img, {**config, 'quality': quality})
                    scale_factor -= 0.1
                    img = temp_img
                    was_resized = True
            
            # Convert to base64 data URL
            optimized_data = cls._to_data_url(optimized_bytes, config['format'])
            
            # Prepare metadata
            metadata = {
                'original_size_bytes': original_size,
                'optimized_size_bytes': len(optimized_bytes),
                'compression_ratio': round(len(optimized_bytes) / original_size * 100, 2),
                'original_dimensions': original_dimensions,
                'optimized_dimensions': img.size,
                'was_resized': was_resized,
                'final_quality': quality,
                'format': config['format']
            }
            
            logger.info(f"Image optimized: {original_size} -> {len(optimized_bytes)} bytes "
                       f"({metadata['compression_ratio']}%), "
                       f"dimensions: {original_dimensions} -> {img.size}")
            
            return optimized_data, metadata
            
        except Exception as e:
            logger.error(f"Error optimizing image: {str(e)}")
            # Return original image if optimization fails
            return image_data, {'error': str(e), 'optimization_failed': True}
    
    @classmethod
    def _get_config(cls, service: str, custom_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get configuration for the service."""
        # Start with service-specific config or defaults
        if service in cls.SERVICE_CONFIGS:
            config = cls.SERVICE_CONFIGS[service].copy()
        else:
            config = {
                'max_width': cls.DEFAULT_MAX_WIDTH,
                'max_height': cls.DEFAULT_MAX_HEIGHT,
                'quality': cls.DEFAULT_QUALITY,
                'max_file_size_mb': cls.DEFAULT_MAX_FILE_SIZE_MB,
                'format': 'JPEG'
            }
        
        # Override with custom config if provided
        if custom_config:
            config.update(custom_config)
        
        return config
    
    @classmethod
    def _parse_image_data(cls, image_data: str) -> bytes:
        """Parse image data from base64 or data URL."""
        # Handle data URL format
        if image_data.startswith('data:'):
            # Extract base64 part from data URL
            header, data = image_data.split(',', 1)
            return base64.b64decode(data)
        else:
            # Assume it's already base64
            return base64.b64decode(image_data)
    
    @classmethod
    def _fix_orientation(cls, img: Image.Image) -> Image.Image:
        """Fix image orientation based on EXIF data."""
        try:
            # Get EXIF data
            exif = img._getexif()
            if exif is None:
                return img
            
            # Find orientation tag
            orientation_key = 274  # Orientation EXIF tag
            if orientation_key not in exif:
                return img
            
            orientation = exif[orientation_key]
            
            # Apply rotation based on orientation
            rotations = {
                3: 180,
                6: 270,
                8: 90
            }
            
            if orientation in rotations:
                img = img.rotate(rotations[orientation], expand=True)
            
            # Handle flips
            if orientation == 2:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 4:
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
            elif orientation == 5:
                img = img.rotate(270, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 7:
                img = img.rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
            
            return img
            
        except (AttributeError, KeyError, TypeError):
            # If there's any error reading EXIF, return original
            return img
    
    @classmethod
    def _resize_image(cls, img: Image.Image, config: Dict[str, Any]) -> Tuple[Image.Image, bool]:
        """Resize image if it exceeds maximum dimensions."""
        max_width = config['max_width']
        max_height = config['max_height']
        
        if img.width <= max_width and img.height <= max_height:
            return img, False
        
        # Calculate resize ratio maintaining aspect ratio
        ratio = min(max_width / img.width, max_height / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        
        # Use high-quality resampling
        resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        return resized_img, True
    
    @classmethod
    def _compress_image(cls, img: Image.Image, config: Dict[str, Any]) -> bytes:
        """Compress image to specified format and quality."""
        output = io.BytesIO()
        
        format_name = config['format']
        quality = config['quality']
        
        # Save with optimization
        save_kwargs = {
            'format': format_name,
            'optimize': True
        }
        
        # Add quality for JPEG
        if format_name == 'JPEG':
            save_kwargs['quality'] = quality
            save_kwargs['progressive'] = True
            
        img.save(output, **save_kwargs)
        
        return output.getvalue()
    
    @classmethod
    def _to_data_url(cls, image_bytes: bytes, format_name: str) -> str:
        """Convert image bytes to data URL."""
        base64_data = base64.b64encode(image_bytes).decode('utf-8')
        mime_type = f"image/{format_name.lower()}"
        if format_name == 'JPEG':
            mime_type = 'image/jpeg'
        return f"data:{mime_type};base64,{base64_data}"
    
    @classmethod
    def batch_optimize(
        cls,
        images: list,
        service: str = 'fal',
        custom_config: Optional[Dict[str, Any]] = None
    ) -> list:
        """
        Optimize multiple images at once.
        
        Args:
            images: List of base64 encoded images
            service: Service name for optimization settings
            custom_config: Optional custom configuration
            
        Returns:
            List of tuples (optimized_image, metadata)
        """
        results = []
        for image_data in images:
            optimized_data, metadata = cls.optimize_image(image_data, service, custom_config)
            results.append((optimized_data, metadata))
        return results
    
    @classmethod
    def estimate_processing_time(cls, file_size_mb: float, count: int = 1) -> float:
        """
        Estimate processing time for optimization.
        
        Args:
            file_size_mb: Size of file in MB
            count: Number of images
            
        Returns:
            Estimated time in seconds
        """
        # Rough estimate: 0.5 seconds per MB + 0.2 seconds overhead per image
        return (file_size_mb * 0.5 + 0.2) * count