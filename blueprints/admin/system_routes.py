from flask import jsonify, request, render_template
from flask_login import login_required, current_user
from models import db, SystemSettings
from extensions import limiter, get_rate_limit_string
from .decorators import admin_required, superadmin_required

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

@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def credit_configuration():
    """Credit configuration page"""
    if not current_user.is_superadmin():
        return jsonify({
            'success': False,
            'message': 'Only superadmins can access credit configuration.'
        }), 403
    
    try:
        settings = SystemSettings.get_settings()
        
        if request.method == 'POST':
            # Handle credit cost updates
            data = request.get_json()
            if data and 'credit_costs' in data:
                settings.update_credit_costs(data['credit_costs'])
                return jsonify({
                    'success': True,
                    'message': 'Credit costs updated successfully',
                    'credit_costs': settings.get_all_credit_costs()
                })
        
        # GET request - render page
        return render_template('admin/credit_configuration.html', 
                             settings=settings)
        
    except Exception as e:
        if request.method == 'POST':
            return jsonify({
                'success': False,
                'message': f'Failed to update credit costs: {str(e)}'
            }), 500
        else:
            # For GET request, still try to render page with defaults
            return render_template('admin/credit_configuration.html', 
                                 settings=SystemSettings.get_settings())

@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def get_credit_costs():
    """API endpoint to get current credit costs"""
    if not current_user.is_superadmin():
        return jsonify({
            'success': False,
            'message': 'Only superadmins can access credit costs.'
        }), 403
    
    try:
        settings = SystemSettings.get_settings()
        return jsonify({
            'success': True,
            'credit_costs': settings.get_all_credit_costs()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Failed to get credit costs: {str(e)}'
        }), 500
