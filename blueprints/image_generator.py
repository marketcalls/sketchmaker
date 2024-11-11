import fal_client
import uuid
import os
import requests
from flask import current_app
from .clients import FLUX_PRO_MODEL
import io

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

            # Generate a unique filename
            filename = f"{uuid.uuid4()}.png"
            
            # Get absolute paths
            filepath = os.path.join(current_app.root_path, 'static', 'images', filename)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Download image
            response = requests.get(img['url'])
            response.raise_for_status()
            
            # Save image
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            print(f"Saved PNG image to: {filepath}")  # Debug log
            
            # Verify file was saved
            if not os.path.exists(filepath):
                print(f"Warning: Failed to save image to {filepath}")
                continue
                
            image_urls.append(f"/static/images/{filename}")

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
