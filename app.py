from flask import Flask
from dotenv import load_dotenv
from flask_cors import CORS
import os

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)  # This will enable CORS for all routes

# Get the API keys and models from environment variables
openai_key = os.getenv('OPENAI_API_KEY')
fal_key = os.getenv('FAL_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL')
FLUX_PRO_MODEL = os.getenv('FLUX_PRO_MODEL')

if not fal_key:
    raise ValueError("FAL_KEY environment variable is not set")

# Register Blueprints
from blueprints.generate import generate_bp
from blueprints.download import download_bp
from blueprints.core import core_bp

app.register_blueprint(generate_bp)
app.register_blueprint(download_bp)
app.register_blueprint(core_bp)

if __name__ == '__main__':
    app.run(debug=True)
