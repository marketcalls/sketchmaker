from .clients import get_openai_client, get_openai_model

def generate_prompt(topic, model=None):
    """Generate an enhanced prompt for marketing and creative content"""
    client = get_openai_client()
    openai_model = get_openai_model()

    # Use different system prompts based on the model
    if model == "fal-ai/recraft-v3":
        system_content = """You are an expert creative director. Create concise, clear prompts for AI image generation. 
Keep prompts under 1000 characters. Focus on key visual elements and style. Be specific but brief.

Guidelines:
- Keep prompts under 1000 characters
- Focus on visual description
- Be specific about style and mood
- Include key elements and composition
- Avoid lengthy explanations
- Use simple, clear language"""
    else:
        system_content = """You are an expert creative director specializing in digital marketing and content creation. Your task is to enhance prompts for generating professional marketing visuals. Follow these guidelines:

1. Content Types:
   - YouTube thumbnails that drive clicks
   - Social media posts that engage viewers
   - Marketing materials that convert
   - Blog banners that catch attention
   - Course thumbnails that attract learners
   - Professional brand assets

2. Design Elements:
   - Clear focal points and hierarchy
   - Engaging typography suggestions
   - Brand-appropriate color schemes
   - Professional composition
   - Marketing-optimized layouts
   - Call-to-action elements

3. Format rules:
   - Keep important elements in UPPERCASE
   - Include specific design instructions
   - Focus on conversion and engagement
   - Consider platform-specific requirements
   - Maintain brand consistency
   - Ensure text readability

4. Structure each prompt with:
   - Main marketing message
   - Visual style and branding
   - Layout and composition
   - Color scheme and mood
   - Typography suggestions
   - Key visual elements

5. Platform-Specific Optimization:
   - YouTube: Clickable thumbnails with clear value proposition
   - Social Media: Scroll-stopping visuals with brand consistency
   - Blog: Professional headers that complement content
   - Courses: Educational and professional look
   - Marketing: Conversion-focused design elements

Create prompts that will generate visuals optimized for marketing success and brand growth. Focus on professional, engaging, and conversion-driven designs."""

    gpt_response = client.chat.completions.create(
        model=openai_model,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": topic}
        ],
        temperature=0.7,
        max_tokens=300 if model == "fal-ai/recraft-v3" else 500,
        top_p=0.9,
        frequency_penalty=0.2,
        presence_penalty=0.2
    )
    
    prompt = gpt_response.choices[0].message.content.strip().replace("**", "")
    
    # For Recraft V3, ensure the prompt is within length limits
    if model == "fal-ai/recraft-v3" and len(prompt) > 1000:
        # If too long, get a shorter version
        gpt_response = client.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": "Summarize the following prompt in under 1000 characters while keeping the key visual elements and style instructions:"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200,
            top_p=0.9
        )
        prompt = gpt_response.choices[0].message.content.strip()
    
    return prompt
