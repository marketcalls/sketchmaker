from openai import OpenAI
from flask import current_app, g
from flask_login import current_user
import fal_client

class APIKeyError(Exception):
    """Exception raised when required API keys are missing"""
    pass

def get_openai_client():
    """Get OpenAI client with user's API key"""
    api_keys = current_user.get_api_keys()
    if not api_keys['openai_api_key']:
        raise APIKeyError("OpenAI API key is required. Please add it in your settings.")
    return OpenAI(api_key=api_keys['openai_api_key'])

def init_fal_client():
    """Initialize FAL client with user's API key"""
    api_keys = current_user.get_api_keys()
    fal_key = api_keys['fal_key']
    
    if not fal_key:
        raise APIKeyError("FAL API key is required. Please add it in your settings.")
    
    try:
        # Create a sync client with the API key
        client = fal_client.SyncClient(key=fal_key)
        return client
    except Exception as e:
        print(f"Error initializing FAL client: {str(e)}")
        if "authentication failed" in str(e).lower():
            raise APIKeyError("FAL API key authentication failed. Please check your key in settings.")
        raise APIKeyError(f"Error initializing FAL client: {str(e)}")

def test_fal_client(client):
    """Test FAL client with a simple request"""
    try:
        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    print(f"FAL log: {log['message']}")

        # Use the dev model for testing as it's simpler
        result = client.subscribe(
            "fal-ai/flux/dev",
            arguments={
                "prompt": "test prompt",
                "image_size": {
                    "width": 512,
                    "height": 512
                },
                "num_images": 1,
                "enable_safety_checker": True,
                "num_inference_steps": 28,
                "guidance_scale": 3.5,
                "seed": 2345
            },
            with_logs=True,
            on_queue_update=on_queue_update
        )
        print("FAL client tested successfully")
        print(f"Test result: {result}")
        return True
    except Exception as e:
        print(f"Error testing FAL client: {str(e)}")
        raise APIKeyError(f"Error testing FAL client: {str(e)}")

def get_openai_model():
    """Get OpenAI model name"""
    return current_app.config.get('OPENAI_MODEL', 'gpt-4o-mini')
