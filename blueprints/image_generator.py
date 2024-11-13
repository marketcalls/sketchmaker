import uuid
import os
import requests
from flask import current_app
from .clients import init_fal_client
import io
import fal_client

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
    if model == "fal-ai/recraft-v3":
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
            if not img.get('url'):
                continue

            # Generate a unique filename
            base_filename = str(uuid.uuid4())
            
            # Get absolute paths
            static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
            images_dir = os.path.join(static_dir, 'images')
            
            # Ensure the images directory exists
            os.makedirs(images_dir, exist_ok=True)
            
            # Download image
            response = requests.get(img['url'])
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
        if "image_size" in arguments:
            response_data.update({
                "width": arguments["image_size"]["width"],
                "height": arguments["image_size"]["height"]
            })

        return response_data

    except Exception as e:
        print(f"Error in generate_image: {str(e)}")
        raise
