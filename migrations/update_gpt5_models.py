#!/usr/bin/env python
"""
Script to update the database with GPT-5 models
Run this script to add the new GPT-5 models to your existing database
"""

from app import create_app
from extensions import db
from models import APIProvider, AIModel

def update_gpt5_models():
    """Add GPT-5 models to the database"""
    app = create_app()
    
    with app.app_context():
        # Find OpenAI provider
        openai = APIProvider.query.filter_by(name="OpenAI").first()
        
        if not openai:
            print("OpenAI provider not found. Creating it...")
            openai = APIProvider(name="OpenAI")
            db.session.add(openai)
            db.session.commit()
            print("OpenAI provider created.")
        
        # GPT-5 models to add
        gpt5_models = [
            {
                "name": "gpt-5",
                "display_name": "GPT-5",
                "description": "Most advanced AI model with unprecedented reasoning capabilities",
                "is_latest": True,
                "sort_order": 1
            },
            {
                "name": "gpt-5-mini",
                "display_name": "GPT-5 Mini",
                "description": "Compact GPT-5 with excellent performance-to-cost ratio",
                "is_latest": True,
                "sort_order": 2
            },
            {
                "name": "gpt-5-nano",
                "display_name": "GPT-5 Nano",
                "description": "Ultra-fast GPT-5 variant for real-time applications",
                "is_latest": True,
                "sort_order": 3
            }
        ]
        
        # Check and add each GPT-5 model
        for model_data in gpt5_models:
            existing_model = AIModel.query.filter_by(
                provider_id=openai.id, 
                name=model_data["name"]
            ).first()
            
            if existing_model:
                # Update existing model
                existing_model.display_name = model_data["display_name"]
                existing_model.description = model_data["description"]
                existing_model.is_latest = model_data.get("is_latest", False)
                existing_model.sort_order = model_data["sort_order"]
                print(f"Updated existing model: {model_data['name']}")
            else:
                # Add new model
                new_model = AIModel(provider_id=openai.id, **model_data)
                db.session.add(new_model)
                print(f"Added new model: {model_data['name']}")
        
        # Update GPT-4 models to not be latest
        gpt4_models = AIModel.query.filter(
            AIModel.provider_id == openai.id,
            AIModel.name.like('gpt-4%')
        ).all()
        
        for model in gpt4_models:
            if model.is_latest:
                model.is_latest = False
                print(f"Updated {model.name} to not be latest")
        
        # Commit all changes
        try:
            db.session.commit()
            print("\nSuccessfully updated the database with GPT-5 models!")
            
            # Display all OpenAI models
            print("\nCurrent OpenAI models in database:")
            all_models = AIModel.query.filter_by(provider_id=openai.id).order_by(AIModel.sort_order).all()
            for model in all_models:
                latest_tag = " [LATEST]" if model.is_latest else ""
                print(f"  - {model.display_name} ({model.name}){latest_tag}")
                
        except Exception as e:
            db.session.rollback()
            print(f"Error updating database: {str(e)}")
            return False
        
        return True

if __name__ == "__main__":
    success = update_gpt5_models()
    if success:
        print("\n✅ Database update completed successfully!")
    else:
        print("\n❌ Database update failed. Please check the errors above.")