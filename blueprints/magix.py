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

        # Base instruction for facial preservation
        face_preserve = "CRITICAL: Preserve and retain 100% of the original facial features, face shape, eyes, nose, mouth, and exact likeness of the person."

        # Mode-specific configurations - AI Photography Focus
        if mode == 'studio_portrait':
            arguments['prompt'] = f"Create a professional studio portrait with clean background, soft diffused lighting, polished and refined look. {face_preserve} {prompt}"

        elif mode == 'environmental':
            arguments['prompt'] = f"Create an environmental portrait with the person in a meaningful real-world setting that tells their story. Natural lighting, contextual background. {face_preserve} {prompt}"

        elif mode == 'lifestyle':
            arguments['prompt'] = f"Create a lifestyle portrait capturing natural, candid everyday moments. Relaxed pose, authentic expression, warm natural lighting. {face_preserve} {prompt}"

        elif mode == 'fashion_editorial':
            arguments['prompt'] = f"Create a high-fashion editorial portrait with dramatic lighting, magazine-quality styling, bold poses, and artistic composition. {face_preserve} {prompt}"

        elif mode == 'cinematic':
            arguments['prompt'] = f"Create a cinematic portrait with movie-scene lighting, shallow depth of field, moody atmospheric tones, and dramatic composition. {face_preserve} {prompt}"

        elif mode == 'corporate_headshot':
            background = data.get('background', 'neutral')
            arguments['prompt'] = f"Create a professional corporate headshot with {background} background. Confident professional posture, approachable expression, executive presence, LinkedIn-ready. {face_preserve} {prompt}"

        elif mode == 'street_portrait':
            arguments['prompt'] = f"Create an urban street portrait with authentic city background, raw energy, natural lighting, and genuine character. {face_preserve} {prompt}"

        elif mode == 'low_key':
            arguments['prompt'] = f"Create a dramatic low-key portrait with dark background, deep shadows, high contrast, and moody dramatic lighting. {face_preserve} {prompt}"

        elif mode == 'high_key':
            arguments['prompt'] = f"Create a bright high-key portrait with clean white background, soft airy lighting, minimal shadows, and fresh uplifting mood. {face_preserve} {prompt}"

        elif mode == 'black_white':
            arguments['prompt'] = f"Create a timeless black and white portrait with rich tonal range, emotional depth, beautiful texture and contrast. {face_preserve} {prompt}"

        elif mode == 'beauty_closeup':
            arguments['prompt'] = f"Create a beauty close-up portrait emphasizing flawless skin, makeup details, perfect symmetry, and refined features. {face_preserve} {prompt}"

        elif mode == 'athletic':
            arguments['prompt'] = f"Create an athletic action portrait with powerful stance, dynamic energy, strength and motion conveyed through pose and lighting. {face_preserve} {prompt}"

        elif mode == 'creative_color':
            arguments['prompt'] = f"Create a creative color portrait with bold gel lighting, neon tones, artistic color grading, and vibrant artistic expression. {face_preserve} {prompt}"

        elif mode == 'vintage_retro':
            arguments['prompt'] = f"Create a vintage retro portrait with film grain, nostalgic color tones, classic camera aesthetics, and timeless charm. {face_preserve} {prompt}"

        elif mode == 'minimalist':
            arguments['prompt'] = f"Create a minimalist portrait with simple elegant pose, generous negative space, calm serene presence, and refined simplicity. {face_preserve} {prompt}"

        elif mode == 'cultural':
            arguments['prompt'] = f"Create a cultural portrait celebrating heritage with traditional ethnic wear, authentic styling, and respectful representation. {face_preserve} {prompt}"

        elif mode == 'conceptual':
            arguments['prompt'] = f"Create a conceptual portrait with symbolic elements, surreal artistic touches, and meaningful visual storytelling. {face_preserve} {prompt}"

        elif mode == 'influencer':
            aesthetic = data.get('aesthetic', 'glamorous')
            arguments['prompt'] = f"Create a social media influencer portrait with {aesthetic} aesthetic, trendy pose, lifestyle framing, Instagram-ready appeal. {face_preserve} {prompt}"

        elif mode == 'luxury':
            arguments['prompt'] = f"Create a luxury elite portrait with rich premium lighting, high-end fashion styling, powerful sophisticated presence. {face_preserve} {prompt}"

        elif mode == 'avatar':
            style = data.get('style', 'semi_realistic')
            arguments['prompt'] = f"Create a stylized avatar portrait with {style.replace('_', ' ')} artistic transformation while maintaining recognizable likeness. {face_preserve} {prompt}"

        elif mode == 'founder_headshot':
            vibe = data.get('vibe', 'visionary')
            arguments['prompt'] = f"Create a startup founder headshot with {vibe} leadership presence, modern tech aesthetic, pitch-deck ready, approachable yet authoritative. {face_preserve} {prompt}"

        elif mode == 'restoration':
            arguments['prompt'] = f"Restore and enhance this image, fix imperfections, improve quality. {face_preserve} {prompt}"

        elif mode == 'style_transfer':
            style = data.get('style', 'artistic')
            arguments['prompt'] = f"Transform to {style} artistic style while preserving identity. {face_preserve} {prompt}"

        # Advanced parameters
        if 'temperature' in data:
            arguments['temperature'] = float(data['temperature'])
        if 'seed' in data and data['seed']:
            arguments['seed'] = int(data['seed'])

        print(f"Calling Nano Banana Pro API with mode: {mode}, arguments: {arguments}")

        # Call Google's Nano Banana Pro (Nano Banana 2) API - State-of-the-art image generation and editing
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
            return jsonify({'error': 'Generation failed. Please try again.'}), 500

    except Exception as e:
        print(f"Error in generate_magix: {str(e)}")
        return jsonify({'error': 'An error occurred. Please try again.'}), 500


@magix_bp.route('/api/magix/history/<int:user_id>')
@limiter.limit(get_rate_limit_string())
@login_required
def get_history(user_id):
    """Get user's Nano Studio history"""
    # Use is_admin() method instead of is_admin attribute for proper authorization check
    if current_user.id != user_id and not current_user.is_admin():
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
        print(f"Error fetching history: {str(e)}")
        return jsonify({'error': 'Failed to fetch history'}), 500