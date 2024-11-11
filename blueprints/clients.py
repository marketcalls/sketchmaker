import os
from openai import OpenAI
import fal_client

def get_required_env(name):
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value

# Configure OpenAI client
OPENAI_API_KEY = get_required_env('OPENAI_API_KEY')
openai_client = OpenAI(api_key=OPENAI_API_KEY)
OPENAI_MODEL = get_required_env('OPENAI_MODEL')

# Configure FAL client
FAL_KEY = get_required_env('FAL_KEY')
FLUX_PRO_MODEL = get_required_env('FLUX_PRO_MODEL')

# Initialize FAL client
try:
    fal_client.api_key = FAL_KEY
    print("FAL client initialized successfully")  # Debug log
except Exception as e:
    print(f"Error initializing FAL client: {str(e)}")  # Debug log
    raise
