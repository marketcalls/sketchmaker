from extensions import db
from flask_login import UserMixin
from datetime import datetime
import os
from PIL import Image as PILImage
import smtplib
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from botocore.config import Config
import json
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlencode

class APIProvider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # e.g. "OpenAI", "Anthropic", "Google Gemini", "Groq"
    is_active = db.Column(db.Boolean, default=True)
    models = db.relationship('AIModel', backref='provider', lazy=True)

class AIModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g. "gpt-4o", "claude-3-sonnet", "llama-3.1-8b-instant"
    provider_id = db.Column(db.Integer, db.ForeignKey('api_provider.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmailSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(20), nullable=False)  # 'smtp' or 'ses'
    is_active = db.Column(db.Boolean, default=False)
    
    # SMTP Settings
    smtp_host = db.Column(db.String(255))
    smtp_port = db.Column(db.Integer)
    smtp_username = db.Column(db.String(255))
    smtp_password = db.Column(db.String(255))
    smtp_use_tls = db.Column(db.Boolean, default=True)
    
    # Amazon SES Settings
    aws_access_key = db.Column(db.String(255))
    aws_secret_key = db.Column(db.String(255))
    aws_region = db.Column(db.String(50))
    
    # Common Settings
    from_email = db.Column(db.String(255))
    from_name = db.Column(db.String(255))
    
    # Last test result
    last_test_date = db.Column(db.DateTime)
    last_test_success = db.Column(db.Boolean)
    last_test_message = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def _get_ses_endpoint(self):
        """Get the SES endpoint URL for the configured region"""
        return f"https://email.{self.aws_region}.amazonaws.com"

    def _sign_ses_request(self, request_params):
        """Sign an SES request with AWS Signature Version 4"""
        credentials = Credentials(
            access_key=self.aws_access_key,
            secret_key=self.aws_secret_key
        )

        endpoint = self._get_ses_endpoint()
        request = AWSRequest(
            method='POST',
            url=endpoint,
            data=urlencode(request_params),
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Host': f"email.{self.aws_region}.amazonaws.com"
            }
        )

        SigV4Auth(credentials, "ses", self.aws_region).add_auth(request)
        return dict(request.headers), request.body

    def _send_ses_raw(self, request_params):
        """Send a raw SES request with proper v4 signature"""
        if not all([self.aws_access_key, self.aws_secret_key, self.aws_region]):
            raise ValueError("Missing AWS credentials or region")

        headers, body = self._sign_ses_request(request_params)
        endpoint = self._get_ses_endpoint()

        response = requests.post(
            endpoint,
            data=body,
            headers=headers,
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(f"SES request failed: {response.text}")
        
        return response.text

    def test_connection(self, test_email):
        """Test email connection with current settings"""
        try:
            if self.provider == 'smtp':
                return self._test_smtp(test_email)
            elif self.provider == 'ses':
                return self._test_ses(test_email)
            return False, "Invalid provider"
        except Exception as e:
            return False, str(e)

    def _test_smtp(self, test_email):
        """Test SMTP connection"""
        try:
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port)
            if self.smtp_use_tls:
                smtp.starttls()
            smtp.login(self.smtp_username, self.smtp_password)
            
            msg = MIMEMultipart()
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = test_email
            msg['Subject'] = "Test Email from Sketch Maker AI"
            
            body = "This is a test email from Sketch Maker AI. If you received this, your email settings are working correctly!"
            msg.attach(MIMEText(body, 'plain'))
            
            smtp.send_message(msg)
            smtp.quit()
            return True, "Test email sent successfully"
        except Exception as e:
            return False, f"SMTP test failed: {str(e)}"

    def _test_ses(self, test_email):
        """Test Amazon SES connection with v4 signature"""
        try:
            params = {
                'Action': 'SendEmail',
                'Source': f"{self.from_name} <{self.from_email}>",
                'Destination.ToAddresses.member.1': test_email,
                'Message.Subject.Data': 'Test Email from Sketch Maker AI',
                'Message.Body.Text.Data': 'This is a test email from Sketch Maker AI. If you received this, your SES settings are working correctly!',
                'Version': '2010-12-01'
            }

            response = self._send_ses_raw(params)
            return True, "Test email sent successfully"
        except Exception as e:
            return False, f"SES test failed: {str(e)}"

    def send_email(self, to_email, subject, html_content, text_content=None):
        """Send email using configured provider"""
        if not self.is_active:
            return False, "Email service is not active"
            
        try:
            if self.provider == 'smtp':
                return self._send_smtp(to_email, subject, html_content, text_content)
            elif self.provider == 'ses':
                return self._send_ses(to_email, subject, html_content, text_content)
            return False, "Invalid provider"
        except Exception as e:
            return False, str(e)

    def _send_smtp(self, to_email, subject, html_content, text_content=None):
        """Send email via SMTP"""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            
            if text_content:
                msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port)
            if self.smtp_use_tls:
                smtp.starttls()
            smtp.login(self.smtp_username, self.smtp_password)
            smtp.send_message(msg)
            smtp.quit()
            return True, "Email sent successfully"
        except Exception as e:
            return False, f"Failed to send email: {str(e)}"

    def _send_ses(self, to_email, subject, html_content, text_content=None):
        """Send email via Amazon SES with v4 signature"""
        try:
            params = {
                'Action': 'SendEmail',
                'Source': f"{self.from_name} <{self.from_email}>",
                'Destination.ToAddresses.member.1': to_email,
                'Message.Subject.Data': subject,
                'Message.Body.Html.Data': html_content,
                'Version': '2010-12-01'
            }

            if text_content:
                params['Message.Body.Text.Data'] = text_content

            response = self._send_ses_raw(params)
            return True, "Email sent successfully"
        except Exception as e:
            return False, f"Failed to send email: {str(e)}"

    @staticmethod
    def get_settings():
        """Get or create email settings"""
        settings = EmailSettings.query.first()
        if not settings:
            settings = EmailSettings(
                provider='smtp',
                is_active=False,
                from_name='Sketch Maker AI',
                from_email='noreply@example.com'
            )
            db.session.add(settings)
            db.session.commit()
        return settings

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(20), default='user')  # 'superadmin', 'admin' or 'user'
    is_active = db.Column(db.Boolean, default=True)
    is_approved = db.Column(db.Boolean, default=True)  # For manual approval process
    images = db.relationship('Image', backref='user', lazy=True)
    training_history = db.relationship('TrainingHistory', backref='user', lazy=True)
    
    # API Provider settings
    selected_provider_id = db.Column(db.Integer, db.ForeignKey('api_provider.id'))
    selected_model_id = db.Column(db.Integer, db.ForeignKey('ai_model.id'))
    
    # API Keys for different providers
    openai_api_key = db.Column(db.String(255))
    anthropic_api_key = db.Column(db.String(255))
    gemini_api_key = db.Column(db.String(255))
    groq_api_key = db.Column(db.String(255))
    fal_key = db.Column(db.String(255))

    def get_api_keys(self):
        """Get user's API keys"""
        return {
            'openai_api_key': self.openai_api_key,
            'anthropic_api_key': self.anthropic_api_key,
            'gemini_api_key': self.gemini_api_key,
            'groq_api_key': self.groq_api_key,
            'fal_key': self.fal_key
        }

    def get_selected_provider_key(self):
        """Get the API key for the currently selected provider"""
        provider = APIProvider.query.get(self.selected_provider_id)
        if provider:
            if provider.name == 'OpenAI':
                return self.openai_api_key
            elif provider.name == 'Anthropic':
                return self.anthropic_api_key
            elif provider.name == 'Google Gemini':
                return self.gemini_api_key
            elif provider.name == 'Groq':
                return self.groq_api_key
        return None

    def has_required_api_keys(self):
        """Check if user has both required API keys"""
        return bool(self.get_selected_provider_key() and self.fal_key)

    def is_admin(self):
        """Check if user is an admin or superadmin"""
        return self.role in ['admin', 'superadmin']

    def is_superadmin(self):
        """Check if user is a superadmin"""
        return self.role == 'superadmin'

    @staticmethod
    def get_first_user():
        """Get the first user in the database"""
        return User.query.order_by(User.id.asc()).first()

    @staticmethod
    def get_total_count():
        """Get total number of users"""
        return User.query.count()

    @staticmethod
    def search_users(query):
        """Search users by username or email"""
        return User.query.filter(
            (User.username.ilike(f'%{query}%')) |
            (User.email.ilike(f'%{query}%'))
        ).all()

class SystemSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    require_manual_approval = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get_settings():
        """Get or create system settings"""
        settings = SystemSettings.query.first()
        if not settings:
            settings = SystemSettings()
            db.session.add(settings)
            db.session.commit()
        return settings

class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    art_style = db.Column(db.String(100))
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey('api_provider.id'))
    model_id = db.Column(db.Integer, db.ForeignKey('ai_model.id'))

    @property
    def dimensions(self):
        return {
            'width': self.width,
            'height': self.height
        }

    def get_dimensions(self):
        """Get image dimensions from file if not stored in database"""
        if not self.width or not self.height:
            try:
                filepath = os.path.join('static', 'images', self.filename)
                with PILImage.open(filepath) as img:
                    self.width, self.height = img.size
                    db.session.commit()
            except Exception as e:
                print(f"Error getting image dimensions: {str(e)}")
        return self.dimensions

    @property
    def file_path(self):
        return os.path.join('static', 'images', self.filename)

    def get_url(self, format='png'):
        base_filename = os.path.splitext(self.filename)[0]
        return f'/static/images/{base_filename}.{format}'

class TrainingHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    training_id = db.Column(db.String(32), unique=True, nullable=False)
    queue_id = db.Column(db.String(100), unique=True)  # FAL queue ID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    trigger_word = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, failed
    logs = db.Column(db.Text)
    result = db.Column(db.JSON)
    config_url = db.Column(db.String(500))
    weights_url = db.Column(db.String(500))
    webhook_secret = db.Column(db.String(48))  # For webhook verification
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'training_id': self.training_id,
            'queue_id': self.queue_id,
            'trigger_word': self.trigger_word,
            'status': self.status,
            'logs': self.logs,
            'config_url': self.config_url,
            'weights_url': self.weights_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'result': self.result
        }
