from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
from models import db, User, SystemSettings, EmailSettings
from extensions import limiter, get_rate_limit_string
from werkzeug.security import generate_password_hash
from datetime import datetime
import json

admin = Blueprint('admin', __name__)

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

@admin.route('/manage/email')
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def email_settings():
    settings = EmailSettings.get_settings()
    return render_template('admin/email.html', settings=settings)

@admin.route('/manage/email/update', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def update_email_settings():
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

@admin.route('/manage/email/test', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def test_email_settings():
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

@admin.route('/manage/user/<int:user_id>', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    action = request.form.get('action')
    
    try:
        # Prevent modifying superadmin unless you are superadmin
        if user.is_superadmin() and not current_user.is_superadmin():
            return jsonify({
                'success': False,
                'message': 'Only superadmins can modify other superadmin accounts.'
            }), 403
        
        # Prevent modifying your own account
        if user == current_user:
            return jsonify({
                'success': False,
                'message': 'You cannot modify your own account.'
            }), 403
        
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
            
        elif action == 'delete':
            if user.is_superadmin() and not current_user.is_superadmin():
                return jsonify({
                    'success': False,
                    'message': 'Only superadmins can delete superadmin accounts.'
                }), 403
            db.session.delete(user)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'User {user.username} has been updated successfully.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to update user: {str(e)}'
        }), 500

@admin.route('/manage/add_user', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def add_user():
    try:
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'user')
        
        # Only superadmin can create superadmin users
        if role == 'superadmin' and not current_user.is_superadmin():
            return jsonify({
                'success': False,
                'message': 'Only superadmins can create superadmin accounts.'
            }), 403
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            return jsonify({
                'success': False,
                'message': 'Username already exists.'
            }), 400
        if User.query.filter_by(email=email).first():
            return jsonify({
                'success': False,
                'message': 'Email already exists.'
            }), 400
        
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
        
        return jsonify({
            'success': True,
            'message': f'User {username} has been created successfully.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to create user: {str(e)}'
        }), 500

@admin.route('/manage/settings', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def update_settings():
    try:
        settings = SystemSettings.get_settings()
        settings.require_manual_approval = request.form.get('require_manual_approval') == 'true'
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
