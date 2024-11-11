import fal_client
import uuid
import os
import requests
from flask import current_app
from .clients import FLUX_PRO_MODEL
from urllib.parse import urlparse
from PIL import Image as PILImage
import io

def get_extension_from_url(url):
    """Extract file extension from URL, defaulting to .png if not found"""
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    return ext if ext in ['.png', '.jpg', '.jpeg', '.webp'] else '.png'

def generate_image(prompt, image_size):
    try:
        # Validate inputs
        if not prompt:
            raise ValueError("Prompt cannot be empty")
        if not isinstance(image_size, dict) or 'width' not in image_size or 'height' not in image_size:
            raise ValueError("Invalid image size format")

        # Prepare request
        fal_request = {
            "prompt": prompt,
            "image_size": image_size,
            "num_images": 1,
            "enable_safety_checker": True,
            "safety_tolerance": "2"
        }

        print(f"Submitting request to FAL: {fal_request}")  # Debug log

        # Submit request
        handler = fal_client.submit(FLUX_PRO_MODEL, arguments=fal_request)
        result = handler.get()
        
        print(f"Received response from FAL: {result}")  # Debug log
        
        if not result or 'images' not in result:
            raise ValueError("Invalid response from FAL API")

        image_urls = []
        for img in result['images']:
            if not img.get('url'):
                continue

            # Generate a unique base filename without extension
            base_filename = str(uuid.uuid4())
            
            # Get absolute paths
            static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
            images_dir = os.path.join(static_dir, 'images')
            
            # Ensure the images directory exists
            os.makedirs(images_dir, exist_ok=True)
            
            # Download image
            response = requests.get(img['url'])
            response.raise_for_status()  # Raise error for bad status codes
            
            # Load image into PIL
            image_data = io.BytesIO(response.content)
            pil_image = PILImage.open(image_data)
            
            # Save as PNG (original)
            png_filename = f"{base_filename}.png"
            png_filepath = os.path.join(images_dir, png_filename)
            pil_image.save(png_filepath, 'PNG')
            
            print(f"Saved PNG image to: {png_filepath}")  # Debug log
            
            # Verify file was saved
            if not os.path.exists(png_filepath):
                print(f"Warning: Failed to save image to {png_filepath}")
                continue
                
            image_urls.append(f"/static/images/{png_filename}")

        if not image_urls:
            raise ValueError("No images were successfully downloaded")

        return {
            "image_url": image_urls,
            "width": fal_request["image_size"]["width"],
            "height": fal_request["image_size"]["height"]
        }
    except requests.exceptions.RequestException as e:
        print(f"Error downloading image: {str(e)}")  # Debug log
        raise ValueError(f"Failed to download generated image: {str(e)}")
    except Exception as e:
        print(f"Error in generate_image: {str(e)}")  # Debug log
        raise
