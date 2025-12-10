from flask import Flask, render_template, jsonify, request
from extensions import db, login_manager, limiter, get_rate_limit_string, csrf
from flask_migrate import Migrate
from services.scheduler import subscription_scheduler
from version import get_version_info, get_display_version
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
    csrf.init_app(app)
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
        from blueprints.virtual import virtual_bp
        from blueprints.image_utils import image_utils_bp
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
        app.register_blueprint(virtual_bp)
        app.register_blueprint(image_utils_bp)
        
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
            """Initialize default API providers and models using LiteLLM"""
            # Only initialize if no providers exist
            if APIProvider.query.first() is None:
                # Create all providers (including new ones for LiteLLM)
                openai = APIProvider(name="OpenAI")
                anthropic = APIProvider(name="Anthropic")
                gemini = APIProvider(name="Google Gemini")
                groq = APIProvider(name="Groq")
                xai = APIProvider(name="xAI")  # Grok
                cerebras = APIProvider(name="Cerebras")
                openrouter = APIProvider(name="OpenRouter")
                db.session.add_all([openai, anthropic, gemini, groq, xai, cerebras, openrouter])
                db.session.commit()

                # OpenAI models - Latest as of December 2025
                # LiteLLM prefix: openai/
                openai_models = [
                    {
                        "name": "gpt-5.1",
                        "display_name": "GPT-5.1",
                        "description": "Latest GPT-5.1 with improved reasoning and conversation",
                        "is_latest": True,
                        "sort_order": 1
                    },
                    {
                        "name": "gpt-5",
                        "display_name": "GPT-5",
                        "description": "Unified AI model combining reasoning and fast responses",
                        "is_latest": True,
                        "sort_order": 2
                    },
                    {
                        "name": "gpt-5-mini",
                        "display_name": "GPT-5 Mini",
                        "description": "Compact GPT-5 with excellent performance-to-cost ratio",
                        "is_latest": True,
                        "sort_order": 3
                    },
                    {
                        "name": "o4-mini",
                        "display_name": "O4 Mini",
                        "description": "Fast, cost-efficient reasoning model for math and coding",
                        "is_latest": True,
                        "sort_order": 4
                    },
                    {
                        "name": "o3",
                        "display_name": "O3",
                        "description": "Advanced reasoning model",
                        "is_latest": True,
                        "sort_order": 5
                    },
                    {
                        "name": "o3-mini",
                        "display_name": "O3 Mini",
                        "description": "Smaller reasoning model for faster responses",
                        "sort_order": 6
                    },
                    {
                        "name": "gpt-4o",
                        "display_name": "GPT-4o",
                        "description": "Multimodal model for text and vision",
                        "sort_order": 7
                    },
                    {
                        "name": "gpt-4o-mini",
                        "display_name": "GPT-4o Mini",
                        "description": "Fast and affordable multimodal model",
                        "sort_order": 8
                    },
                    {
                        "name": "gpt-oss-120b",
                        "display_name": "GPT-OSS 120B",
                        "description": "Open-weight 120B reasoning model",
                        "sort_order": 9
                    },
                    {
                        "name": "gpt-oss-20b",
                        "display_name": "GPT-OSS 20B",
                        "description": "Open-weight 20B model with 3.6B active parameters",
                        "sort_order": 10
                    }
                ]
                for model_data in openai_models:
                    model = AIModel(provider_id=openai.id, **model_data)
                    db.session.add(model)

                # Anthropic models - Latest as of December 2025
                # LiteLLM prefix: anthropic/
                anthropic_models = [
                    {
                        "name": "claude-opus-4-5-20251101",
                        "display_name": "Claude Opus 4.5",
                        "description": "Most intelligent model for coding, agents, and enterprise workflows",
                        "is_latest": True,
                        "sort_order": 1
                    },
                    {
                        "name": "claude-sonnet-4-5-20250929",
                        "display_name": "Claude Sonnet 4.5",
                        "description": "Best coding model, excellent for complex agents",
                        "is_latest": True,
                        "sort_order": 2
                    },
                    {
                        "name": "claude-haiku-4-5-20251015",
                        "display_name": "Claude Haiku 4.5",
                        "description": "Fast and affordable, similar to Sonnet 4 at 1/3 cost",
                        "is_latest": True,
                        "sort_order": 3
                    },
                    {
                        "name": "claude-opus-4-20250514",
                        "display_name": "Claude Opus 4",
                        "description": "Powerful model for complex challenges",
                        "sort_order": 4
                    },
                    {
                        "name": "claude-sonnet-4-20250514",
                        "display_name": "Claude Sonnet 4",
                        "description": "Smart, efficient model for everyday use",
                        "sort_order": 5
                    },
                    {
                        "name": "claude-3-5-haiku-20241022",
                        "display_name": "Claude 3.5 Haiku",
                        "description": "Fastest model for daily tasks",
                        "sort_order": 6
                    }
                ]
                for model_data in anthropic_models:
                    model = AIModel(provider_id=anthropic.id, **model_data)
                    db.session.add(model)

                # Google Gemini models - Latest as of December 2025
                # LiteLLM prefix: gemini/
                gemini_models = [
                    {
                        "name": "gemini-3-pro",
                        "display_name": "Gemini 3 Pro",
                        "description": "Most intelligent Gemini with 1M context, tops LMArena",
                        "is_latest": True,
                        "sort_order": 1
                    },
                    {
                        "name": "gemini-3-flash",
                        "display_name": "Gemini 3 Flash",
                        "description": "Fast Gemini 3 for everyday tasks",
                        "is_latest": True,
                        "sort_order": 2
                    },
                    {
                        "name": "gemini-3-deep-think",
                        "display_name": "Gemini 3 Deep Think",
                        "description": "Advanced reasoning model with 45.1% on ARC-AGI-2",
                        "is_latest": True,
                        "sort_order": 3
                    },
                    {
                        "name": "gemini-2.5-pro",
                        "display_name": "Gemini 2.5 Pro",
                        "description": "Stable 2.5 Pro with adaptive thinking",
                        "sort_order": 4
                    },
                    {
                        "name": "gemini-2.5-flash",
                        "display_name": "Gemini 2.5 Flash",
                        "description": "Fast model for large scale processing",
                        "sort_order": 5
                    },
                    {
                        "name": "gemini-2.5-flash-lite",
                        "display_name": "Gemini 2.5 Flash Lite",
                        "description": "Low-cost, high-performance model",
                        "sort_order": 6
                    },
                    {
                        "name": "gemini-2.0-flash",
                        "display_name": "Gemini 2.0 Flash",
                        "description": "Previous generation flash model",
                        "sort_order": 7
                    }
                ]
                for model_data in gemini_models:
                    model = AIModel(provider_id=gemini.id, **model_data)
                    db.session.add(model)

                # Groq models - Latest as of December 2025
                # LiteLLM prefix: groq/
                groq_models = [
                    {
                        "name": "openai/gpt-oss-120b",
                        "display_name": "GPT-OSS 120B",
                        "description": "OpenAI open-weight 120B reasoning model on Groq",
                        "is_latest": True,
                        "sort_order": 1
                    },
                    {
                        "name": "openai/gpt-oss-20b",
                        "display_name": "GPT-OSS 20B",
                        "description": "OpenAI open-weight 20B model on Groq",
                        "is_latest": True,
                        "sort_order": 2
                    },
                    {
                        "name": "qwen/qwen3-32b",
                        "display_name": "Qwen 3 32B",
                        "description": "Alibaba Qwen 3 with exceptional text generation",
                        "is_latest": True,
                        "sort_order": 3
                    },
                    {
                        "name": "moonshotai/kimi-k2-instruct-0905",
                        "display_name": "Kimi K2 (Moonshot)",
                        "description": "1T parameter MoE with 256K context",
                        "is_latest": True,
                        "sort_order": 4
                    },
                    {
                        "name": "llama-3.3-70b-versatile",
                        "display_name": "Llama 3.3 70B Versatile",
                        "description": "Meta Llama for versatile tasks",
                        "sort_order": 5
                    },
                    {
                        "name": "llama-3.1-8b-instant",
                        "display_name": "Llama 3.1 8B Instant",
                        "description": "Fast 8B model for instant responses",
                        "sort_order": 6
                    }
                ]
                for model_data in groq_models:
                    model = AIModel(provider_id=groq.id, **model_data)
                    db.session.add(model)

                # xAI (Grok) models - Latest as of December 2025
                # LiteLLM prefix: xai/
                xai_models = [
                    {
                        "name": "grok-3",
                        "display_name": "Grok 3",
                        "description": "Latest Grok model with web search support",
                        "is_latest": True,
                        "sort_order": 1
                    },
                    {
                        "name": "grok-2-latest",
                        "display_name": "Grok 2 Latest",
                        "description": "Grok 2 with latest improvements",
                        "is_latest": True,
                        "sort_order": 2
                    },
                    {
                        "name": "grok-2",
                        "display_name": "Grok 2",
                        "description": "Standard Grok 2 model",
                        "sort_order": 3
                    }
                ]
                for model_data in xai_models:
                    model = AIModel(provider_id=xai.id, **model_data)
                    db.session.add(model)

                # Cerebras models - Latest as of December 2025
                # LiteLLM prefix: cerebras/
                cerebras_models = [
                    {
                        "name": "zai-glm-4.6",
                        "display_name": "ZAI GLM 4.6",
                        "description": "Latest GLM model on Cerebras",
                        "is_latest": True,
                        "sort_order": 1
                    },
                    {
                        "name": "llama-3.3-70b",
                        "display_name": "Llama 3.3 70B",
                        "description": "Multilingual Llama with ultra-fast inference",
                        "is_latest": True,
                        "sort_order": 2
                    },
                    {
                        "name": "qwen-3-235b-a22b-instruct-2507",
                        "display_name": "Qwen 3 235B A22B Instruct",
                        "description": "MoE with 22B active params, 262K context",
                        "is_latest": True,
                        "sort_order": 3
                    },
                    {
                        "name": "qwen-3-32b",
                        "display_name": "Qwen 3 32B",
                        "description": "Fast reasoning model, 60x faster than competitors",
                        "is_latest": True,
                        "sort_order": 4
                    },
                    {
                        "name": "gpt-oss-120b",
                        "display_name": "GPT-OSS 120B",
                        "description": "OpenAI's open-weight 120B reasoning model",
                        "is_latest": True,
                        "sort_order": 5
                    }
                ]
                for model_data in cerebras_models:
                    model = AIModel(provider_id=cerebras.id, **model_data)
                    db.session.add(model)

                # OpenRouter models - Latest as of December 2025
                # LiteLLM prefix: openrouter/
                openrouter_models = [
                    {
                        "name": "openai/gpt-5",
                        "display_name": "GPT-5 (OpenRouter)",
                        "description": "OpenAI GPT-5 via OpenRouter",
                        "is_latest": True,
                        "sort_order": 1
                    },
                    {
                        "name": "anthropic/claude-opus-4.5",
                        "display_name": "Claude Opus 4.5 (OpenRouter)",
                        "description": "Anthropic Claude Opus 4.5 via OpenRouter",
                        "is_latest": True,
                        "sort_order": 2
                    },
                    {
                        "name": "google/gemini-3-pro",
                        "display_name": "Gemini 3 Pro (OpenRouter)",
                        "description": "Google Gemini 3 Pro via OpenRouter",
                        "is_latest": True,
                        "sort_order": 3
                    },
                    {
                        "name": "meta-llama/llama-4-maverick",
                        "display_name": "Llama 4 Maverick (OpenRouter)",
                        "description": "Meta Llama 4 via OpenRouter",
                        "sort_order": 4
                    },
                    {
                        "name": "qwen/qwen3-235b",
                        "display_name": "Qwen3 235B (OpenRouter)",
                        "description": "Alibaba Qwen3 via OpenRouter",
                        "sort_order": 5
                    },
                    {
                        "name": "mistralai/mistral-large",
                        "display_name": "Mistral Large (OpenRouter)",
                        "description": "Mistral AI large model via OpenRouter",
                        "sort_order": 6
                    }
                ]
                for model_data in openrouter_models:
                    model = AIModel(provider_id=openrouter.id, **model_data)
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
        
        # Add version information to template context
        @app.context_processor
        def inject_version():
            return {
                'app_version': get_version_info(),
                'display_version': get_display_version()
            }
    
    return app

# Create the application instance for gunicorn
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
