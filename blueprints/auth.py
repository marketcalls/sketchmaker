from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, SystemSettings, EmailSettings
from extensions import limiter, get_rate_limit_string
from jinja2 import Template
import os
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

def send_welcome_email(user, requires_approval=False):
    """Send welcome email to newly registered user"""
    try:
        email_settings = EmailSettings.get_settings()
        if not email_settings.is_active:
            return False, "Email service is not active"

        # Get the welcome email template
        template_path = os.path.join('templates', 'email', 'welcome.html')
        with open(template_path, 'r') as f:
            template_content = f.read()

        # Create template object
        template = Template(template_content)

        # Render the template with user data
        html_content = template.render(
            username=user.username,
            email=user.email,
            requires_approval=requires_approval,
            login_url=url_for('auth.login', _external=True),
            year=datetime.utcnow().year
        )

        # Create plain text version
        text_content = f"""
Welcome to Sketch Maker AI!

Hello {user.username},

Your account has been successfully created{"and is pending administrator approval" if requires_approval else ""}.

With Sketch Maker AI, you can:
- Generate stunning artwork using multiple AI models
- Create custom banners with various styles
- Train your own custom models
- Manage your creations in a personal gallery

{"You will receive another email once your account has been approved by an administrator." if requires_approval else "You can now log in and start creating!"}

Best regards,
The Sketch Maker AI Team
        """

        # Send the email
        success, message = email_settings.send_email(
            to_email=user.email,
            subject="Welcome to Sketch Maker AI",
            html_content=html_content,
            text_content=text_content
        )

        return success, message
    except Exception as e:
        return False, str(e)

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(get_rate_limit_string())
def login():
    # Redirect to dashboard if user is already logged in
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash('Please check your login details and try again.')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            flash('Your account has been deactivated. Please contact an administrator.')
            return redirect(url_for('auth.login'))

        if not user.is_approved:
            flash('Your account is pending approval. Please wait for administrator approval.')
            return redirect(url_for('auth.login'))

        login_user(user, remember=remember)
        next_page = request.args.get('next')
        
        # Redirect admin users to manage page if they're trying to access it
        if user.is_admin() and next_page and 'manage' in next_page:
            return redirect(next_page)
        return redirect(next_page or url_for('core.dashboard'))

    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit(get_rate_limit_string())
def register():
    # Redirect to dashboard if user is already logged in
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')

        # Check if user already exists
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email address already exists')
            return redirect(url_for('auth.register'))

        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists')
            return redirect(url_for('auth.register'))

        # Check if this is the first user
        is_first_user = User.query.first() is None

        # Get system settings for manual approval
        settings = SystemSettings.get_settings()
        requires_approval = settings.require_manual_approval and not is_first_user

        # Create new user
        new_user = User(
            email=email,
            username=username,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            role='superadmin' if is_first_user else 'user',  # First user becomes superadmin
            is_active=True,
            is_approved=not requires_approval  # First user or auto-approved
        )

        db.session.add(new_user)
        db.session.commit()

        # Send welcome email
        email_success, email_message = send_welcome_email(new_user, requires_approval)
        if not email_success:
            print(f"Failed to send welcome email: {email_message}")
            # Don't show email failure to user, just log it
        
        if is_first_user:
            flash('You have been registered as the super administrator.')
            return redirect(url_for('auth.login'))
        elif requires_approval:
            flash('Registration successful. Please wait for administrator approval.')
            return redirect(url_for('auth.login'))
        else:
            flash('Registration successful. Please login.')
            return redirect(url_for('auth.login'))

    return render_template('auth/register.html')

@auth_bp.route('/logout')
@limiter.limit(get_rate_limit_string())
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('auth.login'))
