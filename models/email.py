from extensions import db
from datetime import datetime
import smtplib
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from urllib.parse import urlencode
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

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
