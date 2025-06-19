from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from models import db, EmailSettings
from extensions import limiter, get_rate_limit_string
from datetime import datetime
from .decorators import admin_required

@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def email_settings():
    if not current_user.is_superadmin():
        return jsonify({
            'success': False,
            'message': 'Only superadmins can access email settings.'
        }), 403
    
    settings = EmailSettings.get_settings()
    return render_template('admin/email.html', settings=settings)

@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def update_email_settings():
    if not current_user.is_superadmin():
        return jsonify({
            'success': False,
            'message': 'Only superadmins can modify email settings.'
        }), 403
    settings = EmailSettings.get_settings()
    
    try:
        # Update provider and status
        settings.provider = request.form.get('provider', 'smtp')
        settings.is_active = request.form.get('is_active') == 'on'
        
        # Update SMTP settings if provider is SMTP
        if settings.provider == 'smtp':
            settings.smtp_host = request.form.get('smtp_host')
            settings.smtp_port = int(request.form.get('smtp_port', 0)) or None
            settings.smtp_username = request.form.get('smtp_username')
            # Only update password if provided
            if request.form.get('smtp_password'):
                settings.smtp_password = request.form.get('smtp_password')
            settings.smtp_use_tls = request.form.get('smtp_use_tls') == 'on'
        
        # Update SES settings if provider is SES
        elif settings.provider == 'ses':
            settings.aws_access_key = request.form.get('aws_access_key')
            # Only update secret key if provided
            if request.form.get('aws_secret_key'):
                settings.aws_secret_key = request.form.get('aws_secret_key')
            settings.aws_region = request.form.get('aws_region')
        
        # Update common settings
        settings.from_email = request.form.get('from_email')
        settings.from_name = request.form.get('from_name')
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Email settings updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to update email settings: {str(e)}'
        }), 500

@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def test_email_settings():
    if not current_user.is_superadmin():
        return jsonify({
            'success': False,
            'message': 'Only superadmins can test email settings.'
        }), 403
    
    try:
        data = request.get_json()
        test_email = data.get('test_email')
        if not test_email:
            return jsonify({
                'success': False,
                'message': 'Test email address is required'
            }), 400
        
        settings = EmailSettings.get_settings()
        success, message = settings.test_connection(test_email)
        
        # Update test results
        settings.last_test_date = datetime.utcnow()
        settings.last_test_success = success
        settings.last_test_message = message
        db.session.commit()
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Failed to test email settings: {str(e)}'
        }), 500
