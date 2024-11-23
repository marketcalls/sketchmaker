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
                return jsonify({'image_url': local_url})

            raise ValueError("No images were generated")

        except Exception as e:
            print(f"Error calling FAL API: {str(e)}")
            return jsonify({'error': f'Generation failed: {str(e)}'}), 500

    except Exception as e:
        print(f"Error in generate_magix: {str(e)}")
        return jsonify({'error': str(e)}), 500
