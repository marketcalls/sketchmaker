import os
import sys

def test_fal_key(key):
    """Test if a FAL API key works"""
    print(f"Testing FAL key: {key}")
    
    try:
        # Set the environment variable before importing fal_client
        os.environ['FAL_KEY'] = key
        
        # Import fal_client after setting environment variable
        import fal_client
        
        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    print(f"Log: {log['message']}")

        # Try to generate a test image
        result = fal_client.subscribe(
            "fal-ai/flux-pro/v1.1",
            arguments={
                "prompt": "test prompt",
                "image_size": {
                    "width": 512,
                    "height": 512
                },
                "num_images": 1,
                "enable_safety_checker": True,
                "safety_tolerance": "2",
                "seed": 2345
            },
            with_logs=True,
            on_queue_update=on_queue_update
        )
        
        print("Success! Result:", result)
        return True
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_fal.py <fal_key>")
        sys.exit(1)
    
    fal_key = sys.argv[1]
    test_fal_key(fal_key)
