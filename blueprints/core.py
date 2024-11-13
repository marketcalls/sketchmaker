from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime
from models import db
import os
from openai import OpenAI, AuthenticationError
import fal_client

core_bp = Blueprint('core', __name__)

def validate_openai_key(key):
    """Validate OpenAI API key by making a test request"""
    if not key or not key.startswith('sk-'):
        return False, "OpenAI API key must start with 'sk-'"
    try:
        client = OpenAI(api_key=key)
        # Make a minimal test request
        client.models.list()
        return True, "OpenAI API key is valid"
    except AuthenticationError:
        return False, "Invalid OpenAI API key. Authentication failed."
    except Exception as e:
        print(f"OpenAI key validation error: {str(e)}")
        return False, "Error validating OpenAI API key. Please try again."

def test_fal_key(key):
    """Test FAL API key by making a minimal request"""
    try:
        print(f"\nTesting FAL key: {key}")
        
        # Create a sync client with the API key
        client = fal_client.SyncClient(key=key)
        
        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    print(f"Log: {log['message']}")

        # Try to generate a test image
        result = client.subscribe(
            "fal-ai/flux-pro/v1.1",
            arguments={
                "prompt": "test prompt",
                "image_size": {
                    "width": 512,
                    "height": 512
                },
                "num_images": 1,
                "enable_safety_checker": True,
                "safety_tolerance": "2",
                "seed": 2345
            },
            with_logs=True,
            on_queue_update=on_queue_update
        )
        
        print("FAL key test successful!")
        return True, "FAL API key is valid"
    except Exception as e:
        error_msg = str(e).lower()
        print(f"FAL key validation error: {error_msg}")
        
        if "authentication" in error_msg or "unauthorized" in error_msg:
            return False, "FAL API key authentication failed. Please check your key."
        elif "quota" in error_msg or "credits" in error_msg:
            return False, "FAL API key is valid but has no available credits."
        elif "rate limit" in error_msg:
            return False, "FAL API rate limit exceeded. Please try again later."
        
        return False, f"Error validating FAL API key: {str(e)}"

@core_bp.route('/')
def index():
    return render_template('index.html', current_year=datetime.now().year)

@core_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@core_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # Debug print current keys
    print("\nCurrent API Keys in DB:")
    print(f"OpenAI Key: {current_user.openai_api_key}")
    print(f"FAL Key: {current_user.fal_key}\n")
    
    if request.method == 'POST':
        openai_api_key = request.form.get('openai_api_key')
        fal_key = request.form.get('fal_key')
        
        # Debug print submitted keys
        print("\nSubmitted API Keys:")
        print(f"OpenAI Key: {openai_api_key}")
        print(f"FAL Key: {fal_key}\n")
        
        # Track if any keys were updated
        keys_updated = False
        
        # Validate OpenAI API key if provided
        if openai_api_key:
            is_valid, message = validate_openai_key(openai_api_key)
            if not is_valid:
                flash(message, 'error')
                return redirect(url_for('core.settings'))
            current_user.openai_api_key = openai_api_key
            keys_updated = True
            flash('OpenAI API key validated and saved successfully!', 'success')
        
        # Validate FAL API key if provided
        if fal_key:
            is_valid, message = test_fal_key(fal_key)
            if not is_valid:
                flash(message, 'error')
                return redirect(url_for('core.settings'))
            current_user.fal_key = fal_key
            keys_updated = True
            flash('FAL API key validated and saved successfully!', 'success')
        
        if keys_updated:
            try:
                db.session.commit()
                # Debug print updated keys
                print("\nUpdated API Keys in DB:")
                print(f"OpenAI Key: {current_user.openai_api_key}")
                print(f"FAL Key: {current_user.fal_key}\n")
            except Exception as e:
                db.session.rollback()
                flash('Error updating settings. Please try again.', 'error')
                print(f"Error updating settings: {str(e)}")
        
        return redirect(url_for('core.settings'))
    
    return render_template('settings.html')
