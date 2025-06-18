from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, SystemSettings, EmailSettings, PasswordResetOTP, AuthSettings, SubscriptionPlanModel, UserSubscription
from extensions import limiter, get_rate_limit_string
from jinja2 import Template
import os
from datetime import datetime
import re
import requests

auth_bp = Blueprint('auth', __name__)

def is_valid_password(password):
    """Check if password meets requirements"""
    # Must have at least 8 characters, one uppercase, one lowercase, one number, and one special character
    pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
    return bool(re.match(pattern, password))

def assign_free_plan(user):
    """Assign free plan to a new user"""
    try:
        # Get the free plan
        free_plan = SubscriptionPlanModel.query.filter_by(name='free').first()
        
        if not free_plan:
            print("Warning: Free plan not found. Creating default free plan.")
            # Initialize default plans if they don't exist
            SubscriptionPlanModel.initialize_default_plans()
            free_plan = SubscriptionPlanModel.query.filter_by(name='free').first()
        
        if free_plan:
            # Create subscription for the user
            subscription = UserSubscription(
                user_id=user.id,
                plan_id=free_plan.id,
                credits_remaining=free_plan.monthly_credits,
                credits_used_this_month=0,
                subscription_start=datetime.utcnow()
            )
            db.session.add(subscription)
            db.session.commit()
            print(f"Assigned free plan to user {user.username}")
            return True
        else:
            print("Error: Could not create or find free plan")
            return False
    except Exception as e:
        print(f"Error assigning free plan to user {user.username}: {str(e)}")
        db.session.rollback()
        return False

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

{"🎉 You've been automatically enrolled in our Free Plan with 3 credits to get you started!" if not requires_approval else ""}

With Sketch Maker AI, you can:
- Generate stunning artwork using multiple AI models (1 credit each)
- Create custom banners with various styles (0.5 credits each)
- Edit images with Magix AI tools (1 credit each)
- Train your own custom models (40 credits each)
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

def send_reset_password_email(user, otp):
    """Send password reset email with OTP"""
    try:
        email_settings = EmailSettings.get_settings()
        if not email_settings.is_active:
            return False, "Email service is not active"

        # Get the reset password email template
        template_path = os.path.join('templates', 'email', 'reset_password.html')
        with open(template_path, 'r') as f:
            template_content = f.read()

        # Create template object
        template = Template(template_content)

        # Render the template with user data
        html_content = template.render(
            username=user.username,
            email=user.email,
            otp=otp.otp,
            year=datetime.utcnow().year
        )

        # Create plain text version
        text_content = f"""
Password Reset Request - Sketch Maker AI

Hello {user.username},

We received a request to reset your password for your Sketch Maker AI account.
Your one-time password (OTP) is: {otp.otp}

Please use this OTP to reset your password. This code will expire in 15 minutes.

If you didn't request this password reset, please ignore this email or contact support if you have concerns about your account's security.

For security reasons, please do not share this OTP with anyone.

Best regards,
The Sketch Maker AI Team
        """

        # Send the email
        success, message = email_settings.send_email(
            to_email=user.email,
            subject="Reset Your Password - Sketch Maker AI",
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

    # Get auth settings
    auth_settings = AuthSettings.get_settings()

    # If both auth methods are disabled, show error
    if not auth_settings.regular_auth_enabled and not auth_settings.google_auth_enabled:
        flash('Authentication is currently disabled. Please contact an administrator.')
        return render_template('auth/login.html', auth_settings=auth_settings)

    if request.method == 'POST':
        # Only process form if regular auth is enabled
        if not auth_settings.regular_auth_enabled:
            flash('Regular authentication is disabled.')
            return redirect(url_for('auth.login'))

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

    return render_template('auth/login.html', auth_settings=auth_settings)

@auth_bp.route('/auth/google/login')
@limiter.limit(get_rate_limit_string())
def google_login():
    # Get auth settings
    auth_settings = AuthSettings.get_settings()
    if not auth_settings.google_auth_enabled:
        flash('Google authentication is disabled.')
        return redirect(url_for('auth.login'))

    # Construct the callback URL
    callback_url = url_for('auth.google_callback', _external=True)

    # Google OAuth configuration
    params = {
        'client_id': auth_settings.google_client_id,
        'redirect_uri': callback_url,
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'offline',
        'prompt': 'consent',
    }
    
    # Redirect to Google's OAuth page
    auth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + '&'.join([f'{k}={v}' for k, v in params.items()])
    return redirect(auth_url)

@auth_bp.route('/auth/google/callback')
@limiter.limit(get_rate_limit_string())
def google_callback():
    # Get auth settings
    auth_settings = AuthSettings.get_settings()
    if not auth_settings.google_auth_enabled:
        flash('Google authentication is disabled.')
        return redirect(url_for('auth.login'))

    error = request.args.get('error')
    if error:
        flash('Google authentication failed: ' + error)
        return redirect(url_for('auth.login'))

    code = request.args.get('code')
    if not code:
        flash('Authentication failed: No authorization code received')
        return redirect(url_for('auth.login'))

    try:
        # Exchange code for tokens
        callback_url = url_for('auth.google_callback', _external=True)
        token_url = 'https://oauth2.googleapis.com/token'
        token_data = {
            'code': code,
            'client_id': auth_settings.google_client_id,
            'client_secret': auth_settings.google_client_secret,
            'redirect_uri': callback_url,
            'grant_type': 'authorization_code'
        }

        # Get user info from Google
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()

        userinfo_url = 'https://www.googleapis.com/oauth2/v3/userinfo'
        headers = {'Authorization': f'Bearer {tokens["access_token"]}'}
        userinfo_response = requests.get(userinfo_url, headers=headers)
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

        # Get or create user
        user = User.query.filter_by(email=userinfo['email']).first()
        if not user:
            # Create new user
            username = userinfo['email'].split('@')[0]
            base_username = username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1

            # Get system settings for manual approval
            settings = SystemSettings.get_settings()
            requires_approval = settings.require_manual_approval and User.query.first() is not None

            user = User(
                email=userinfo['email'],
                username=username,
                password_hash='',  # No password for Google auth users
                google_id=userinfo['sub'],
                is_active=True,
                is_approved=not requires_approval,  # Set based on system settings
                role='user'
            )
            db.session.add(user)
            db.session.commit()

            # Assign free plan to new user
            assign_free_plan(user)

            # Send welcome email
            email_success, email_message = send_welcome_email(user, requires_approval)
            if not email_success:
                print(f"Failed to send welcome email: {email_message}")
                # Don't show email failure to user, just log it

        elif not user.google_id:
            # Link existing user to Google
            user.google_id = userinfo['sub']
            db.session.commit()

        # Check if user is approved and active
        if not user.is_approved:
            flash('Your account is pending approval. Please wait for administrator approval.')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            flash('Your account has been deactivated. Please contact an administrator.')
            return redirect(url_for('auth.login'))

        # Log in the user
        login_user(user)
        return redirect(url_for('core.dashboard'))

    except Exception as e:
        flash('Failed to authenticate with Google: ' + str(e))
        return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit(get_rate_limit_string())
def register():
    # Redirect to dashboard if user is already logged in
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))

    # Get auth settings
    auth_settings = AuthSettings.get_settings()

    # If both auth methods are disabled, show error
    if not auth_settings.regular_auth_enabled and not auth_settings.google_auth_enabled:
        flash('Registration is currently disabled. Please contact an administrator.')
        return render_template('auth/register.html', auth_settings=auth_settings)

    if request.method == 'POST':
        # Only process form if regular auth is enabled
        if not auth_settings.regular_auth_enabled:
            flash('Regular registration is disabled.')
            return redirect(url_for('auth.register'))

        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')

        # Validate password
        if not is_valid_password(password):
            flash('Password must be at least 8 characters and include uppercase, lowercase, number, and special character.')
            return redirect(url_for('auth.register'))

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

        # Assign free plan to new user (except for first user who becomes superadmin)
        if not is_first_user:
            assign_free_plan(new_user)

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

    return render_template('auth/register.html', auth_settings=auth_settings)

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit(get_rate_limit_string())
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate OTP
            otp = PasswordResetOTP.generate_otp(user.id)
            
            # Send reset email
            email_success, email_message = send_reset_password_email(user, otp)
            if not email_success:
                print(f"Failed to send reset email: {email_message}")
                flash('Failed to send reset email. Please try again later.')
                return redirect(url_for('auth.forgot_password'))
            
            # Store email in session for the reset page
            session['reset_email'] = email
            flash('Password reset code has been sent to your email.')
            return redirect(url_for('auth.reset_password'))
        else:
            # Don't reveal if email exists
            flash('If an account exists with this email, a password reset code will be sent.')
            return redirect(url_for('auth.forgot_password'))
    
    return render_template('auth/forgot_password.html')

@auth_bp.route('/reset-password', methods=['GET', 'POST'])
@limiter.limit(get_rate_limit_string())
def reset_password():
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))
    
    # Get email from session
    email = session.get('reset_email')
    if not email and request.method == 'GET':
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        otp_value = request.form.get('otp')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Invalid request. Please try again.')
            return redirect(url_for('auth.forgot_password'))
        
        # Verify OTP
        otp = PasswordResetOTP.verify_otp(user.id, otp_value)
        if not otp:
            flash('Invalid or expired code. Please request a new one.')
            return redirect(url_for('auth.forgot_password'))
        
        # Validate password
        if not is_valid_password(password):
            flash('Password must be at least 8 characters and include uppercase, lowercase, number, and special character.')
            return redirect(url_for('auth.reset_password'))
        
        # Update password
        user.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        otp.use()  # Mark OTP as used
        db.session.commit()
        
        # Clear session
        session.pop('reset_email', None)
        
        flash('Your password has been reset successfully. Please login with your new password.')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', email=email)

@auth_bp.route('/logout')
@limiter.limit(get_rate_limit_string())
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('auth.login'))
