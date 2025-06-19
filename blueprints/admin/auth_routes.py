from flask import render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models.auth import AuthSettings
from extensions import db, limiter, get_rate_limit_string
from .decorators import admin_required

@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def auth_settings():
    """Show auth settings page - only accessible by superadmin"""
    if not current_user.is_superadmin():
        return jsonify({
            'success': False,
            'message': 'Only superadmins can access auth settings.'
        }), 403
        
    settings = AuthSettings.get_settings()
    return render_template('admin/auth.html', settings=settings)

@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def update_auth_settings():
    """Update auth settings - only accessible by superadmin"""
    if request.method != 'POST':
        return jsonify({
            'success': False,
            'message': 'Method not allowed'
        }), 405
        
    if not current_user.is_superadmin():
        return jsonify({
            'success': False,
            'message': 'Only superadmins can modify auth settings.'
        }), 403
    
    try:
        settings = AuthSettings.get_settings()
        
        # Update auth modes
        settings.regular_auth_enabled = request.form.get('regular_auth_enabled') == 'true'
        settings.google_auth_enabled = request.form.get('google_auth_enabled') == 'true'
        
        # Update Google OAuth settings if enabled
        if settings.google_auth_enabled:
            client_id = request.form.get('google_client_id')
            client_secret = request.form.get('google_client_secret')
            
            if not client_id or not client_secret:
                return jsonify({
                    'success': False,
                    'message': 'Google Client ID and Client Secret are required when Google Auth is enabled.'
                }), 400
            
            settings.google_client_id = client_id
            settings.google_client_secret = client_secret
        
        # Ensure at least one auth method is enabled
        if not settings.regular_auth_enabled and not settings.google_auth_enabled:
            return jsonify({
                'success': False,
                'message': 'At least one authentication method must be enabled.'
            }), 400
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Auth settings updated successfully.',
            'regular_auth_enabled': settings.regular_auth_enabled,
            'google_auth_enabled': settings.google_auth_enabled
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to update auth settings: {str(e)}'
        }), 500
