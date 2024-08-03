import os
from dotenv import load_dotenv
import fal_client

# Load environment variables from .env file
load_dotenv()

# Ensure FAL_KEY is set in the environment
fal_key = os.getenv('FAL_KEY')
if not fal_key:
    raise ValueError("FAL_KEY environment variable is not set")

# You do not need to manually configure the client, it uses the environment variable by default

# Submit a request using the fal-client
handler = fal_client.submit(
    "fal-ai/flux-pro",
    arguments={
        "prompt": "Extreme close-up of a single tiger eye, direct frontal view. Detailed iris and pupil. Sharp focus on eye texture and color. Natural lighting to capture authentic eye shine and depth. The word \"FLUX\" is painted over it in big, white brush strokes with visible texture."
    },
)

# Get and print the result
result = handler.get()
print(result)
