from flask import Blueprint, render_template, jsonify, request, current_app, url_for
from flask_login import login_required, current_user
from extensions import limiter, get_rate_limit_string, db
from .clients import init_fal_client
import os
import json
import requests
from datetime import datetime
from werkzeug.utils import secure_filename
import zipfile
import io
import base64
import fal_client
from models import TrainingHistory
import traceback
import hmac
import hashlib

training_bp = Blueprint('training', __name__)

def generate_webhook_secret():
    """Generate a unique webhook secret for this training job"""
    return os.urandom(24).hex()

def verify_webhook_signature(secret, signature, body):
    """Verify the webhook signature"""
    expected = hmac.new(
        secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

def allowed_file(filename):
    """Check if file has an allowed extension"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_zip_archive(files):
    """Create a ZIP archive from uploaded files"""
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                zf.writestr(filename, file.read())
    memory_file.seek(0)
    return memory_file

@training_bp.route('/training')
@limiter.limit(get_rate_limit_string())
@login_required
def training_page():
    try:
        history = TrainingHistory.query.filter_by(user_id=current_user.id)\
                                    .order_by(TrainingHistory.created_at.desc())\
                                    .all()
        return render_template('training.html', history=history)
    except Exception as e:
        current_app.logger.error(f"Error in training_page: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@training_bp.route('/api/training/upload', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def upload_training_images():
    try:
        if 'files[]' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        files = request.files.getlist('files[]')
        current_app.logger.info(f"Received {len(files)} files")

        if not 5 <= len(files) <= 20:
            return jsonify({'error': 'Please upload between 5 and 20 images'}), 400

        try:
            zip_file = create_zip_archive(files)
            zip_base64 = base64.b64encode(zip_file.read()).decode('utf-8')
            data_url = f"data:application/zip;base64,{zip_base64}"
            return jsonify({
                'status': 'success',
                'images_data_url': data_url
            })
        except Exception as e:
            current_app.logger.error(f"Upload error: {str(e)}\n{traceback.format_exc()}")
            return jsonify({'error': str(e)}), 500

    except Exception as e:
        current_app.logger.error(f"Upload error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@training_bp.route('/api/training/start', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def start_training():
    try:
        if not current_user.has_required_api_keys():
            return jsonify({'error': 'Please add your API keys in settings'}), 400

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        required_fields = ['images_data_url', 'trigger_word']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({'error': f'Missing fields: {", ".join(missing_fields)}'}), 400

        # Initialize FAL client
        try:
            client = init_fal_client()
        except Exception as e:
            current_app.logger.error(f"FAL client error: {str(e)}\n{traceback.format_exc()}")
            return jsonify({'error': 'Failed to initialize FAL client'}), 500

        # Generate webhook secret and URL
        webhook_secret = generate_webhook_secret()
        webhook_url = url_for('training.webhook', _external=True)

        # Create training record
        training_record = TrainingHistory(
            user_id=current_user.id,
            training_id=os.urandom(16).hex(),
            trigger_word=data['trigger_word'],
            status='in_progress',
            logs='',
            webhook_secret=webhook_secret
        )
        db.session.add(training_record)
        db.session.commit()

        # Prepare training arguments
        training_args = {
            'images_data_url': data['images_data_url'],
            'trigger_word': data['trigger_word'],
            'create_masks': data.get('create_masks', True),
            'steps': data.get('steps', 1000),
            'data_archive_format': 'zip',
            'webhook': {
                'url': webhook_url,
                'secret': webhook_secret
            }
        }

        try:
            # Start training with webhook
            result = client.submit(
                "fal-ai/flux-lora-fast-training",
                training_args
            )
            
            # Store request ID in queue_id
            training_record.queue_id = result.request_id
            db.session.commit()

            return jsonify({
                'status': 'success',
                'message': 'Training started successfully',
                'training_id': training_record.training_id
            })

        except Exception as e:
            current_app.logger.error(f"Training error: {str(e)}\n{traceback.format_exc()}")
            training_record.status = 'failed'
            training_record.logs = (training_record.logs or '') + f"\nError: {str(e)}"
            db.session.commit()
            return jsonify({'error': str(e)}), 500

    except Exception as e:
        current_app.logger.error(f"Training error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@training_bp.route('/api/training/webhook', methods=['POST'])
def webhook():
    try:
        # Get webhook signature from headers
        signature = request.headers.get('X-FAL-Signature')
        if not signature:
            return jsonify({'error': 'No signature provided'}), 400

        # Get request body as bytes
        body = request.get_data()
        
        # Parse the JSON data
        data = request.get_json()
        if not data or 'queue_id' not in data:
            return jsonify({'error': 'Invalid webhook data'}), 400

        # Find the training record
        training = TrainingHistory.query.filter_by(queue_id=data['queue_id']).first()
        if not training:
            return jsonify({'error': 'Training record not found'}), 404

        # Verify webhook signature
        if not verify_webhook_signature(training.webhook_secret, signature, body):
            return jsonify({'error': 'Invalid signature'}), 401

        # Update training record based on webhook data
        if data.get('status') == 'completed':
            training.status = 'completed'
            training.completed_at = datetime.utcnow()
            training.result = data.get('result', {})
            training.config_url = data.get('result', {}).get('config_file', {}).get('url')
            training.weights_url = data.get('result', {}).get('diffusers_lora_file', {}).get('url')
        elif data.get('status') == 'failed':
            training.status = 'failed'
            training.logs = (training.logs or '') + f"\nError: {data.get('error', 'Unknown error')}"
        elif data.get('status') == 'in_progress':
            if 'logs' in data:
                training.logs = (training.logs or '') + f"\n{data['logs']}"

        db.session.commit()
        return jsonify({'status': 'success'}), 200

    except Exception as e:
        current_app.logger.error(f"Webhook error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@training_bp.route('/api/training/<training_id>')
@limiter.limit(get_rate_limit_string())
@login_required
def get_training_status(training_id):
    try:
        training = TrainingHistory.query.filter_by(
            user_id=current_user.id,
            training_id=training_id
        ).first_or_404()
        
        return jsonify({
            'status': training.status,
            'logs': training.logs,
            'config_url': training.config_url,
            'weights_url': training.weights_url,
            'trigger_word': training.trigger_word,
            'completed_at': training.completed_at.isoformat() if training.completed_at else None,
            'result': training.result
        })
    except Exception as e:
        current_app.logger.error(f"Status error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@training_bp.errorhandler(500)
def handle_500(error):
    current_app.logger.error(f"Internal error: {str(error)}\n{traceback.format_exc()}")
    return jsonify({'error': 'Internal server error'}), 500

@training_bp.errorhandler(404)
def handle_404(error):
    return jsonify({'error': 'Not found'}), 404
