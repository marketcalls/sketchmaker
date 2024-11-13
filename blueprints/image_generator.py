import uuid
import os
import requests
from flask import current_app
from .clients import init_fal_client
import io
import fal_client

def generate_image(prompt, image_size):
    """Generate image using FAL API with user's API key"""
    try:
        # Validate inputs
        if not prompt:
            raise ValueError("Prompt cannot be empty")
        if not isinstance(image_size, dict) or 'width' not in image_size or 'height' not in image_size:
            raise ValueError("Invalid image size format")

        print(f"Generating image with prompt: {prompt}, size: {image_size}")  # Debug log

        # Initialize FAL client and get instance
        client = init_fal_client()

        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    print(f"FAL generation log: {log['message']}")

        # Generate image using FAL API
        result = client.subscribe(
            "fal-ai/flux-pro/v1.1",
            arguments={
                "prompt": prompt,
                "image_size": image_size,
                "num_images": 1,
                "enable_safety_checker": True,
                "safety_tolerance": "2",
                "seed": 2345
            },
            with_logs=True,
            on_queue_update=on_queue_update
        )
        
        print(f"Received response from FAL: {result}")  # Debug log
        
        if not result or 'images' not in result:
            raise ValueError("Invalid response from FAL API")

        image_urls = []
        for img in result['images']:
            if not img.get('url'):
                continue

            # Generate a unique filename
            base_filename = str(uuid.uuid4())
            
            # Get absolute paths
            static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
            images_dir = os.path.join(static_dir, 'images')
            
            # Ensure the images directory exists
            os.makedirs(images_dir, exist_ok=True)
            
            # Download image
            response = requests.get(img['url'])
            response.raise_for_status()
            
            # Load image into PIL
            image_data = io.BytesIO(response.content)
            
            # Save as PNG
            png_filename = f"{base_filename}.png"
            png_filepath = os.path.join(images_dir, png_filename)
            
            with open(png_filepath, 'wb') as f:
                f.write(image_data.getvalue())
            
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
            "width": image_size["width"],
            "height": image_size["height"]
        }
    except Exception as e:
        print(f"Error in generate_image: {str(e)}")  # Debug log
        raise
