from flask import Flask, render_template, jsonify, request
from extensions import db, login_manager, limiter, get_rate_limit_string
from flask_migrate import Migrate
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  # 25MB max file size (matching nginx)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DB_PATH', 'sqlite:///sketchmaker.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
    app.config['TRAINING_FILES_FOLDER'] = os.path.join(app.root_path, 'static', 'training_files')
    
    # Ensure required environment variables are set
    required_vars = ['SECRET_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    # Create required directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['TRAINING_FILES_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.root_path, 'static', 'images'), exist_ok=True)
    
    # Initialize extensions
    db.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    migrate = Migrate(app, db)

    with app.app_context():
        # Import models here to avoid circular imports
        from models import User, APIProvider, AIModel, AuthSettings
        
        # Import blueprints
        from blueprints.auth import auth_bp
        from blueprints.core import core_bp
        from blueprints.generate import generate_bp
        from blueprints.gallery import gallery_bp
        from blueprints.download import download_bp
        from blueprints.admin import admin
        from blueprints.training import training_bp
        from blueprints.banner import banner
        from blueprints.image_generator import image_generator_bp
        
        # Register blueprints
        app.register_blueprint(auth_bp)
        app.register_blueprint(core_bp)
        app.register_blueprint(generate_bp)
        app.register_blueprint(gallery_bp)
        app.register_blueprint(download_bp)
        app.register_blueprint(admin)
        app.register_blueprint(training_bp)
        app.register_blueprint(banner)
        app.register_blueprint(image_generator_bp)
        
        # Error handlers
        @app.errorhandler(404)
        def page_not_found(e):
            return render_template('errors/404.html'), 404

        @app.errorhandler(413)
        def request_entity_too_large(e):
            if request.path.startswith('/api/'):
                return jsonify({
                    "error": "File too large",
                    "message": "The uploaded file exceeds the maximum allowed size.",
                }), 413
            return render_template('errors/413.html'), 413

        @app.errorhandler(429)
        def ratelimit_handler(e):
            # Default retry time of 60 seconds if not provided
            retry_after = getattr(e, 'retry_after', 60)
            if retry_after is None:
                retry_after = 60

            # For API endpoints, return JSON response
            if request.path.startswith('/api/'):
                return jsonify({
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": retry_after
                }), 429
            
            # For web pages, render template
            return render_template('errors/429.html', 
                retry_after=retry_after
            ), 429

        @app.errorhandler(500)
        def internal_server_error(e):
            return render_template('errors/500.html'), 500
        
        # User loader
        @login_manager.user_loader
        def load_user(user_id):
            return db.session.get(User, int(user_id))

        def init_api_providers():
            """Initialize default API providers and models"""
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
        
        # Create database tables and initialize providers
        db.create_all()
        init_api_providers()
    
    return app

# Create the application instance for gunicorn
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
