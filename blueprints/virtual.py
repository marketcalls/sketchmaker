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

virtual_bp = Blueprint('virtual', __name__)

def save_result_image(url):
    """Save the result image locally and return both URL and filename"""
    try:
        response = requests.get(url)
        response.raise_for_status()

        # Generate unique filename
        filename = f"virtual_{uuid.uuid4()}.jpg"
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

@virtual_bp.route('/virtual')
@limiter.limit(get_rate_limit_string())
@login_required
def virtual_page():
    """Render the Virtual Try-On page"""
    return render_template('virtual.html')

@virtual_bp.route('/api/virtual/generate', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def generate_virtual():
    try:
        # Check if user can use Virtual Try-On (credit-based limit)
        if not current_user.can_use_feature('virtual'):
            subscription = current_user.get_subscription()
            plan_name = subscription.plan.display_name if subscription else 'No Plan'
            credits_remaining = current_user.get_credits_remaining()
            credit_cost = current_user.get_credit_cost('virtual')
            return jsonify({
                'error': 'Insufficient credits for Virtual Try-On',
                'details': f'You need {credit_cost} credit{"s" if credit_cost > 1 else ""} to use Virtual Try-On. You have {credits_remaining} credits remaining.',
                'type': 'insufficient_credits',
                'feature': 'virtual',
                'credits_needed': credit_cost,
                'credits_remaining': credits_remaining,
                'plan': plan_name
            }), 403
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        prompt = data.get('prompt', '')
        person_image = data.get('person_image')
        dress_image = data.get('dress_image')
        use_dress_background = data.get('use_dress_background', False)
        
        if not person_image:
            return jsonify({'error': 'Person image is required'}), 400
        if not dress_image:
            return jsonify({'error': 'Dress image is required'}), 400
        
        # Initialize FAL client
        client = init_fal_client()

        # Progress tracking
        progress_updates = []
        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    progress_updates.append(log['message'])
                    print(f"Virtual Try-On Progress: {log['message']}")

        # Optimize images before sending to FAL
        optimized_person, person_metadata = ImageOptimizer.optimize_image(person_image, service='virtual')
        optimized_dress, dress_metadata = ImageOptimizer.optimize_image(dress_image, service='virtual')
        
        if person_metadata.get('optimization_failed'):
            print(f"Warning: Person image optimization failed, using original")
        else:
            print(f"Person image optimized: {person_metadata.get('compression_ratio', 100)}% of original size")
            
        if dress_metadata.get('optimization_failed'):
            print(f"Warning: Dress image optimization failed, using original")
        else:
            print(f"Dress image optimized: {dress_metadata.get('compression_ratio', 100)}% of original size")

        # Prepare arguments for the virtual try-on API
        # Construct a comprehensive prompt
        base_prompt = f"Make the person wear the dress from the second image"
        
        if use_dress_background:
            base_prompt += " and place them in the same background as the dress image"
        
        if prompt:
            base_prompt += f". {prompt}"
        
        arguments = {
            "prompt": base_prompt,
            "image_urls": [optimized_person, optimized_dress],
            "num_images": data.get('num_images', 1)
        }

        # Advanced parameters
        if 'temperature' in data:
            arguments['temperature'] = float(data['temperature'])
        if 'seed' in data and data['seed']:
            arguments['seed'] = int(data['seed'])

        print(f"Calling Virtual Try-On API with arguments: {arguments}")

        # Call the FAL API (using the Nano Banana edit endpoint which can handle virtual try-on)
        try:
            result = client.subscribe(
                "fal-ai/nano-banana/edit",
                arguments=arguments,
                with_logs=True,
                on_queue_update=on_queue_update
            )

            if not result:
                raise ValueError("Invalid response from Virtual Try-On API")

            # Process results
            results_data = {
                'mode': 'virtual',
                'progress': progress_updates,
                'images': [],
                'metadata': {}
            }

            # Handle the response format
            if 'images' in result:
                for img in result['images']:
                    if img.get('url'):
                        local_url, filename, width, height = save_result_image(img['url'])
                        
                        # Save to gallery
                        try:
                            gallery_image = Image(
                                filename=filename,
                                prompt=base_prompt,
                                art_style='virtual_tryon',
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
                            prompt=base_prompt,
                            art_style='dress_virtual_tryon',
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
                'prompt': result.get('prompt', base_prompt),
                'mode': 'virtual',
                'timestamp': str(uuid.uuid4())
            }

            # Track usage
            current_user.use_feature(
                feature_type='virtual',
                amount=len(results_data['images']),
                extra_data={
                    'prompt': base_prompt,
                    'images_generated': len(results_data['images'])
                }
            )
            
            return jsonify(results_data)

        except Exception as e:
            print(f"Error calling Virtual Try-On API: {str(e)}")
            return jsonify({'error': f'Generation failed: {str(e)}'}), 500

    except Exception as e:
        print(f"Error in generate_virtual: {str(e)}")
        return jsonify({'error': str(e)}), 500

@virtual_bp.route('/api/virtual/history/<int:user_id>')
@login_required
def get_virtual_history(user_id):
    """Get user's Virtual Try-On history"""
    if current_user.id != user_id and not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        images = Image.query.filter_by(user_id=user_id)\
                           .filter(Image.art_style == 'virtual_tryon')\
                           .order_by(Image.created_at.desc())\
                           .limit(50)\
                           .all()
        
        history = []
        for img in images:
            history.append({
                'id': img.id,
                'url': f'/static/images/{img.filename}',
                'prompt': img.prompt,
                'created_at': img.created_at.isoformat()
            })
        
        return jsonify({'history': history})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500