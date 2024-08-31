document.addEventListener('DOMContentLoaded', () => {
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
    modelSelect.addEventListener('change', (e) => {
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
    reEnhancePromptButton.addEventListener('click', async () => {
        await enhancePrompt(true);
    });

    // Generate image button handler
    generateImageButton.addEventListener('click', async () => {
        await generateImage();
    });

    async function enhancePrompt(reEnhance = false) {
        showLoading(loadingIndicator);
        enhancedPromptContainer.classList.add('hidden');

        const formData = getFormData();
        formData.enhance_prompt = true;
        formData.enhance_prompt_only = true;

        if (reEnhance) {
            formData.message = enhancedPromptText.value;
        }

        try {
            const response = await fetch('/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData),
            });

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

        const formData = getFormData();
        formData.message = enhancedPromptText.value;

        try {
            const response = await fetch('/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData),
            });

            const data = await response.json();
            if (data.image_url) {
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

    function getFormData() {
        const formData = {
            message: document.getElementById('userInput').value,
            model: modelSelect.value,
            image_size: document.getElementById('imageSize').value,
            art_style: document.getElementById('artStyle').value,
            color_scheme: document.getElementById('colorScheme').value,
            lighting_mood: document.getElementById('lightingMood').value,
            subject_focus: document.getElementById('subjectFocus').value,
            background_style: document.getElementById('backgroundStyle').value,
            effects_filters: document.getElementById('effectsFilters').value,
            num_inference_steps: parseInt(document.getElementById('numInferenceSteps').value),
            guidance_scale: parseFloat(document.getElementById('guidanceScale').value),
        };

        const seedValue = document.getElementById('seed').value;
        if (seedValue) {
            formData.seed = parseInt(seedValue);
        }

        if (modelSelect.value === 'fal-ai/flux-lora') {
            formData.lora_path = document.getElementById('loraPath').value;
            formData.lora_scale = parseFloat(document.getElementById('loraScale').value);
        }

        return formData;
    }

    function showLoading(loadingIndicator) {
        loadingIndicator.classList.remove('hidden');
    }

    function hideLoading(loadingIndicator) {
        loadingIndicator.classList.add('hidden');
    }

    function displayGeneratedImage(data) {
        imageContainer.innerHTML = '';
        const imgContainer = document.createElement('div');
        imgContainer.className = 'bg-white rounded-lg shadow-lg overflow-hidden mb-8';
        
        const imgWrapper = document.createElement('div');
        imgWrapper.className = 'relative';
        
        const imgElement = document.createElement('img');
        imgElement.src = data.image_url;
        imgElement.alt = 'Generated Image';
        imgElement.className = 'w-full h-auto';
        
        imgWrapper.appendChild(imgElement);
        imgContainer.appendChild(imgWrapper);
        
        const infoContainer = document.createElement('div');
        infoContainer.className = 'p-4';
        
        const promptElement = document.createElement('p');
        promptElement.className = 'text-sm text-gray-600 mb-2';
        promptElement.textContent = `Prompt: ${data.prompt}`;
        infoContainer.appendChild(promptElement);

        const dimensionsElement = document.createElement('p');
        dimensionsElement.className = 'text-sm text-gray-600 mb-4';
        dimensionsElement.textContent = `Dimensions: ${data.width}x${data.height}`;
        infoContainer.appendChild(dimensionsElement);
        
        const downloadContainer = document.createElement('div');
        downloadContainer.className = 'flex justify-center space-x-4';
        
        ['webp', 'png', 'jpeg'].forEach(format => {
            const downloadButton = document.createElement('a');
            downloadButton.href = `/download?url=${encodeURIComponent(data.image_url)}&format=${format}`;
            downloadButton.className = 'bg-blue-500 text-white py-2 px-4 rounded hover:bg-blue-600 transition duration-300 text-sm font-medium';
            downloadButton.textContent = format.toUpperCase();
            downloadButton.download = `generated_image.${format}`;
            downloadContainer.appendChild(downloadButton);
        });
        
        infoContainer.appendChild(downloadContainer);
        imgContainer.appendChild(infoContainer);
        imageContainer.appendChild(imgContainer);
        
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

    artStyleSelect.addEventListener('change', showArtStyleDescription);

    // Hide tooltip when clicking outside
    document.addEventListener('click', function(event) {
        if (event.target !== artStyleSelect && event.target !== artStyleTooltip) {
            artStyleTooltip.classList.add('hidden');
        }
    });
});