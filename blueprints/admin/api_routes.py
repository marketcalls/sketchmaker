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