from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from .clients import init_fal_client
import fal_client
import base64
import os
import uuid
import requests
from PIL import Image
import io
from extensions import limiter, get_rate_limit_string

magix_bp = Blueprint('magix', __name__)

def save_result_image(url):
    """Save the result image locally"""
    try:
        response = requests.get(url)
        response.raise_for_status()

        # Generate unique filename
        filename = f"magix_{uuid.uuid4()}.jpg"
        filepath = os.path.join(current_app.root_path, 'static', 'images', filename)

        # Save the image
        with open(filepath, 'wb') as f:
            f.write(response.content)

        return f'/static/images/{filename}'
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

        required_fields = ['prompt', 'image_data', 'mask_data']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        # Initialize FAL client
        client = init_fal_client()

        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    print(f"FAL generation log: {log['message']}")

        # Prepare arguments for the model
        # Note: The image_data and mask_data should already be complete data URLs
        # e.g., "data:image/png;base64,..."
        arguments = {
            "prompt": data['prompt'],
            "num_images": 1,
            "safety_tolerance": "2",
            "output_format": "jpeg",
            "image_url": data['image_data'],  # Pass the complete data URL
            "mask_url": data['mask_data']     # Pass the complete data URL
        }

        print(f"Calling FAL API with arguments: {arguments}")

        # Call the FAL API
        try:
            result = client.subscribe(
                "fal-ai/flux-pro/v1/fill",
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
                local_url = save_result_image(img['url'])
                
                # Track Magix usage
                current_user.use_feature(
                    feature_type='magix',
                    amount=1,
                    extra_data={
                        'prompt': data['prompt'],
                        'image_url': local_url
                    }
                )
                
                return jsonify({'image_url': local_url})

            raise ValueError("No images were generated")

        except Exception as e:
            print(f"Error calling FAL API: {str(e)}")
            return jsonify({'error': f'Generation failed: {str(e)}'}), 500

    except Exception as e:
        print(f"Error in generate_magix: {str(e)}")
        return jsonify({'error': str(e)}), 500
