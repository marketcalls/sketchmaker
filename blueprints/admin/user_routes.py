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
                # Delete the actual image files (both PNG and WebP versions)
                base_filename = os.path.splitext(image.filename)[0]
                png_path = os.path.join('static', 'images', f'{base_filename}.png')
                webp_path = os.path.join('static', 'images', f'{base_filename}.webp')
                
                # Try to delete both file versions if they exist
                if os.path.exists(png_path):
                    os.remove(png_path)
                if os.path.exists(webp_path):
                    os.remove(webp_path)
                
                # Delete the image record
                db.session.delete(image)
            
            # Delete all user's training history
            TrainingHistory.query.filter_by(user_id=user.id).delete()
            
            # Delete associated password reset OTPs
            PasswordResetOTP.query.filter_by(user_id=user.id).delete()
            
            # Clear provider and model selections
            user.selected_provider_id = None
            user.selected_model_id = None
            
            # Clear API keys
            user.openai_api_key = None
            user.anthropic_api_key = None
            user.gemini_api_key = None
            user.groq_api_key = None
            user.fal_key = None
            
            # Clear OAuth info
            user.google_id = None
            
            # Finally delete the user
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
