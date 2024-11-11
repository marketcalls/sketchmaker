from flask import Blueprint, render_template
from flask_login import login_required
from datetime import datetime

core_bp = Blueprint('core', __name__)

@core_bp.route('/')
def index():
    return render_template('index.html', current_year=datetime.now().year)

@core_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')
