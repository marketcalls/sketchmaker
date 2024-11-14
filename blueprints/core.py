from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from models import db, User, APIProvider, AIModel
from datetime import datetime
from extensions import limiter, get_rate_limit_string

core_bp = Blueprint('core', __name__)

@core_bp.route('/')
@limiter.limit(get_rate_limit_string())
def index():
    return render_template('index.html', current_year=datetime.now().year)

@core_bp.route('/dashboard')
@limiter.limit(get_rate_limit_string())
@login_required
def dashboard():
    return render_template('dashboard.html')

@core_bp.route('/settings')
@limiter.limit(get_rate_limit_string())
@login_required
def settings():
    # Get all providers and models
    providers = APIProvider.query.filter_by(is_active=True).all()
    models = AIModel.query.filter_by(is_active=True).all()
    
    # Get current provider and its key
    current_provider = None
    current_provider_key = None
    if current_user.selected_provider_id:
        current_provider = APIProvider.query.get(current_user.selected_provider_id)
        if current_provider:
            if current_provider.name == 'OpenAI':
                current_provider_key = current_user.openai_api_key
            elif current_provider.name == 'Anthropic':
                current_provider_key = current_user.anthropic_api_key
            elif current_provider.name == 'Google Gemini':
                current_provider_key = current_user.gemini_api_key
            elif current_provider.name == 'Groq':
                current_provider_key = current_user.groq_api_key
    
    # Get user's API keys
    api_keys = {
        'openai_api_key': current_user.openai_api_key or '',
        'anthropic_api_key': current_user.anthropic_api_key or '',
        'gemini_api_key': current_user.gemini_api_key or '',
        'groq_api_key': current_user.groq_api_key or '',
        'fal_key': current_user.fal_key or '',
        'current_provider_key': current_provider_key or '',
        'current_provider_name': current_provider.name if current_provider else ''
    }
    
    return render_template('settings.html', 
                         providers=providers,
                         models=models,
                         api_keys=api_keys)

@core_bp.route('/settings/update', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def update_settings():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        provider_id = data.get('provider_id')
        model_id = data.get('model_id')
        
        if not provider_id or not model_id:
            return jsonify({'error': 'Provider and model selection required'}), 400
        
        # Verify provider and model exist and are active
        provider = APIProvider.query.filter_by(id=provider_id, is_active=True).first()
        model = AIModel.query.filter_by(id=model_id, provider_id=provider_id, is_active=True).first()
        
        if not provider or not model:
            return jsonify({'error': 'Invalid provider or model selection'}), 400
        
        # Update provider settings
        current_user.selected_provider_id = provider_id
        current_user.selected_model_id = model_id
        
        # Update API keys if provided
        if 'openai_api_key' in data:
            current_user.openai_api_key = data['openai_api_key']
        if 'anthropic_api_key' in data:
            current_user.anthropic_api_key = data['anthropic_api_key']
        if 'gemini_api_key' in data:
            current_user.gemini_api_key = data['gemini_api_key']
        if 'groq_api_key' in data:
            current_user.groq_api_key = data['groq_api_key']
        if 'fal_key' in data:
            current_user.fal_key = data['fal_key']
        
        db.session.commit()
        
        # Get the current provider's key after update
        current_provider_key = None
        if provider.name == 'OpenAI':
            current_provider_key = current_user.openai_api_key
        elif provider.name == 'Anthropic':
            current_provider_key = current_user.anthropic_api_key
        elif provider.name == 'Google Gemini':
            current_provider_key = current_user.gemini_api_key
        elif provider.name == 'Groq':
            current_provider_key = current_user.groq_api_key
        
        # Return updated API keys in response
        response_data = {
            'message': 'Settings updated successfully',
            'api_keys': {
                'openai_api_key': current_user.openai_api_key or '',
                'anthropic_api_key': current_user.anthropic_api_key or '',
                'gemini_api_key': current_user.gemini_api_key or '',
                'groq_api_key': current_user.groq_api_key or '',
                'fal_key': current_user.fal_key or '',
                'current_provider_key': current_provider_key or '',
                'current_provider_name': provider.name
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@core_bp.route('/settings/models/<int:provider_id>')
@limiter.limit(get_rate_limit_string())
@login_required
def get_provider_models(provider_id):
    try:
        models = AIModel.query.filter_by(
            provider_id=provider_id,
            is_active=True
        ).all()
        
        return jsonify({
            'models': [{'id': m.id, 'name': m.name} for m in models]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
