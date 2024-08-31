from flask import Blueprint, request, jsonify
from .prompt_generator import generate_prompt
from .image_generator import generate_image
import fal_client

generate_bp = Blueprint('generate', __name__)

@generate_bp.route('/generate', methods=['POST'])
def generate():
    data = request.json
    user_input = data.get('message')
    art_style = data.get('art_style', 'None')
    color_scheme = data.get('color_scheme', 'None')
    lighting_mood = data.get('lighting_mood', 'None')
    subject_focus = data.get('subject_focus', 'None')
    background_style = data.get('background_style', 'None')
    effects_filters = data.get('effects_filters', 'None')

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

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

    try:
        # If the request is for prompt generation
        if 'regenerate_prompt' in data:
            prompt = generate_prompt(enhanced_prompt)
            return jsonify({"prompt": prompt})

        # If the request is for image generation
        else:
            prompt = enhanced_prompt
            image_size = data.get('image_size')

            # Define custom image sizes
            custom_sizes = {
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
                "youtube_thumbnail": {"width": 1280, "height": 720},
                "blog_banner": {"width": 1440, "height": 832},
                "linkedin_post": {"width": 1216, "height": 1216},
                "facebook_post_landscape": {"width": 960, "height": 768},
                "twitter_header": {"width": 1504, "height": 480}
            }

            if isinstance(image_size, dict):
                width = image_size.get('width', 1024)
                height = image_size.get('height', 1024)
                width = max(256, min(1440, (width // 32) * 32))
                height = max(256, min(1440, (height // 32) * 32))
                image_size = {"width": width, "height": height}
            elif image_size in custom_sizes:
                image_size = custom_sizes[image_size]
            else:
                image_size = {"width": 1024, "height": 1024}

            result = generate_image(prompt, image_size)
            return jsonify({
                "prompt": prompt,
                **result
            })

    except fal_client.FalServerException as e:
        return jsonify({"error": f"FAL API Error: {str(e)}"}), 422
    except Exception as e:
        return jsonify({"error": str(e)}), 500