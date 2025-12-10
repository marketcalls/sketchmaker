"""
Explainer Tool - Generate visual content using Nano Banana Pro AI
Supports: Infographics, concept explainers, flowcharts, technical diagrams, and more
"""
from flask import Blueprint, jsonify, request, render_template, current_app
from flask_login import login_required, current_user
from models import Image, db
import traceback
import os
import uuid
import requests
import io
from datetime import datetime
from extensions import limiter, get_rate_limit_string
from PIL import Image as PILImage
from .clients import init_fal_client

explainer = Blueprint('explainer', __name__)

# Content type templates with detailed prompts
CONTENT_TEMPLATES = {
    'concept': {
        'name': 'Concept Explainer',
        'description': 'Educational breakdowns of complex topics',
        'icon': 'lightbulb',
        'template': """Create a detailed visual explainer about [TOPIC]. Include:
- Main concept prominently displayed at the center
- 4-5 key components with clear icons
- Brief explanations for each component
- Visual connections showing relationships
- Professional color scheme
- Clean, readable typography"""
    },
    'infographic': {
        'name': 'Infographic',
        'description': 'Data visualization, statistics, timelines',
        'icon': 'chart-bar',
        'template': """Design an infographic showing [DATA/STATISTICS]. Include:
- Eye-catching header with clear title
- Key statistics displayed with large, bold numbers
- Icons representing each data point
- Timeline or flow visualization if applicable
- Color-coded sections for easy scanning
- Source attribution at the bottom"""
    },
    'flowchart': {
        'name': 'Flowchart / Diagram',
        'description': 'Process flows, decision trees, architectures',
        'icon': 'share-nodes',
        'template': """Create a flowchart explaining [PROCESS]. Include:
- Clear start and end points
- Decision diamonds for branching logic
- Process boxes with brief descriptions
- Arrows showing flow direction
- Color coding for different stages
- Legend explaining symbols if needed"""
    },
    'kids': {
        'name': 'Kids Explainer',
        'description': 'Child-friendly illustrations with simple language',
        'icon': 'child',
        'template': """Create a fun, kid-friendly explainer about [TOPIC]. Include:
- Cartoon-style colorful illustrations
- Simple, large readable text
- Bright, cheerful colors
- Friendly characters or mascots
- Numbered steps for easy following
- Fun visual elements and decorations"""
    },
    'technical': {
        'name': 'Technical Diagram',
        'description': 'System architectures, workflows, code concepts',
        'icon': 'microchip',
        'template': """Design a technical diagram showing [SYSTEM/ARCHITECTURE]. Include:
- Component boxes with clear labels
- Connection lines showing data/protocol flow
- Layer separation (frontend/backend/database)
- Color coding by component type
- Legend explaining symbols and colors
- Version or technology labels where relevant"""
    },
    'comparison': {
        'name': 'Comparison Chart',
        'description': 'Side-by-side comparisons, pros/cons',
        'icon': 'code-compare',
        'template': """Create a comparison between [A] vs [B]. Include:
- Side-by-side layout with clear headers
- Key features/attributes listed vertically
- Checkmarks and X marks for feature availability
- Pros and cons section for each option
- Visual indicators (colors/icons) for quick scanning
- Summary recommendation at the bottom"""
    },
    'steps': {
        'name': 'Step-by-Step Guide',
        'description': 'Numbered tutorials, how-to guides',
        'icon': 'list-ol',
        'template': """Create a step-by-step guide for [TASK]. Include:
- Clear numbered steps (1, 2, 3...)
- Icon or illustration for each step
- Brief, actionable instruction text
- Tips or warnings highlighted with icons
- Final result preview at the end
- Clean visual flow from start to finish"""
    },
    'pitchdeck': {
        'name': 'Startup Pitchdeck',
        'description': 'Investor presentations, startup visuals',
        'icon': 'rocket',
        'template': """Create a startup pitchdeck slide about [TOPIC/COMPANY]. Include:
- Bold, impactful headline
- Key metrics or traction numbers prominently displayed
- Clean, modern startup aesthetic
- Problem/Solution or Market opportunity visualization
- Team or product showcase section
- Call-to-action or next steps
- Professional investor-ready design"""
    }
}

# Visual style options
VISUAL_STYLES = {
    'professional': {
        'name': 'Professional',
        'description': 'Clean, corporate, minimal design',
        'prompt_modifier': 'professional corporate style with clean lines, subtle colors, and minimal design elements'
    },
    'vibrant': {
        'name': 'Vibrant',
        'description': 'Colorful, engaging, modern',
        'prompt_modifier': 'vibrant colorful style with bold colors, modern gradients, and engaging visual elements'
    },
    'educational': {
        'name': 'Educational',
        'description': 'Clear hierarchy, learning-focused',
        'prompt_modifier': 'educational style with clear visual hierarchy, readable fonts, learning-focused layout'
    },
    'playful': {
        'name': 'Playful',
        'description': 'Fun, illustrated, cartoon-style',
        'prompt_modifier': 'playful cartoon style with fun illustrations, rounded shapes, and cheerful colors'
    },
    'technical': {
        'name': 'Technical',
        'description': 'Detailed, precise, schematic',
        'prompt_modifier': 'technical schematic style with precise details, grid layouts, and engineering aesthetics'
    },
    'minimalist': {
        'name': 'Minimalist',
        'description': 'Simple, focused, whitespace',
        'prompt_modifier': 'minimalist style with lots of whitespace, simple shapes, and focused content'
    }
}

# Aspect ratio options
ASPECT_RATIOS = {
    '1:1': {'name': 'Square (1:1)', 'description': 'Social media, thumbnails'},
    '16:9': {'name': 'Landscape 16:9', 'description': 'Presentations, YouTube'},
    '4:3': {'name': 'Landscape 4:3', 'description': 'Blog posts, articles'},
    '9:16': {'name': 'Portrait 9:16', 'description': 'Stories, mobile'},
    '21:9': {'name': 'Ultra-wide 21:9', 'description': 'Banners, headers'}
}


def enhance_prompt_with_ai(prompt, content_type, style):
    """Enhance the user's prompt using AI to create a comprehensive 2000+ word description"""
    from .clients import get_ai_client, get_selected_model

    try:
        client = get_ai_client()
        model = get_selected_model()

        system_prompt = """You are an expert visual content designer and prompt engineer specializing in creating detailed, comprehensive prompts for AI image generation.

Your task is to transform the user's brief idea into an extremely detailed, rich prompt of approximately 1500-2000 words that will guide AI to create stunning visual content.

Your enhanced prompt MUST include ALL of the following sections with extensive detail:

1. **OVERALL CONCEPT** (200-300 words)
   - Main theme and message
   - Target audience
   - Emotional tone and mood
   - Key takeaways for viewers

2. **VISUAL LAYOUT & COMPOSITION** (300-400 words)
   - Exact placement of all elements (top, center, bottom, left, right)
   - Visual hierarchy and flow
   - Grid structure or layout pattern
   - White space usage
   - Balance and symmetry considerations

3. **TYPOGRAPHY & TEXT ELEMENTS** (200-300 words)
   - Headline style, size, font characteristics
   - Subheadings and body text treatment
   - Text placement and alignment
   - Font pairing suggestions
   - Text effects (shadows, outlines, etc.)

4. **COLOR PALETTE & SCHEME** (200-300 words)
   - Primary, secondary, and accent colors with specific hex codes or color names
   - Color psychology and meaning
   - Gradient usage
   - Background colors and patterns
   - Color contrast for readability

5. **ICONS, ILLUSTRATIONS & GRAPHICS** (300-400 words)
   - Specific icons needed and their style
   - Illustration style (flat, 3D, hand-drawn, etc.)
   - Decorative elements
   - Data visualization elements if applicable
   - Borders, dividers, and frames

6. **DETAILED CONTENT SECTIONS** (300-400 words)
   - Break down each section of the visual
   - Specific content for each area
   - How sections connect visually
   - Annotations and labels

Return ONLY the enhanced prompt text as a continuous, detailed description. Do not include section headers or markdown formatting in your output - write it as flowing descriptive text that an AI image generator can understand."""

        content_info = CONTENT_TEMPLATES.get(content_type, CONTENT_TEMPLATES['concept'])
        style_info = VISUAL_STYLES.get(style, VISUAL_STYLES['professional'])

        user_content = f"""Transform this brief idea into a comprehensive, detailed prompt of 1500-2000 words for creating a {content_info['name']}:

ORIGINAL IDEA:
{prompt}

CONTENT TYPE: {content_info['name']}
DESCRIPTION: {content_info['description']}

VISUAL STYLE: {style_info['name']}
STYLE DETAILS: {style_info['prompt_modifier']}

Create an extremely detailed, comprehensive prompt that covers every visual aspect needed to generate a professional, high-quality {content_info['name'].lower()}.

Be specific about:
- Exact layout and positioning of every element
- Specific colors (use color names or hex codes)
- Typography choices and text styling
- Icons and visual elements needed
- How different sections should look and connect
- Background treatment
- Any decorative elements

The output should be detailed enough that an AI image generator can create exactly what the user envisions without any ambiguity."""

        enhanced = client.generate_completion(
            system_content=system_prompt,
            user_content=user_content,
            model=model,
            temperature=0.7,
            max_tokens=4000
        )

        return enhanced.strip()
    except Exception as e:
        print(f"Error enhancing prompt: {str(e)}")
        return prompt  # Return original if enhancement fails


def build_generation_prompt(prompt, content_type, style, enhance=False):
    """Build the final prompt for image generation"""
    content_info = CONTENT_TEMPLATES.get(content_type, CONTENT_TEMPLATES['concept'])
    style_info = VISUAL_STYLES.get(style, VISUAL_STYLES['professional'])

    # Enhance prompt if requested
    if enhance:
        prompt = enhance_prompt_with_ai(prompt, content_type, style)

    # Build comprehensive prompt
    final_prompt = f"""Create a {content_info['name'].lower()} visual:

{prompt}

Visual Style: {style_info['prompt_modifier']}

Requirements:
- High quality, professional design
- Clear visual hierarchy
- Readable text and labels
- Well-organized layout
- Appropriate use of colors and icons
- Clean, polished final result"""

    return final_prompt


def generate_explainer_image(prompt, aspect_ratio, resolution, output_format):
    """Generate image using Nano Banana Pro via FAL API"""
    try:
        client = init_fal_client()

        arguments = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "output_format": output_format,
            "num_images": 1
        }

        print(f"\n=== Explainer Generation ===")
        print(f"Arguments: {arguments}")

        result = client.subscribe(
            "fal-ai/nano-banana-pro",
            arguments=arguments,
            with_logs=True
        )

        print(f"FAL Response: {result}")

        if not result or 'images' not in result:
            raise ValueError("Invalid response from FAL API")

        # Download and save the image
        image_urls = []
        for img in result['images']:
            image_url = img.get('url') if isinstance(img, dict) else img
            if not image_url:
                continue

            # Generate unique filename
            base_filename = f"explainer_{uuid.uuid4()}"

            # Get paths
            static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
            images_dir = os.path.join(static_dir, 'images')
            os.makedirs(images_dir, exist_ok=True)

            # Download image
            response = requests.get(image_url)
            response.raise_for_status()

            # Save original format
            ext = output_format if output_format != 'png' else 'png'
            filename = f"{base_filename}.{ext}"
            filepath = os.path.join(images_dir, filename)

            with open(filepath, 'wb') as f:
                f.write(response.content)

            # Load image for conversions
            img_data = io.BytesIO(response.content)
            pil_img = PILImage.open(img_data)
            width, height = pil_img.size

            # Save PNG version
            png_filename = f"{base_filename}.png"
            png_filepath = os.path.join(images_dir, png_filename)
            pil_img.save(png_filepath, 'PNG')

            # Save WebP version
            webp_filename = f"{base_filename}.webp"
            webp_filepath = os.path.join(images_dir, webp_filename)
            pil_img.save(webp_filepath, 'WEBP')

            # Save JPEG version
            jpeg_filename = f"{base_filename}.jpeg"
            jpeg_filepath = os.path.join(images_dir, jpeg_filename)
            if pil_img.mode in ('RGBA', 'P'):
                pil_img = pil_img.convert('RGB')
            pil_img.save(jpeg_filepath, 'JPEG')

            image_urls.append({
                'filename': png_filename,
                'width': width,
                'height': height,
                'urls': {
                    'png': f'/static/images/{png_filename}',
                    'webp': f'/static/images/{webp_filename}',
                    'jpeg': f'/static/images/{jpeg_filename}'
                }
            })

        if not image_urls:
            raise ValueError("No images were successfully processed")

        return image_urls[0]

    except Exception as e:
        print(f"Error generating explainer: {str(e)}")
        print(traceback.format_exc())
        raise


@explainer.route('/explainer')
@limiter.limit(get_rate_limit_string())
@login_required
def explainer_page():
    """Render the explainer tool page"""
    return render_template(
        'explainer.html',
        content_templates=CONTENT_TEMPLATES,
        visual_styles=VISUAL_STYLES,
        aspect_ratios=ASPECT_RATIOS
    )


@explainer.route('/explainer/generate', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def generate_explainer():
    """Generate explainer visual using Nano Banana Pro"""
    try:
        # Check credits
        if not current_user.can_use_feature('explainers'):
            subscription = current_user.get_subscription()
            plan_name = subscription.plan.display_name if subscription else 'No Plan'
            credits_remaining = current_user.get_credits_remaining()
            credit_cost = current_user.get_credit_cost('explainers')
            return jsonify({
                'error': 'Insufficient credits',
                'details': f'You need {credit_cost} credit{"s" if credit_cost > 1 else ""} to generate an explainer. You have {credits_remaining} credits remaining.',
                'type': 'insufficient_credits',
                'credits_needed': credit_cost,
                'credits_remaining': credits_remaining,
                'plan': plan_name
            }), 403

        # Check FAL API key
        from models import APISettings
        api_settings = APISettings.get_settings()
        if not api_settings.get_fal_key():
            return jsonify({
                'error': 'FAL API key not configured',
                'details': 'Contact administrator to configure FAL API key'
            }), 503

        # Get parameters
        data = request.get_json() or {}
        prompt = data.get('prompt', '').strip()
        content_type = data.get('content_type', 'concept')
        style = data.get('style', 'professional')
        aspect_ratio = data.get('aspect_ratio', '16:9')
        resolution = data.get('resolution', '2K')
        output_format = data.get('output_format', 'png')
        enhance_prompt = data.get('enhance_prompt', False)

        if not prompt:
            return jsonify({
                'error': 'Missing prompt',
                'details': 'Please provide a description for your visual content'
            }), 400

        # Build the generation prompt
        final_prompt = build_generation_prompt(prompt, content_type, style, enhance_prompt)

        try:
            # Generate the image
            result = generate_explainer_image(final_prompt, aspect_ratio, resolution, output_format)

            # Save to database
            new_image = Image(
                filename=result['filename'],
                prompt=prompt,
                art_style=f"{content_type}_{style}",
                width=result['width'],
                height=result['height'],
                user_id=current_user.id,
                created_at=datetime.utcnow()
            )
            db.session.add(new_image)
            db.session.commit()

            # Track usage
            current_user.use_feature(
                feature_type='explainers',
                amount=1,
                extra_data={
                    'prompt': prompt,
                    'content_type': content_type,
                    'style': style,
                    'aspect_ratio': aspect_ratio,
                    'resolution': resolution,
                    'image_id': new_image.id,
                    'tool': 'explainer'
                }
            )

            return jsonify({
                'success': True,
                'image': {
                    'id': new_image.id,
                    'urls': result['urls'],
                    'width': result['width'],
                    'height': result['height']
                }
            })

        except Exception as e:
            print(f"Error generating image: {str(e)}")
            print(traceback.format_exc())
            return jsonify({
                'error': 'Generation failed',
                'details': str(e)
            }), 500

    except Exception as e:
        print(f"Error in generate_explainer: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'error': 'Unexpected error',
            'details': str(e)
        }), 500


@explainer.route('/explainer/templates')
@login_required
def get_templates():
    """Get content type templates"""
    return jsonify({
        'templates': CONTENT_TEMPLATES,
        'styles': VISUAL_STYLES,
        'aspect_ratios': ASPECT_RATIOS
    })


@explainer.route('/explainer/enhance', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def enhance_prompt():
    """Enhance the user's prompt using AI"""
    try:
        data = request.get_json() or {}
        prompt = data.get('prompt', '').strip()
        content_type = data.get('content_type', 'concept')
        style = data.get('style', 'professional')

        if not prompt:
            return jsonify({
                'error': 'Missing prompt',
                'details': 'Please provide a prompt to enhance'
            }), 400

        # Enhance the prompt
        enhanced = enhance_prompt_with_ai(prompt, content_type, style)

        return jsonify({
            'success': True,
            'original_prompt': prompt,
            'enhanced_prompt': enhanced
        })

    except Exception as e:
        print(f"Error enhancing prompt: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'error': 'Enhancement failed',
            'details': str(e)
        }), 500
