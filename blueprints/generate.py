from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from .image_generator import generate_image
from .prompt_generator import generate_prompt
from .clients import APIKeyError
from models import db, Image, APISettings
from extensions import limiter, get_rate_limit_string
import os
from PIL import Image as PILImage
import uuid
import traceback
from fal_client.client import FalClientError
from openai import AuthenticationError, OpenAIError
import anthropic
from google.api_core import exceptions as google_exceptions

generate_bp = Blueprint('generate', __name__)

def get_absolute_path(filename):
    """Get absolute path for a file in the static/images directory"""
    return os.path.join(current_app.root_path, 'static', 'images', filename)

@generate_bp.route('/generate/prompt', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def generate_prompt_route():
    try:
        # Check if request has JSON content
        if not request.is_json:
            return jsonify({
                'error': 'Invalid content type',
                'details': f'Request must be JSON, got: {request.content_type}',
                'type': 'invalid_content_type'
            }), 400
            
        data = request.get_json()
        if data is None:
            return jsonify({
                'error': 'Invalid JSON',
                'details': 'Could not parse JSON data',
                'type': 'invalid_json'
            }), 400
            
        if 'topic' not in data:
            return jsonify({
                'error': 'No topic provided',
                'details': 'Please provide a topic to generate a prompt',
                'type': 'missing_topic'
            }), 400
            
        if not data['topic'].strip():
            return jsonify({
                'error': 'Empty topic provided',
                'details': 'Topic cannot be empty',
                'type': 'empty_topic'
            }), 400

        # Check if system has required API keys
        api_settings = APISettings.get_settings()
        if not api_settings.has_required_keys():
            return jsonify({
                'error': 'System configuration incomplete',
                'details': 'API keys not configured by administrators',
                'type': 'missing_system_keys'
            }), 503

        try:
            # Pass the model to generate_prompt for model-specific prompt generation
            model = data.get('model')
            prompt = generate_prompt(data['topic'], model)
            
            return jsonify({'prompt': prompt})
            
        except (AuthenticationError, anthropic.AuthenticationError, google_exceptions.InvalidArgument) as e:
            # Handle authentication errors from all providers
            if isinstance(e, google_exceptions.InvalidArgument) and "API key not valid" not in str(e):
                raise  # Re-raise if it's not an API key error
            return jsonify({
                'error': 'Invalid API key',
                'details': 'Contact administrator - system API key is invalid',
                'type': 'invalid_key'
            }), 401
        except OpenAIError as e:
            error_message = str(e)
            if 'rate limit' in error_message.lower():
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'details': 'Please try again later',
                    'type': 'rate_limit'
                }), 429
            else:
                return jsonify({
                    'error': 'API error',
                    'details': error_message,
                    'type': 'api_error'
                }), 400

        except APIKeyError as e:
            return jsonify({
                'error': str(e),
                'details': 'Contact administrator - system API configuration issue',
                'type': 'api_key_error'
            }), 400
        except Exception as e:
            current_app.logger.error(f"Error generating prompt: {str(e)}\n{traceback.format_exc()}")
            return jsonify({
                'error': 'Failed to generate prompt',
                'details': 'An internal error occurred. Please try again.',
                'type': 'generation_error'
            }), 500

    except Exception as e:
        current_app.logger.error(f"Unexpected error in generate_prompt_route: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'error': 'An unexpected error occurred',
            'details': 'Please try again. If the problem persists, contact support.',
            'type': 'unexpected_error'
        }), 500

@generate_bp.route('/generate/image', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def generate_image_route():
    try:
        # Check if system has required API keys first (before credit check)
        api_settings = APISettings.get_settings()
        if not api_settings.has_required_keys():
            return jsonify({
                'error': 'System configuration incomplete',
                'details': 'API keys not configured by administrators',
                'type': 'missing_system_keys'
            }), 503

        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({
                'error': 'No prompt provided',
                'details': 'A prompt is required to generate an image',
                'type': 'missing_prompt'
            }), 400

        # Get number of images to calculate credit cost upfront
        num_images = data.get('num_images', 1)

        # Get all parameters from request
        prompt = data['prompt']
        art_style = data.get('artStyle')
        model = data.get('model', 'fal-ai/z-image/turbo/lora')

        # Add art style to prompt if provided and not using Recraft V3
        if art_style and model != 'fal-ai/recraft-v3':
            full_prompt = f"{prompt} in {art_style} style"
        else:
            full_prompt = prompt

        # Prepare generation parameters
        generation_params = {
            'prompt': full_prompt,
            'model': model,
            'num_images': num_images,
            'enable_safety_checker': data.get('enable_safety_checker', True),
            'seed': data.get('seed')
        }

        # Add model-specific parameters
        if model == 'fal-ai/recraft-v3':
            generation_params.update({
                'style': data.get('style', 'realistic_image'),
                'colors': data.get('colors', []),
                'style_id': data.get('style_id'),
                'image_size': data.get('image_size', {
                    'width': 1024,
                    'height': 1024
                })
            })
        elif model == 'fal-ai/flux-pro/v1.1-ultra':
            generation_params['aspect_ratio'] = data.get('aspect_ratio', '16:9')
        elif model == 'fal-ai/bytedance/seedream/v4.5/text-to-image':
            # Seedream V4.5 specific parameters
            preset = data.get('seedream_image_size_preset', 'landscape_16_9')

            # Handle image size based on preset
            if preset == 'custom':
                # Validate custom dimensions to prevent resource exhaustion
                MIN_DIMENSION = 256
                MAX_DIMENSION = 4096
                try:
                    width = int(data.get('seedream_width', 2048))
                    height = int(data.get('seedream_height', 1152))
                    # Clamp values to safe range
                    width = max(MIN_DIMENSION, min(MAX_DIMENSION, width))
                    height = max(MIN_DIMENSION, min(MAX_DIMENSION, height))
                except (ValueError, TypeError):
                    width, height = 2048, 1152  # Safe defaults
                generation_params['image_size'] = {
                    'width': width,
                    'height': height
                }
            elif preset == 'square_hd':
                generation_params['image_size'] = {'width': 2048, 'height': 2048}
            elif preset == 'square':
                generation_params['image_size'] = {'width': 1024, 'height': 1024}
            elif preset == 'portrait_3_4':
                generation_params['image_size'] = {'width': 1536, 'height': 2048}
            elif preset == 'portrait_9_16':
                generation_params['image_size'] = {'width': 1152, 'height': 2048}
            elif preset == 'landscape_4_3':
                generation_params['image_size'] = {'width': 2048, 'height': 1536}
            elif preset == 'landscape_16_9':
                generation_params['image_size'] = {'width': 2048, 'height': 1152}
            elif preset == 'auto':
                generation_params['image_size'] = {'width': 1024, 'height': 1024}
            elif preset == 'auto_2k':
                generation_params['image_size'] = {'width': 2048, 'height': 2048}
            elif preset == 'auto_4k':
                generation_params['image_size'] = {'width': 4096, 'height': 4096}
            else:  # fallback to landscape 16:9
                generation_params['image_size'] = {'width': 2048, 'height': 1152}

            # Max images parameter
            generation_params['max_images'] = int(data.get('seedream_max_images', 1))
            generation_params['num_images'] = int(data.get('seedream_max_images', 1))
        elif model == 'fal-ai/flux-pro/kontext/max/text-to-image':
            # Flux Kontext Max specific parameters
            generation_params.update({
                'aspect_ratio': data.get('aspect_ratio', '1:1'),
                'guidance_scale': float(data.get('guidance_scale', 3.5)),
                'num_images': int(data.get('num_images', 1)),
                'output_format': data.get('output_format', 'jpeg'),
                'safety_tolerance': data.get('safety_tolerance', '2')
            })
        elif model == 'fal-ai/nano-banana-pro':
            # Nano Banana Pro specific parameters
            generation_params.update({
                'aspect_ratio': data.get('aspect_ratio', '1:1'),
                'resolution': data.get('resolution', '1K'),
                'output_format': data.get('output_format', 'png'),
                'num_images': int(data.get('num_images', 1))
            })
        elif model == 'fal-ai/ideogram/v2':
            generation_params.update({
                'aspect_ratio': data.get('aspect_ratio') or '1:1',
                'expand_prompt': data.get('expand_prompt') if data.get('expand_prompt') is not None else True,
                'style': data.get('style') or 'auto',
                'negative_prompt': data.get('negative_prompt') or ''
            })
        elif model == 'fal-ai/ideogram/v2a':
            generation_params.update({
                'aspect_ratio': data.get('aspect_ratio') or '1:1',
                'expand_prompt': data.get('expand_prompt') if data.get('expand_prompt') is not None else True,
                'style': data.get('style') or 'auto',
                'negative_prompt': data.get('negative_prompt') or ''
            })
        elif model == 'fal-ai/imagen4/preview':
            generation_params.update({
                'aspect_ratio': data.get('aspect_ratio') or '1:1',
                'num_images': data.get('num_images', 1)
            })
            if data.get('negative_prompt'):
                generation_params['negative_prompt'] = data.get('negative_prompt')
        elif model == 'fal-ai/ideogram/v3':
            generation_params.update({
                'rendering_speed': data.get('rendering_speed') or 'BALANCED',
                'expand_prompt': data.get('expand_prompt') if data.get('expand_prompt') is not None else True,
                'num_images': data.get('num_images', 1),
                'image_size': data.get('image_size') or 'square_hd',
                'image_urls': []
            })
            if data.get('negative_prompt'):
                generation_params['negative_prompt'] = data.get('negative_prompt')
        elif model == 'fal-ai/flux-2-flex':
            # Flux 2 Flex specific parameters with hardcoded values
            generation_params.update({
                'image_size': data.get('image_size', 'landscape_4_3'),
                'guidance_scale': data.get('guidance_scale', 3.5),
                'output_format': data.get('output_format', 'jpeg'),
                # Hardcoded values
                'enable_prompt_expansion': True,
                'safety_tolerance': '2',
                'enable_safety_checker': True,
                'num_inference_steps': 28,
                'sync_mode': False
            })
        elif model == 'fal-ai/flux-2-pro':
            # Flux 2 Pro specific parameters
            generation_params.update({
                'image_size': data.get('image_size', 'landscape_4_3'),
                'safety_tolerance': '2',
                'enable_safety_checker': True,
                'output_format': data.get('output_format', 'jpeg')
            })
        elif model == 'fal-ai/flux-2-max':
            # Flux 2 Max specific parameters
            generation_params.update({
                'image_size': data.get('image_size', 'landscape_4_3'),
                'safety_tolerance': '2',
                'enable_safety_checker': True,
                'output_format': data.get('output_format', 'jpeg')
            })
        elif model == 'fal-ai/z-image/turbo/lora':
            # Z-Image specific parameters
            generation_params.update({
                'image_size': data.get('image_size', 'landscape_4_3'),
                'num_inference_steps': data.get('num_inference_steps', 8),
                'output_format': data.get('output_format', 'png'),
                'acceleration': data.get('acceleration', 'none'),
                'loras': data.get('loras', [])
            })
        else:
            generation_params['image_size'] = data.get('image_size', {
                'width': 1024,
                'height': 1024
            })

        if model in ['fal-ai/flux-lora', 'fal-ai/flux-realism']:
            generation_params.update({
                'num_inference_steps': data.get('num_inference_steps', 28),
                'guidance_scale': data.get('guidance_scale', 3.5)
            })

        if model == 'fal-ai/flux-lora' and data.get('loras'):
            generation_params['loras'] = data.get('loras')

        if model == 'fal-ai/flux-realism':
            generation_params['strength'] = data.get('strength', 1)

        print(f"Generating image with parameters: {generation_params}")

        # SECURITY FIX: Reserve credits BEFORE generating images
        # This prevents race condition attacks where users send concurrent requests
        subscription = current_user.get_subscription()
        try:
            with subscription.reserve_credits('images', num_images) as credits_cost:
                print(f"Reserved {credits_cost} credits for {num_images} image(s)")

                # Generate the image (credits already deducted, will be refunded if this fails)
                try:
                    result = generate_image(generation_params)
                except FalClientError as e:
                    if "No user found for Key ID and Secret" in str(e):
                        # Credits will be automatically refunded
                        return jsonify({
                            'error': 'Invalid FAL API key',
                            'details': 'Contact administrator - FAL API key issue',
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
                    # Credits will be automatically refunded
                    return jsonify({
                        'error': 'Failed to generate image',
                        'details': str(e),
                        'type': 'generation_error'
                    }), 500

                if not result or 'image_url' not in result:
                    # Credits will be automatically refunded
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
                    original_ext = os.path.splitext(filename)[1].lower()

                    try:
                        print(f"Processing image: {filename}")

                        # Load the original image
                        original_filepath = get_absolute_path(filename)
                        if not os.path.exists(original_filepath):
                            print(f"Warning: Original file not found: {original_filepath}")
                            continue

                        img = PILImage.open(original_filepath)

                        # Always save a PNG version first
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

                        # Save image record to database with PNG as primary filename
                        new_image = Image(
                            filename=png_filename,  # Always store PNG as the primary filename
                            prompt=prompt,
                            art_style=art_style,
                            width=result.get('width'),
                            height=result.get('height'),
                            user_id=current_user.id
                        )
                        db.session.add(new_image)

                        saved_images.append({
                            'png_url': f'/static/images/{png_filename}',
                            'webp_url': f'/static/images/{webp_filename}',
                            'jpeg_url': f'/static/images/{jpeg_filename}',
                            'image_url': f'/static/images/{png_filename}'  # Keep image_url for backward compatibility
                        })

                        print(f"Successfully processed image: {filename}")

                        # Clean up original file if it's not PNG
                        if original_ext != '.png' and os.path.exists(original_filepath):
                            os.remove(original_filepath)

                    except FileNotFoundError as e:
                        print(f"File not found error: {str(e)}")
                        continue
                    except Exception as e:
                        print(f"Error processing image {filename}: {str(e)}")
                        print(traceback.format_exc())
                        continue

                if not saved_images:
                    # Credits will be automatically refunded
                    return jsonify({
                        'error': 'No images were successfully processed',
                        'details': 'Failed to save generated images',
                        'type': 'processing_error'
                    }), 500

                db.session.commit()

                # Log usage history for audit trail
                images_generated = len(saved_images)
                if images_generated > 0:
                    current_user.log_usage(
                        action='images',
                        credits_used=credits_cost,
                        extra_data={
                            'model': model,
                            'prompt': prompt,
                            'art_style': art_style,
                            'images_generated': images_generated
                        }
                    )

                response_data = {
                    'images': saved_images,
                    'prompt': prompt,
                    'art_style': art_style,
                    'model': model,
                    'credits_remaining': current_user.get_credits_remaining()
                }

                # Add dimension info if available
                if 'width' in result and 'height' in result:
                    response_data.update({
                        'width': result['width'],
                        'height': result['height']
                    })

                return jsonify(response_data)

        except ValueError as e:
            # Insufficient credits or other validation error
            error_msg = str(e)
            if "Insufficient credits" in error_msg:
                subscription = current_user.get_subscription()
                plan_name = subscription.plan.display_name if subscription else 'No Plan'
                credits_remaining = current_user.get_credits_remaining()
                credit_cost = current_user.get_credit_cost('images')
                return jsonify({
                    'error': 'Insufficient credits for image generation',
                    'details': f'You need {credit_cost * num_images} credit{"s" if (credit_cost * num_images) > 1 else ""} to generate {num_images} image{"s" if num_images > 1 else ""}. You have {credits_remaining} credits remaining. Your current plan is: {plan_name}',
                    'type': 'insufficient_credits',
                    'feature': 'images',
                    'credits_needed': credit_cost * num_images,
                    'credits_remaining': credits_remaining,
                    'plan': plan_name
                }), 403
            else:
                return jsonify({
                    'error': 'Credit validation failed',
                    'details': error_msg,
                    'type': 'validation_error'
                }), 400
    except APIKeyError as e:
        return jsonify({
            'error': 'API configuration issue',
            'details': 'Contact administrator - system API configuration issue',
            'type': 'api_key_error'
        }), 400
    except Exception as e:
        current_app.logger.error(f"Error in generate_image_route: {str(e)}\n{traceback.format_exc()}")
        db.session.rollback()
        return jsonify({
            'error': 'An unexpected error occurred',
            'details': 'Please try again. If the problem persists, contact support.',
            'type': 'unexpected_error'
        }), 500
