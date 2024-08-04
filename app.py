from flask import Flask, request, jsonify, render_template, send_file
from openai import OpenAI
from dotenv import load_dotenv
from flask_cors import CORS
import os
import fal_client
import requests
from io import BytesIO
from PIL import Image
import json

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)  # This will enable CORS for all routes

# Get the API keys and models from environment variables
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
fal_key = os.getenv('FAL_KEY')
if not fal_key:
    raise ValueError("FAL_KEY environment variable is not set")
OPENAI_MODEL = os.getenv('OPENAI_MODEL')
FLUX_PRO_MODEL = os.getenv('FLUX_PRO_MODEL')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    user_input = data.get('message')
    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    try:
        # If the request is for prompt generation
        if 'regenerate_prompt' in data:
            # Print the request data
            print("Request for prompt generation:", json.dumps(data, indent=2))
            
            # Generate the prompt using OpenAI API
            gpt_response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": """You are ImageGPT, an AI specialized in creating compelling and attention-grabbing image descriptions for various social media platforms, with a focus on YouTube thumbnails. Your task is to transform user-provided concepts into detailed, vivid prompts for AI image generation. Follow these guidelines:

1. Tailor the prompt to the specific platform (e.g., YouTube, Instagram, LinkedIn) if mentioned by the user.
2. For YouTube thumbnails:
   a. Focus on eye-catching, clickable designs that stand out in search results.
   b. Incorporate bold, contrasting colors and simple, clear compositions.
   c. Emphasize facial expressions and emotions if people are involved.
   d. Include text elements that are short, impactful, and easy to read.
   e. Suggest dynamic poses or actions that create a sense of energy or urgency.

3. For other platforms, adapt the style accordingly (e.g., more professional for LinkedIn, more artistic for Instagram).
4. Blend relevant imagery with the content's topic or main message.
5. Aim for a style that's slightly exaggerated or dramatized, but still professional.
6. Consider the target audience and tailor the imagery accordingly.
7. Incorporate trending visual styles or memes when appropriate.
8. Ensure the prompt will result in an image that's clear and understandable at thumbnail size.
9. If no specific platform is mentioned, create a versatile prompt suitable for multiple uses.
10. Include specific details about composition, colors, lighting, and focal points.

Provide only the enhanced prompt as output, without any additional explanation or commentary. The prompt should be detailed enough for an AI image generator to create a compelling visual based solely on your description."""},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.7,
                max_tokens=300,
                top_p=0.9,
                frequency_penalty=0.2,
                presence_penalty=0.2
            )
            prompt = gpt_response.choices[0].message.content.strip()
            
            # Print the response from OpenAI API
            print("OpenAI API response:", json.dumps({
                "id": gpt_response.id,
                "object": gpt_response.object,
                "created": gpt_response.created,
                "model": gpt_response.model,
                "choices": [{
                    "index": choice.index,
                    "finish_reason": choice.finish_reason,
                    "message": choice.message.content
                } for choice in gpt_response.choices]
            }, indent=2))
            
            return jsonify({"prompt": prompt})

        # If the request is for image generation
        else:
            prompt = user_input
            image_size = data.get('image_size')

            # Define custom image sizes
            custom_sizes = {
                "landscape_4_3": {"width": 1024, "height": 768},  # Fixed Landscape 4:3 ratio
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
                "num_inference_steps": 20,  # Fixed value
                "guidance_scale": 3.5,  # Fixed value
                "num_images": 1,
                "safety_tolerance": "2"  # Fixed to High
            }

            # Handle image size
            if isinstance(image_size, dict):
                width = image_size.get('width', 1024)
                height = image_size.get('height', 1024)
                # Adjust width and height to be multiples of 32 within the range 256 to 1440
                width = max(256, min(1440, (width // 32) * 32))
                height = max(256, min(1440, (height // 32) * 32))
                fal_request["image_size"] = {"width": width, "height": height}
            elif image_size in custom_sizes:
                fal_request["image_size"] = custom_sizes[image_size]
            else:
                fal_request["image_size"] = {"width": 1024, "height": 1024}

            try:
                # Print the request data for image generation
                print("Request for image generation:", json.dumps(fal_request, indent=2))
                
                # Generate image using Flux Pro
                handler = fal_client.submit(FLUX_PRO_MODEL, arguments=fal_request)
                result = handler.get()
                
                # Print the response from Flux Pro
                print("Flux Pro response:", json.dumps(result, indent=2))
                
                image_urls = [img['url'] for img in result['images']]

                return jsonify({
                    "prompt": prompt,
                    "image_url": image_urls,
                    "width": fal_request["image_size"]["width"],
                    "height": fal_request["image_size"]["height"]
                })
            except fal_client.FalServerException as e:
                print("FAL API Error:", str(e))
                return jsonify({"error": f"FAL API Error: {str(e)}"}), 422
            except Exception as e:
                print("Unexpected error during image generation:", str(e))
                return jsonify({"error": str(e)}), 500

    except Exception as e:
        print("Error during generation:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/download', methods=['GET'])
def download_image():
    image_url = request.args.get('url')
    format = request.args.get('format', 'png')
    
    if not image_url:
        return jsonify({"error": "No image URL provided"}), 400

    try:
        response = requests.get(image_url)
        img = Image.open(BytesIO(response.content))
        
        output = BytesIO()
        if format == 'webp':
            img.save(output, format='WEBP')
        elif format == 'jpeg':
            img = img.convert('RGB')
            img.save(output, format='JPEG')
        else:
            img.save(output, format='PNG')
        
        output.seek(0)
        return send_file(output, mimetype=f'image/{format}', as_attachment=True, download_name=f'thumbnail.{format}')
    except Exception as e:
        print("Error downloading image:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
