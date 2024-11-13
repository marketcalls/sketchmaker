from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from .image_generator import generate_image
from .prompt_generator import generate_prompt
from .clients import APIKeyError
from models import db, Image
import os
from PIL import Image as PILImage
import uuid
import traceback

generate_bp = Blueprint('generate', __name__)

def get_absolute_path(filename):
    """Get absolute path for a file in the static/images directory"""
    return os.path.join(current_app.root_path, 'static', 'images', filename)

@generate_bp.route('/generate/prompt', methods=['POST'])
@login_required
def generate_prompt_route():
    data = request.get_json()
    if not data or 'topic' not in data:
        return jsonify({'error': 'No topic provided'}), 400

    try:
        if not current_user.has_required_api_keys():
            return jsonify({'error': 'API keys are required. Please add them in your settings.'}), 400

        prompt = generate_prompt(data['topic'])
        return jsonify({'prompt': prompt})
    except APIKeyError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"Error generating prompt: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@generate_bp.route('/generate/image', methods=['POST'])
@login_required
def generate_image_route():
    try:
        if not current_user.has_required_api_keys():
            return jsonify({'error': 'API keys are required. Please add them in your settings.'}), 400

        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({'error': 'No prompt provided'}), 400

        # Get all parameters from request
        prompt = data['prompt']
        art_style = data.get('artStyle')
        model = data.get('model')

        print("\n=== Image Generation Request ===")
        print(f"Requested Model: {model}")
        print(f"Request Data: {data}")
        print("==============================\n")
        
        if not model:
            model = 'fal-ai/flux-pro/v1.1'
            print(f"No model specified, using default: {model}")
        
        # Add art style to prompt if provided
        full_prompt = f"{prompt} in {art_style} style" if art_style else prompt
        
        # Prepare generation parameters
        generation_params = {
            'prompt': full_prompt,
            'model': model,
            'num_images': data.get('num_images', 1),
            'enable_safety_checker': data.get('enable_safety_checker', True),
            'seed': data.get('seed')
        }

        # Add model-specific parameters
        if model != 'fal-ai/flux-pro/v1.1-ultra':
            # All models except Ultra use image_size
            generation_params['image_size'] = data.get('image_size', {
                'width': 1024,
                'height': 1024
            })

        if model in ['fal-ai/flux-lora', 'fal-ai/flux-realism']:
            # Add parameters specific to Lora and Realism models
            generation_params.update({
                'num_inference_steps': data.get('num_inference_steps', 28),
                'guidance_scale': data.get('guidance_scale', 3.5)
            })

        if model == 'fal-ai/flux-lora' and data.get('loras'):
            # Add LoRA specific parameters
            generation_params['loras'] = data.get('loras')

        if model == 'fal-ai/flux-realism':
            # Add Realism specific parameters
            generation_params['strength'] = data.get('strength', 1)

        if model == 'fal-ai/flux-pro/v1.1-ultra':
            # Add Ultra specific parameters
            generation_params['aspect_ratio'] = data.get('aspect_ratio', '16:9')
        
        print("\n=== Generation Parameters ===")
        print(f"Using Model: {model}")
        print(f"Parameters: {generation_params}")
        print("==========================\n")
        
        # Generate the image
        result = generate_image(generation_params)
        
        if not result or 'image_url' not in result:
            raise ValueError("Failed to generate image: Invalid response from image generator")
        
        # Save each generated image to database
        saved_images = []
        for image_url in result['image_url']:
            filename = image_url.split('/')[-1]
            base_name = os.path.splitext(filename)[0]
            
            try:
                print(f"Processing image: {filename}")  # Debug log
                
                # Load the original image
                original_filepath = get_absolute_path(filename)
                if not os.path.exists(original_filepath):
                    print(f"Warning: Original file not found: {original_filepath}")
                    continue
                
                img = PILImage.open(original_filepath)
                
                # Save PNG version
                png_filename = f"{base_name}.png"
                png_filepath = get_absolute_path(png_filename)
                img.save(png_filepath, 'PNG')
                
                # Save WebP version
                webp_filename = f"{base_name}.webp"
                webp_filepath = get_absolute_path(webp_filename)
                img.save(webp_filepath, 'WEBP')
                
                # Save JPEG version
                jpeg_filename = f"{base_name}.jpeg"
                jpeg_filepath = get_absolute_path(jpeg_filename)
                # Convert to RGB mode for JPEG
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                img.save(jpeg_filepath, 'JPEG')
                
                # Save image record to database
                new_image = Image(
                    filename=png_filename,  # Store PNG as the primary filename
                    prompt=prompt,
                    art_style=art_style,
                    width=result.get('width'),
                    height=result.get('height'),
                    user_id=current_user.id
                )
                db.session.add(new_image)
                
                saved_images.append({
                    'image_url': f'/static/images/{png_filename}',
                    'webp_url': f'/static/images/{webp_filename}',
                    'jpeg_url': f'/static/images/{jpeg_filename}'
                })
                
                print(f"Successfully processed image: {filename}")  # Debug log
            except FileNotFoundError as e:
                print(f"File not found error: {str(e)}")
                continue
            except Exception as e:
                print(f"Error processing image {filename}: {str(e)}")
                print(traceback.format_exc())
                continue
        
        if not saved_images:
            raise ValueError("No images were successfully processed")
        
        db.session.commit()

        response_data = {
            'images': saved_images,
            'prompt': prompt,
            'art_style': art_style,
            'model': model
        }

        # Add dimension info if available
        if 'width' in result and 'height' in result:
            response_data.update({
                'width': result['width'],
                'height': result['height']
            })

        return jsonify(response_data)
    except APIKeyError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"Error in generate_image_route: {str(e)}")
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
