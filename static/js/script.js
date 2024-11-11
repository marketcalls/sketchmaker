document.addEventListener('DOMContentLoaded', () => {
    const IMAGE_SIZES = {
        'youtube_thumbnail': { width: 1280, height: 704 },
        'landscape_4_3': { width: 1280, height: 960 },
        'landscape_16_9': { width: 1280, height: 720 },
        'portrait_4_3': { width: 960, height: 1280 },
        'portrait_16_9': { width: 720, height: 1280 },
        'square': { width: 1024, height: 1024 },
        'square_hd': { width: 1280, height: 1280 },
        'instagram_post_square': { width: 1080, height: 1080 },
        'instagram_post_portrait': { width: 1080, height: 1350 },
        'instagram_story': { width: 1080, height: 1920 },
        'logo': { width: 512, height: 512 },
        'blog_banner': { width: 1280, height: 640 },
        'linkedin_post': { width: 1200, height: 627 },
        'facebook_post_landscape': { width: 1200, height: 630 },
        'twitter_header': { width: 1500, height: 500 }
    };

    // Theme handling
    const themeController = document.querySelector('.theme-controller');
    if (themeController) {
        // Set initial state
        themeController.checked = localStorage.getItem('theme') === 'dark';
        
        // Handle theme changes
        themeController.addEventListener('change', function(e) {
            const theme = e.target.checked ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
        });
    }

    const form = document.getElementById('imageGenForm');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const imageResultContainer = document.getElementById('imageResultContainer');
    const imageContainer = document.getElementById('imageContainer');
    const modelSelect = document.getElementById('model');
    const loraInputs = document.getElementById('loraInputs');
    const enhancePromptButton = document.getElementById('enhancePrompt');
    const reEnhancePromptButton = document.getElementById('reEnhancePrompt');
    const generateImageButton = document.getElementById('generateImage');
    const enhancedPromptContainer = document.getElementById('enhancedPromptContainer');
    const enhancedPromptText = document.getElementById('enhancedPromptText');

    // Animation for page load
    gsap.from('header', { duration: 1, y: -50, opacity: 0, ease: 'power3.out' });
    gsap.from('main', { duration: 1, y: 50, opacity: 0, ease: 'power3.out', delay: 0.3 });

    // Toggle LoRA inputs visibility
    modelSelect?.addEventListener('change', (e) => {
        if (e.target.value === 'fal-ai/flux-lora') {
            loraInputs.classList.remove('hidden');
        } else {
            loraInputs.classList.add('hidden');
        }
    });

    // Enhance prompt button handler
    enhancePromptButton.addEventListener('click', async () => {
        await enhancePrompt();
    });

    // Re-enhance prompt button handler
    reEnhancePromptButton?.addEventListener('click', async () => {
        await enhancePrompt(true);
    });

    // Generate image button handler
    generateImageButton?.addEventListener('click', async () => {
        await generateImage();
    });

    async function enhancePrompt(reEnhance = false) {
        const userInput = document.getElementById('userInput');
        if (!userInput.value.trim()) {
            alert('Please enter a prompt to enhance');
            return;
        }

        showLoading(loadingIndicator);
        enhancedPromptContainer.classList.add('hidden');

        try {
            // Get all form parameters
            const formData = {
                topic: reEnhance ? enhancedPromptText.value : userInput.value,
                image_size: document.getElementById('imageSize').value,
                art_style: document.getElementById('artStyle').value,
                color_scheme: document.getElementById('colorScheme').value,
                lighting_mood: document.getElementById('lightingMood').value,
                subject_focus: document.getElementById('subjectFocus').value,
                background_style: document.getElementById('backgroundStyle').value,
                effects_filters: document.getElementById('effectsFilters').value,
                model: document.getElementById('model').value,
                num_inference_steps: parseInt(document.getElementById('numInferenceSteps').value),
                guidance_scale: parseFloat(document.getElementById('guidanceScale').value)
            };

            // Add seed if provided
            const seed = document.getElementById('seed').value;
            if (seed) {
                formData.seed = parseInt(seed);
            }

            // Add LoRA parameters if applicable
            if (modelSelect.value === 'fal-ai/flux-lora') {
                formData.lora_path = document.getElementById('loraPath').value;
                formData.lora_scale = parseFloat(document.getElementById('loraScale').value);
            }

            const response = await fetch('/generate/prompt', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.prompt) {
                enhancedPromptText.value = data.prompt;
                enhancedPromptContainer.classList.remove('hidden');
                window.scrollTo({
                    top: enhancedPromptContainer.offsetTop,
                    behavior: 'smooth'
                });
            } else {
                throw new Error(data.error || 'Invalid response from server');
            }
        } catch (error) {
            console.error('Error enhancing prompt:', error);
            alert('An error occurred while enhancing the prompt: ' + error.message);
        } finally {
            hideLoading(loadingIndicator);
        }
    }

    async function generateImage() {
        if (!enhancedPromptText.value.trim()) {
            alert('Please enhance the prompt before generating an image.');
            return;
        }

        showLoading(loadingIndicator);
        imageResultContainer.classList.add('hidden');

        const imageSizeKey = document.getElementById('imageSize').value;
        const dimensions = IMAGE_SIZES[imageSizeKey] || IMAGE_SIZES.square;

        try {
            const response = await fetch('/generate/image', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    prompt: enhancedPromptText.value,
                    art_style: document.getElementById('artStyle').value,
                    image_size: dimensions
                }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.images && data.images.length > 0) {
                displayGeneratedImage(data);
            } else {
                throw new Error(data.error || 'Invalid response from server');
            }
        } catch (error) {
            console.error('Error generating image:', error);
            alert('An error occurred while generating the image: ' + error.message);
        } finally {
            hideLoading(loadingIndicator);
        }
    }

    function showLoading(loadingIndicator) {
        loadingIndicator.classList.remove('hidden');
    }

    function hideLoading(loadingIndicator) {
        loadingIndicator.classList.add('hidden');
    }

    function displayGeneratedImage(data) {
        imageContainer.innerHTML = '';
        
        data.images.forEach(image => {
            const imgContainer = document.createElement('div');
            imgContainer.className = 'card bg-base-300/50 backdrop-blur-lg border border-base-content/10 mb-8';
            
            const imgWrapper = document.createElement('figure');
            imgWrapper.className = 'px-4 pt-4';
            
            const imgElement = document.createElement('img');
            imgElement.src = image.image_url;
            imgElement.alt = 'Generated Image';
            imgElement.className = 'rounded-xl w-full h-auto';
            
            imgWrapper.appendChild(imgElement);
            imgContainer.appendChild(imgWrapper);
            
            const cardBody = document.createElement('div');
            cardBody.className = 'card-body';
            
            const promptElement = document.createElement('p');
            promptElement.className = 'text-sm text-base-content/70';
            promptElement.textContent = data.prompt;
            cardBody.appendChild(promptElement);

            if (data.art_style) {
                const styleElement = document.createElement('div');
                styleElement.className = 'badge badge-secondary';
                styleElement.textContent = data.art_style;
                cardBody.appendChild(styleElement);
            }
            
            const downloadContainer = document.createElement('div');
            downloadContainer.className = 'card-actions justify-end mt-4';
            
            ['webp', 'png', 'jpeg'].forEach(format => {
                const downloadButton = document.createElement('a');
                downloadButton.href = image[`${format}_url`];
                downloadButton.className = 'btn btn-primary btn-sm';
                downloadButton.textContent = format.toUpperCase();
                downloadButton.download = `generated_image.${format}`;
                downloadContainer.appendChild(downloadButton);
            });
            
            cardBody.appendChild(downloadContainer);
            imgContainer.appendChild(cardBody);
            imageContainer.appendChild(imgContainer);
        });
        
        imageResultContainer.classList.remove('hidden');
        window.scrollTo({
            top: imageResultContainer.offsetTop,
            behavior: 'smooth'
        });
    }

    // Art style tooltip functionality
    const artStyleSelect = document.getElementById('artStyle');
    const artStyleTooltip = document.getElementById('artStyleTooltip');

    function showArtStyleDescription() {
        const artStyle = artStyleSelect.value;
        const descriptions = {
            'Impressionism': 'Captures light and color, focusing on moments of time.',
            'Cubism': 'Depicts objects from multiple angles, abstracted into geometric forms.',
            'Surrealism': 'Merges dreamlike elements with reality, emphasizing the unconscious mind.',
            'Abstract Expressionism': 'Focuses on spontaneous, abstract forms to express emotions.',
            'Fauvism': 'Known for bold, vibrant colors and simple, exaggerated forms.',
            'Art Nouveau': 'Features flowing lines and organic shapes inspired by nature.',
            'Baroque': 'Ornate and dramatic, emphasizing movement, contrast, and detail.',
            'Renaissance': 'Revival of classical themes, focusing on realism and proportion.',
            'Gothic': 'Characterized by dark, intricate designs and dramatic elements.',
            'Pop Art': 'Incorporates imagery from popular culture, often in a bold, graphic style.',
            'Minimalism': 'Reduces art to its essential forms, focusing on simplicity.',
            'Post-Impressionism': 'Builds on Impressionism, with more emphasis on structure and form.',
            'Romanticism': 'Emphasizes emotion, nature, and individualism, often with dramatic scenes.',
            'Realism': 'Depicts subjects truthfully, without idealization or exaggeration.',
            'Symbolism': 'Uses symbolic imagery to convey deeper meanings and emotions.',
            'Expressionism': 'Focuses on intense emotions through distorted forms and bold colors.',
            'Neo-Classical': 'Inspired by classical antiquity, emphasizing harmony and order.',
            'Constructivism': 'Geometric abstraction using industrial materials, focusing on function.',
            'Futurism': 'Celebrates speed, technology, and dynamic movement.',
            'Dadaism': 'An anti-art movement emphasizing absurdity and randomness.',
            'Art Deco': 'Combines geometric patterns with bold colors and luxurious materials.',
            'Op Art': 'Creates visual effects and illusions through patterns and colors.',
            'Photorealism': 'Paintings that are extremely detailed, resembling photographs.',
            'Bauhaus': 'Integrates art, craft, and technology, focusing on simplicity and function.',
            'Illustrative': 'Detailed and narrative-driven, often used in books, comics, and advertising.'
        };
        
        if (descriptions[artStyle]) {
            artStyleTooltip.textContent = descriptions[artStyle];
            artStyleTooltip.classList.remove('hidden');
        } else {
            artStyleTooltip.classList.add('hidden');
        }
    }

    artStyleSelect?.addEventListener('change', showArtStyleDescription);

    // Hide tooltip when clicking outside
    document.addEventListener('click', function(event) {
        if (artStyleTooltip && event.target !== artStyleSelect && event.target !== artStyleTooltip) {
            artStyleTooltip.classList.add('hidden');
        }
    });
});
