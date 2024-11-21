import re
import os
from datetime import datetime
from jinja2 import Template
from flask import url_for

def is_valid_password(password):
    """Check if password meets requirements"""
    # Must have at least 8 characters, one uppercase, one lowercase, one number, and one special character
    pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
    return bool(re.match(pattern, password))

def send_approval_email(user):
    """Send approval email to user"""
    try:
        from models import EmailSettings
        email_settings = EmailSettings.get_settings()
        if not email_settings.is_active:
            return False, "Email service is not active"

        # Get the approval email template
        template_path = os.path.join('templates', 'email', 'approval.html')
        with open(template_path, 'r') as f:
            template_content = f.read()

        # Create template object
        template = Template(template_content)

        # Render the template with user data
        html_content = template.render(
            username=user.username,
            email=user.email,
            login_url=url_for('auth.login', _external=True),
            year=datetime.utcnow().year
        )

        # Create plain text version
        text_content = f"""
Account Approved - Sketch Maker AI

Hello {user.username},

Great news! Your Sketch Maker AI account has been approved by an administrator. You can now log in and start using all the features of our platform.

What you can do now:
- Generate stunning artwork using multiple AI models
- Create custom banners with various styles
- Train your own custom models
- Manage your creations in a personal gallery

You can log in at: {url_for('auth.login', _external=True)}

If you have any questions or need assistance, please don't hesitate to contact our support team.

Best regards,
The Sketch Maker AI Team
        """

        # Send the email
        success, message = email_settings.send_email(
            to_email=user.email,
            subject="Your Sketch Maker AI Account Has Been Approved",
            html_content=html_content,
            text_content=text_content
        )

        return success, message
    except Exception as e:
        return False, str(e)
