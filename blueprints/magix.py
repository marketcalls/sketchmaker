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

magix_bp = Blueprint('magix', __name__)

def save_result_image(url):
    """Save the result image locally and return both URL and filename"""
    try:
        response = requests.get(url)
        response.raise_for_status()

        # Generate unique filename
        filename = f"magix_{uuid.uuid4()}.jpg"
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

@magix_bp.route('/magix')
@limiter.limit(get_rate_limit_string())
@login_required
def magix_page():
    """Render the image magix page"""
    return render_template('magix.html')

@magix_bp.route('/api/magix/generate', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def generate_magix():
    try:
        # Check if user can use Magix (credit-based limit)
        if not current_user.can_use_feature('magix'):
            subscription = current_user.get_subscription()
            plan_name = subscription.plan.display_name if subscription else 'No Plan'
            credits_remaining = current_user.get_credits_remaining()
            credit_cost = current_user.get_credit_cost('magix')
            return jsonify({
                'error': 'Insufficient credits for Magix editing',
                'details': f'You need {credit_cost} credit{"s" if credit_cost > 1 else ""} to use Magix. You have {credits_remaining} credits remaining. Your current plan is: {plan_name}',
                'type': 'insufficient_credits',
                'feature': 'magix',
                'credits_needed': credit_cost,
                'credits_remaining': credits_remaining,
                'plan': plan_name
            }), 403
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        required_fields = ['prompt', 'image_url']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        # Initialize FAL client
        client = init_fal_client()

        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    print(f"FAL Magix log: {log['message']}")

        # Prepare arguments for Magix (using Flux Kontext model)
        arguments = {
            "prompt": data['prompt'],
            "image_url": data['image_url'],
            "guidance_scale": data.get('guidance_scale', 3.5),
            "num_images": 1,
            "safety_tolerance": "2",
            "output_format": "jpeg"
        }

        # Add optional seed if provided
        if 'seed' in data and data['seed']:
            arguments['seed'] = int(data['seed'])
            
        # Add aspect ratio if provided
        if 'aspect_ratio' in data and data['aspect_ratio']:
            arguments['aspect_ratio'] = data['aspect_ratio']

        print(f"Calling Magix API with arguments: {arguments}")

        # Call the FAL API with Flux Kontext model for Magix functionality
        try:
            result = client.subscribe(
                "fal-ai/flux-pro/kontext",
                arguments=arguments,
                with_logs=True,
                on_queue_update=on_queue_update
            )

            if not result or 'images' not in result:
                raise ValueError("Invalid response from FAL API")

            # Save the generated image
            for img in result['images']:
                if not img.get('url'):
                    continue

                # Save the result image locally
                local_url, filename, width, height = save_result_image(img['url'])
                
                # Save to gallery
                try:
                    gallery_image = Image(
                        filename=filename,
                        prompt=data['prompt'],
                        art_style='magix',
                        width=width,
                        height=height,
                        user_id=current_user.id
                    )
                    db.session.add(gallery_image)
                    db.session.commit()
                    print(f"Successfully saved Magix image to gallery: {filename}")
                except Exception as e:
                    print(f"Error saving to gallery: {str(e)}")
                    db.session.rollback()
                    # Continue even if gallery save fails
                    gallery_image = None
                
                # Track Magix usage
                current_user.use_feature(
                    feature_type='magix',
                    amount=1,
                    extra_data={
                        'prompt': data['prompt'],
                        'image_url': local_url,
                        'original_image': data['image_url'],
                        'seed': result.get('seed'),
                        'guidance_scale': arguments['guidance_scale'],
                        'gallery_id': gallery_image.id
                    }
                )
                
                return jsonify({
                    'image_url': local_url,
                    'seed': result.get('seed'),
                    'prompt': result.get('prompt', data['prompt']),
                    'gallery_id': gallery_image.id if gallery_image else None
                })

            raise ValueError("No images were generated")

        except Exception as e:
            print(f"Error calling FAL API: {str(e)}")
            return jsonify({'error': f'Generation failed: {str(e)}'}), 500

    except Exception as e:
        print(f"Error in generate_magix: {str(e)}")
        return jsonify({'error': str(e)}), 500
