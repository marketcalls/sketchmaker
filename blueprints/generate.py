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
        enhanced_prompt = enhance_prompt(user_input, data)
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
    if isinstance(image_size, dict):
        fal_request["image_size"] = image_size
    elif image_size == 'landscape_16_9':
        fal_request["image_size"] = {"width": 1280, "height": 720}
    elif image_size == 'square':
        fal_request["image_size"] = {"width": 1024, "height": 1024}
    elif image_size == 'portrait_4_3':
        fal_request["image_size"] = {"width": 768, "height": 1024}
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

def enhance_prompt(user_input, data):
    art_style = data.get('art_style', 'None')
    color_scheme = data.get('color_scheme', 'None')
    lighting_mood = data.get('lighting_mood', 'None')
    subject_focus = data.get('subject_focus', 'None')
    background_style = data.get('background_style', 'None')
    effects_filters = data.get('effects_filters', 'None')

    # Construct the enhanced prompt
    enhanced_prompt = user_input
    if art_style != 'None':
        enhanced_prompt += f' in the style of {art_style}'
    if color_scheme != 'None':
        enhanced_prompt += f' with a {color_scheme} color scheme'
    if lighting_mood != 'None':
        enhanced_prompt += f' featuring {lighting_mood} lighting and mood'
    if subject_focus != 'None':
        enhanced_prompt += f' focusing on {subject_focus}'
    if background_style != 'None':
        enhanced_prompt += f' with a {background_style} background'
    if effects_filters != 'None':
        enhanced_prompt += f' applying {effects_filters} effects'

    # Use the generate_prompt function from prompt_generator.py
    return generate_prompt(enhanced_prompt)

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