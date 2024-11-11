from flask import Flask, render_template
from flask_login import LoginManager
from models import db, User
from blueprints.auth import auth_bp
from blueprints.core import core_bp
from blueprints.generate import generate_bp
from blueprints.gallery import gallery_bp
from blueprints.download import download_bp
import os

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sketchmaker.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
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

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
