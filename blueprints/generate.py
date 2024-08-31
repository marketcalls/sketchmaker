from flask import Blueprint, request, jsonify, current_app
import fal_client
import os
import uuid
import requests
from .prompt_generator import generate_prompt

generate_bp = Blueprint('generate', __name__)

@generate_bp.route('/generate', methods=['POST'])
def generate():
    data = request.json
    user_input = data.get('message')
    model = data.get('model')
    
    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    # Enhance prompt if requested
    if data.get('enhance_prompt', False):
        enhanced_prompt = generate_prompt(user_input)
    else:
        enhanced_prompt = user_input

    # If only prompt enhancement is requested, return the enhanced prompt
    if data.get('enhance_prompt_only', False):
        return jsonify({"prompt": enhanced_prompt})

    if not model:
        return jsonify({"error": "No model provided"}), 400

    # Common parameters
    fal_request = {
        "prompt": enhanced_prompt,
        "num_inference_steps": data.get('num_inference_steps', 28),
        "guidance_scale": data.get('guidance_scale', 3.5),
        "num_images": 1,
    }

    # Handle image size
    image_size = data.get('image_size')
    custom_sizes = {
        "youtube_thumbnail": {"width": 1280, "height": 704},
        "landscape_4_3": {"width": 1024, "height": 768},
        "landscape_16_9": {"width": 1280, "height": 720},
        "portrait_4_3": {"width": 768, "height": 1024},
        "portrait_16_9": {"width": 720, "height": 1280},
        "square": {"width": 1024, "height": 1024},
        "square_hd": {"width": 1080, "height": 1080},
        "instagram_post_square": {"width": 1088, "height": 1088},
        "instagram_post_portrait": {"width": 1088, "height": 1344},
        "instagram_story": {"width": 1088, "height": 1920},
        "logo": {"width": 512, "height": 512},
        "blog_banner": {"width": 1440, "height": 832},
        "linkedin_post": {"width": 1216, "height": 1216},
        "facebook_post_landscape": {"width": 960, "height": 768},
        "twitter_header": {"width": 1504, "height": 480}
    }

    if image_size in custom_sizes:
        fal_request["image_size"] = custom_sizes[image_size]
    else:
        fal_request["image_size"] = {"width": 1024, "height": 1024}  # Default size

    # Add seed if provided
    if 'seed' in data:
        fal_request["seed"] = data['seed']

    # Model-specific parameters
    if model == "fal-ai/flux-pro":
        fal_request["safety_tolerance"] = data.get('safety_tolerance', "2")
    elif model == "fal-ai/flux/dev" or model == "fal-ai/flux-realism":
        fal_request["enable_safety_checker"] = data.get('enable_safety_checker', True)
        if model == "fal-ai/flux-realism":
            fal_request["strength"] = data.get('strength', 1)
    elif model == "fal-ai/flux-lora":
        fal_request["enable_safety_checker"] = data.get('enable_safety_checker', True)
        fal_request["output_format"] = data.get('output_format', "jpeg")
        if 'lora_path' in data:
            fal_request["loras"] = [{
                "path": data['lora_path'],
                "scale": data.get('lora_scale', 1)
            }]

    try:
        handler = fal_client.submit(model, arguments=fal_request)
        result = handler.get()
        
        # Save the image to the gallery
        image_url = result['images'][0]['url']
        local_image_path = save_image_to_gallery(image_url)
        
        return jsonify({
            "prompt": enhanced_prompt,
            "image_url": f"/static/images/{os.path.basename(local_image_path)}",
            "width": fal_request["image_size"]["width"],
            "height": fal_request["image_size"]["height"]
        })

    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 500

def save_image_to_gallery(image_url):
    response = requests.get(image_url)
    if response.status_code == 200:
        filename = f"{uuid.uuid4()}.png"
        filepath = os.path.join(current_app.root_path, 'static', 'images', filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)
        return filepath
    else:
        raise Exception("Failed to download image from URL")