from flask import Blueprint, jsonify, request, render_template, send_file, current_app
from flask_login import login_required, current_user
from models import AIModel, Image, db
import anthropic
from openai import OpenAI
import google.generativeai as genai
from groq import Groq
import traceback
from io import BytesIO
import cairosvg
from PIL import Image as PILImage
import os
import uuid
from datetime import datetime

banner = Blueprint('banner', __name__)

def get_system_prompt():
    return """You are a skilled SVG banner creator specializing in modern, visually striking designs. Create beautiful SVG banners with these requirements:

Technical Requirements:
- Use proper SVG structure with xmlns attribute
- Include viewBox attribute for proper scaling
- Add preserveAspectRatio="xMidYMid meet" for consistent display
- Use transform attributes for precise element positioning
- Implement proper SVG grouping with <g> elements
- Optimize paths and shapes for web performance

Text Alignment Requirements:
- Use text-anchor="middle" for centered text
- Implement dominant-baseline="middle" for vertical alignment
- Group related text elements within <g> tags
- For comparison texts (like "VS"):
  * Position exactly between the compared items
  * Use consistent spacing from both items
  * Align vertically with the compared items
- For multi-line text:
  * Use tspan elements with precise dy attributes
  * Maintain consistent line spacing
  * Center align each line independently

Design Requirements:
- Create layered designs with proper z-index ordering
- Use defs for gradient definitions
- Implement linear gradients with precise stop positions
- For dark backgrounds:
  * Use high contrast text colors
  * Add subtle glow effects for better readability
  * Implement drop shadows where appropriate
- For comparison layouts:
  * Use equal spacing between elements
  * Maintain consistent sizing for compared items
  * Create visual hierarchy through size and position
  * Use connecting elements (lines, arrows) with proper alignment

Best Practices:
- Use mathematical positioning for precise alignment
- Calculate positions based on viewBox dimensions
- Implement proper spacing ratios
- Use relative units for scalability
- Add subtle animations where appropriate
- Ensure accessibility with proper ARIA labels
- Optimize for web performance

Return ONLY the SVG code without any explanation or markdown formatting."""

def get_user_prompt(prompt, width, height, style):
    # Base style descriptions
    style_descriptions = {
        'modern': """
            - Use bold geometric shapes and clean lines
            - Implement subtle gradients in modern colors
            - Add floating elements and asymmetric layouts
            - Include minimalist iconography
            - Use contemporary sans-serif fonts
            - Ensure precise text alignment and spacing
            """,
        'minimalist': """
            - Focus on essential elements with plenty of whitespace
            - Use monochromatic or limited color palette
            - Implement subtle grid-based layouts
            - Add thin lines and simple shapes
            - Use lightweight typography
            - Maintain mathematical precision in spacing
            """,
        'artistic': """
            - Create organic, flowing shapes and patterns
            - Use rich, vibrant color combinations
            - Add artistic textures and brush-like elements
            - Implement dynamic, expressive layouts
            - Include decorative typography
            - Balance artistic freedom with precise alignment
            """,
        'corporate': """
            - Use professional color schemes (blues, grays)
            - Implement structured, grid-based layouts
            - Add subtle gradients and clean shapes
            - Include business-appropriate icons
            - Use professional sans-serif fonts
            - Ensure perfect alignment of all elements
            """,
        'playful': """
            - Use bright, energetic colors
            - Add bouncy, rounded shapes
            - Implement playful patterns and icons
            - Include fun typography with personality
            - Create dynamic, engaging layouts
            - Maintain alignment despite playful nature
            """,
        'tech': """
            - Use circuit-board patterns and tech elements
            - Implement data-flow lines and connections
            - Add binary or code-like decorative elements
            - Include modern tech-inspired icons
            - Use futuristic typography
            - Ensure precise geometric alignment
            """,
        'elegant': """
            - Use sophisticated color palettes
            - Implement refined, classical patterns
            - Add subtle, luxurious gradients
            - Include elegant serif typography
            - Create balanced, symmetrical layouts
            - Perfect alignment of all elements
            """
    }

    # Get style-specific description
    style_desc = style_descriptions.get(style, style_descriptions['modern'])

    return f"""Create an SVG banner with these specifications:

Content Theme:
{prompt}

Dimensions and Layout:
- Width: {width}px
- Height: {height}px
- Aspect Ratio: {width}:{height}
- Calculate element positions mathematically based on dimensions
- Use precise spacing ratios (e.g., rule of thirds)

Style Requirements:
{style_desc}

Text Alignment:
- Center all text elements both horizontally and vertically
- For comparison text (VS, versus, etc.):
  * Position exactly at 50% between compared items
  * Align vertically with the baseline of compared items
  * Use consistent spacing from adjacent elements
- Use mathematical positioning for precise alignment
- Group related text elements
- Add subtle animations for text elements

Visual Elements:
- Create multi-layered design with proper z-indexing
- Use high contrast for text on dark backgrounds
- Implement smooth transitions between elements
- Add subtle glows or shadows for depth
- Include visual hierarchy with focal points
- Balance text and graphical elements
- Use proper spacing and alignment

Technical Optimization:
- Ensure text remains readable at all sizes
- Optimize paths and shapes for performance
- Use proper grouping for related elements
- Implement smooth gradients without banding
- Add subtle hover states for interactive elements
- Ensure proper rendering across browsers

The final SVG should be visually striking, professionally designed, and optimized for web use."""

def generate_svg(prompt, system_prompt):
    # Get the current provider and model
    if not current_user.selected_provider_id or not current_user.selected_model_id:
        raise ValueError("No provider or model selected")

    model = AIModel.query.get(current_user.selected_model_id)
    if not model:
        raise ValueError("Selected model not found")

    provider_name = model.provider.name
    model_name = model.name

    # Generate SVG based on provider
    if provider_name == 'Anthropic':
        client = anthropic.Anthropic(api_key=current_user.anthropic_api_key)
        message = client.messages.create(
            model=model_name,  # Use model name from database
            max_tokens=1500,
            temperature=0.7,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text

    elif provider_name == 'OpenAI':
        client = OpenAI(api_key=current_user.openai_api_key)
        response = client.chat.completions.create(
            model=model_name,  # Use model name from database
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content

    elif provider_name == 'Google Gemini':
        genai.configure(api_key=current_user.gemini_api_key)
        model = genai.GenerativeModel(model_name)  # Use model name from database
        response = model.generate_content(
            f"{system_prompt}\n\nUser request: {prompt}"
        )
        return response.text

    elif provider_name == 'Groq':
        client = Groq(api_key=current_user.groq_api_key)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            model=model_name,  # Use model name from database
            temperature=0.7
        )
        return chat_completion.choices[0].message.content

    else:
        raise ValueError(f"Unsupported provider: {provider_name}")

def save_banner_image(svg_content, prompt, width, height, style):
    """Save banner as PNG and create database record"""
    try:
        # Generate unique filename
        filename = f"banner_{uuid.uuid4()}"
        
        # Convert SVG to PNG
        png_data = cairosvg.svg2png(bytestring=svg_content.encode())
        
        # Save PNG version
        png_filename = f"{filename}.png"
        png_path = os.path.join(current_app.root_path, 'static', 'images', png_filename)
        with open(png_path, 'wb') as f:
            f.write(png_data)
        
        # Create WebP version
        webp_filename = f"{filename}.webp"
        webp_path = os.path.join(current_app.root_path, 'static', 'images', webp_filename)
        img = PILImage.open(BytesIO(png_data))
        img.save(webp_path, 'WEBP')
        
        # Create JPEG version
        jpeg_filename = f"{filename}.jpeg"
        jpeg_path = os.path.join(current_app.root_path, 'static', 'images', jpeg_filename)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.save(jpeg_path, 'JPEG')
        
        # Create database record
        new_image = Image(
            filename=png_filename,  # Store PNG as primary filename
            prompt=prompt,
            art_style=style,
            width=width,
            height=height,
            user_id=current_user.id,
            provider_id=current_user.selected_provider_id,
            model_id=current_user.selected_model_id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_image)
        db.session.commit()
        
        return new_image
        
    except Exception as e:
        print(f"Error saving banner: {str(e)}")
        print(traceback.format_exc())
        # Clean up files if there was an error
        for path in [png_path, webp_path, jpeg_path]:
            if os.path.exists(path):
                os.remove(path)
        raise

@banner.route('/banner')
@login_required
def banner_page():
    """Render the banner generation page"""
    return render_template('banner.html')

@banner.route('/banner/generate', methods=['POST'])
@login_required
def generate_banner():
    try:
        if not current_user.get_selected_provider_key():
            return jsonify({
                'error': 'API key required',
                'details': 'Please configure your API key in settings'
            }), 400

        # Get parameters
        data = request.get_json() or {}
        prompt = data.get('prompt', '')
        width = data.get('width', 800)
        height = data.get('height', 400)
        style = data.get('style', 'modern')

        if not prompt:
            return jsonify({
                'error': 'Missing prompt',
                'details': 'Please provide a description for your banner'
            }), 400

        # Get prompts
        system_prompt = get_system_prompt()
        user_prompt = get_user_prompt(prompt, width, height, style)

        try:
            # Generate SVG
            svg_content = generate_svg(user_prompt, system_prompt)

            # Clean up and validate SVG content
            if '<svg' in svg_content:
                svg_content = svg_content[svg_content.find('<svg'):svg_content.find('</svg>') + 6]
                
                # Ensure proper attributes
                if 'viewBox' not in svg_content:
                    svg_content = svg_content.replace('<svg', f'<svg viewBox="0 0 {width} {height}"')
                if 'preserveAspectRatio' not in svg_content:
                    svg_content = svg_content.replace('<svg', '<svg preserveAspectRatio="xMidYMid meet"')

                # Save banner and create database record
                image = save_banner_image(svg_content, prompt, width, height, style)
                
                return jsonify({
                    'svg': svg_content,
                    'image': {
                        'id': image.id,
                        'urls': {
                            'png': image.get_url('png'),
                            'webp': image.get_url('webp'),
                            'jpeg': image.get_url('jpeg')
                        }
                    }
                })
            else:
                return jsonify({
                    'error': 'Invalid SVG',
                    'details': 'Generated content is not a valid SVG'
                }), 500

        except Exception as e:
            print(f"Error generating SVG: {str(e)}")
            print(traceback.format_exc())
            return jsonify({
                'error': 'Generation failed',
                'details': str(e)
            }), 500

    except Exception as e:
        print(f"Error in generate_banner: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'error': 'Unexpected error',
            'details': str(e)
        }), 500
