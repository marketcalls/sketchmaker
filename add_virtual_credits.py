#!/usr/bin/env python
"""
Migration script to add virtual try-on credit cost support to the database.
Run this script after updating the code to add the virtual feature.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from sqlalchemy import text
from models.system import SystemSettings

def add_virtual_credit_column():
    """Add the credit_cost_virtual column to SystemSettings table"""
    app = create_app()
    
    with app.app_context():
        try:
            # Check if the column already exists
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('system_settings')]
            
            if 'credit_cost_virtual' not in columns:
                print("Adding credit_cost_virtual column to system_settings table...")
                
                # Add the column with a default value
                with db.engine.connect() as conn:
                    conn.execute(text("""
                        ALTER TABLE system_settings 
                        ADD COLUMN credit_cost_virtual FLOAT DEFAULT 1.0
                    """))
                    conn.commit()
                
                print("✓ Column added successfully")
                
                # Update existing settings record if it exists
                settings = SystemSettings.query.first()
                if settings and not hasattr(settings, 'credit_cost_virtual'):
                    settings.credit_cost_virtual = 1.0
                    db.session.commit()
                    print("✓ Updated existing settings record")
            else:
                print("✓ Column credit_cost_virtual already exists")
            
            # Verify the column was added
            settings = SystemSettings.get_settings()
            print(f"\nCurrent credit costs:")
            print(f"  Images: {settings.credit_cost_images} credits")
            print(f"  Banners: {settings.credit_cost_banners} credits")
            print(f"  Magix: {settings.credit_cost_magix} credits")
            print(f"  Virtual Try-On: {settings.credit_cost_virtual} credits")
            print(f"  LoRA Training: {settings.credit_cost_lora_training} credits")
            
            print("\n✅ Migration completed successfully!")
            print("Virtual Try-On feature is now properly configured with credit costs.")
            
        except Exception as e:
            print(f"❌ Error during migration: {str(e)}")
            print("\nIf you're seeing a column already exists error, that's okay!")
            print("The migration may have already been applied.")
            return False
    
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("Virtual Try-On Credit System Migration")
    print("=" * 60)
    print("\nThis script will add support for Virtual Try-On credit costs.")
    print("It will add a new column to the system_settings table.\n")
    
    response = input("Do you want to proceed? (yes/no): ").strip().lower()
    if response in ['yes', 'y']:
        if add_virtual_credit_column():
            print("\n✨ You can now configure Virtual Try-On credit costs in the admin panel!")
        else:
            print("\n⚠️ Migration failed. Please check the error messages above.")
    else:
        print("\nMigration cancelled.")