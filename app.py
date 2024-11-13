from flask import Flask, render_template
from flask_login import LoginManager
from models import db, User
from blueprints.auth import auth_bp
from blueprints.core import core_bp
from blueprints.generate import generate_bp
from blueprints.gallery import gallery_bp
from blueprints.download import download_bp
from blueprints.admin import admin  # Import admin blueprint
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
    
    # Set OpenAI model
    app.config['OPENAI_MODEL'] = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    app.config['FLUX_PRO_MODEL'] = os.getenv('FLUX_PRO_MODEL', 'fal-ai/flux-pro/v1.1')

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
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(core_bp)
    app.register_blueprint(generate_bp)
    app.register_blueprint(gallery_bp)
    app.register_blueprint(download_bp)
    app.register_blueprint(admin)  # Register admin blueprint
    
    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404
    
    # User loader
    @login_manager.user_loader
    def load_user(user_id):
        # Use Session.get() instead of Query.get()
        return db.session.get(User, int(user_id))
    
    return app

# Create the application instance for gunicorn
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
