from flask import Blueprint, render_template, jsonify, request, current_app
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

training_bp = Blueprint('training', __name__)

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

def allowed_file(filename):
    """Check if file has an allowed extension"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@training_bp.route('/training')
@limiter.limit(get_rate_limit_string())
@login_required
def training_page():
    # Get user's training history
    history = TrainingHistory.query.filter_by(user_id=current_user.id)\
                                 .order_by(TrainingHistory.created_at.desc())\
                                 .all()
    return render_template('training.html', history=history)

@training_bp.route('/api/training/history')
@limiter.limit(get_rate_limit_string())
@login_required
def get_training_history():
    history = TrainingHistory.query.filter_by(user_id=current_user.id)\
                                 .order_by(TrainingHistory.created_at.desc())\
                                 .all()
    return jsonify([h.to_dict() for h in history])

@training_bp.route('/api/training/upload', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def upload_training_images():
    try:
        if 'files[]' not in request.files:
            return jsonify({
                'error': 'No files provided',
                'details': 'Please select files to upload'
            }), 400

        files = request.files.getlist('files[]')
        if not 5 <= len(files) <= 20:
            return jsonify({
                'error': 'Invalid number of files',
                'details': 'Please upload between 5 and 20 images'
            }), 400

        # Create ZIP archive
        zip_file = create_zip_archive(files)
        
        # Convert to base64
        zip_base64 = base64.b64encode(zip_file.read()).decode('utf-8')
        
        # Create data URL
        data_url = f"data:application/zip;base64,{zip_base64}"
        
        return jsonify({
            'status': 'success',
            'message': 'Files uploaded successfully',
            'images_data_url': data_url
        })

    except Exception as e:
        print(f"Upload error: {str(e)}")
        return jsonify({
            'error': 'Upload failed',
            'details': str(e)
        }), 500

@training_bp.route('/api/training/start', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def start_training():
    try:
        if not current_user.has_required_api_keys():
            return jsonify({
                'error': 'API keys required',
                'details': 'Please add your API keys in settings'
            }), 400

        data = request.get_json()
        if not data:
            return jsonify({
                'error': 'No data provided',
                'details': 'Request body is required'
            }), 400

        required_fields = ['images_data_url', 'trigger_word']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'error': 'Missing required fields',
                'details': f'The following fields are required: {", ".join(missing_fields)}'
            }), 400

        # Initialize FAL client
        client = init_fal_client()

        # Create training history record
        training_record = TrainingHistory(
            user_id=current_user.id,
            training_id=os.urandom(16).hex(),
            trigger_word=data['trigger_word'],
            status='in_progress',
            logs=''
        )
        db.session.add(training_record)
        db.session.commit()

        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    print(f"Training log: {log['message']}")
                    # Append log to training record
                    training_record.logs = (training_record.logs or '') + f"{log['message']}\n"
                    db.session.commit()

        # Prepare training arguments
        training_args = {
            'images_data_url': data['images_data_url'],
            'trigger_word': data['trigger_word'],
            'create_masks': data.get('create_masks', True),
            'steps': data.get('steps', 1000),
            'data_archive_format': 'zip'
        }

        print("Starting training with arguments:", training_args)

        # Start training
        result = client.subscribe(
            "fal-ai/flux-lora-fast-training",
            arguments=training_args,
            with_logs=True,
            on_queue_update=on_queue_update
        )

        print("Training result:", result)

        if not result:
            training_record.status = 'failed'
            db.session.commit()
            return jsonify({
                'error': 'Training failed',
                'details': 'No result returned from training'
            }), 500

        # Update training record with results
        training_record.status = 'completed'
        training_record.completed_at = datetime.utcnow()
        training_record.result = result
        training_record.config_url = result['config_file']['url']
        training_record.weights_url = result['diffusers_lora_file']['url']
        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': 'Training completed successfully',
            'training_id': training_record.training_id,
            'result': result
        })

    except Exception as e:
        print(f"Training error: {str(e)}")
        if 'training_record' in locals():
            training_record.status = 'failed'
            training_record.logs = (training_record.logs or '') + f"\nError: {str(e)}"
            db.session.commit()
        return jsonify({
            'error': 'Training failed',
            'details': str(e)
        }), 500

@training_bp.route('/api/training/<training_id>')
@limiter.limit(get_rate_limit_string())
@login_required
def get_training_status(training_id):
    training = TrainingHistory.query.filter_by(
        user_id=current_user.id,
        training_id=training_id
    ).first_or_404()
    
    return jsonify(training.to_dict())
