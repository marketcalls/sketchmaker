from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime
from models import db
import os
from openai import OpenAI, AuthenticationError

core_bp = Blueprint('core', __name__)

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
    if request.method == 'POST':
        openai_api_key = request.form.get('openai_api_key')
        fal_key = request.form.get('fal_key')
        
        # Track if any keys were updated
        keys_updated = False
        
        # Update OpenAI API key if provided
        if openai_api_key:
            if not openai_api_key.startswith('sk-'):
                flash('OpenAI API key must start with "sk-"', 'error')
                return redirect(url_for('core.settings'))
            current_user.openai_api_key = openai_api_key
            keys_updated = True
        
        # Update FAL API key if provided
        if fal_key:
            current_user.fal_key = fal_key
            keys_updated = True
        
        if keys_updated:
            try:
                db.session.commit()
                flash('Settings updated successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Error updating settings. Please try again.', 'error')
                print(f"Error updating settings: {str(e)}")
        
        return redirect(url_for('core.settings'))
    
    return render_template('settings.html')
