from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from models import db, User, PasswordResetOTP, Image, TrainingHistory
from extensions import limiter, get_rate_limit_string
from .decorators import admin_required
from .utils import is_valid_password, send_approval_email
import os

@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def manage():
    search_query = request.args.get('search', '')
    users = User.search_users(search_query) if search_query else User.query.all()
    total_users = User.get_total_count()
    from models import SystemSettings
    settings = SystemSettings.get_settings()
    return render_template('admin/manage.html', 
                         users=users, 
                         total_users=total_users,
                         settings=settings,
                         search_query=search_query)

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
            was_approved = user.is_approved
            user.is_approved = not user.is_approved
            
            # Send approval email if user was just approved
            if not was_approved and user.is_approved:
                email_success, email_message = send_approval_email(user)
                if not email_success:
                    print(f"Failed to send approval email: {email_message}")
                    # Don't show email failure to user, just log it
            
        elif action == 'set_password':
            new_password = request.form.get('new_password')
            if not new_password:
                return jsonify({
                    'success': False,
                    'message': 'New password is required.'
                }), 400
                
            if not is_valid_password(new_password):
                return jsonify({
                    'success': False,
                    'message': 'Password must be at least 8 characters and include uppercase, lowercase, number, and special character.'
                }), 400
                
            user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
            
        elif action == 'delete':
            if user.is_superadmin() and not current_user.is_superadmin():
                return jsonify({
                    'success': False,
                    'message': 'Only superadmins can delete superadmin accounts.'
                }), 403
                
            # Delete all user's images first
            images = Image.query.filter_by(user_id=user.id).all()
            for image in images:
                # Delete the actual image files (multiple formats)
                base_filename = os.path.splitext(image.filename)[0]
                static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'static', 'images')
                
                # Try to delete all possible file formats
                for ext in ['.png', '.webp', '.jpeg', '.jpg']:
                    file_path = os.path.join(static_dir, f'{base_filename}{ext}')
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            print(f"Deleted file: {file_path}")
                        except Exception as e:
                            print(f"Failed to delete file {file_path}: {e}")
                
                # Delete the image record
                db.session.delete(image)
            
            # Delete all user's training history
            TrainingHistory.query.filter_by(user_id=user.id).delete()
            
            # Delete associated password reset OTPs
            PasswordResetOTP.query.filter_by(user_id=user.id).delete()
            
            # Delete user subscriptions and usage history
            from models import UserSubscription, UsageHistory
            UserSubscription.query.filter_by(user_id=user.id).delete()
            UserSubscription.query.filter_by(assigned_by_id=user.id).update({'assigned_by_id': None})
            UsageHistory.query.filter_by(user_id=user.id).delete()
            
            # Store username for success message before deletion
            username = user.username
            
            # Finally delete the user
            db.session.delete(user)
        
        db.session.commit()
        
        # Handle different action messages
        if action == 'delete':
            message = f'User {username} has been deleted successfully.'
        else:
            message = f'User {user.username} has been updated successfully.'
            
        return jsonify({
            'success': True,
            'message': message
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to update user: {str(e)}'
        }), 500

@limiter.limit(get_rate_limit_string())
@login_required
@admin_required
def add_user():
    try:
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'user')
        
        # Validate password
        if not is_valid_password(password):
            return jsonify({
                'success': False,
                'message': 'Password must be at least 8 characters and include uppercase, lowercase, number, and special character.'
            }), 400
        
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
