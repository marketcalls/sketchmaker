from flask import current_app
from alembic import context
from flask_migrate import Migrate
from extensions import db

# Create the migrate instance
migrate = Migrate()

def run_migrations():
    """Run migrations in 'online' mode."""
    # Initialize migration configuration
    config = context.config

    # Get database URL from Flask app config
    config.set_main_option("sqlalchemy.url", current_app.config["SQLALCHEMY_DATABASE_URI"])

    # Register models
    with current_app.app_context():
        # Import all models to ensure they're known to SQLAlchemy
        from models import (
            User, PasswordResetOTP, AuthSettings,
            APIProvider, AIModel,
            Image, TrainingHistory,
            EmailSettings, SystemSettings
        )
        target_metadata = db.metadata

    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []

    # Run the migration
    context.configure(
        target_metadata=target_metadata,
        process_revision_directives=process_revision_directives,
        compare_type=True
    )

    with context.begin_transaction():
        context.run_migrations()
