from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

core_bp = Blueprint('core', __name__)

@core_bp.route('/')
def index():
    return render_template('index.html')

@core_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')
