from flask import Flask, render_template, jsonify, request
from extensions import db, login_manager, limiter, get_rate_limit_string
from flask_migrate import Migrate
from services.scheduler import subscription_scheduler
import os
import atexit
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
    
    # Initialize scheduler
    subscription_scheduler.init_app(app)
    
    # Ensure scheduler stops when app shuts down
    atexit.register(lambda: subscription_scheduler.stop())

    with app.app_context():
        # Import models here to avoid circular imports
        from models import User, APIProvider, AIModel, AuthSettings, SubscriptionPlanModel, UserSubscription, APISettings
        
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
        from blueprints.magix import magix_bp
        from blueprints.admin.subscription_routes import admin_subscription_bp
        from blueprints.admin.api_routes import admin_api_bp
        
        # Register blueprints
        app.register_blueprint(auth_bp)
        app.register_blueprint(core_bp)
        app.register_blueprint(generate_bp)
        app.register_blueprint(gallery_bp)
        app.register_blueprint(download_bp)
        app.register_blueprint(admin)
        app.register_blueprint(admin_subscription_bp)
        app.register_blueprint(admin_api_bp)
        app.register_blueprint(training_bp)
        app.register_blueprint(banner)
        app.register_blueprint(image_generator_bp)
        app.register_blueprint(magix_bp)
        
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

                # OpenAI models - Latest as of June 2025
                openai_models = [
                    {
                        "name": "gpt-4.1",
                        "display_name": "GPT-4.1",
                        "description": "Smartest model for complex tasks",
                        "is_latest": True,
                        "sort_order": 1
                    },
                    {
                        "name": "gpt-4.1-mini",
                        "display_name": "GPT-4.1 Mini",
                        "description": "Affordable model balancing speed and intelligence",
                        "is_latest": True,
                        "sort_order": 2
                    },
                    {
                        "name": "gpt-4.1-nano",
                        "display_name": "GPT-4.1 Nano",
                        "description": "Fastest, most cost-effective model for low-latency tasks",
                        "is_latest": True,
                        "sort_order": 3
                    },
                    {
                        "name": "gpt-4o",
                        "display_name": "GPT-4o",
                        "description": "Previous generation model",
                        "sort_order": 4
                    },
                    {
                        "name": "gpt-4o-mini",
                        "display_name": "GPT-4o Mini",
                        "description": "Previous generation mini model",
                        "sort_order": 5
                    }
                ]
                for model_data in openai_models:
                    model = AIModel(provider_id=openai.id, **model_data)
                    db.session.add(model)

                # Anthropic models - Latest as of June 2025
                anthropic_models = [
                    {
                        "name": "claude-opus-4-20250514",
                        "display_name": "Claude Opus 4",
                        "description": "Powerful, large model for complex challenges",
                        "is_latest": True,
                        "sort_order": 1
                    },
                    {
                        "name": "claude-sonnet-4-20250514",
                        "display_name": "Claude Sonnet 4",
                        "description": "Smart, efficient model for everyday use",
                        "is_latest": True,
                        "sort_order": 2
                    },
                    {
                        "name": "claude-3-5-haiku-20241022",
                        "display_name": "Claude 3.5 Haiku",
                        "description": "Fastest model for daily tasks",
                        "is_latest": True,
                        "sort_order": 3
                    },
                    {
                        "name": "claude-3-7-sonnet-20250219",
                        "display_name": "Claude 3.7 Sonnet",
                        "description": "Enhanced Sonnet model",
                        "sort_order": 4
                    },
                    {
                        "name": "claude-3-5-sonnet-20241022",
                        "display_name": "Claude 3.5 Sonnet",
                        "description": "Previous Sonnet version",
                        "sort_order": 5
                    }
                ]
                for model_data in anthropic_models:
                    model = AIModel(provider_id=anthropic.id, **model_data)
                    db.session.add(model)

                # Google Gemini models - Latest as of June 2025
                gemini_models = [
                    {
                        "name": "gemini-2.5-pro",
                        "display_name": "Gemini 2.5 Pro",
                        "description": "Latest and most capable Gemini model",
                        "is_latest": True,
                        "sort_order": 1
                    },
                    {
                        "name": "gemini-2.5-flash",
                        "display_name": "Gemini 2.5 Flash",
                        "description": "Fast and efficient for most tasks",
                        "is_latest": True,
                        "sort_order": 2
                    },
                    {
                        "name": "gemini-2.5-flash-lite-preview-06-17",
                        "display_name": "Gemini 2.5 Flash Lite Preview",
                        "description": "Ultra-light preview model",
                        "is_latest": True,
                        "sort_order": 3
                    },
                    {
                        "name": "gemini-2.5-pro-preview-05-06",
                        "display_name": "Gemini 2.5 Pro Preview",
                        "description": "Preview version of Pro model",
                        "sort_order": 4
                    },
                    {
                        "name": "gemini-2.5-flash-preview-04-17",
                        "display_name": "Gemini 2.5 Flash Preview",
                        "description": "Preview version of Flash model",
                        "sort_order": 5
                    }
                ]
                for model_data in gemini_models:
                    model = AIModel(provider_id=gemini.id, **model_data)
                    db.session.add(model)

                # Groq models - Latest as of June 2025
                groq_models = [
                    {
                        "name": "compound-beta",
                        "display_name": "Compound Beta",
                        "description": "Latest compound model from Groq",
                        "is_latest": True,
                        "sort_order": 1
                    },
                    {
                        "name": "compound-beta-mini",
                        "display_name": "Compound Beta Mini",
                        "description": "Smaller compound model",
                        "is_latest": True,
                        "sort_order": 2
                    },
                    {
                        "name": "llama-3.3-70b-versatile",
                        "display_name": "Llama 3.3 70B Versatile",
                        "description": "Latest Llama model, versatile for various tasks",
                        "is_latest": True,
                        "sort_order": 3
                    },
                    {
                        "name": "llama-3.1-8b-instant",
                        "display_name": "Llama 3.1 8B Instant",
                        "description": "Fast 8B model for instant responses",
                        "sort_order": 4
                    },
                    {
                        "name": "llama3-8b-8192",
                        "display_name": "Llama 3 8B",
                        "description": "8B model with 8192 context",
                        "sort_order": 5
                    },
                    {
                        "name": "llama3-70b-8192",
                        "display_name": "Llama 3 70B",
                        "description": "70B model with 8192 context",
                        "sort_order": 6
                    }
                ]
                for model_data in groq_models:
                    model = AIModel(provider_id=groq.id, **model_data)
                    db.session.add(model)

                db.session.commit()
        
        def init_subscription_plans():
            """Initialize default subscription plans"""
            SubscriptionPlanModel.initialize_default_plans()
            
            # Assign free plan to all existing users without subscription
            users_without_sub = User.query.filter(
                ~User.id.in_(
                    db.session.query(UserSubscription.user_id).filter_by(is_active=True)
                )
            ).all()
            
            free_plan = SubscriptionPlanModel.query.filter_by(name='free').first()
            if free_plan:
                for user in users_without_sub:
                    sub = UserSubscription(
                        user_id=user.id,
                        plan_id=free_plan.id,
                        credits_remaining=free_plan.monthly_credits,
                        credits_used_this_month=0
                    )
                    db.session.add(sub)
                db.session.commit()
        
        def init_api_settings():
            """Initialize API settings"""
            # This just ensures the API settings record exists
            APISettings.get_settings()
        
        # Create database tables and initialize providers
        db.create_all()
        init_api_providers()
        init_subscription_plans()
        init_api_settings()
    
    return app

# Create the application instance for gunicorn
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
