from flask import Flask, render_template
from flask_login import LoginManager
from models import db, User, APIProvider, AIModel
from blueprints.auth import auth_bp
from blueprints.core import core_bp
from blueprints.generate import generate_bp
from blueprints.gallery import gallery_bp
from blueprints.download import download_bp
from blueprints.admin import admin
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sketchmaker.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Ensure required environment variables are set
    required_vars = ['SECRET_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    # Initialize extensions
    db.init_app(app)
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)
    
    # Create database tables and initialize providers
    with app.app_context():
        db.create_all()
        init_api_providers(app)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(core_bp)
    app.register_blueprint(generate_bp)
    app.register_blueprint(gallery_bp)
    app.register_blueprint(download_bp)
    app.register_blueprint(admin)
    
    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404
    
    # User loader
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
    
    return app

def init_api_providers(app):
    """Initialize default API providers and models"""
    with app.app_context():
        # Only initialize if no providers exist
        if APIProvider.query.first() is None:
            # Create providers
            openai = APIProvider(name="OpenAI")
            anthropic = APIProvider(name="Anthropic")
            gemini = APIProvider(name="Google Gemini")
            groq = APIProvider(name="Groq")
            db.session.add_all([openai, anthropic, gemini, groq])
            db.session.commit()

            # OpenAI models
            openai_models = [
                "gpt-4o",
                "gpt-4o-mini",
                "o1-preview",
                "o1-mini"
            ]
            for model in openai_models:
                db.session.add(AIModel(name=model, provider_id=openai.id))

            # Anthropic models
            anthropic_models = [
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
                "claude-3-haiku-20240307"
            ]
            for model in anthropic_models:
                db.session.add(AIModel(name=model, provider_id=anthropic.id))

            # Google Gemini models
            gemini_models = [
                "gemini-1.5-flash-002",
                "gemini-1.5-flash-exp-0827",
                "gemini-1.5-flash-8b-exp-0827",
                "gemini-1.5-pro-002",
                "gemini-1.5-pro-exp-0827"
            ]
            for model in gemini_models:
                db.session.add(AIModel(name=model, provider_id=gemini.id))

            # Groq models
            groq_models = [
                "llama-3.1-70b-versatile",
                "llama-3.1-8b-instant",
                "llama-3.2-11b-text-preview",
                "llama-3.2-11b-vision-preview",
                "llama-3.2-1b-preview",
                "llama-3.2-3b-preview",
                "llama-3.2-90b-text-preview",
                "llama-3.2-90b-vision-preview"
            ]
            for model in groq_models:
                db.session.add(AIModel(name=model, provider_id=groq.id))

            db.session.commit()

# Create the application instance for gunicorn
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
