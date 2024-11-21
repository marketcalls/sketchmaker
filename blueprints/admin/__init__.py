from flask import Blueprint

# Create the main admin blueprint
admin = Blueprint('admin', __name__, url_prefix='/admin')

# Import route functions
from .user_routes import manage, update_user, add_user, search_users
from .email_routes import email_settings, update_email_settings, test_email_settings
from .system_routes import update_settings
from .auth_routes import auth_settings, update_auth_settings

# Register routes directly on the admin blueprint
admin.add_url_rule('/manage', 'manage', manage)
admin.add_url_rule('/manage/user/<int:user_id>', 'update_user', update_user, methods=['POST'])
admin.add_url_rule('/manage/add_user', 'add_user', add_user, methods=['POST'])
admin.add_url_rule('/manage/search', 'search_users', search_users)

admin.add_url_rule('/manage/email', 'email_settings', email_settings)
admin.add_url_rule('/manage/email/update', 'update_email_settings', update_email_settings, methods=['POST'])
admin.add_url_rule('/manage/email/test', 'test_email_settings', test_email_settings, methods=['POST'])

admin.add_url_rule('/manage/settings', 'update_settings', update_settings, methods=['POST'])

# Register auth settings routes
admin.add_url_rule('/manage/auth', 'auth_settings', auth_settings)
admin.add_url_rule('/manage/auth/update', 'update_auth_settings', update_auth_settings, methods=['POST'])
