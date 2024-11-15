from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
from models import db, User, SystemSettings
from extensions import limiter, get_rate_limit_string
from werkzeug.security import generate_password_hash

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
    search_query = request.args.get('search', '')
    users = User.search_users(search_query) if search_query else User.query.all()
    total_users = User.get_total_count()
    settings = SystemSettings.get_settings()
    return render_template('admin/manage.html', 
                         users=users, 
                         total_users=total_users,
                         settings=settings,
                         search_query=search_query)

@admin.route('/manage/user/<int:user_id>', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    action = request.form.get('action')
    
    # Prevent modifying superadmin unless you are superadmin
    if user.is_superadmin() and not current_user.is_superadmin():
        flash('Only superadmins can modify other superadmin accounts.', 'error')
        return redirect(url_for('admin.manage'))
    
    # Prevent modifying your own account
    if user == current_user:
        flash('You cannot modify your own account.', 'error')
        return redirect(url_for('admin.manage'))
    
    if action == 'toggle_role':
        if current_user.is_superadmin():
            # Superadmin can set any role
            new_role = request.form.get('role', 'user')
            if new_role in ['user', 'admin', 'superadmin']:
                user.role = new_role
        else:
            # Regular admin can only toggle between user and admin
            user.role = 'user' if user.role == 'admin' else 'admin'
            
    elif action == 'toggle_status':
        user.is_active = not user.is_active
        
    elif action == 'toggle_approval':
        user.is_approved = not user.is_approved
        
    elif action == 'set_password':
        new_password = request.form.get('new_password')
        if new_password:
            user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
            flash(f'Password updated for user {user.username}.', 'success')
        
    elif action == 'delete':
        if user.is_superadmin() and not current_user.is_superadmin():
            flash('Only superadmins can delete superadmin accounts.', 'error')
            return redirect(url_for('admin.manage'))
        db.session.delete(user)
    
    db.session.commit()
    flash(f'User {user.username} has been updated.', 'success')
    return redirect(url_for('admin.manage'))

@admin.route('/manage/add_user', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def add_user():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role', 'user')
    
    # Only superadmin can create superadmin users
    if role == 'superadmin' and not current_user.is_superadmin():
        flash('Only superadmins can create superadmin accounts.', 'error')
        return redirect(url_for('admin.manage'))
    
    # Check if user already exists
    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'error')
        return redirect(url_for('admin.manage'))
    if User.query.filter_by(email=email).first():
        flash('Email already exists.', 'error')
        return redirect(url_for('admin.manage'))
    
    # Create new user
    new_user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
        role=role,
        is_active=True,
        is_approved=True
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    flash(f'User {username} has been created successfully.', 'success')
    return redirect(url_for('admin.manage'))

@admin.route('/manage/settings', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def update_settings():
    settings = SystemSettings.get_settings()
    settings.require_manual_approval = request.form.get('require_manual_approval') == 'true'
    db.session.commit()
    
    return jsonify({
        'success': True,
        'require_manual_approval': settings.require_manual_approval
    })

@admin.route('/manage/search')
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def search_users():
    query = request.args.get('q', '')
    users = User.search_users(query)
    return jsonify([{
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'is_active': user.is_active,
        'is_approved': user.is_approved
    } for user in users])
