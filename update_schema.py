from flask import Flask
from extensions import db
from models import User, APIProvider, AIModel, Image, TrainingHistory
import os
from dotenv import load_dotenv
import sqlite3
from datetime import datetime
from sqlalchemy import text

# Load environment variables
load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DB_PATH', 'sqlite:///instance/sketchmaker.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

def backup_training_data(db_path):
    """Backup existing training data"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get existing training data
    try:
        cursor.execute("SELECT * FROM training_history")
        training_data = cursor.fetchall()
        
        # Get column names
        cursor.execute("PRAGMA table_info(training_history)")
        columns = [col[1] for col in cursor.fetchall()]
        
        return columns, training_data
    except sqlite3.OperationalError:
        return None, None
    finally:
        conn.close()

def parse_sqlite_datetime(dt_str):
    """Parse SQLite datetime string to Python datetime object"""
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return None

def restore_training_data(columns, data, app):
    """Restore training data with new schema"""
    if not columns or not data:
        return
    
    with app.app_context():
        for row in data:
            row_dict = dict(zip(columns, row))
            training = TrainingHistory()
            
            # Handle datetime fields specially
            if 'created_at' in row_dict:
                training.created_at = parse_sqlite_datetime(row_dict['created_at'])
            if 'completed_at' in row_dict:
                training.completed_at = parse_sqlite_datetime(row_dict['completed_at'])
            
            # Handle other fields
            for col in columns:
                if col not in ['created_at', 'completed_at']:
                    if hasattr(TrainingHistory, col):
                        setattr(training, col, row_dict[col])
            
            # Set default values for new columns
            if 'queue_id' not in columns:
                training.queue_id = None
            if 'webhook_secret' not in columns:
                training.webhook_secret = None
            
            db.session.add(training)
        
        try:
            db.session.commit()
        except Exception as e:
            print(f"Error committing data: {str(e)}")
            db.session.rollback()
            raise

def update_schema():
    app = create_app()
    db_path = 'instance/sketchmaker.db'
    backup_path = f"instance/sketchmaker_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    
    try:
        # Create backup
        if os.path.exists(db_path):
            print("Creating database backup...")
            # Backup existing training data
            columns, training_data = backup_training_data(db_path)
            
            # Create full database backup
            conn = sqlite3.connect(db_path)
            with sqlite3.connect(backup_path) as backup:
                conn.backup(backup)
            conn.close()
            print(f"Backup created at {backup_path}")
            
            # Drop existing training_history table
            with app.app_context():
                # Use SQLAlchemy text() for raw SQL
                db.session.execute(text('DROP TABLE IF EXISTS training_history'))
                db.session.commit()
        
        # Update schema
        print("Updating database schema...")
        with app.app_context():
            # Create tables
            db.create_all()
            
            # Restore training data with new schema
            if columns and training_data:
                print("Restoring training data...")
                restore_training_data(columns, training_data, app)
        
        print("Schema update complete!")
        
        print("\nNext steps:")
        print("1. Verify the application works correctly")
        print("2. If everything is working, you can delete the backup")
        print(f"   rm {backup_path}")
        print("3. If there are issues, restore the backup:")
        print(f"   cp {backup_path} {db_path}")
        
    except Exception as e:
        print(f"Error updating schema: {str(e)}")
        if os.path.exists(backup_path):
            print("\nRestoring from backup...")
            if os.path.exists(db_path):
                os.remove(db_path)
            os.rename(backup_path, db_path)
            print("Backup restored!")
        raise

if __name__ == '__main__':
    update_schema()
