from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from models import db, User
from extensions import limiter, get_rate_limit_string

admin = Blueprint('admin', __name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@admin.route('/manage')
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def manage():
    users = User.query.all()
    return render_template('admin/manage.html', users=users)

@admin.route('/manage/user/<int:user_id>', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    action = request.form.get('action')
    
    if user == current_user:
        flash('You cannot modify your own role.', 'error')
        return redirect(url_for('admin.manage'))
    
    if action == 'toggle_role':
        user.role = 'user' if user.role == 'admin' else 'admin'
    elif action == 'toggle_status':
        user.is_active = not user.is_active
    
    db.session.commit()
    flash(f'User {user.username} has been updated.', 'success')
    return redirect(url_for('admin.manage'))
