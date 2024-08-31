import fal_client
import uuid
import os
import requests
from flask import current_app
from .clients import FLUX_PRO_MODEL

def generate_image(prompt, image_size):
    fal_request = {
        "prompt": prompt,
        "num_inference_steps": 20,
        "guidance_scale": 3.5,
        "num_images": 1,
        "safety_tolerance": "2",
        "image_size": image_size
    }

    handler = fal_client.submit(FLUX_PRO_MODEL, arguments=fal_request)
    result = handler.get()
    
    image_urls = []
    for img in result['images']:
        filename = f"{uuid.uuid4()}.png"
        filepath = os.path.join(current_app.root_path, 'static', 'images', filename)
        
        response = requests.get(img['url'])
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        image_urls.append(f"/static/images/{filename}")

    return {
        "image_url": image_urls,
        "width": fal_request["image_size"]["width"],
        "height": fal_request["image_size"]["height"]
    }