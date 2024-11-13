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
from fal_client.client import FalClientError

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
            return jsonify({
                'error': 'API keys are required',
                'details': 'Please add your API keys in settings',
                'type': 'missing_keys'
            }), 400

        prompt = generate_prompt(data['topic'])
        return jsonify({'prompt': prompt})
    except APIKeyError as e:
        return jsonify({
            'error': str(e),
            'details': 'Please check your API keys in settings',
            'type': 'api_key_error'
        }), 400
    except Exception as e:
        print(f"Error generating prompt: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'error': 'Failed to generate prompt',
            'details': str(e),
            'type': 'generation_error'
        }), 500

@generate_bp.route('/generate/image', methods=['POST'])
@login_required
def generate_image_route():
    try:
        if not current_user.has_required_api_keys():
            return jsonify({
                'error': 'API keys are required',
                'details': 'Please add your API keys in settings',
                'type': 'missing_keys'
            }), 400

        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({
                'error': 'No prompt provided',
                'details': 'A prompt is required to generate an image',
                'type': 'missing_prompt'
            }), 400

        # Get all parameters from request
        prompt = data['prompt']
        art_style = data.get('artStyle')
        model = data.get('model', 'fal-ai/flux-pro/v1.1')
        
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
        
        print(f"Generating image with parameters: {generation_params}")
        
        # Generate the image
        try:
            result = generate_image(generation_params)
        except FalClientError as e:
            if "No user found for Key ID and Secret" in str(e):
                return jsonify({
                    'error': 'Invalid FAL API key',
                    'details': 'Please check your FAL API key in settings',
                    'type': 'invalid_fal_key'
                }), 401
            elif "rate limit" in str(e).lower():
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'details': 'Please try again later',
                    'type': 'rate_limit'
                }), 429
            else:
                return jsonify({
                    'error': 'FAL API error',
                    'details': str(e),
                    'type': 'fal_api_error'
                }), 400
        except Exception as e:
            return jsonify({
                'error': 'Failed to generate image',
                'details': str(e),
                'type': 'generation_error'
            }), 500
        
        if not result or 'image_url' not in result:
            return jsonify({
                'error': 'Invalid response from image generator',
                'details': 'The image generation service returned an invalid response',
                'type': 'invalid_response'
            }), 500
        
        # Save each generated image to database
        saved_images = []
        for image_url in result['image_url']:
            filename = image_url.split('/')[-1]
            base_name = os.path.splitext(filename)[0]
            
            try:
                print(f"Processing image: {filename}")
                
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
                
                print(f"Successfully processed image: {filename}")
            except FileNotFoundError as e:
                print(f"File not found error: {str(e)}")
                continue
            except Exception as e:
                print(f"Error processing image {filename}: {str(e)}")
                print(traceback.format_exc())
                continue
        
        if not saved_images:
            return jsonify({
                'error': 'No images were successfully processed',
                'details': 'Failed to save generated images',
                'type': 'processing_error'
            }), 500
        
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
        return jsonify({
            'error': str(e),
            'details': 'Please check your API keys in settings',
            'type': 'api_key_error'
        }), 400
    except Exception as e:
        print(f"Error in generate_image_route: {str(e)}")
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({
            'error': 'An unexpected error occurred',
            'details': str(e),
            'type': 'unexpected_error'
        }), 500
