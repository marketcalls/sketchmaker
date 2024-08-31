import os
from openai import OpenAI
import fal_client

openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
OPENAI_MODEL = os.getenv('OPENAI_MODEL')
FLUX_PRO_MODEL = os.getenv('FLUX_PRO_MODEL')