from functools import wraps
from flask import redirect, url_for, flash, request, jsonify
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            if request.is_xhr:
                return jsonify({
                    'success': False,
                    'message': 'You do not have permission to access this page.'
                }), 403
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function