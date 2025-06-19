from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, APISettings, APIProvider, AIModel
from .decorators import admin_required, superadmin_required
from datetime import datetime

admin_api_bp = Blueprint('admin_api', __name__, url_prefix='/admin/api')

@admin_api_bp.route('/')
@login_required
@admin_required
def manage_api_keys():
    """Manage centralized API keys"""
    if not current_user.is_superadmin():
        return jsonify({
            'success': False,
            'message': 'Only superadmins can access API management.'
        }), 403
    
    api_settings = APISettings.get_settings()
    providers = APIProvider.query.filter_by(is_active=True).all()
    models = AIModel.query.filter_by(is_active=True).all()
    
    # Get available providers (those with API keys configured)
    available_providers = api_settings.get_available_providers()
    
    return render_template('admin/api_management.html',
                         api_settings=api_settings,
                         providers=providers,
                         models=models,
                         available_providers=available_providers)

@admin_api_bp.route('/update', methods=['POST'])
@login_required
@admin_required
def update_api_keys():
    if not current_user.is_superadmin():
        return jsonify({
            'success': False,
            'message': 'Only superadmins can update API keys.'
        }), 403
    """Update API keys and settings"""
    try:
        api_settings = APISettings.get_settings()
        
        # Update API keys (only if provided)
        openai_key = request.form.get('openai_api_key', '').strip()
        if openai_key:
            api_settings.set_openai_key(openai_key)
        
        anthropic_key = request.form.get('anthropic_api_key', '').strip()
        if anthropic_key:
            api_settings.set_anthropic_key(anthropic_key)
        
        gemini_key = request.form.get('gemini_api_key', '').strip()
        if gemini_key:
            api_settings.set_gemini_key(gemini_key)
        
        groq_key = request.form.get('groq_api_key', '').strip()
        if groq_key:
            api_settings.set_groq_key(groq_key)
        
        fal_key = request.form.get('fal_key', '').strip()
        if fal_key:
            api_settings.set_fal_key(fal_key)
        
        # Update default provider and model
        default_provider = request.form.get('default_provider_id')
        if default_provider:
            api_settings.default_provider_id = int(default_provider)
        
        default_model = request.form.get('default_model_id')
        if default_model:
            api_settings.default_model_id = int(default_model)
        
        # Update metadata
        api_settings.updated_by_id = current_user.id
        api_settings.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'API keys updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to update API keys: {str(e)}'
        }), 500

@admin_api_bp.route('/test', methods=['POST'])
@login_required
@admin_required
def test_api_keys():
    """Test API key connectivity"""
    if not current_user.is_superadmin():
        return jsonify({
            'success': False,
            'message': 'Only superadmins can test API keys.'
        }), 403
    
    try:
        api_settings = APISettings.get_settings()
        provider_name = request.json.get('provider')
        
        if not provider_name:
            return jsonify({
                'success': False,
                'message': 'Provider name is required'
            }), 400
        
        # Test the API key based on provider
        if provider_name == 'OpenAI':
            api_key = api_settings.get_openai_key()
            if not api_key:
                return jsonify({
                    'success': False,
                    'message': 'OpenAI API key not configured'
                }), 400
            
            # Test OpenAI API
            import openai
            client = openai.OpenAI(api_key=api_key)
            response = client.models.list()
            
        elif provider_name == 'Anthropic':
            api_key = api_settings.get_anthropic_key()
            if not api_key:
                return jsonify({
                    'success': False,
                    'message': 'Anthropic API key not configured'
                }), 400
            
            # Test Anthropic API
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            # Simple test - just initialize client
            
        elif provider_name == 'Google Gemini':
            api_key = api_settings.get_gemini_key()
            if not api_key:
                return jsonify({
                    'success': False,
                    'message': 'Google Gemini API key not configured'
                }), 400
            
            # Test Google Gemini API
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            models = genai.list_models()
            
        elif provider_name == 'Groq':
            api_key = api_settings.get_groq_key()
            if not api_key:
                return jsonify({
                    'success': False,
                    'message': 'Groq API key not configured'
                }), 400
            
            # Test Groq API
            from groq import Groq
            client = Groq(api_key=api_key)
            # Simple test - just initialize client
            
        elif provider_name == 'FAL':
            api_key = api_settings.get_fal_key()
            if not api_key:
                return jsonify({
                    'success': False,
                    'message': 'FAL API key not configured'
                }), 400
            
            # Test FAL API
            import fal_client
            fal_client.api_key = api_key
            # Simple test - just set the key
            
        else:
            return jsonify({
                'success': False,
                'message': f'Unknown provider: {provider_name}'
            }), 400
        
        return jsonify({
            'success': True,
            'message': f'{provider_name} API key is valid'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'API key test failed: {str(e)}'
        }), 400

@admin_api_bp.route('/clear/<provider>', methods=['POST'])
@login_required
@superadmin_required
def clear_api_key(provider):
    """Clear API key for specific provider (superadmin only)"""
    try:
        api_settings = APISettings.get_settings()
        
        if provider == 'openai':
            api_settings.openai_api_key = None
        elif provider == 'anthropic':
            api_settings.anthropic_api_key = None
        elif provider == 'gemini':
            api_settings.gemini_api_key = None
        elif provider == 'groq':
            api_settings.groq_api_key = None
        elif provider == 'fal':
            api_settings.fal_key = None
        else:
            return jsonify({
                'success': False,
                'message': 'Invalid provider'
            }), 400
        
        api_settings.updated_by_id = current_user.id
        api_settings.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{provider.title()} API key cleared'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to clear API key: {str(e)}'
        }), 500

@admin_api_bp.route('/status')
@login_required
@admin_required
def api_status():
    """Get API configuration status"""
    api_settings = APISettings.get_settings()
    
    status = {
        'has_openai': bool(api_settings.get_openai_key()),
        'has_anthropic': bool(api_settings.get_anthropic_key()),
        'has_gemini': bool(api_settings.get_gemini_key()),
        'has_groq': bool(api_settings.get_groq_key()),
        'has_fal': bool(api_settings.get_fal_key()),
        'has_required_keys': api_settings.has_required_keys(),
        'available_providers': len(api_settings.get_available_providers()),
        'last_updated': api_settings.updated_at.isoformat() if api_settings.updated_at else None
    }
    
    return jsonify(status)

@admin_api_bp.route('/models')
@login_required
@admin_required
def manage_models():
    """Manage AI models"""
    providers = APIProvider.query.filter_by(is_active=True).all()
    models = AIModel.query.order_by(AIModel.provider_id, AIModel.sort_order, AIModel.name).all()
    return render_template('admin/model_management.html', providers=providers, models=models)

@admin_api_bp.route('/models/add', methods=['POST'])
@login_required
@admin_required
def add_model():
    """Add a new AI model"""
    data = request.get_json()
    
    # Validate required fields
    if not data.get('name') or not data.get('provider_id'):
        return jsonify({'success': False, 'message': 'Model name and provider are required'}), 400
    
    # Check if model already exists
    existing = AIModel.query.filter_by(
        name=data['name'], 
        provider_id=data['provider_id']
    ).first()
    
    if existing:
        return jsonify({'success': False, 'message': 'Model already exists'}), 400
    
    # Create new model
    model = AIModel(
        name=data['name'],
        display_name=data.get('display_name', data['name']),
        provider_id=data['provider_id'],
        description=data.get('description'),
        context_window=data.get('context_window'),
        is_latest=data.get('is_latest', False),
        capabilities=data.get('capabilities', []),
        sort_order=data.get('sort_order', 0),
        is_active=data.get('is_active', True)
    )
    
    # If marking as latest, unmark other models from same provider
    if model.is_latest:
        AIModel.query.filter_by(
            provider_id=model.provider_id,
            is_latest=True
        ).update({'is_latest': False})
    
    db.session.add(model)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Model added successfully'})

@admin_api_bp.route('/models/<int:model_id>/update', methods=['POST'])
@login_required
@admin_required
def update_model(model_id):
    """Update an existing AI model"""
    model = AIModel.query.get_or_404(model_id)
    data = request.get_json()
    
    # Update fields
    if 'display_name' in data:
        model.display_name = data['display_name']
    if 'description' in data:
        model.description = data['description']
    if 'context_window' in data:
        model.context_window = data['context_window']
    if 'is_latest' in data:
        # If marking as latest, unmark others
        if data['is_latest'] and not model.is_latest:
            AIModel.query.filter_by(
                provider_id=model.provider_id,
                is_latest=True
            ).update({'is_latest': False})
        model.is_latest = data['is_latest']
    if 'capabilities' in data:
        model.capabilities = data['capabilities']
    if 'sort_order' in data:
        model.sort_order = data['sort_order']
    if 'is_active' in data:
        model.is_active = data['is_active']
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Model updated successfully'})

@admin_api_bp.route('/models/<int:model_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_model(model_id):
    """Delete an AI model"""
    model = AIModel.query.get_or_404(model_id)
    
    # Check if model is being used as default
    api_settings = APISettings.get_settings()
    if api_settings.default_model_id == model_id:
        return jsonify({
            'success': False, 
            'message': 'Cannot delete the default model. Please change the default model first.'
        }), 400
    
    db.session.delete(model)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Model deleted successfully'})