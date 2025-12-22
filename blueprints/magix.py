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

        # Base instruction for facial preservation - comprehensive
        face_preserve = """CRITICAL REQUIREMENT - FACIAL PRESERVATION: You must preserve and retain 100% of the original facial features with absolute precision. This includes: the exact face shape and bone structure, eye shape, color, size and spacing, nose shape and size, mouth and lip shape, eyebrow shape and position, skin texture and natural marks, ear shape if visible, hairline shape, and overall facial proportions. The person must be immediately recognizable as themselves. Do not idealize, beautify beyond recognition, or alter ethnic features. Maintain the subject's unique identity and likeness throughout the transformation."""

        # Mode-specific configurations - AI Photography Focus with comprehensive prompts
        if mode == 'studio_portrait':
            arguments['prompt'] = f"""Transform this image into a professional studio portrait photography with the following specifications:

LIGHTING SETUP: Use classic three-point lighting with a large softbox as key light positioned 45 degrees from subject creating soft, wrapping illumination. Add fill light at 2:1 ratio to gently open shadows while maintaining dimension. Include subtle hair/rim light from behind to separate subject from background and add depth. Ensure catchlights in eyes are visible and natural.

BACKGROUND: Clean, seamless backdrop - either pure white, neutral gray, or subtle gradient. Background should be evenly lit without hotspots or shadows. Slight vignette acceptable for focus on subject.

TECHNICAL QUALITY: Sharp focus on eyes, professional-grade image quality, no noise or grain, smooth skin with natural texture retained (not plastic), proper white balance for natural skin tones, high dynamic range preserving details in highlights and shadows.

COMPOSITION: Head and shoulders framing, subject positioned using rule of thirds, adequate headroom, eyes at upper third line, shoulders slightly angled for dimension, chin slightly forward and down for flattering angle.

RETOUCHING STYLE: Professional but natural - remove temporary blemishes, even skin tone, subtle under-eye correction, enhance but don't over-process. Maintain all natural features, pores, and skin texture.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'environmental':
            arguments['prompt'] = f"""Transform this image into a compelling environmental portrait that tells a story about the subject:

SETTING & CONTEXT: Place the subject in a meaningful, contextual environment that reveals something about their personality, profession, or interests. The background should complement and enhance the narrative without overwhelming the subject. Include relevant environmental details that add depth and interest.

LIGHTING: Utilize available natural light masterfully - window light, golden hour sunlight, or ambient environmental lighting. Balance subject exposure with background. Use natural light modifiers like doorways, windows, or architectural elements. Allow for natural shadows that add dimension and mood.

COMPOSITION: Use environmental elements to frame the subject naturally. Apply depth of field to separate subject from background while keeping context recognizable. Include leading lines, layers, and foreground/background elements for visual interest. Subject should occupy 30-50% of frame with meaningful negative space.

COLOR & MOOD: Natural, authentic color palette derived from environment. Cohesive color story between subject and surroundings. Mood should feel genuine and unposed while remaining visually compelling.

TECHNICAL: Sharp focus on subject's eyes, background appropriately soft but identifiable, professional image quality, balanced exposure throughout frame, natural skin tones.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'lifestyle':
            arguments['prompt'] = f"""Transform this image into an authentic lifestyle portrait capturing genuine, candid moments:

MOOD & FEEL: Natural, relaxed, and authentic - as if captured during a real moment in the subject's life. Avoid stiff or posed appearance. The image should feel warm, inviting, and relatable. Capture genuine emotion and personality.

LIGHTING: Soft, natural lighting that feels effortless - window light, open shade, or golden hour warmth. Avoid harsh shadows or artificial-looking illumination. Light should wrap around subject naturally, creating a comfortable, lived-in atmosphere.

SETTING: Casual, relatable environment - home interior, café, park, or everyday location. Background should feel natural and uncluttered while adding context. Include lifestyle elements that feel organic, not staged.

EXPRESSION & POSE: Relaxed, natural expression - genuine smile, thoughtful gaze, or candid moment. Body language should be comfortable and unforced. Slight motion or interaction with environment adds authenticity.

COLOR GRADING: Warm, inviting tones. Slightly lifted shadows for airy feel. Natural skin tones with subtle warmth. Clean whites, soft contrast. Instagram-worthy but not over-filtered.

COMPOSITION: Casual framing that feels spontaneous. Negative space for breathing room. Subject doesn't need to be centered. Include environmental context. Shoot as if capturing a moment, not posing for a photo.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'fashion_editorial':
            arguments['prompt'] = f"""Transform this image into a high-fashion editorial portrait worthy of Vogue or Harper's Bazaar:

LIGHTING: Dramatic, intentional lighting that sculpts features and creates visual impact. Options include: hard directional light for bold shadows, beauty dish for glamorous glow, dramatic side lighting for editorial edge, or creative mixed lighting. Lighting should be a deliberate creative choice that enhances the fashion narrative.

STYLING & AESTHETIC: High-fashion sensibility with attention to every detail. Emphasize clothing, accessories, and overall styling. Create a cohesive visual story. The image should feel curated, intentional, and magazine-ready. Bold, confident, and fashion-forward.

POSE & EXPRESSION: Editorial poses with attitude and intention. Strong body lines, dynamic angles, and purposeful positioning. Expression should convey confidence, mystery, or high-fashion aloofness. Elongate the body, create interesting shapes, emphasize fashion elements.

COMPOSITION: Bold, graphic composition with strong visual impact. Use negative space dramatically. Unconventional framing encouraged. Create tension and visual interest through positioning and cropping. Magazine cover or spread worthy.

POST-PROCESSING: Fashion-grade retouching - flawless skin while maintaining texture, enhanced eyes, sculpted features through light and shadow. Color grading should support the editorial concept - could be rich and saturated, desaturated and moody, or high-contrast black and white.

PRODUCTION VALUE: Every element should feel intentional and elevated. Hair styled to perfection, makeup editorial-ready, clothing presented beautifully. The complete package of high-fashion photography.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'cinematic':
            arguments['prompt'] = f"""Transform this image into a cinematic portrait that looks like a still from a major motion picture:

LIGHTING: Cinematic lighting techniques - motivated lighting that appears to come from a natural source within the scene. Use of practicals, window light, or dramatic single-source illumination. Strong light-to-shadow ratio creating mood and depth. Rim lighting to separate subject from background. Consider classic cinema lighting: Rembrandt, split light, or atmospheric haze.

DEPTH & ATMOSPHERE: Shallow depth of field (f/1.4-2.8 equivalent) with creamy bokeh. Subject sharp, background beautifully blurred. Add atmospheric elements if appropriate - subtle haze, dust particles in light beams, or environmental depth. Create layers of foreground, subject, and background.

COLOR GRADING: Cinematic color science - could be teal and orange complementary scheme, desaturated with selective color, rich shadows with film-like rolloff, or specific movie color palette (Blade Runner neons, Amelie greens, Matrix greens, etc.). Lifted blacks for film look, controlled highlights.

ASPECT RATIO FEEL: Even if not cropped, compose as if shooting 2.39:1 or 1.85:1 widescreen. Cinematic framing with purposeful negative space. Subject positioned for dramatic effect.

MOOD: Contemplative, dramatic, or emotionally charged. The image should tell a story or suggest a narrative. Evoke curiosity about what's happening or about to happen. Movie poster or film still quality.

TECHNICAL: Film-like grain if appropriate (subtle, not overwhelming), high dynamic range, rich shadows with detail, controlled highlights, professional color depth.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'corporate_headshot':
            background = data.get('background', 'neutral_gray')
            arguments['prompt'] = f"""Transform this image into a polished corporate headshot suitable for LinkedIn, company websites, and professional materials:

BACKGROUND: {background.replace('_', ' ')} background - clean, professional, non-distracting. If office environment, use shallow depth of field to blur while maintaining professional context. Solid backgrounds should be evenly lit without gradients or shadows.

LIGHTING: Professional, flattering illumination that conveys competence and approachability. Soft key light at 30-45 degrees, fill light to reduce shadows to professional level (not flat, but not dramatic). Subtle rim light for separation. Even, consistent lighting that would work for company-wide headshot consistency.

EXPRESSION & POSE: Confident, approachable, professional expression - genuine but controlled smile or pleasant neutral expression. Direct eye contact with camera. Shoulders at slight angle (not straight-on), head straight or very slight tilt. Chin slightly forward for defined jawline. Posture conveying confidence and competence.

ATTIRE & GROOMING: Ensure professional appearance - neat, polished look appropriate for business environment. Clothing should be crisp and professional. Hair neat and styled. Overall impression of someone you'd want to do business with.

FRAMING: Head and shoulders composition, tight enough to see facial features clearly but with adequate breathing room. Centered or rule-of-thirds positioning. Consistent with professional headshot standards.

RETOUCHING: Professional but authentic - remove temporary blemishes, minimize under-eye shadows, even skin tone, subtle enhancement while maintaining authentic appearance. The person should look like themselves on their best day, not artificially perfected.

COLOR: Natural, accurate skin tones. Clean whites in eyes. Professional color balance - not too warm or cool. Colors should work in both digital and print contexts.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'street_portrait':
            arguments['prompt'] = f"""Transform this image into a compelling street portrait with urban authenticity:

URBAN ENVIRONMENT: Authentic city backdrop - textured walls, graffiti, urban architecture, neon signs, or street scenes. The environment should feel real and lived-in, adding character and context. Include urban textures, layers, and visual interest without overwhelming the subject.

LIGHTING: Natural street lighting - could be harsh midday sun with hard shadows, golden hour warmth in urban canyon, neon and artificial city lights, or overcast diffused light. Embrace imperfect lighting as part of the authentic street aesthetic. Mixed color temperatures welcome.

MOOD & ATTITUDE: Raw, authentic energy and genuine character. The subject should feel connected to their urban environment. Capture personality, attitude, and individuality. Street photography sensibility - real, unpolished, honest.

COMPOSITION: Dynamic street photography composition - use of leading lines, urban geometry, layers of depth. Subject can be off-center, partially framed, or interacting with environment. Include environmental context that tells a story. Shoot from interesting angles.

STYLE: Documentary-meets-portrait aesthetic. Not overly processed or artificial. Retain grit and authenticity of street photography while still being a compelling portrait. Colors can be bold or muted depending on environment.

TECHNICAL: Sharp focus on subject, environmental bokeh as appropriate, embrace some imperfection as authentic. Natural skin tones that work with environmental color cast. High-quality but not sterile.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'low_key':
            arguments['prompt'] = f"""Transform this image into a dramatic low-key portrait with powerful shadows and contrast:

LIGHTING CONCEPT: Predominantly dark image with selective, dramatic illumination. Single strong light source creating defined shadows and highlights. Light should sculpt the face, revealing form through shadow. Lighting ratio of 8:1 or higher. Consider: strong side light, Rembrandt lighting, or split lighting for maximum drama.

SHADOW TREATMENT: Deep, rich blacks that dominate the frame. Shadows should be intentional and compositional elements. Allow parts of the subject to fall into complete darkness. Shadow areas should be clean and noise-free. The darkness is not absence but presence.

HIGHLIGHTS: Controlled, precise highlights that draw attention to key features - eyes, facial planes, essential details. Highlights should not blow out but retain detail. The interplay between highlight and shadow creates the image's power.

MOOD: Mysterious, dramatic, powerful, contemplative, or intense. The darkness creates psychological depth and emotional weight. The image should feel intentional and artistic, not underexposed.

BACKGROUND: Pure black or nearly black, seamlessly blending with shadows on subject. No visible backdrop texture or color. Subject emerges from darkness.

TECHNICAL: Careful exposure for highlights while letting shadows go dark. Rich blacks without losing all shadow detail where intended. Sharp focus on illuminated areas. High contrast but controlled. Professional quality in both technical execution and artistic vision.

COMPOSITION: Use negative space (darkness) as compositional element. Subject can be positioned unconventionally. Let shadows frame and lead the eye to illuminated features.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'high_key':
            arguments['prompt'] = f"""Transform this image into a bright, airy high-key portrait:

LIGHTING CONCEPT: Predominantly bright image with minimal shadows. Multiple soft light sources creating even, wrap-around illumination. Low contrast with lifted shadows. Light should feel abundant and uplifting. Clean, fresh, optimistic mood.

BACKGROUND: Pure white or very light gray, evenly lit to near-white. No shadows, gradients, or visible texture. Subject should appear to exist in a bright, clean space. Background brightness should match or slightly exceed subject lighting.

SHADOW TREATMENT: Minimal shadows - fill all shadow areas with soft light. What shadows exist should be gentle, subtle, and never dark. Under-chin and under-nose shadows should be barely perceptible. Overall feeling of light everywhere.

MOOD: Fresh, clean, optimistic, youthful, pure, hopeful, or angelic. The abundance of light creates a positive, uplifting feeling. Image should feel open and inviting.

SKIN & COMPLEXION: Even, luminous skin with soft, glowing quality. Light wrapping around features. Subtle gradation in skin tones. Fresh, healthy appearance. Bright catchlights in eyes.

TECHNICAL: Careful exposure to retain detail in bright areas. White background should be white but subject should not be overexposed. Soft, flattering light on skin. No harsh shadows or contrast. Professional quality with intentional brightness.

COLOR PALETTE: Clean, fresh colors. Can be neutral/white dominant, soft pastels, or bright clean colors. Avoid muddy or dark tones. Whites should be true white, not gray or cream.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'black_white':
            arguments['prompt'] = f"""Transform this image into a timeless black and white portrait:

TONAL RANGE: Rich, full range of tones from deep blacks to bright whites with smooth gradation between. Ansel Adams Zone System sensibility - detail in shadows, detail in highlights, with full midtone range. The image should demonstrate mastery of monochromatic tonal values.

CONTRAST & MOOD: Consider the emotional intent - high contrast for drama and intensity, lower contrast for softness and intimacy, or full range for classic portraiture. Contrast should be a creative choice that supports the portrait's mood.

TEXTURE & DETAIL: Black and white emphasizes texture - skin texture, fabric, hair, environmental details. Ensure rich detail and texture throughout. The absence of color makes form, shape, and texture more prominent.

LIGHTING FOR B&W: Lighting should be considered specifically for how it translates to grayscale. Strong directional light often works beautifully. Consider how shadows will define features. Lighting that might seem harsh in color can be stunning in B&W.

SKIN TONES: Beautiful, luminous skin that translates well to grayscale. Even tonal rendering across different skin tones. Classic portraiture look with smooth gradation.

EMOTIONAL DEPTH: Black and white has timeless, emotional quality. The image should feel classic, artistic, and emotionally resonant. Strip away color distractions to focus on expression, form, and human connection.

STYLE OPTIONS: Could range from classic Karsh/Avedon portraiture to contemporary editorial B&W, from high-fashion contrast to soft romantic. The style should be intentional and consistent.

POST-PROCESSING: Professional black and white conversion with attention to how each color channel translates. Possible subtle film grain for texture. Dodging and burning to guide the eye. Classic darkroom quality.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'beauty_closeup':
            arguments['prompt'] = f"""Transform this image into a professional beauty close-up portrait:

FRAMING: Tight close-up focusing on face - from mid-forehead to chin, or even tighter cropping for specific features. Fill the frame with the subject's face. This is about showcasing facial features and beauty.

LIGHTING: Classic beauty lighting - butterfly/paramount light creating subtle shadow under nose, or beauty dish for glamorous wrap-around illumination. Soft, even lighting that minimizes texture while maintaining dimension. Ring light or similar for signature catchlights. Fill shadows adequately for beauty standard.

SKIN QUALITY: Flawless, luminous skin that still appears natural and has subtle texture. Professional beauty retouching - even tone, smooth but not plastic, healthy glow. Pores visible but minimized. The goal is best-possible skin while remaining believable.

FEATURES: Eyes should be sharp, bright, and captivating - enhanced but natural. Lips defined and beautiful. Eyebrows groomed and shaped. Each facial feature should be presented at its best while remaining true to the person.

MAKEUP & STYLING: Beauty-ready presentation - clean, polished, intentional. If makeup is present, it should be flawlessly applied. Hair styled and positioned deliberately. Everything should appear camera-ready for a beauty campaign.

SYMMETRY & COMPOSITION: Centered or near-centered composition typical of beauty photography. Attention to facial symmetry while embracing natural asymmetries that add character. Head angle and tilt chosen to present features optimally.

TECHNICAL: Extreme sharpness on eyes and key features. Highest quality capture with no noise. Colors accurate and beautiful. Professional beauty photography standard.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'athletic':
            arguments['prompt'] = f"""Transform this image into a dynamic athletic portrait showcasing strength and power:

POSE & ENERGY: Powerful stance conveying strength, athleticism, and confidence. Dynamic body positioning - flexed muscles, action poses, or powerful stillness. Body language should communicate physical capability and athletic prowess. Even in stillness, there should be implied motion and energy.

LIGHTING: Dramatic lighting that sculpts musculature and emphasizes physical form. Hard, directional light for defined muscles and dramatic shadows. Rim lighting to separate subject and add dimension. Consider dramatic single-source or motivated sport lighting. Lighting should enhance physicality.

MOOD & INTENSITY: Powerful, determined, focused, intense. The portrait should convey athletic mindset - concentration, determination, or competitive fire. Sweat and exertion are authentic elements. Raw, powerful energy.

ENVIRONMENT: Options include - clean dark background for focus on physique, gym/training environment for context, outdoor athletic setting, or sport-specific location. Environment should enhance athletic narrative.

MOVEMENT & DYNAMICS: Even in a still image, convey sense of motion and capability. Frozen action, implied movement, or powerful stillness. The body should look capable and trained. Consider motion blur or dynamic elements if appropriate.

TECHNICAL: Sharp focus on subject with possible motion elements. High contrast for muscle definition. Colors can be bold and energetic or dramatic and moody. Professional sports photography quality.

STYLING: Athletic wear, sport-specific attire, or minimal clothing to showcase physique. Everything should be intentional and enhance the athletic narrative.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'creative_color':
            arguments['prompt'] = f"""Transform this image into a creative color portrait with bold, artistic lighting:

COLOR PALETTE: Bold, intentional use of color - neon gels, colored lighting, creative color grading. Colors should be a primary creative element, not just accurate reproduction. Consider complementary color schemes (cyan/red, magenta/green), analogous harmonies, or bold single-color dominance.

LIGHTING: Creative colored lighting - gel lights, neon sources, LED color mixing. Multiple colored light sources creating interplay of hues on skin and environment. Embrace color casts as creative elements. Lighting becomes a painterly tool.

MOOD: Artistic, contemporary, edgy, creative, or futuristic. The bold colors create immediate visual impact and emotional response. Modern, fashion-forward, or experimental sensibility.

TECHNICAL APPROACH: Understand how colored light interacts with skin tones. Balance creative color with flattering subject representation. Colors should be vibrant and intentional, not muddy or accidental. High color saturation where appropriate.

COMPOSITION: Contemporary, artistic composition that complements the creative color approach. Use of negative space, unconventional framing, or graphic elements that enhance the color story.

STYLE REFERENCE: Think music video stills, contemporary fashion editorials, artistic portraits, or creative advertising. The image should feel current, creative, and visually striking.

BACKGROUND: Could be dark to make colors pop, or colored to complement/contrast with lighting. Background should support the overall color concept.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'vintage_retro':
            arguments['prompt'] = f"""Transform this image into a vintage/retro portrait with classic film aesthetics:

FILM AESTHETIC: Authentic film photography look - could be 1970s warm tones, 1980s bold colors, Polaroid instant film, Kodachrome saturation, or Fuji film greens. The specific era or film stock should inform the entire aesthetic approach.

COLOR GRADING: Period-appropriate color science - lifted blacks, rolled-off highlights, specific color casts depending on era. Faded shadows, vintage color crossovers, film-specific color rendering. Colors should feel nostalgic and era-authentic.

GRAIN & TEXTURE: Appropriate film grain - subtle or prominent depending on the film stock being emulated. Grain should look organic and film-like, not digital noise. Consider halation, light leaks, or other film artifacts if appropriate.

LIGHTING STYLE: Lighting that feels period-appropriate - could be natural light photography style of the era, studio lighting techniques of the time, or flash photography aesthetic. Consider how photographers of the chosen era would have lit their subjects.

STYLING & MOOD: Nostalgic, timeless, romantic, or era-specific mood. The image should transport viewers to another time. Warmth and humanity of film photography. Connection to photographic history.

TECHNICAL APPROACH: Emulate limitations and characteristics of vintage processes - specific dynamic range, color rendering, depth of field characteristics. The "imperfections" of film become aesthetic choices.

POST-PROCESSING: Film emulation that's authentic and consistent. Consider the complete vintage photography workflow from capture to print.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'minimalist':
            arguments['prompt'] = f"""Transform this image into a minimalist portrait with refined simplicity:

COMPOSITION: Maximum impact through minimal elements. Generous negative space - 60-80% of frame can be empty. Subject positioned with intentional use of space. Every element in frame must earn its place. Clean, uncluttered composition.

BACKGROUND: Simple, clean, undistracting - solid color, subtle gradient, or very minimal texture. The background should not compete with the subject but provide breathing room. Consider white, soft gray, or single muted color.

LIGHTING: Simple, clean lighting that creates form without complexity. Single soft source or very simple two-light setup. Avoid complex shadows or dramatic effects unless very intentional. Light should be a quiet element, not a statement.

POSE: Simple, elegant, unforced pose. Natural and relaxed without elaborate positioning. The subject's presence itself becomes the focus. Quiet strength rather than dynamic action.

COLOR PALETTE: Restricted, harmonious colors. Monochromatic or very limited palette. No visual noise or competing color elements. Colors should feel intentional and curated.

MOOD: Calm, serene, contemplative, peaceful. The simplicity should create a meditative quality. Space to breathe and reflect. Quiet sophistication.

STYLING: Simple, minimal wardrobe - solid colors, clean lines. No busy patterns or distracting accessories. Everything supporting the minimal aesthetic.

PHILOSOPHY: Less is more. Every choice should be deliberate. The image should achieve impact through restraint and refinement, not addition or complexity.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'cultural':
            arguments['prompt'] = f"""Transform this image into a cultural portrait celebrating heritage and tradition:

CULTURAL AUTHENTICITY: Respectful, authentic representation of cultural heritage. Traditional attire, accessories, or styling that's meaningful and accurate. Avoid stereotypes or superficial representation. The portrait should honor and celebrate cultural identity.

WARDROBE & STYLING: Traditional clothing, textiles, jewelry, or accessories appropriate to the culture being represented. Attention to detail and authenticity in every element. Styling should be respectful and accurately represent the culture.

LIGHTING: Lighting that complements the cultural aesthetic and enhances traditional elements. Could be natural light for authenticity, or studio lighting that showcases textile details and accessories. Warm, respectful illumination.

BACKGROUND & SETTING: Context-appropriate setting - could be simple to focus on the person, or environmental to provide cultural context. Colors and elements should harmonize with cultural aesthetic.

EXPRESSION & PRESENCE: Dignified, proud representation of cultural identity. The subject should embody the strength and beauty of their heritage. Expression should feel authentic and meaningful.

COLOR & MOOD: Colors should feel authentic to the cultural palette - traditional colors, natural dyes, cultural color symbolism. Mood should be celebratory and respectful.

TECHNICAL: High quality that honors the subject and their cultural representation. Sharp detail on traditional elements. Rich colors that accurately represent textiles and materials.

SENSITIVITY: This portrait should be created with cultural sensitivity, celebrating rather than appropriating, honoring rather than othering.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'conceptual':
            arguments['prompt'] = f"""Transform this image into a conceptual portrait with artistic symbolism and creative vision:

CONCEPT & MEANING: The portrait should convey an idea, emotion, or narrative beyond simple representation. Symbolic elements, surreal touches, or visual metaphors that communicate deeper meaning. The image tells a story or expresses a concept.

CREATIVE ELEMENTS: Incorporation of symbolic props, unusual compositions, surreal elements, or creative techniques. These elements should support and express the conceptual intent. Balance between portrait and artistic expression.

ARTISTIC VISION: Fine art sensibility - the image as creative expression rather than documentation. Consider influences from art history, contemporary art, or conceptual photography. The portrait becomes a vehicle for artistic ideas.

VISUAL STORYTELLING: Every element contributes to the narrative or concept. Composition, lighting, color, and styling all support the conceptual intent. The viewer should be engaged in interpretation and meaning-making.

TECHNICAL EXECUTION: High-quality execution of creative concepts. Technical excellence in service of artistic vision. Complex concepts require flawless execution.

MOOD & ATMOSPHERE: The mood should support the concept - could be surreal, dreamlike, challenging, provocative, peaceful, or transformative. Emotional resonance beyond surface beauty.

COMPOSITION: Creative, possibly unconventional composition that serves the concept. Break rules intentionally when it supports the artistic vision.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'dating':
            vibe = data.get('dating_vibe', 'confident_authentic')
            arguments['prompt'] = f"""Transform this image into an attractive dating profile photo with {vibe.replace('_', ' ')} energy:

DATING PROFILE OPTIMIZATION: Create a photo that makes an immediate positive impression on dating apps like Tinder, Bumble, and Hinge. The image should be scroll-stopping, approachable, and convey genuine personality.

EXPRESSION & ENERGY: Capture authentic, warm expression that invites connection. Genuine smile that reaches the eyes, approachable body language, confident but not arrogant. The expression should say "I'm fun to be around" and "I'm genuinely interested in meeting you." Avoid stiff posed looks - aim for natural, candid-feeling moments.

LIGHTING & COLOR: Warm, flattering lighting that enhances natural features. Vibrant but natural colors that pop on mobile screens. Golden hour warmth or soft natural light preferred. Colors should be eye-catching without being oversaturated. The photo should stand out in a sea of other profiles.

POSES & FRAMING: Natural, relaxed poses that show personality. Slight angle (not straight-on) for dimension. Head and shoulders or upper body framing works best. Show genuine personality through body language - whether that's playful, confident, adventurous, or warm.

BACKGROUND: Clean, uncluttered background that doesn't distract. Can suggest lifestyle (café, outdoors, travel) but subject is clearly the focus. Blurred backgrounds work well to keep attention on you.

AUTHENTICITY: Look like yourself on your best day - enhanced but not transformed beyond recognition. The person you meet should recognize you from your photo. Enhance natural attractiveness while maintaining authentic appearance.

APPEAL FACTORS: Studies show dating photos perform best with: genuine smiles, eye contact with camera, warm lighting, clean backgrounds, and confident body language. This photo should incorporate these proven elements.

TECHNICAL: Sharp focus on face, pleasing bokeh if background visible, professional quality but not overly produced. Should feel like a great candid photo, not a formal portrait.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'influencer':
            aesthetic = data.get('aesthetic', 'glamorous')
            arguments['prompt'] = f"""Transform this image into a social media influencer portrait with {aesthetic} aesthetic:

PLATFORM OPTIMIZATION: Instagram-ready composition and quality. Square or 4:5 format friendly. Eye-catching for scroll-stopping impact. The image should perform well in the social media context - high engagement potential.

AESTHETIC DIRECTION ({aesthetic}):
- If glamorous: luxury feel, perfect lighting, aspirational quality, high-end styling
- If natural: authentic, relatable, effortlessly beautiful, approachable
- If golden_hour: warm, dreamy, sun-kissed, romantic lighting
- If urban_chic: street style, city backdrop, trendy, fashion-forward
- If soft_dreamy: ethereal, soft focus elements, pastel tones, romantic
- If vibrant_bold: saturated colors, high impact, energetic, dynamic

LIGHTING: Flattering, consistent with the chosen aesthetic. Usually soft, beautiful light that makes subject look their best. Golden hour warmth, ring light glamour, or natural window light depending on aesthetic. Always flattering.

POSE & EXPRESSION: Natural yet photogenic - the practiced casualness of influencer photography. Confident, engaging, relatable. Body language that works for the chosen aesthetic. Expression that connects with the audience.

STYLING: Trend-aware, aesthetically consistent wardrobe and accessories. Hair and makeup camera-ready. Overall look that fits the influencer brand and aesthetic.

POST-PROCESSING: Clean, consistent color grading that matches the aesthetic. Skin retouching that's flattering but not obviously filtered. The editing style should feel like a cohesive feed aesthetic.

ENGAGEMENT FACTOR: The image should make viewers stop scrolling, engage, and want to follow. Aspirational yet achievable. Beautiful but relatable.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'luxury':
            arguments['prompt'] = f"""Transform this image into a luxury portrait exuding wealth, power, and sophistication:

LIGHTING: Rich, sophisticated illumination that suggests premium quality. Dramatic but controlled - think luxury brand advertising. Beautiful light that enhances without being obvious. Professional, refined, expensive-looking light quality.

STYLING & FASHION: High-end, premium fashion aesthetic. Designer or designer-quality attire. Impeccable grooming. Attention to every detail of personal presentation. Luxury accessories if present. Everything should suggest wealth and refinement.

SETTING & BACKGROUND: Context suggesting affluence - could be clean dark/light background for timeless luxury, or sophisticated environmental setting. If environmental, every visible element should suggest quality and wealth.

MOOD & EXPRESSION: Confident, powerful, sophisticated, perhaps slightly aloof. The expression of someone accustomed to success. Not arrogant, but assured. Authority and elegance.

COLOR PALETTE: Rich, sophisticated colors - deep blacks, clean whites, gold accents, jewel tones, or refined neutral palette. Colors should feel expensive and intentional.

COMPOSITION: Elegant, refined composition. Strong but not aggressive. Classical proportions with contemporary edge. Every element precisely placed.

POST-PROCESSING: Premium quality - flawless execution, refined retouching, rich tones. The technical quality should match the luxury positioning. Think luxury brand campaign or premium magazine.

ASPIRATIONAL QUALITY: The image should represent the pinnacle of success and sophistication. Viewers should aspire to this level of presentation.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'avatar':
            style = data.get('style', 'semi_realistic')
            arguments['prompt'] = f"""Transform this image into a stylized avatar portrait with {style.replace('_', ' ')} aesthetic:

STYLE DIRECTION ({style}):
- If semi_realistic: Painterly quality while maintaining likeness, slightly idealized features, artistic interpretation of reality
- If 3d_pixar: Pixar/Disney animation style, expressive features, appealing character design, 3D rendered look
- If anime: Japanese animation aesthetic, large expressive eyes, anime hair styling, cel-shaded appearance
- If comic_book: Comic/graphic novel illustration style, bold lines, dynamic rendering, superhero aesthetic potential
- If digital_art: Contemporary digital painting, vibrant colors, artistic brushwork visible, modern illustration
- If fantasy: Fantasy character aesthetic, ethereal or heroic qualities, fantastical elements integrated

LIKENESS PRESERVATION: Despite stylization, the avatar must be recognizably the same person. Key identifying features (face shape, eye configuration, notable features) must be preserved within the chosen art style. The person should look at their avatar and see themselves.

ARTISTIC QUALITY: High-quality digital art execution. The style should be consistent and well-executed, not a cheap filter effect. Professional illustration quality.

CHARACTER APPEAL: The avatar should be appealing and engaging in its chosen style. Character design principles applied - readable silhouette, expressive features, visual appeal.

TECHNICAL EXECUTION: Clean, professional digital art. Appropriate for the chosen style - could be cel-shaded, painterly, 3D rendered, etc. Consistent styling throughout the image.

USE CASE: Suitable for social media profile pictures, gaming avatars, personal branding, or digital identity. Should work at various sizes.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'founder_headshot':
            vibe = data.get('vibe', 'visionary')
            arguments['prompt'] = f"""Transform this image into a startup founder headshot with {vibe} leadership presence:

LEADERSHIP VIBE ({vibe}):
- If visionary: Forward-looking, innovative, seeing possibilities others don't, Steve Jobs energy
- If approachable_ceo: Warm, accessible, team-builder, servant leadership feel
- If tech_innovator: Modern, technical credibility, Silicon Valley aesthetic
- If disruptor: Bold, challenging status quo, confident rule-breaker energy
- If thought_leader: Intellectual, authoritative, expert presence
- If creative_founder: Artistic, innovative, design-forward sensibility

CONTEXT: This image is for pitch decks, investor meetings, company about pages, speaking engagements, and press features. It needs to convey leadership credibility and the specific founder archetype.

LIGHTING: Professional but not corporate-stiff. Modern, confident lighting that suggests innovation while maintaining professionalism. Slightly dramatic acceptable for founder context.

EXPRESSION: Confident, visionary, determined - someone you'd trust with investment. Approachable enough to work with but authoritative enough to lead. The specific expression should match the chosen vibe.

BACKGROUND: Clean, modern - could be simple backdrop, modern office blur, or tech-appropriate environment. Should feel contemporary and founder-appropriate, not traditional corporate.

STYLING: Smart casual or dressed-up startup appropriate. The founder uniform that matches their brand and industry. Contemporary, confident, successful but not stuffy.

TECHNICAL: High quality suitable for large format printing and digital use. Sharp, professional, confidence-inspiring.

NARRATIVE: The image should tell the story of someone building something important, leading a team, and ready to change their industry.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'restoration':
            arguments['prompt'] = f"""Restore and enhance this image with professional quality improvements:

RESTORATION GOALS: Fix any visible damage, imperfections, or quality issues while maintaining the authentic character of the image. Improve without over-processing or making the image look artificial.

QUALITY ENHANCEMENT: Improve resolution and sharpness, reduce noise and artifacts, enhance detail and clarity. Professional-grade image quality improvement.

SKIN & FEATURES: Natural enhancement of skin - even tone, reduce blemishes, subtle improvement while maintaining natural texture and character. Brighten eyes, enhance features naturally.

COLOR CORRECTION: Accurate, pleasing color balance. Fix any color casts or inconsistencies. Rich, natural colors. Proper white balance and exposure optimization.

TECHNICAL FIXES: Address any technical issues - fix lighting problems, improve contrast and dynamic range, sharpen appropriately, reduce any blur or softness.

AUTHENTICITY: Maintain the essential character and authenticity of the original image. Enhancement should be invisible - the image should look like it was simply captured well, not obviously processed.

{face_preserve}

Additional instructions: {prompt}"""

        elif mode == 'style_transfer':
            style = data.get('style', 'artistic')
            arguments['prompt'] = f"""Transform this image with {style.replace('_', ' ')} artistic styling:

STYLE APPLICATION: Apply {style} visual style to the portrait while maintaining clear likeness and recognition of the subject. The style should transform the aesthetic while preserving identity.

ARTISTIC QUALITY: High-quality artistic transformation - not a simple filter but a thoughtful application of artistic style. Professional quality output.

CONSISTENCY: Style should be applied consistently across the entire image. Unified aesthetic approach throughout.

BALANCE: Find the right balance between artistic style transformation and portrait integrity. The subject should remain the clear focus and be immediately recognizable.

{face_preserve}

Additional instructions: {prompt}"""

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
                        
                        # Save to gallery
                        try:
                            gallery_image = Image(
                                filename=filename,
                                prompt=prompt,
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
                            prompt=prompt,
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