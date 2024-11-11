from flask import Flask, jsonify, render_template
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from dotenv import load_dotenv
import os

from models import db, User

# Load environment variables from .env file
load_dotenv()

# Initialize the Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sketchmaker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Initialize SQLAlchemy
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize rate limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["10 per minute", "50 per hour", "150 per day"],
    storage_uri="memory://"
)

# Fetch necessary environment variables
openai_key = os.getenv('OPENAI_API_KEY')
fal_key = os.getenv('FAL_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL')
FLUX_PRO_MODEL = os.getenv('FLUX_PRO_MODEL')

# Ensure required environment variables are set
if not openai_key or not fal_key or not OPENAI_MODEL or not FLUX_PRO_MODEL:
    raise ValueError("Some required environment variables are missing. Please check your .env file.")

# Register Blueprints
from blueprints.generate import generate_bp
from blueprints.download import download_bp
from blueprints.core import core_bp
from blueprints.gallery import gallery_bp
from blueprints.auth import auth_bp

app.register_blueprint(generate_bp)
app.register_blueprint(download_bp)
app.register_blueprint(core_bp)
app.register_blueprint(gallery_bp)
app.register_blueprint(auth_bp)

# Create database tables
with app.app_context():
    db.create_all()

# Custom 404 error handler
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# Unified 4xx error handler excluding 429
@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(405)
def handle_4xx_error(error):
    return jsonify(error=str(error)), error.code

# Error handler for rate limiting (429)
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify(error="Rate limit exceeded", description=str(e.description)), 429

if __name__ == '__main__':
    app.run(debug=True)
