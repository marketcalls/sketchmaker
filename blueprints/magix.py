from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from .clients import init_fal_client
import fal_client
import os
import uuid
import requests
from extensions import limiter, get_rate_limit_string
from models import db
from models.content import Image
from PIL import Image as PILImage
import json
import base64
from io import BytesIO
from services.image_optimizer import ImageOptimizer

magix_bp = Blueprint('magix', __name__)

def save_result_image(url):
    """Save the result image locally and return both URL and filename"""
    try:
        response = requests.get(url)
        response.raise_for_status()

        # Generate unique filename
        filename = f"nano_{uuid.uuid4()}.jpg"
        filepath = os.path.join(current_app.root_path, 'static', 'images', filename)

        # Save the image
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        # Get image dimensions
        width, height = None, None
        try:
            with PILImage.open(filepath) as img:
                width, height = img.size
        except Exception as e:
            print(f"Error getting image dimensions: {str(e)}")

        return f'/static/images/{filename}', filename, width, height
    except Exception as e:
        print(f"Error saving result image: {str(e)}")
        raise

def image_to_base64(image_path):
    """Convert image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

@magix_bp.route('/magix')
@limiter.limit(get_rate_limit_string())
@login_required
def magix_page():
    """Render the Nano Studio page"""
    return render_template('magix.html')

@magix_bp.route('/api/magix/generate', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def generate_magix():
    try:
        # Check if user can use Nano Studio (credit-based limit)
        if not current_user.can_use_feature('magix'):
            subscription = current_user.get_subscription()
            plan_name = subscription.plan.display_name if subscription else 'No Plan'
            credits_remaining = current_user.get_credits_remaining()
            credit_cost = current_user.get_credit_cost('magix')
            return jsonify({
                'error': 'Insufficient credits for Nano Studio',
                'details': f'You need {credit_cost} credit{"s" if credit_cost > 1 else ""} to use Nano Studio. You have {credits_remaining} credits remaining.',
                'type': 'insufficient_credits',
                'feature': 'magix',
                'credits_needed': credit_cost,
                'credits_remaining': credits_remaining,
                'plan': plan_name
            }), 403
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        mode = data.get('mode', 'edit')
        prompt = data.get('prompt', '')
        
        # Initialize FAL client
        client = init_fal_client()

        # Progress tracking
        progress_updates = []
        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    progress_updates.append(log['message'])
                    print(f"Nano Studio Progress: {log['message']}")

        # Prepare base arguments for Nano Banana Pro
        arguments = {
            "prompt": prompt,
            "num_images": data.get('num_images', 1),
            "aspect_ratio": data.get('aspect_ratio', 'auto'),
            "output_format": data.get('output_format', 'png'),
            "resolution": data.get('resolution', '1K')  # Supports: 1K, 2K, 4K
        }

        # Add image URLs if provided (for editing modes)
        # Optimize images before sending to FAL
        if 'image_urls' in data:
            optimized_urls = []
            for img_url in data['image_urls']:
                optimized_img, metadata = ImageOptimizer.optimize_image(img_url, service='magix')
                optimized_urls.append(optimized_img)
                if metadata.get('optimization_failed'):
                    print(f"Warning: Image optimization failed, using original")
                else:
                    print(f"Image optimized: {metadata.get('compression_ratio', 100)}% of original size")
            arguments['image_urls'] = optimized_urls
        elif 'image_url' in data:
            optimized_img, metadata = ImageOptimizer.optimize_image(data['image_url'], service='magix')
            arguments['image_urls'] = [optimized_img]
            if not metadata.get('optimization_failed'):
                print(f"Image optimized: {metadata.get('compression_ratio', 100)}% of original size")

        # Mode-specific configurations
        if mode == 'director':
            # Sequential editing with version control
            arguments['prompt'] = f"Step by step edit: {prompt}"
            
        elif mode == '3d_vision':
            # Generate multiple views
            arguments['prompt'] = f"Show multiple angles and views: {prompt}"
            
        elif mode == 'story':
            # Comic strip generation
            arguments['prompt'] = f"Create a 4 panel comic strip: {prompt}"
            arguments['num_images'] = 4
            
        elif mode == 'style_transfer':
            # Artistic transformations
            style = data.get('style', 'anime')
            arguments['prompt'] = f"Convert to {style} style: {prompt}"
            
        elif mode == 'restoration':
            # Fix and enhance
            arguments['prompt'] = f"Restore and enhance this image: {prompt}"
            
        elif mode == 'professional':
            # Content creation
            template = data.get('template', 'youtube_thumbnail')
            arguments['prompt'] = f"Create a {template}: {prompt}"
            
        elif mode == 'physics':
            # Physics simulations
            effect = data.get('effect', 'reflection')
            arguments['prompt'] = f"Add realistic {effect}: {prompt}"

        # Advanced parameters
        if 'temperature' in data:
            arguments['temperature'] = float(data['temperature'])
        if 'seed' in data and data['seed']:
            arguments['seed'] = int(data['seed'])

        print(f"Calling Nano Banana Pro API with mode: {mode}, arguments: {arguments}")

        # Call the Google Gemini 2.5 Flash Image (Nano Banana Pro) API
        try:
            result = client.subscribe(
                "fal-ai/nano-banana-pro/edit",
                arguments=arguments,
                with_logs=True,
                on_queue_update=on_queue_update
            )

            if not result:
                raise ValueError("Invalid response from Nano Banana Pro API")

            # Process results based on mode
            results_data = {
                'mode': mode,
                'progress': progress_updates,
                'images': [],
                'metadata': {}
            }

            # Handle the response format from Nano Banana API
            # Response format: {"images": [{"url": "..."}], "description": "..."}
            if 'images' in result:
                for img in result['images']:
                    if img.get('url'):
                        local_url, filename, width, height = save_result_image(img['url'])
                        
                        # Save to gallery
                        try:
                            gallery_image = Image(
                                filename=filename,
                                prompt=prompt,
                                art_style=f'nano_{mode}',
                                width=width,
                                height=height,
                                user_id=current_user.id
                            )
                            db.session.add(gallery_image)
                            db.session.commit()
                            
                            results_data['images'].append({
                                'url': local_url,
                                'gallery_id': gallery_image.id,
                                'width': width,
                                'height': height
                            })
                        except Exception as e:
                            print(f"Error saving to gallery: {str(e)}")
                            db.session.rollback()
                            results_data['images'].append({
                                'url': local_url,
                                'width': width,
                                'height': height
                            })
            elif 'image' in result:
                # Single image result (fallback)
                if result['image'].get('url'):
                    local_url, filename, width, height = save_result_image(result['image']['url'])
                    
                    try:
                        gallery_image = Image(
                            filename=filename,
                            prompt=prompt,
                            art_style=f'nano_{mode}',
                            width=width,
                            height=height,
                            user_id=current_user.id
                        )
                        db.session.add(gallery_image)
                        db.session.commit()
                        
                        results_data['images'].append({
                            'url': local_url,
                            'gallery_id': gallery_image.id,
                            'width': width,
                            'height': height
                        })
                    except Exception as e:
                        print(f"Error saving to gallery: {str(e)}")
                        db.session.rollback()
                        results_data['images'].append({
                            'url': local_url,
                            'width': width,
                            'height': height
                        })
            
            # Add description if available
            if 'description' in result:
                results_data['metadata']['description'] = result['description']

            # Add metadata
            results_data['metadata'] = {
                'seed': result.get('seed'),
                'prompt': result.get('prompt', prompt),
                'mode': mode,
                'timestamp': str(uuid.uuid4())
            }

            # Track usage
            current_user.use_feature(
                feature_type='magix',
                amount=len(results_data['images']),
                extra_data={
                    'mode': mode,
                    'prompt': prompt,
                    'images_generated': len(results_data['images'])
                }
            )
            
            return jsonify(results_data)

        except Exception as e:
            print(f"Error calling Nano Banana Pro API: {str(e)}")
            return jsonify({'error': f'Generation failed: {str(e)}'}), 500

    except Exception as e:
        print(f"Error in generate_magix: {str(e)}")
        return jsonify({'error': str(e)}), 500


@magix_bp.route('/api/magix/history/<int:user_id>')
@login_required
def get_history(user_id):
    """Get user's Nano Studio history"""
    if current_user.id != user_id and not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        images = Image.query.filter_by(user_id=user_id)\
                           .filter(Image.art_style.like('nano_%'))\
                           .order_by(Image.created_at.desc())\
                           .limit(50)\
                           .all()
        
        history = []
        for img in images:
            history.append({
                'id': img.id,
                'url': f'/static/images/{img.filename}',
                'prompt': img.prompt,
                'mode': img.art_style.replace('nano_', ''),
                'created_at': img.created_at.isoformat()
            })
        
        return jsonify({'history': history})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500