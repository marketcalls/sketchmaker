from flask import Blueprint, request, jsonify, send_file
import requests
from io import BytesIO
from PIL import Image

download_bp = Blueprint('download', __name__)

@download_bp.route('/download', methods=['GET'])
def download_image():
    image_url = request.args.get('url')
    format = request.args.get('format', 'png')
    
    if not image_url:
        return jsonify({"error": "No image URL provided"}), 400

    try:
        response = requests.get(image_url)
        img = Image.open(BytesIO(response.content))
        
        output = BytesIO()
        if format == 'webp':
            img.save(output, format='WEBP')
        elif format == 'jpeg':
            img = img.convert('RGB')
            img.save(output, format='JPEG')
        else:
            img.save(output, format='PNG')
        
        output.seek(0)
        return send_file(output, mimetype=f'image/{format}', as_attachment=True, download_name=f'thumbnail.{format}')
    except Exception as e:
        return jsonify({"error": str(e)}), 500
