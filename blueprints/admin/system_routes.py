from flask import jsonify, request
from flask_login import login_required
from models import db, SystemSettings
from extensions import limiter, get_rate_limit_string
from .decorators import admin_required

@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def update_settings():
    try:
        settings = SystemSettings.get_settings()
        # Get the value and convert to boolean
        require_manual_approval = request.form.get('require_manual_approval')
        settings.require_manual_approval = require_manual_approval in ['true', 'True', '1', 'on', True]
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Settings updated successfully',
            'require_manual_approval': settings.require_manual_approval
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to update settings: {str(e)}'
        }), 500
