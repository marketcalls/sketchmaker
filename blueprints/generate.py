from flask import Blueprint, request, jsonify
from openai import OpenAI
import os
import fal_client
import json

generate_bp = Blueprint('generate', __name__)

openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
OPENAI_MODEL = os.getenv('OPENAI_MODEL')
FLUX_PRO_MODEL = os.getenv('FLUX_PRO_MODEL')

@generate_bp.route('/generate', methods=['POST'])
def generate():
    data = request.json
    user_input = data.get('message')
    art_style = data.get('art_style', 'None')
    
    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    if art_style != 'None':
        user_input += f' make it with {art_style}'

    try:
        # If the request is for prompt generation
        if 'regenerate_prompt' in data:
            gpt_response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are ImageGPT, an AI specialized in creating compelling and attention-grabbing image descriptions for various social media platforms, with a focus on YouTube thumbnails. Your task is to transform user-provided concepts into detailed, vivid prompts for AI image generation. Follow these guidelines: ..."},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.7,
                max_tokens=300,
                top_p=0.9,
                frequency_penalty=0.2,
                presence_penalty=0.2
            )
            prompt = gpt_response.choices[0].message.content.strip()
            
            return jsonify({"prompt": prompt})

        # If the request is for image generation
        else:
            prompt = user_input
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

            fal_request = {
                "prompt": prompt,
                "num_inference_steps": 20,
                "guidance_scale": 3.5,
                "num_images": 1,
                "safety_tolerance": "2"
            }

            if isinstance(image_size, dict):
                width = image_size.get('width', 1024)
                height = image_size.get('height', 1024)
                width = max(256, min(1440, (width // 32) * 32))
                height = max(256, min(1440, (height // 32) * 32))
                fal_request["image_size"] = {"width": width, "height": height}
            elif image_size in custom_sizes:
                fal_request["image_size"] = custom_sizes[image_size]
            else:
                fal_request["image_size"] = {"width": 1024, "height": 1024}

            try:
                handler = fal_client.submit(FLUX_PRO_MODEL, arguments=fal_request)
                result = handler.get()
                
                image_urls = [img['url'] for img in result['images']]

                return jsonify({
                    "prompt": prompt,
                    "image_url": image_urls,
                    "width": fal_request["image_size"]["width"],
                    "height": fal_request["image_size"]["height"]
                })
            except fal_client.FalServerException as e:
                return jsonify({"error": f"FAL API Error: {str(e)}"}), 422
            except Exception as e:
                return jsonify({"error": str(e)}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500
