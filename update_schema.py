from flask import Flask
from extensions import db
from models import User, APIProvider, AIModel, Image, TrainingHistory
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DB_PATH', 'sqlite:///instance/sketchmaker.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

def update_schema():
    app = create_app()
    with app.app_context():
        # Create backup of existing database
        import sqlite3
        from datetime import datetime
        backup_path = f"instance/sketchmaker_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        try:
            # Create backup
            if os.path.exists('instance/sketchmaker.db'):
                print("Creating database backup...")
                conn = sqlite3.connect('instance/sketchmaker.db')
                with sqlite3.connect(backup_path) as backup:
                    conn.backup(backup)
                conn.close()
                print(f"Backup created at {backup_path}")
            
            # Update schema
            print("Updating database schema...")
            db.create_all()
            print("Schema update complete!")
            
            print("\nNext steps:")
            print("1. Verify the application works correctly")
            print("2. If everything is working, you can delete the backup")
            print(f"   rm {backup_path}")
            print("3. If there are issues, restore the backup:")
            print(f"   cp {backup_path} instance/sketchmaker.db")
            
        except Exception as e:
            print(f"Error updating schema: {str(e)}")
            if os.path.exists(backup_path):
                print("\nRestoring from backup...")
                if os.path.exists('instance/sketchmaker.db'):
                    os.remove('instance/sketchmaker.db')
                os.rename(backup_path, 'instance/sketchmaker.db')
                print("Backup restored!")
            raise

if __name__ == '__main__':
    update_schema()
