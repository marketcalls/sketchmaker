from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from .clients import init_fal_client
import fal_client
import os
import uuid
import requests
from extensions import limiter, get_rate_limit_string
from models import db
from models.content import Image
from PIL import Image as PILImage
import json
import base64
from io import BytesIO
from services.image_optimizer import ImageOptimizer

magix_bp = Blueprint('magix', __name__)

def save_result_image(url):
    """Save the result image locally and return both URL and filename"""
    try:
        response = requests.get(url)
        response.raise_for_status()

        # Generate unique filename
        filename = f"nano_{uuid.uuid4()}.jpg"
        filepath = os.path.join(current_app.root_path, 'static', 'images', filename)

        # Save the image
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        # Get image dimensions
        width, height = None, None
        try:
            with PILImage.open(filepath) as img:
                width, height = img.size
        except Exception as e:
            print(f"Error getting image dimensions: {str(e)}")

        return f'/static/images/{filename}', filename, width, height
    except Exception as e:
        print(f"Error saving result image: {str(e)}")
        raise

def image_to_base64(image_path):
    """Convert image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

@magix_bp.route('/magix')
@limiter.limit(get_rate_limit_string())
@login_required
def magix_page():
    """Render the Nano Studio page"""
    return render_template('magix.html')

@magix_bp.route('/api/magix/generate', methods=['POST'])
@limiter.limit(get_rate_limit_string())
@login_required
def generate_magix():
    try:
        # Check if user can use Nano Studio (credit-based limit)
        if not current_user.can_use_feature('magix'):
            subscription = current_user.get_subscription()
            plan_name = subscription.plan.display_name if subscription else 'No Plan'
            credits_remaining = current_user.get_credits_remaining()
            credit_cost = current_user.get_credit_cost('magix')
            return jsonify({
                'error': 'Insufficient credits for Nano Studio',
                'details': f'You need {credit_cost} credit{"s" if credit_cost > 1 else ""} to use Nano Studio. You have {credits_remaining} credits remaining.',
                'type': 'insufficient_credits',
                'feature': 'magix',
                'credits_needed': credit_cost,
                'credits_remaining': credits_remaining,
                'plan': plan_name
            }), 403
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        mode = data.get('mode', 'edit')
        prompt = data.get('prompt', '')
        
        # Initialize FAL client
        client = init_fal_client()

        # Progress tracking
        progress_updates = []
        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    progress_updates.append(log['message'])
                    print(f"Nano Studio Progress: {log['message']}")

        # Prepare base arguments for Nano Banana Pro
        arguments = {
            "prompt": prompt,
            "num_images": data.get('num_images', 1),
            "aspect_ratio": data.get('aspect_ratio', 'auto'),
            "output_format": data.get('output_format', 'png'),
            "resolution": data.get('resolution', '1K')  # Supports: 1K, 2K, 4K
        }

        # Add image URLs if provided (for editing modes)
        # Optimize images before sending to FAL
        if 'image_urls' in data:
            optimized_urls = []
            for img_url in data['image_urls']:
                optimized_img, metadata = ImageOptimizer.optimize_image(img_url, service='magix')
                optimized_urls.append(optimized_img)
                if metadata.get('optimization_failed'):
                    print(f"Warning: Image optimization failed, using original")
                else:
                    print(f"Image optimized: {metadata.get('compression_ratio', 100)}% of original size")
            arguments['image_urls'] = optimized_urls
        elif 'image_url' in data:
            optimized_img, metadata = ImageOptimizer.optimize_image(data['image_url'], service='magix')
            arguments['image_urls'] = [optimized_img]
            if not metadata.get('optimization_failed'):
                print(f"Image optimized: {metadata.get('compression_ratio', 100)}% of original size")

        # Base instruction for facial preservation - as JSON object
        face_preserve_obj = {
            "requirement": "CRITICAL - ABSOLUTE FACIAL PRESERVATION",
            "preserve_exactly": [
                "face shape and bone structure",
                "eye shape, color, size, spacing",
                "nose shape and size",
                "mouth and lip shape",
                "eyebrow shape and position",
                "skin texture and natural marks",
                "ear shape if visible",
                "hairline shape",
                "overall facial proportions",
                "ethnic features unchanged"
            ],
            "instruction": "Person must be immediately recognizable as themselves. Do not idealize or beautify beyond recognition."
        }

        # Mode-specific configurations - AI Photography Focus with JSON structured prompts
        if mode == 'studio_portrait':
            prompt_json = {
                "scene": "Professional photography studio with seamless backdrop",
                "subjects": [{
                    "type": "portrait subject",
                    "description": "The person from the input image with all original features preserved",
                    "pose": "head and shoulders, shoulders slightly angled, chin forward and down",
                    "position": "centered using rule of thirds, eyes at upper third"
                }],
                "style": "Professional studio portrait photography, polished and refined",
                "background": {
                    "type": "seamless backdrop",
                    "options": ["pure white", "neutral gray hex #808080", "subtle gradient"],
                    "qualities": "evenly lit, no hotspots or shadows, slight vignette acceptable"
                },
                "lighting": {
                    "setup": "classic three-point lighting",
                    "key_light": "large softbox at 45 degrees, soft wrapping illumination",
                    "fill_light": "2:1 ratio to key, gently opens shadows",
                    "rim_light": "subtle hair light from behind for separation",
                    "catchlights": "visible and natural in eyes"
                },
                "mood": "professional, confident, approachable",
                "composition": {
                    "framing": "head and shoulders",
                    "rule": "rule of thirds",
                    "headroom": "adequate space above head"
                },
                "camera": {
                    "angle": "eye level",
                    "distance": "medium shot",
                    "lens": "85mm portrait lens",
                    "focus": "sharp on eyes"
                },
                "technical": {
                    "quality": "professional-grade, no noise or grain",
                    "skin": "smooth with natural texture retained, not plastic",
                    "white_balance": "natural skin tones",
                    "dynamic_range": "high, details in highlights and shadows"
                },
                "retouching": "Professional but natural - remove temporary blemishes, even skin tone, subtle under-eye correction, maintain natural pores and texture",
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'environmental':
            prompt_json = {
                "scene": "Meaningful real-world environment revealing personality, profession, or interests",
                "subjects": [{
                    "type": "portrait subject",
                    "description": "The person from input image with preserved features in contextual setting",
                    "pose": "natural, authentic interaction with environment",
                    "position": "occupies 30-50% of frame with meaningful negative space"
                }],
                "style": "Environmental portrait photography, documentary-meets-portrait",
                "environment": {
                    "type": "contextual real-world setting",
                    "elements": "relevant details that add depth and narrative",
                    "relationship": "background complements subject without overwhelming"
                },
                "lighting": {
                    "type": "natural available light",
                    "sources": ["window light", "golden hour sunlight", "ambient environmental"],
                    "balance": "subject properly exposed with balanced background",
                    "modifiers": "doorways, windows, architectural elements as natural modifiers",
                    "shadows": "natural shadows adding dimension and mood"
                },
                "mood": "genuine, unposed, authentic, visually compelling",
                "composition": {
                    "framing": "environmental elements frame subject naturally",
                    "elements": ["leading lines", "layers", "foreground interest", "background context"],
                    "depth_of_field": "subject sharp, background soft but identifiable"
                },
                "camera": {
                    "angle": "contextually appropriate",
                    "distance": "medium to wide shot showing environment",
                    "lens": "35mm or 50mm",
                    "focus": "sharp on subject's eyes"
                },
                "color_palette": "natural, authentic colors derived from environment, cohesive story",
                "technical": {
                    "quality": "professional, balanced exposure throughout",
                    "skin_tones": "natural and accurate"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'lifestyle':
            prompt_json = {
                "scene": "Casual, relatable everyday environment - home, café, park",
                "subjects": [{
                    "type": "portrait subject",
                    "description": "Person from input image in natural, candid moment",
                    "pose": "relaxed, comfortable, unforced body language",
                    "expression": "genuine smile or thoughtful gaze, authentic emotion",
                    "position": "casual placement, doesn't need to be centered"
                }],
                "style": "Authentic lifestyle portrait, candid-feeling photography",
                "environment": {
                    "type": "everyday relatable location",
                    "feel": "natural, uncluttered, organic not staged",
                    "elements": "lifestyle details that feel authentic"
                },
                "lighting": {
                    "type": "soft natural light",
                    "sources": ["window light", "open shade", "golden hour warmth"],
                    "quality": "effortless, wrapping, comfortable atmosphere",
                    "avoid": "harsh shadows, artificial-looking illumination"
                },
                "mood": "warm, inviting, relaxed, authentic, relatable",
                "composition": {
                    "framing": "casual, spontaneous feeling",
                    "negative_space": "breathing room around subject",
                    "approach": "capturing a moment, not posing for photo"
                },
                "camera": {
                    "angle": "natural, candid",
                    "distance": "medium shot with context",
                    "lens": "35mm or 50mm"
                },
                "color_palette": {
                    "tones": "warm, inviting",
                    "shadows": "slightly lifted for airy feel",
                    "skin": "natural with subtle warmth",
                    "whites": "clean",
                    "contrast": "soft"
                },
                "technical": {
                    "quality": "Instagram-worthy but not over-filtered",
                    "feel": "lived-in atmosphere"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'fashion_editorial':
            prompt_json = {
                "scene": "High-fashion editorial setting, Vogue or Harper's Bazaar worthy",
                "subjects": [{
                    "type": "fashion portrait subject",
                    "description": "Person from input image as high-fashion model",
                    "pose": "editorial with attitude, strong body lines, dynamic angles, purposeful positioning",
                    "expression": "confidence, mystery, or high-fashion aloofness",
                    "styling": "hair perfection, editorial makeup, clothing beautifully presented"
                }],
                "style": "High-fashion editorial photography, magazine-ready",
                "aesthetic": {
                    "sensibility": "curated, intentional, bold, confident, fashion-forward",
                    "emphasis": ["clothing", "accessories", "overall styling"],
                    "narrative": "cohesive visual story"
                },
                "lighting": {
                    "type": "dramatic, intentional, sculpting",
                    "options": ["hard directional for bold shadows", "beauty dish for glamorous glow", "dramatic side lighting", "creative mixed lighting"],
                    "purpose": "deliberate creative choice enhancing fashion narrative"
                },
                "mood": "bold, confident, editorial, high-fashion",
                "composition": {
                    "style": "bold, graphic, strong visual impact",
                    "negative_space": "used dramatically",
                    "framing": "unconventional encouraged",
                    "goal": "magazine cover or spread worthy"
                },
                "camera": {
                    "angle": "dynamic, fashion photography angles",
                    "distance": "varies for editorial impact",
                    "lens": "85mm or 70-200mm"
                },
                "post_processing": {
                    "retouching": "fashion-grade, flawless skin with texture maintained",
                    "eyes": "enhanced",
                    "features": "sculpted through light and shadow",
                    "color_grading": "supports editorial concept - rich saturated, desaturated moody, or high-contrast B&W"
                },
                "production_value": "every element intentional and elevated",
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'cinematic':
            prompt_json = {
                "scene": "Major motion picture film still, cinematic environment",
                "subjects": [{
                    "type": "cinematic portrait subject",
                    "description": "Person from input image as movie character",
                    "pose": "dramatic, story-suggesting positioning",
                    "expression": "contemplative, dramatic, or emotionally charged",
                    "position": "positioned for dramatic effect"
                }],
                "style": "Cinematic portrait, film still quality, movie poster worthy",
                "atmosphere": {
                    "depth_of_field": "shallow f/1.4-2.8 with creamy bokeh",
                    "layers": ["foreground", "subject sharp", "background beautifully blurred"],
                    "elements": "subtle haze, dust particles in light beams if appropriate"
                },
                "lighting": {
                    "type": "cinematic, motivated from natural scene source",
                    "techniques": ["practicals", "window light", "dramatic single-source"],
                    "ratio": "strong light-to-shadow creating mood and depth",
                    "rim_light": "separates subject from background",
                    "styles": ["Rembrandt", "split light", "atmospheric haze"]
                },
                "mood": "contemplative, dramatic, emotionally charged, narrative-suggesting",
                "composition": {
                    "aspect_feel": "2.39:1 or 1.85:1 widescreen composition",
                    "framing": "cinematic with purposeful negative space",
                    "goal": "evoke curiosity about story"
                },
                "camera": {
                    "angle": "cinematic, dramatic",
                    "distance": "medium shot with depth",
                    "lens": "50mm or 85mm anamorphic feel"
                },
                "color_grading": {
                    "style": "cinematic color science",
                    "options": ["teal and orange complementary", "desaturated with selective color", "rich shadows with film rolloff"],
                    "references": ["Blade Runner neons", "Amelie greens", "custom palette"],
                    "blacks": "lifted for film look",
                    "highlights": "controlled"
                },
                "technical": {
                    "grain": "subtle film-like if appropriate",
                    "dynamic_range": "high",
                    "shadows": "rich with detail",
                    "quality": "professional color depth"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'corporate_headshot':
            background = data.get('background', 'neutral_gray')
            background_colors = {
                "neutral_gray": "#808080",
                "clean_white": "#FFFFFF",
                "soft_gradient": "gradient from #E8E8E8 to #C0C0C0",
                "office_blur": "blurred office environment",
                "outdoor_blur": "blurred outdoor professional setting"
            }
            prompt_json = {
                "scene": "Professional corporate headshot setting for LinkedIn and business materials",
                "subjects": [{
                    "type": "corporate portrait subject",
                    "description": "Person from input image as business professional",
                    "pose": "shoulders at slight angle, head straight or very slight tilt, chin forward for defined jawline",
                    "expression": "confident, approachable, genuine but controlled smile or pleasant neutral",
                    "eye_contact": "direct with camera",
                    "grooming": "neat, polished, professional appearance"
                }],
                "style": "Polished corporate headshot, LinkedIn-ready, company website quality",
                "background": {
                    "type": background.replace('_', ' '),
                    "color": background_colors.get(background, "#808080"),
                    "qualities": "clean, professional, non-distracting, evenly lit"
                },
                "lighting": {
                    "type": "professional, flattering, conveys competence",
                    "key_light": "soft at 30-45 degrees",
                    "fill_light": "reduces shadows to professional level, not flat",
                    "rim_light": "subtle for separation",
                    "consistency": "suitable for company-wide headshot standards"
                },
                "mood": "professional, confident, approachable, trustworthy",
                "composition": {
                    "framing": "head and shoulders",
                    "space": "adequate breathing room",
                    "positioning": "centered or rule-of-thirds",
                    "standard": "professional headshot conventions"
                },
                "camera": {
                    "angle": "eye level",
                    "distance": "close-up to medium",
                    "lens": "85mm portrait"
                },
                "retouching": {
                    "level": "professional but authentic",
                    "includes": ["remove temporary blemishes", "minimize under-eye shadows", "even skin tone"],
                    "goal": "look like best version of themselves, not artificially perfected"
                },
                "color": {
                    "skin_tones": "natural, accurate",
                    "eyes": "clean whites",
                    "balance": "professional, works in digital and print"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'street_portrait':
            prompt_json = {
                "scene": "Authentic urban street environment with character",
                "subjects": [{
                    "type": "street portrait subject",
                    "description": "Person from input image connected to urban environment",
                    "pose": "natural, possibly off-center or interacting with environment",
                    "expression": "raw, authentic, genuine character and personality",
                    "attitude": "street photography sensibility - real, unpolished, honest"
                }],
                "style": "Street portrait photography, documentary-meets-portrait",
                "environment": {
                    "type": "authentic city backdrop",
                    "elements": ["textured walls", "graffiti", "urban architecture", "neon signs", "street scenes"],
                    "feel": "real, lived-in, adding character and context",
                    "textures": "urban layers and visual interest"
                },
                "lighting": {
                    "type": "natural street lighting",
                    "options": ["harsh midday sun with hard shadows", "golden hour urban canyon", "neon and artificial city lights", "overcast diffused"],
                    "color_temperature": "mixed welcome as authentic",
                    "approach": "embrace imperfect lighting as part of street aesthetic"
                },
                "mood": "raw, authentic, energetic, genuine, urban",
                "composition": {
                    "style": "dynamic street photography",
                    "elements": ["leading lines", "urban geometry", "layers of depth"],
                    "subject_placement": "can be off-center, partially framed",
                    "angles": "interesting, unconventional"
                },
                "camera": {
                    "angle": "dynamic street photography angles",
                    "distance": "varies with context",
                    "lens": "35mm street photography"
                },
                "color_palette": "bold or muted depending on environment, authentic urban tones",
                "technical": {
                    "focus": "sharp on subject",
                    "bokeh": "environmental as appropriate",
                    "imperfection": "embrace as authentic",
                    "skin_tones": "natural, works with environmental color cast",
                    "quality": "high but not sterile"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'low_key':
            prompt_json = {
                "scene": "Dramatic low-key portrait studio with controlled darkness",
                "subjects": [{
                    "type": "low-key portrait subject",
                    "description": "Person from input image emerging from shadows",
                    "pose": "dramatic positioning, possibly unconventional",
                    "expression": "mysterious, powerful, contemplative, or intense",
                    "position": "parts can fall into complete darkness"
                }],
                "style": "Dramatic low-key portrait photography, high contrast artistic",
                "background": {
                    "color": "hex #000000 pure black",
                    "treatment": "seamlessly blends with subject shadows",
                    "visibility": "no visible backdrop texture"
                },
                "lighting": {
                    "type": "single strong source, selective dramatic illumination",
                    "ratio": "8:1 or higher",
                    "techniques": ["strong side light", "Rembrandt lighting", "split lighting"],
                    "purpose": "sculpt face, reveal form through shadow"
                },
                "shadows": {
                    "treatment": "deep, rich blacks dominating frame",
                    "role": "intentional compositional elements",
                    "quality": "clean, noise-free",
                    "philosophy": "darkness as presence, not absence"
                },
                "highlights": {
                    "control": "precise, drawing attention to key features",
                    "areas": ["eyes", "facial planes", "essential details"],
                    "retention": "no blowout, retain detail"
                },
                "mood": "mysterious, dramatic, powerful, contemplative, intense",
                "composition": {
                    "negative_space": "use darkness as compositional element",
                    "framing": "shadows frame and lead eye to illuminated features"
                },
                "camera": {
                    "angle": "dramatic",
                    "distance": "medium shot",
                    "lens": "85mm"
                },
                "technical": {
                    "exposure": "for highlights, let shadows go dark",
                    "blacks": "rich without losing intended detail",
                    "focus": "sharp on illuminated areas",
                    "contrast": "high but controlled"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'high_key':
            prompt_json = {
                "scene": "Bright, airy high-key portrait studio",
                "subjects": [{
                    "type": "high-key portrait subject",
                    "description": "Person from input image in bright, clean light",
                    "pose": "open, inviting positioning",
                    "expression": "fresh, optimistic, youthful",
                    "skin": "luminous, soft glowing quality"
                }],
                "style": "High-key portrait photography, bright and airy",
                "background": {
                    "color": "hex #FFFFFF pure white or very light gray",
                    "lighting": "evenly lit to near-white",
                    "qualities": "no shadows, gradients, or visible texture"
                },
                "lighting": {
                    "type": "multiple soft sources, wrap-around illumination",
                    "contrast": "low with lifted shadows",
                    "feel": "abundant and uplifting",
                    "shadows": "minimal, fill all shadow areas with soft light"
                },
                "shadows": {
                    "treatment": "gentle, subtle, never dark",
                    "under_chin": "barely perceptible",
                    "under_nose": "barely perceptible",
                    "overall": "feeling of light everywhere"
                },
                "mood": "fresh, clean, optimistic, youthful, pure, hopeful",
                "composition": {
                    "style": "open, bright framing",
                    "feel": "inviting"
                },
                "camera": {
                    "angle": "eye level or slightly above",
                    "distance": "medium close-up",
                    "lens": "85mm portrait"
                },
                "skin": {
                    "quality": "even, luminous, soft glowing",
                    "light": "wrapping around features",
                    "gradation": "subtle in skin tones",
                    "appearance": "fresh, healthy",
                    "catchlights": "bright in eyes"
                },
                "color_palette": {
                    "style": "clean, fresh colors",
                    "options": ["neutral white dominant", "soft pastels", "bright clean colors"],
                    "avoid": "muddy or dark tones",
                    "whites": "true white hex #FFFFFF, not gray or cream"
                },
                "technical": {
                    "exposure": "careful to retain detail in bright areas",
                    "subject": "not overexposed",
                    "light_quality": "soft, flattering on skin",
                    "contrast": "no harsh shadows"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'black_white':
            prompt_json = {
                "scene": "Timeless black and white portrait setting",
                "subjects": [{
                    "type": "monochrome portrait subject",
                    "description": "Person from input image in classic B&W aesthetic",
                    "pose": "classic portraiture positioning",
                    "expression": "emotionally resonant, timeless quality",
                    "skin": "luminous, beautiful grayscale translation"
                }],
                "style": "Timeless black and white portrait photography",
                "color_mode": "monochrome, no color",
                "tonal_range": {
                    "blacks": "deep and rich",
                    "whites": "bright with detail",
                    "midtones": "full range with smooth gradation",
                    "approach": "Ansel Adams Zone System sensibility"
                },
                "contrast": {
                    "options": ["high for drama", "lower for softness", "full range for classic"],
                    "purpose": "creative choice supporting portrait mood"
                },
                "texture": {
                    "emphasis": ["skin texture", "fabric", "hair", "environmental details"],
                    "quality": "rich detail throughout",
                    "note": "absence of color makes form and texture prominent"
                },
                "lighting": {
                    "consideration": "specifically for grayscale translation",
                    "type": "strong directional often works beautifully",
                    "shadows": "define features",
                    "note": "harsh color lighting can be stunning in B&W"
                },
                "mood": "timeless, emotional, classic, artistic, resonant",
                "composition": {
                    "style": "classic portraiture",
                    "focus": "expression, form, human connection"
                },
                "camera": {
                    "angle": "classic portrait angles",
                    "distance": "medium shot",
                    "lens": "85mm or 105mm"
                },
                "post_processing": {
                    "conversion": "professional B&W with attention to color channel translation",
                    "grain": "possible subtle film grain for texture",
                    "technique": "dodging and burning to guide eye",
                    "quality": "classic darkroom standards"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'beauty_closeup':
            prompt_json = {
                "scene": "Professional beauty photography studio",
                "subjects": [{
                    "type": "beauty portrait subject",
                    "description": "Person from input image in beauty close-up",
                    "framing": "tight close-up, mid-forehead to chin, face fills frame",
                    "features": {
                        "eyes": "sharp, bright, captivating, enhanced but natural",
                        "lips": "defined and beautiful",
                        "eyebrows": "groomed and shaped",
                        "skin": "flawless, luminous, natural texture retained"
                    },
                    "presentation": "beauty-ready, camera-ready for beauty campaign"
                }],
                "style": "Professional beauty close-up photography",
                "lighting": {
                    "type": "classic beauty lighting",
                    "setup": ["butterfly/paramount light", "beauty dish for glamorous wrap-around"],
                    "quality": "soft, even, minimizes texture while maintaining dimension",
                    "catchlights": "ring light or similar for signature catchlights",
                    "shadows": "filled adequately for beauty standard"
                },
                "skin": {
                    "quality": "flawless, luminous, still appears natural",
                    "texture": "subtle, pores visible but minimized",
                    "tone": "even, smooth but not plastic",
                    "glow": "healthy",
                    "goal": "best-possible while remaining believable"
                },
                "mood": "beautiful, glamorous, polished",
                "composition": {
                    "style": "centered or near-centered typical of beauty",
                    "symmetry": "attention to facial symmetry, embrace natural asymmetries",
                    "angle": "head angle chosen to present features optimally"
                },
                "camera": {
                    "angle": "eye level or slightly above",
                    "distance": "extreme close-up",
                    "lens": "100mm macro or 85mm",
                    "focus": "extreme sharpness on eyes and key features"
                },
                "technical": {
                    "quality": "highest, no noise",
                    "colors": "accurate and beautiful",
                    "standard": "professional beauty photography"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'athletic':
            prompt_json = {
                "scene": "Dynamic athletic portrait environment",
                "subjects": [{
                    "type": "athletic portrait subject",
                    "description": "Person from input image as athlete",
                    "pose": "powerful stance, dynamic body positioning, flexed muscles or action pose",
                    "expression": "determined, focused, intense, competitive fire",
                    "body_language": "communicates physical capability and athletic prowess",
                    "energy": "implied motion even in stillness"
                }],
                "style": "Dynamic athletic portrait photography, sports photography quality",
                "environment": {
                    "options": ["clean dark background hex #1A1A1A", "gym/training environment", "outdoor athletic setting", "sport-specific location"],
                    "purpose": "enhance athletic narrative"
                },
                "lighting": {
                    "type": "dramatic, sculpts musculature",
                    "quality": "hard, directional for defined muscles",
                    "shadows": "dramatic",
                    "rim_light": "separates subject, adds dimension",
                    "purpose": "enhance physicality"
                },
                "mood": "powerful, determined, focused, intense, raw energy",
                "movement": {
                    "feel": "convey motion and capability",
                    "options": ["frozen action", "implied movement", "powerful stillness"],
                    "body": "looks capable and trained"
                },
                "composition": {
                    "focus": "on physique and form",
                    "style": "dynamic sports photography"
                },
                "camera": {
                    "angle": "dynamic, possibly low angle for power",
                    "distance": "full body or upper body",
                    "lens": "70-200mm sports lens"
                },
                "color_palette": {
                    "options": ["bold and energetic", "dramatic and moody"],
                    "contrast": "high for muscle definition"
                },
                "styling": "athletic wear, sport-specific attire, intentional and narrative-enhancing",
                "technical": {
                    "focus": "sharp on subject",
                    "motion": "possible motion elements if appropriate",
                    "quality": "professional sports photography"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'creative_color':
            prompt_json = {
                "scene": "Creative color portrait studio with colored lighting",
                "subjects": [{
                    "type": "creative color portrait subject",
                    "description": "Person from input image with bold colored lighting",
                    "pose": "contemporary, artistic positioning",
                    "expression": "edgy, creative, modern"
                }],
                "style": "Creative color portrait photography, artistic, contemporary",
                "color_palette": {
                    "approach": "bold, intentional, primary creative element",
                    "schemes": ["complementary cyan hex #00FFFF and red hex #FF0000", "magenta hex #FF00FF and green hex #00FF00", "analogous harmonies", "bold single-color dominance"],
                    "sources": ["neon gels", "colored lighting", "creative grading"],
                    "saturation": "high and vibrant where appropriate"
                },
                "lighting": {
                    "type": "creative colored lighting",
                    "sources": ["gel lights", "neon sources", "LED color mixing"],
                    "effect": "multiple colored sources creating interplay of hues",
                    "approach": "embrace color casts as creative elements, lighting as painterly tool"
                },
                "mood": "artistic, contemporary, edgy, creative, futuristic",
                "composition": {
                    "style": "contemporary, artistic",
                    "elements": ["negative space", "unconventional framing", "graphic elements"],
                    "purpose": "complement creative color approach"
                },
                "camera": {
                    "angle": "creative, unconventional",
                    "distance": "varies for impact",
                    "lens": "35mm or 85mm"
                },
                "background": {
                    "options": ["dark hex #0A0A0A to make colors pop", "colored to complement lighting"],
                    "purpose": "support overall color concept"
                },
                "reference": "music video stills, contemporary fashion editorials, creative advertising",
                "technical": {
                    "skin": "colored light flattering on skin tones",
                    "colors": "vibrant and intentional, not muddy",
                    "quality": "visually striking and current"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'vintage_retro':
            prompt_json = {
                "scene": "Vintage/retro portrait with classic film aesthetic",
                "subjects": [{
                    "type": "vintage portrait subject",
                    "description": "Person from input image in nostalgic film style",
                    "pose": "period-appropriate, classic",
                    "expression": "timeless, romantic, era-authentic"
                }],
                "style": "Vintage/retro portrait photography, classic film aesthetics",
                "film_aesthetic": {
                    "options": ["1970s warm tones", "1980s bold colors", "Polaroid instant film", "Kodachrome saturation", "Fuji film greens"],
                    "approach": "specific era or film stock informs entire aesthetic"
                },
                "color_grading": {
                    "style": "period-appropriate color science",
                    "blacks": "lifted",
                    "highlights": "rolled-off",
                    "color_casts": "era-specific",
                    "shadows": "faded, vintage crossovers",
                    "feel": "nostalgic and era-authentic"
                },
                "grain": {
                    "type": "film grain, organic, not digital noise",
                    "intensity": "subtle or prominent based on film stock",
                    "artifacts": ["possible halation", "light leaks if appropriate"]
                },
                "lighting": {
                    "style": "period-appropriate",
                    "options": ["natural light of the era", "studio techniques of the time", "flash photography aesthetic"],
                    "approach": "how photographers of chosen era would light subjects"
                },
                "mood": "nostalgic, timeless, romantic, era-specific, warm",
                "composition": {
                    "style": "classic film photography",
                    "feel": "transport viewers to another time"
                },
                "camera": {
                    "emulation": "vintage process characteristics",
                    "dynamic_range": "era-specific",
                    "depth_of_field": "period-appropriate"
                },
                "post_processing": {
                    "style": "authentic film emulation",
                    "consistency": "complete vintage workflow feel",
                    "imperfections": "become aesthetic choices"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'minimalist':
            prompt_json = {
                "scene": "Minimalist portrait setting with refined simplicity",
                "subjects": [{
                    "type": "minimalist portrait subject",
                    "description": "Person from input image in simple, elegant presentation",
                    "pose": "simple, elegant, unforced, natural and relaxed",
                    "expression": "quiet strength, calm, contemplative",
                    "styling": "simple, minimal wardrobe, solid colors, clean lines, no busy patterns"
                }],
                "style": "Minimalist portrait photography, maximum impact through minimal elements",
                "background": {
                    "type": "simple, clean, undistracting",
                    "options": ["solid color hex #F5F5F5", "subtle gradient", "very minimal texture"],
                    "colors": ["white", "soft gray hex #E0E0E0", "single muted color"],
                    "purpose": "provide breathing room, not compete with subject"
                },
                "negative_space": {
                    "amount": "generous, 60-80% of frame can be empty",
                    "purpose": "intentional use of space, every element earns its place"
                },
                "lighting": {
                    "type": "simple, clean, creates form without complexity",
                    "setup": "single soft source or simple two-light",
                    "shadows": "avoid complex or dramatic unless very intentional",
                    "role": "quiet element, not a statement"
                },
                "mood": "calm, serene, contemplative, peaceful, quiet sophistication",
                "composition": {
                    "style": "clean, uncluttered",
                    "approach": "subject positioned with intentional space use",
                    "quality": "meditative, space to breathe"
                },
                "camera": {
                    "angle": "simple, direct",
                    "distance": "medium shot with space",
                    "lens": "85mm"
                },
                "color_palette": {
                    "approach": "restricted, harmonious",
                    "style": "monochromatic or very limited palette",
                    "quality": "no visual noise, intentional and curated"
                },
                "philosophy": "less is more, every choice deliberate, impact through restraint and refinement",
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'cultural':
            prompt_json = {
                "scene": "Cultural portrait setting celebrating heritage and tradition",
                "subjects": [{
                    "type": "cultural portrait subject",
                    "description": "Person from input image in authentic cultural presentation",
                    "styling": "traditional clothing, textiles, jewelry, accessories authentic to culture",
                    "expression": "dignified, proud, embodying strength and beauty of heritage",
                    "presence": "authentic and meaningful representation"
                }],
                "style": "Cultural portrait photography, respectful and celebratory",
                "cultural_authenticity": {
                    "approach": "respectful, authentic representation of heritage",
                    "avoid": "stereotypes or superficial representation",
                    "goal": "honor and celebrate cultural identity"
                },
                "wardrobe": {
                    "elements": ["traditional clothing", "textiles", "jewelry", "cultural accessories"],
                    "quality": "attention to detail and authenticity",
                    "representation": "respectful and accurate"
                },
                "lighting": {
                    "style": "complements cultural aesthetic, enhances traditional elements",
                    "options": ["natural light for authenticity", "studio lighting for textile details"],
                    "quality": "warm, respectful illumination"
                },
                "background": {
                    "options": ["simple to focus on person", "environmental for cultural context"],
                    "colors": "harmonize with cultural aesthetic"
                },
                "mood": "celebratory, respectful, dignified, proud",
                "composition": {
                    "style": "cultural portrait",
                    "focus": "subject and traditional elements"
                },
                "camera": {
                    "angle": "respectful, dignified",
                    "distance": "medium shot showing cultural attire",
                    "lens": "85mm portrait"
                },
                "color_palette": {
                    "approach": "authentic to cultural palette",
                    "elements": ["traditional colors", "natural dyes", "cultural color symbolism"]
                },
                "technical": {
                    "quality": "high, honors subject and representation",
                    "detail": "sharp on traditional elements",
                    "colors": "rich, accurate representation of textiles"
                },
                "sensitivity": "celebrating rather than appropriating, honoring rather than othering",
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'conceptual':
            prompt_json = {
                "scene": "Conceptual portrait with artistic symbolism and creative vision",
                "subjects": [{
                    "type": "conceptual portrait subject",
                    "description": "Person from input image in artistic conceptual presentation",
                    "role": "vehicle for artistic ideas",
                    "interaction": "with symbolic props, surreal elements, or creative techniques"
                }],
                "style": "Conceptual portrait photography, fine art sensibility",
                "concept": {
                    "approach": "convey idea, emotion, or narrative beyond simple representation",
                    "elements": ["symbolic props", "visual metaphors", "surreal touches"],
                    "purpose": "image tells a story or expresses a concept"
                },
                "creative_elements": {
                    "types": ["symbolic props", "unusual compositions", "surreal elements", "creative techniques"],
                    "purpose": "support and express conceptual intent",
                    "balance": "between portrait and artistic expression"
                },
                "artistic_vision": {
                    "sensibility": "fine art, creative expression not documentation",
                    "influences": ["art history", "contemporary art", "conceptual photography"]
                },
                "visual_storytelling": {
                    "approach": "every element contributes to narrative",
                    "elements": ["composition", "lighting", "color", "styling"],
                    "goal": "engage viewer in interpretation and meaning-making"
                },
                "mood": "surreal, dreamlike, provocative, peaceful, or transformative as concept requires",
                "composition": {
                    "style": "creative, possibly unconventional",
                    "approach": "serves the concept, break rules intentionally when supporting vision"
                },
                "camera": {
                    "angle": "serves conceptual intent",
                    "distance": "varies for artistic impact",
                    "lens": "varies for creative effect"
                },
                "technical": {
                    "execution": "high-quality, flawless execution of creative concepts",
                    "quality": "technical excellence in service of artistic vision"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'dating':
            vibe = data.get('dating_vibe', 'confident_authentic')
            vibe_descriptions = {
                "confident_authentic": "confident and genuinely authentic",
                "playful_fun": "playful and fun-loving",
                "warm_approachable": "warm and approachable",
                "adventurous": "adventurous and exciting",
                "sophisticated": "sophisticated and classy",
                "casual_relaxed": "casual and relaxed"
            }
            prompt_json = {
                "scene": "Dating profile photo setting optimized for dating apps",
                "subjects": [{
                    "type": "dating profile subject",
                    "description": "Person from input image looking attractive and approachable",
                    "vibe": vibe_descriptions.get(vibe, "confident and authentic"),
                    "expression": "genuine smile reaching eyes, warm, inviting connection",
                    "body_language": "approachable, confident but not arrogant, natural",
                    "pose": "natural, relaxed, shows personality, slight angle for dimension"
                }],
                "style": "Dating profile photography, scroll-stopping, genuine personality",
                "optimization": {
                    "platforms": ["Tinder", "Bumble", "Hinge"],
                    "goal": "immediate positive impression, scroll-stopping",
                    "appeal": ["genuine smiles", "eye contact with camera", "warm lighting", "clean backgrounds", "confident body language"]
                },
                "lighting": {
                    "type": "warm, flattering, enhances natural features",
                    "options": ["golden hour warmth hex #FFB347", "soft natural light"],
                    "colors": "vibrant but natural, pop on mobile screens",
                    "quality": "eye-catching without oversaturation"
                },
                "background": {
                    "style": "clean, uncluttered, doesn't distract",
                    "options": ["suggests lifestyle - café, outdoors, travel", "blurred for focus on subject"],
                    "focus": "subject is clearly the focus"
                },
                "mood": vibe_descriptions.get(vibe, "confident and authentic"),
                "composition": {
                    "framing": "head and shoulders or upper body",
                    "angle": "slight angle not straight-on for dimension",
                    "feel": "great candid photo, not formal portrait"
                },
                "camera": {
                    "angle": "eye level or slightly above",
                    "distance": "medium close-up",
                    "lens": "50mm or 85mm",
                    "focus": "sharp on face",
                    "bokeh": "pleasing if background visible"
                },
                "authenticity": {
                    "goal": "look like yourself on your best day",
                    "approach": "enhanced but not transformed beyond recognition",
                    "test": "the person you meet should recognize you"
                },
                "technical": {
                    "quality": "professional but not overly produced",
                    "feel": "natural, candid-feeling moment"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'influencer':
            aesthetic = data.get('aesthetic', 'glamorous')
            aesthetic_specs = {
                "glamorous": {"feel": "luxury, aspirational", "lighting": "perfect, high-end", "colors": "rich, polished"},
                "natural_beauty": {"feel": "authentic, relatable", "lighting": "soft, effortless", "colors": "natural, approachable"},
                "golden_hour": {"feel": "warm, dreamy, romantic", "lighting": "sun-kissed hex #FFD700", "colors": "golden, warm tones"},
                "urban_chic": {"feel": "street style, trendy", "lighting": "city environment", "colors": "fashion-forward"},
                "soft_dreamy": {"feel": "ethereal, romantic", "lighting": "soft focus elements", "colors": "pastel tones"},
                "vibrant_bold": {"feel": "energetic, dynamic", "lighting": "high impact", "colors": "saturated, vibrant"}
            }
            current_aesthetic = aesthetic_specs.get(aesthetic, aesthetic_specs["glamorous"])
            prompt_json = {
                "scene": f"Social media influencer portrait with {aesthetic.replace('_', ' ')} aesthetic",
                "subjects": [{
                    "type": "influencer portrait subject",
                    "description": "Person from input image as social media influencer",
                    "pose": "natural yet photogenic, practiced casualness",
                    "expression": "confident, engaging, relatable, connects with audience",
                    "styling": "trend-aware, aesthetically consistent, camera-ready hair and makeup"
                }],
                "style": "Social media influencer photography, Instagram-ready",
                "aesthetic": {
                    "name": aesthetic.replace('_', ' '),
                    "feel": current_aesthetic["feel"],
                    "lighting_style": current_aesthetic["lighting"],
                    "color_approach": current_aesthetic["colors"]
                },
                "platform_optimization": {
                    "format": "Instagram-ready, square or 4:5 format friendly",
                    "goal": "scroll-stopping, high engagement potential",
                    "quality": "eye-catching for social media context"
                },
                "lighting": {
                    "type": "flattering, consistent with aesthetic",
                    "quality": "soft, beautiful light, makes subject look best",
                    "options": ["golden hour warmth", "ring light glamour", "natural window light"]
                },
                "mood": current_aesthetic["feel"],
                "composition": {
                    "style": "influencer photography",
                    "body_language": "works for chosen aesthetic"
                },
                "camera": {
                    "angle": "flattering social media angles",
                    "distance": "medium shot",
                    "lens": "35mm or 50mm"
                },
                "post_processing": {
                    "color_grading": "clean, consistent, matches aesthetic",
                    "retouching": "flattering but not obviously filtered",
                    "feel": "cohesive feed aesthetic"
                },
                "engagement": {
                    "goal": "make viewers stop scrolling and want to follow",
                    "quality": "aspirational yet achievable, beautiful but relatable"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'luxury':
            prompt_json = {
                "scene": "Luxury portrait setting exuding wealth, power, sophistication",
                "subjects": [{
                    "type": "luxury portrait subject",
                    "description": "Person from input image in premium, high-end presentation",
                    "styling": "designer attire, impeccable grooming, luxury accessories",
                    "expression": "confident, powerful, sophisticated, assured authority",
                    "presence": "someone accustomed to success, elegant not arrogant"
                }],
                "style": "Luxury portrait photography, premium brand quality",
                "background": {
                    "options": ["clean dark hex #0A0A0A for timeless luxury", "clean light hex #F8F8F8", "sophisticated environmental"],
                    "quality": "every element suggests quality and wealth"
                },
                "lighting": {
                    "type": "rich, sophisticated, suggests premium quality",
                    "quality": "dramatic but controlled, luxury brand advertising feel",
                    "description": "beautiful light that enhances without being obvious",
                    "feel": "professional, refined, expensive-looking"
                },
                "mood": "confident, powerful, sophisticated, elegant",
                "composition": {
                    "style": "elegant, refined",
                    "approach": "strong but not aggressive, classical with contemporary edge",
                    "precision": "every element precisely placed"
                },
                "camera": {
                    "angle": "powerful, sophisticated",
                    "distance": "medium shot",
                    "lens": "85mm or 105mm"
                },
                "color_palette": {
                    "style": "rich, sophisticated",
                    "colors": ["deep black hex #0A0A0A", "clean white hex #FAFAFA", "gold accents hex #D4AF37", "jewel tones"],
                    "feel": "expensive and intentional"
                },
                "post_processing": {
                    "quality": "premium, flawless execution",
                    "retouching": "refined",
                    "tones": "rich",
                    "reference": "luxury brand campaign or premium magazine"
                },
                "aspirational": "represent pinnacle of success and sophistication",
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'avatar':
            style = data.get('style', 'semi_realistic')
            style_specs = {
                "semi_realistic": {"approach": "painterly quality, slightly idealized", "technique": "artistic interpretation of reality"},
                "3d_pixar": {"approach": "Pixar/Disney animation style", "technique": "3D rendered, expressive features, appealing character design"},
                "anime": {"approach": "Japanese animation aesthetic", "technique": "large expressive eyes, anime hair, cel-shaded"},
                "comic_book": {"approach": "comic/graphic novel style", "technique": "bold lines, dynamic rendering, superhero aesthetic"},
                "digital_art": {"approach": "contemporary digital painting", "technique": "vibrant colors, visible brushwork, modern illustration"},
                "fantasy": {"approach": "fantasy character aesthetic", "technique": "ethereal or heroic qualities, fantastical elements"}
            }
            current_style = style_specs.get(style, style_specs["semi_realistic"])
            prompt_json = {
                "scene": f"Stylized avatar portrait with {style.replace('_', ' ')} aesthetic",
                "subjects": [{
                    "type": "avatar subject",
                    "description": "Person from input image transformed into stylized avatar",
                    "likeness": "recognizably the same person despite stylization",
                    "features_preserved": ["face shape", "eye configuration", "notable features"],
                    "result": "person should see themselves in the avatar"
                }],
                "style": f"{current_style['approach']}, professional digital art",
                "style_direction": {
                    "name": style.replace('_', ' '),
                    "approach": current_style["approach"],
                    "technique": current_style["technique"]
                },
                "artistic_quality": {
                    "execution": "high-quality digital art, not cheap filter effect",
                    "consistency": "style consistent throughout image",
                    "level": "professional illustration quality"
                },
                "character_design": {
                    "appeal": "engaging in chosen style",
                    "principles": ["readable silhouette", "expressive features", "visual appeal"]
                },
                "technical": {
                    "execution": "clean, professional digital art",
                    "rendering": "appropriate for style - cel-shaded, painterly, 3D, etc.",
                    "consistency": "styling consistent throughout"
                },
                "use_case": {
                    "applications": ["social media profile pictures", "gaming avatars", "personal branding", "digital identity"],
                    "sizes": "works at various sizes"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'founder_headshot':
            vibe = data.get('vibe', 'visionary')
            vibe_specs = {
                "visionary": {"energy": "forward-looking, innovative, seeing possibilities", "reference": "Steve Jobs energy"},
                "approachable_ceo": {"energy": "warm, accessible, team-builder", "reference": "servant leadership feel"},
                "tech_innovator": {"energy": "modern, technical credibility", "reference": "Silicon Valley aesthetic"},
                "disruptor": {"energy": "bold, challenging status quo", "reference": "confident rule-breaker"},
                "thought_leader": {"energy": "intellectual, authoritative", "reference": "expert presence"},
                "creative_founder": {"energy": "artistic, innovative", "reference": "design-forward sensibility"}
            }
            current_vibe = vibe_specs.get(vibe, vibe_specs["visionary"])
            prompt_json = {
                "scene": f"Startup founder headshot with {vibe.replace('_', ' ')} leadership presence",
                "subjects": [{
                    "type": "founder headshot subject",
                    "description": "Person from input image as startup founder/CEO",
                    "vibe": current_vibe["energy"],
                    "expression": "confident, visionary, determined, trustworthy for investment",
                    "presence": "approachable yet authoritative, ready to lead",
                    "styling": "smart casual or startup appropriate, contemporary, confident"
                }],
                "style": "Startup founder headshot, pitch-deck ready",
                "leadership_vibe": {
                    "name": vibe.replace('_', ' '),
                    "energy": current_vibe["energy"],
                    "reference": current_vibe["reference"]
                },
                "context": {
                    "use_cases": ["pitch decks", "investor meetings", "company about pages", "speaking engagements", "press features"],
                    "goal": "convey leadership credibility and founder archetype"
                },
                "background": {
                    "style": "clean, modern",
                    "options": ["simple backdrop hex #2D2D2D", "modern office blur", "tech-appropriate environment"],
                    "feel": "contemporary, founder-appropriate, not traditional corporate"
                },
                "lighting": {
                    "style": "professional but not corporate-stiff",
                    "quality": "modern, confident, suggests innovation",
                    "drama": "slightly dramatic acceptable for founder context"
                },
                "mood": current_vibe["energy"],
                "composition": {
                    "framing": "head and shoulders, founder portrait",
                    "style": "professional yet approachable"
                },
                "camera": {
                    "angle": "confident, eye level or slightly below",
                    "distance": "close-up to medium",
                    "lens": "85mm portrait"
                },
                "narrative": "building something important, leading a team, ready to change industry",
                "technical": {
                    "quality": "high, suitable for large format print and digital",
                    "sharpness": "professional",
                    "impact": "confidence-inspiring"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'restoration':
            prompt_json = {
                "scene": "Photo restoration and enhancement",
                "subjects": [{
                    "type": "restoration subject",
                    "description": "Person from input image with quality improvements",
                    "skin": "natural enhancement, even tone, reduced blemishes, natural texture maintained",
                    "eyes": "brightened naturally",
                    "features": "enhanced naturally while preserving character"
                }],
                "style": "Professional photo restoration and enhancement",
                "restoration_goals": {
                    "approach": "fix damage and imperfections while maintaining authentic character",
                    "philosophy": "improve without over-processing or artificial appearance"
                },
                "quality_enhancement": {
                    "resolution": "improved",
                    "sharpness": "enhanced appropriately",
                    "noise": "reduced",
                    "artifacts": "removed",
                    "detail": "enhanced clarity",
                    "level": "professional-grade improvement"
                },
                "color_correction": {
                    "balance": "accurate, pleasing",
                    "color_casts": "fixed",
                    "consistency": "improved",
                    "colors": "rich, natural",
                    "white_balance": "proper",
                    "exposure": "optimized"
                },
                "technical_fixes": {
                    "lighting": "problems addressed",
                    "contrast": "improved",
                    "dynamic_range": "enhanced",
                    "sharpness": "appropriate level",
                    "blur": "reduced if present"
                },
                "authenticity": {
                    "goal": "maintain essential character of original",
                    "enhancement": "invisible - looks like well-captured image",
                    "processing": "not obviously processed"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        elif mode == 'style_transfer':
            style = data.get('style', 'artistic')
            prompt_json = {
                "scene": f"Artistic style transfer with {style.replace('_', ' ')} styling",
                "subjects": [{
                    "type": "style transfer subject",
                    "description": "Person from input image with artistic style applied",
                    "likeness": "clear, immediately recognizable",
                    "focus": "subject remains the clear focus"
                }],
                "style": f"{style.replace('_', ' ')} artistic styling",
                "style_application": {
                    "approach": f"apply {style.replace('_', ' ')} visual style to portrait",
                    "goal": "transform aesthetic while preserving identity",
                    "quality": "thoughtful application, not simple filter"
                },
                "artistic_quality": {
                    "level": "high-quality artistic transformation",
                    "execution": "professional quality output"
                },
                "consistency": {
                    "application": "style applied consistently across entire image",
                    "approach": "unified aesthetic throughout"
                },
                "balance": {
                    "goal": "right balance between style transformation and portrait integrity",
                    "subject": "clear focus, immediately recognizable"
                },
                "face_preservation": face_preserve_obj,
                "additional_instructions": prompt
            }
            arguments['prompt'] = json.dumps(prompt_json, indent=2)

        # Advanced parameters
        if 'temperature' in data:
            arguments['temperature'] = float(data['temperature'])
        if 'seed' in data and data['seed']:
            arguments['seed'] = int(data['seed'])

        print(f"Calling Nano Banana Pro API with mode: {mode}, arguments: {arguments}")

        # Call Google's Nano Banana Pro (Nano Banana 2) API - State-of-the-art image generation and editing
        try:
            result = client.subscribe(
                "fal-ai/nano-banana-pro/edit",
                arguments=arguments,
                with_logs=True,
                on_queue_update=on_queue_update
            )

            if not result:
                raise ValueError("Invalid response from Nano Banana Pro API")

            # Process results based on mode
            results_data = {
                'mode': mode,
                'progress': progress_updates,
                'images': [],
                'metadata': {}
            }

            # Handle the response format from Nano Banana API
            # Response format: {"images": [{"url": "..."}], "description": "..."}
            if 'images' in result:
                for img in result['images']:
                    if img.get('url'):
                        local_url, filename, width, height = save_result_image(img['url'])

                        # Save to gallery with the actual JSON prompt sent to API
                        try:
                            gallery_image = Image(
                                filename=filename,
                                prompt=arguments['prompt'],  # Save the full JSON prompt
                                art_style=f'nano_{mode}',
                                width=width,
                                height=height,
                                user_id=current_user.id
                            )
                            db.session.add(gallery_image)
                            db.session.commit()
                            
                            results_data['images'].append({
                                'url': local_url,
                                'gallery_id': gallery_image.id,
                                'width': width,
                                'height': height
                            })
                        except Exception as e:
                            print(f"Error saving to gallery: {str(e)}")
                            db.session.rollback()
                            results_data['images'].append({
                                'url': local_url,
                                'width': width,
                                'height': height
                            })
            elif 'image' in result:
                # Single image result (fallback)
                if result['image'].get('url'):
                    local_url, filename, width, height = save_result_image(result['image']['url'])

                    try:
                        gallery_image = Image(
                            filename=filename,
                            prompt=arguments['prompt'],  # Save the full JSON prompt
                            art_style=f'nano_{mode}',
                            width=width,
                            height=height,
                            user_id=current_user.id
                        )
                        db.session.add(gallery_image)
                        db.session.commit()
                        
                        results_data['images'].append({
                            'url': local_url,
                            'gallery_id': gallery_image.id,
                            'width': width,
                            'height': height
                        })
                    except Exception as e:
                        print(f"Error saving to gallery: {str(e)}")
                        db.session.rollback()
                        results_data['images'].append({
                            'url': local_url,
                            'width': width,
                            'height': height
                        })
            
            # Add description if available
            if 'description' in result:
                results_data['metadata']['description'] = result['description']

            # Add metadata
            results_data['metadata'] = {
                'seed': result.get('seed'),
                'prompt': result.get('prompt', prompt),
                'mode': mode,
                'timestamp': str(uuid.uuid4())
            }

            # Track usage
            current_user.use_feature(
                feature_type='magix',
                amount=len(results_data['images']),
                extra_data={
                    'mode': mode,
                    'prompt': prompt,
                    'images_generated': len(results_data['images'])
                }
            )
            
            return jsonify(results_data)

        except Exception as e:
            print(f"Error calling Nano Banana Pro API: {str(e)}")
            return jsonify({'error': 'Generation failed. Please try again.'}), 500

    except Exception as e:
        print(f"Error in generate_magix: {str(e)}")
        return jsonify({'error': 'An error occurred. Please try again.'}), 500


@magix_bp.route('/api/magix/history/<int:user_id>')
@limiter.limit(get_rate_limit_string())
@login_required
def get_history(user_id):
    """Get user's Nano Studio history"""
    # Use is_admin() method instead of is_admin attribute for proper authorization check
    if current_user.id != user_id and not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        images = Image.query.filter_by(user_id=user_id)\
                           .filter(Image.art_style.like('nano_%'))\
                           .order_by(Image.created_at.desc())\
                           .limit(50)\
                           .all()

        history = []
        for img in images:
            history.append({
                'id': img.id,
                'url': f'/static/images/{img.filename}',
                'prompt': img.prompt,
                'mode': img.art_style.replace('nano_', ''),
                'created_at': img.created_at.isoformat()
            })

        return jsonify({'history': history})

    except Exception as e:
        print(f"Error fetching history: {str(e)}")
        return jsonify({'error': 'Failed to fetch history'}), 500