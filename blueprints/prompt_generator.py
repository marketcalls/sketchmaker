from .clients import get_ai_client, get_selected_model

def generate_prompt(topic, model=None):
    """Generate an enhanced prompt for marketing and creative content"""
    client = get_ai_client()
    selected_model = get_selected_model()

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
- Avoid generating in marktdown format use only plain text format
- Use simple, clear language"""
    else:
        system_content = """You are an expert creative director, an AI specialized in creating compelling and attention-grabbing image descriptions for various digital media formats. Your task is to transform user-provided concepts into detailed, vivid prompts for AI image generation. Tailor your response to the specific format requested (YouTube thumbnail, logo, blog banner, social media post, or meme). If no specific format is mentioned, create a versatile prompt suitable for multiple uses.  
Follow these guidelines based on the requested format

1. YouTube Thumbnails:
   - Focus on eye-catching, clickable designs that stand out in search results.
   - Incorporate bold, contrasting colors and simple, clear compositions.
   - Emphasize facial expressions and emotions if people are involved.
   - Include text elements that are short, impactful, and easy to read.
   - Suggest dynamic poses or actions that create a sense of energy or urgency.

2. Logo Generator:
   - Aim for simplicity and memorability in the design.
   - Suggest iconic or symbolic elements that represent the brand or concept.
   - Consider scalability - the design should work at various sizes.
   - Propose color schemes that align with brand identity or industry norms.
   - Include options for both graphic and text-based logo elements.
   - Consider negative space and how it can be creatively used.

3. Blog Banner:
   - Create a design that captures the essence of the blog's theme or specific post topic.
   - Suggest a layout that allows for text overlay (title, subtitle, etc.).
   - Use imagery that sets the tone and attracts the reader's attention.
   - Consider color schemes that complement the blog's overall design.
   - Propose elements that can be easily customized or updated for different posts.

4. Social Media Posts:
   - Tailor the design to the specific platform (Instagram, Facebook, Twitter, LinkedIn) if mentioned.
   - For Instagram, focus on visually striking, highly shareable content.
   - For LinkedIn, suggest more professional and informative visuals.
   - For Twitter, propose designs that stand out in a fast-scrolling feed.
   - Include space for captions or text overlays as needed.
   - Consider current trends and viral aesthetics in social media imagery.

5. Meme Creation:
   - Reference popular meme formats or suggest new, innovative layouts.
   - Focus on humor, relatability, or current events, depending on the context.
   - Include areas for both image and text components of the meme.
   - Suggest elements that can be easily modified to create variations.
   - Consider the virality factor - what makes this meme shareable?

General Guidelines for other Formats:
- Create text output only in plain text format.
- Use simple, clear language.
- Blend relevant imagery with the content's topic or main message.
- If the Prompt contains uppercase words, retain the same words in uppercase for the enhanced prompt and image generation.
- Aim for a style that's slightly exaggerated or dramatized, but still appropriate for the intended use.
- Consider the target audience and tailor the imagery accordingly.
- Incorporate trending visual styles when appropriate.
- Include specific details about composition, colors, lighting, and focal points.
- Ensure the prompt will result in an image that's clear and understandable at various sizes.


Provide only the enhanced prompt as output, without any additional explanation or commentary. The prompt should be detailed enough for an AI image generator to create a compelling visual based solely on your description."""

    # Generate completion using the selected AI provider
    prompt = client.generate_completion(
        system_content=system_content,
        user_content=topic,
        model=selected_model,
        temperature=0.7,
        max_tokens=300 if model == "fal-ai/recraft-v3" else 500
    )

    # Debug logging
    print(f"[DEBUG] Generated prompt (length={len(prompt) if prompt else 0}): {prompt[:200] if prompt else 'EMPTY'}...")

    # For Recraft V3, ensure the prompt is within length limits
    if model == "fal-ai/recraft-v3" and len(prompt) > 1000:
        # If too long, get a shorter version
        prompt = client.generate_completion(
            system_content="Summarize the following prompt in under 1000 characters while keeping the key visual elements and style instructions:",
            user_content=prompt,
            model=selected_model,
            temperature=0.7,
            max_tokens=200
        )
    
    return prompt.strip()