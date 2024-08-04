from flask import Flask, jsonify, render_template
from dotenv import load_dotenv
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)  # This will enable CORS for all routes

# Initialize rate limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["10 per minute", "50 per hour", "150 per day"],
    storage_uri="memory://"
)

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

# Custom 404 error handler
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# Error handler for other 4xx errors
@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(405)
@app.errorhandler(429)
def handle_4xx_error(error):
    return jsonify(error=str(error)), error.code

# Error handler for rate limiting
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify(error="Rate limit exceeded", description=str(e.description)), 429

if __name__ == '__main__':
    app.run(debug=True)