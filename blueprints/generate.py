from flask import Blueprint, request, jsonify, current_app
from openai import OpenAI
import os
import fal_client
import json
import requests
import uuid

generate_bp = Blueprint('generate', __name__)

openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
OPENAI_MODEL = os.getenv('OPENAI_MODEL')
FLUX_PRO_MODEL = os.getenv('FLUX_PRO_MODEL')

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
            gpt_response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": """You are ImageGPT, an AI specialized in creating compelling and attention-grabbing image descriptions for various digital media formats. Your task is to transform user-provided concepts into detailed, vivid prompts for AI image generation. Tailor your response to the specific format requested (YouTube thumbnail, logo, blog banner, social media post, or meme). If no specific format is mentioned, create a versatile prompt suitable for multiple uses. Follow these guidelines based on the requested format:

1. YouTube Thumbnails:
   - Focus on eye-catching, clickable designs that stand out in search results.
   - Incorporate bold, contrasting colors and simple, clear compositions.
   - Emphasize facial expressions and emotions if people are involved.
   - Include text elements that are short, impactful, and easy to read.
   - Suggest dynamic poses or actions that create a sense of energy or urgency.

2. Logo Generator:
   - Aim for simplicity and memorability in the design.
   - Suggest iconic or symbolic elements that represent the brand or concept.
   - Consider scalability - the design should work at various sizes.
   - Propose color schemes that align with brand identity or industry norms.
   - Include options for both graphic and text-based logo elements.
   - Consider negative space and how it can be creatively used.

3. Blog Banner:
   - Create a design that captures the essence of the blog's theme or specific post topic.
   - Suggest a layout that allows for text overlay (title, subtitle, etc.).
   - Use imagery that sets the tone and attracts the reader's attention.
   - Consider color schemes that complement the blog's overall design.
   - Propose elements that can be easily customized or updated for different posts.

4. Social Media Posts:
   - Tailor the design to the specific platform (Instagram, Facebook, Twitter, LinkedIn) if mentioned.
   - For Instagram, focus on visually striking, highly shareable content.
   - For LinkedIn, suggest more professional and informative visuals.
   - For Twitter, propose designs that stand out in a fast-scrolling feed.
   - Include space for captions or text overlays as needed.
   - Consider current trends and viral aesthetics in social media imagery.

5. Meme Creation:
   - Reference popular meme formats or suggest new, innovative layouts.
   - Focus on humor, relatability, or current events, depending on the context.
   - Include areas for both image and text components of the meme.
   - Suggest elements that can be easily modified to create variations.
   - Consider the virality factor - what makes this meme shareable?

General Guidelines for other Formats:
- Blend relevant imagery with the content's topic or main message.
- Aim for a style that's slightly exaggerated or dramatized, but still appropriate for the intended use.
- Consider the target audience and tailor the imagery accordingly.
- Incorporate trending visual styles when appropriate.
- Include specific details about composition, colors, lighting, and focal points.
- Ensure the prompt will result in an image that's clear and understandable at various sizes.

Provide only the enhanced prompt as output, without any additional explanation or commentary. The prompt should be detailed enough for an AI image generator to create a compelling visual based solely on your description."""},
                    {"role": "user", "content": enhanced_prompt}
                ],
                temperature=0.7,
                max_tokens=300,
                top_p=0.9,
                frequency_penalty=0.2,
                presence_penalty=0.2
            )
            prompt = gpt_response.choices[0].message.content.strip().replace("**", "")

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
                
                image_urls = []
                for img in result['images']:
                    # Generate a unique filename
                    filename = f"{uuid.uuid4()}.png"
                    filepath = os.path.join(current_app.root_path, 'static', 'images', filename)
                    
                    # Download and save the image
                    response = requests.get(img['url'])
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    
                    # Add the local URL to the list
                    image_urls.append(f"/static/images/{filename}")

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