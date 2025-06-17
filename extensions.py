from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
csrf = CSRFProtect()

def get_rate_limit_string():
    """Get rate limit string from environment variables"""
    per_minute = os.getenv('RATE_LIMIT_PER_MINUTE', '20')
    per_hour = os.getenv('RATE_LIMIT_PER_HOUR', '200')
    per_day = os.getenv('RATE_LIMIT_PER_DAY', '1000')
    return f"{per_minute} per minute;{per_hour} per hour;{per_day} per day"

# Initialize limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[get_rate_limit_string()],
    storage_uri=f"{os.getenv('RATE_LIMIT_STORAGE', 'memory')}://"
)
