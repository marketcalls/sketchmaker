import uuid
import os
import requests
from flask import current_app, jsonify, Blueprint
from flask_login import login_required, current_user
from .clients import init_fal_client
import io
import fal_client
from models import db, TrainingHistory

image_generator_bp = Blueprint('image_generator', __name__)

@image_generator_bp.route('/api/lora-data')
@login_required
def get_lora_data():
    """Get LoRA data from training history for current user"""
    try:
        # Query training history using Flask-SQLAlchemy, filtered by current user
        trainings = TrainingHistory.query.filter_by(
            user_id=current_user.id,
            status='completed'
        ).filter(
            TrainingHistory.weights_url.isnot(None)
        ).order_by(
            TrainingHistory.created_at.desc()
        ).all()

        lora_data = [{
            "trigger_word": training.trigger_word,
            "weights_url": training.weights_url
        } for training in trainings]

        return jsonify({"lora_data": lora_data})
    except Exception as e:
        print(f"Error fetching LoRA data: {str(e)}")
        return jsonify({"error": "Failed to fetch LoRA data"}), 500

def get_model_arguments(model, data):
    """Get model-specific arguments based on the model type"""
    print("\n=== Model Arguments Generation ===")
    print(f"Preparing arguments for model: {model}")

    base_args = {
        "prompt": data["prompt"],
        "num_images": data.get("num_images", 1),
        "enable_safety_checker": data.get("enable_safety_checker", True),
        "seed": data.get("seed", 2345)
    }

    # Define model-specific arguments
    if model == "fal-ai/nano-banana-pro":
        model_args = {
            "aspect_ratio": data.get("aspect_ratio", "1:1"),
            "resolution": data.get("resolution", "1K"),
            "output_format": data.get("output_format", "png"),
            "num_images": data.get("num_images", 1)
        }
    elif model == "fal-ai/recraft-v3":
        model_args = {
            "image_size": data.get("image_size", {"width": 1024, "height": 1024}),
            "style": data.get("style", "realistic_image"),
            "colors": data.get("colors", []),
            "style_id": data.get("style_id")
        }
    elif model == "fal-ai/flux-pro/v1.1-ultra":
        model_args = {
            "aspect_ratio": data.get("aspect_ratio", "16:9"),
            "output_format": "jpeg",
            "safety_tolerance": "2"
        }
    elif model == "fal-ai/bytedance/seedream/v4/text-to-image":
        model_args = {
            "image_size": data.get("image_size", {"width": 1024, "height": 1024}),
            "max_images": data.get("max_images", 1),
            "num_images": data.get("num_images", 1)
        }
    elif model == "fal-ai/flux-pro/kontext/max/text-to-image":
        model_args = {
            "aspect_ratio": data.get("aspect_ratio", "1:1"),
            "guidance_scale": float(data.get("guidance_scale", 3.5)),
            "num_images": int(data.get("num_images", 1)),
            "output_format": data.get("output_format", "jpeg"),
            "safety_tolerance": data.get("safety_tolerance", "2")
        }
    elif model == "fal-ai/ideogram/v2":
        model_args = {
            "aspect_ratio": data.get("aspect_ratio") or "1:1",
            "expand_prompt": data.get("expand_prompt") if data.get("expand_prompt") is not None else True,
            "style": data.get("style") or "auto",
            "negative_prompt": data.get("negative_prompt") or ""
        }
    elif model == "fal-ai/ideogram/v2a":
        model_args = {
            "aspect_ratio": data.get("aspect_ratio") or "1:1",
            "expand_prompt": data.get("expand_prompt") if data.get("expand_prompt") is not None else True,
            "style": data.get("style") or "auto",
            "negative_prompt": data.get("negative_prompt") or ""
        }
    elif model == "fal-ai/imagen4/preview":
        model_args = {
            "aspect_ratio": data.get("aspect_ratio") or "1:1",
            "num_images": data.get("num_images", 1)
        }
        # Add negative prompt if provided
        if data.get("negative_prompt"):
            model_args["negative_prompt"] = data.get("negative_prompt")
    elif model == "fal-ai/ideogram/v3":
        model_args = {
            "rendering_speed": data.get("rendering_speed") or "BALANCED",
            "expand_prompt": data.get("expand_prompt") if data.get("expand_prompt") is not None else True,
            "num_images": data.get("num_images", 1),
            "image_size": data.get("image_size") or "square_hd"
        }
        # Add negative prompt if provided
        if data.get("negative_prompt"):
            model_args["negative_prompt"] = data.get("negative_prompt")
        # Add image_urls parameter (empty array as per API spec)
        model_args["image_urls"] = []
    else:
        # All other models require image_size
        if not isinstance(data.get("image_size"), dict) or 'width' not in data["image_size"] or 'height' not in data["image_size"]:
            raise ValueError("Invalid image size format")
        
        model_args = {
            "image_size": data["image_size"]
        }

        # Add additional parameters based on model
        if model == "fal-ai/flux-pro/v1.1":
            model_args["safety_tolerance"] = "2"
        elif model == "fal-ai/flux-lora":
            model_args.update({
                "num_inference_steps": data.get("num_inference_steps", 28),
                "guidance_scale": data.get("guidance_scale", 3.5),
                "output_format": "jpeg",
                "loras": data.get("loras", [])
            })
        elif model == "fal-ai/flux/dev":
            model_args.update({
                "num_inference_steps": 28,
                "guidance_scale": 3.5
            })
        elif model == "fal-ai/flux-realism":
            model_args.update({
                "num_inference_steps": data.get("num_inference_steps", 28),
                "guidance_scale": data.get("guidance_scale", 3.5),
                "strength": data.get("strength", 1),
                "output_format": "jpeg"
            })

    # Merge base arguments with model-specific arguments
    final_args = {**base_args, **model_args}
    print(f"Model-specific arguments: {model_args}")
    print(f"Final arguments: {final_args}")
    print("==============================\n")

    return final_args

def generate_image(data):
    """Generate image using FAL API with user's API key"""
    try:
        # Validate inputs
        if not data.get("prompt"):
            raise ValueError("Prompt cannot be empty")
        
        model = data.get("model", "fal-ai/flux-pro/v1.1")
        print("\n=== Image Generation Start ===")
        print(f"Requested Model: {model}")
        print(f"Input data: {data}")

        # Initialize FAL client and get instance
        client = init_fal_client()

        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    print(f"FAL generation log: {log['message']}")

        # Get model-specific arguments
        arguments = get_model_arguments(model, data)

        print("\n=== Calling FAL API ===")
        print(f"Using Model: {model}")
        print(f"With Arguments: {arguments}")
        
        # Generate image using FAL API
        result = client.subscribe(
            model,
            arguments=arguments,
            with_logs=True,
            on_queue_update=on_queue_update
        )
        
        print(f"Received response from FAL: {result}")
        print("=======================\n")
        
        if not result or 'images' not in result:
            raise ValueError("Invalid response from FAL API")

        image_urls = []
        for img in result['images']:
            # Handle different response formats
            if isinstance(img, dict):
                image_url = img.get('url')
            elif isinstance(img, str):
                image_url = img
            else:
                print(f"Unexpected image format: {type(img)} - {img}")
                continue
                
            if not image_url:
                continue

            # Generate a unique filename
            base_filename = str(uuid.uuid4())
            
            # Get absolute paths
            static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
            images_dir = os.path.join(static_dir, 'images')
            
            # Ensure the images directory exists
            os.makedirs(images_dir, exist_ok=True)
            
            # Download image
            response = requests.get(image_url)
            response.raise_for_status()
            
            # Load image into memory
            image_data = io.BytesIO(response.content)
            
            # Save image
            extension = 'png'
            if arguments.get('output_format') == 'jpeg':
                extension = 'jpg'
            
            filename = f"{base_filename}.{extension}"
            filepath = os.path.join(images_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(image_data.getvalue())
            
            print(f"Saved image to: {filepath}")
            
            # Verify file was saved
            if not os.path.exists(filepath):
                print(f"Warning: Failed to save image to {filepath}")
                continue
                
            image_urls.append(f"/static/images/{filename}")

        if not image_urls:
            raise ValueError("No images were successfully downloaded")

        response_data = {
            "image_url": image_urls,
        }

        # Add dimension info for models that use it
        if "image_size" in arguments and isinstance(arguments["image_size"], dict):
            # Only add width/height if image_size is a dictionary (not for Ideogram V3 which uses strings)
            response_data.update({
                "width": arguments["image_size"]["width"],
                "height": arguments["image_size"]["height"]
            })

        return response_data

    except Exception as e:
        print(f"Error in generate_image: {str(e)}")
        raise
