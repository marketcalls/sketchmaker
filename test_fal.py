import sys
import fal_client

def test_fal_key(key):
    """Test if a FAL API key works"""
    print(f"Testing FAL key: {key}")
    
    try:
        # Create a sync client with the API key
        client = fal_client.SyncClient(key=key)
        
        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    print(f"Log: {log['message']}")
        
        # Use the client's subscribe method
        result = client.subscribe(
            "fal-ai/flux-pro/v1.1",
            arguments={
                "prompt": "man on the moon",
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
        
        # Print the image URL separately for easy access
        if result.get('images') and len(result['images']) > 0:
            print("\nGenerated Image URL:", result['images'][0]['url'])
            
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
