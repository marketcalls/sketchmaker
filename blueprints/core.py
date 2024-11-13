from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from models import db, User, APIProvider, AIModel

core_bp = Blueprint('core', __name__)

@core_bp.route('/')
def index():
    return render_template('index.html')

@core_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@core_bp.route('/settings')
@login_required
def settings():
    # Get all providers and models
    providers = APIProvider.query.filter_by(is_active=True).all()
    models = AIModel.query.filter_by(is_active=True).all()
    
    return render_template('settings.html', 
                         providers=providers,
                         models=models)

@core_bp.route('/settings/update', methods=['POST'])
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
        
        return jsonify({'message': 'Settings updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@core_bp.route('/settings/models/<int:provider_id>')
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
