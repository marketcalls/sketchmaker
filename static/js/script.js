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

    // Toast notification system
    function showToast(message, type = 'error') {
        const toast = document.createElement('div');
        toast.className = `alert alert-${type} fixed bottom-4 right-4 w-96 z-50 animate-fade-in-up shadow-lg`;
        
        const icon = document.createElement('svg');
        icon.className = 'h-6 w-6 shrink-0';
        icon.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        icon.setAttribute('fill', 'none');
        icon.setAttribute('viewBox', '0 0 24 24');
        icon.setAttribute('stroke', 'currentColor');
        
        const path = document.createElement('path');
        path.setAttribute('stroke-linecap', 'round');
        path.setAttribute('stroke-linejoin', 'round');
        path.setAttribute('stroke-width', '2');
        
        if (type === 'success') {
            path.setAttribute('d', 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z');
        } else {
            path.setAttribute('d', 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z');
        }
        
        icon.appendChild(path);
        toast.appendChild(icon);
        toast.appendChild(document.createTextNode(message));
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.classList.add('animate-fade-out-down');
            setTimeout(() => toast.remove(), 500);
        }, 5000);
    }

    // Convert hex color to RGB
    function hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : null;
    }

    // Get colors from color pickers
    function getSelectedColors() {
        const colorPickers = document.querySelectorAll('#colorPickers input[type="color"]');
        const colors = [];
        colorPickers.forEach(picker => {
            const rgb = hexToRgb(picker.value);
            if (rgb) {
                colors.push(rgb);
            }
        });
        return colors;
    }

    // API error handler
    function handleAPIError(error) {
        const errorMessage = error.message || error;
        if (errorMessage.toLowerCase().includes('insufficient credits')) {
            showToast('You have no credits remaining. Please contact an administrator to upgrade your plan.', 'error');
            // Update credits display if it exists
            updateCreditsDisplay(0);
        } else if (errorMessage.toLowerCase().includes('api key')) {
            showToast('Invalid or missing API key. Please contact administrator.', 'error');
        } else if (errorMessage.toLowerCase().includes('authentication failed')) {
            showToast('API authentication failed. Please contact administrator.', 'error');
        } else {
            showToast(errorMessage, 'error');
        }
    }
    
    // Update credits display
    function updateCreditsDisplay(credits) {
        const creditsElement = document.querySelector('.text-primary');
        if (creditsElement && creditsElement.textContent.match(/^\d+$/)) {
            creditsElement.textContent = credits;
        }
    }

    const form = document.getElementById('imageGenForm');
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

    // Toggle model-specific controls
    modelSelect?.addEventListener('change', (e) => {
        console.log('Model changed to:', e.target.value);
        const recraftControls = document.getElementById('recraftStyleControl');
        const recraftColorsControl = document.getElementById('recraftColorsControl');
        const imageSizeControl = document.getElementById('imageSizeControl');
        
        // Ideogram V2 Controls
        const ideogramAspectRatioControl = document.getElementById('ideogramAspectRatioControl');
        const ideogramExpandPromptControl = document.getElementById('ideogramExpandPromptControl');
        const ideogramStyleControl = document.getElementById('ideogramStyleControl');
        const ideogramNegativePromptControl = document.getElementById('ideogramNegativePromptControl');
        
        // Debug logging for Ideogram controls
        console.log('Ideogram controls present:', {
            aspectRatioControl: !!ideogramAspectRatioControl,
            expandPromptControl: !!ideogramExpandPromptControl,
            styleControl: !!ideogramStyleControl,
            negativePromptControl: !!ideogramNegativePromptControl
        });
        
        // Hide all model-specific controls first
        if (recraftControls) recraftControls.classList.add('hidden');
        if (recraftColorsControl) recraftColorsControl.classList.add('hidden');
        if (loraInputs) loraInputs.classList.add('hidden');
        if (ideogramAspectRatioControl) ideogramAspectRatioControl.classList.add('hidden');
        if (ideogramExpandPromptControl) ideogramExpandPromptControl.classList.add('hidden');
        if (ideogramStyleControl) ideogramStyleControl.classList.add('hidden');
        if (ideogramNegativePromptControl) ideogramNegativePromptControl.classList.add('hidden');
        
        // Show controls based on model
        if (e.target.value === 'fal-ai/recraft-v3') {
            if (recraftControls) recraftControls.classList.remove('hidden');
            if (recraftColorsControl) recraftColorsControl.classList.remove('hidden');
            if (imageSizeControl) imageSizeControl.classList.remove('hidden');
        } else if (e.target.value === 'fal-ai/flux-lora') {
            if (loraInputs) loraInputs.classList.remove('hidden');
            if (imageSizeControl) imageSizeControl.classList.remove('hidden');
        } else if (e.target.value === 'fal-ai/ideogram/v2' || e.target.value === 'fal-ai/ideogram/v2a') {
            console.log('Showing Ideogram controls for model:', e.target.value);
            if (ideogramAspectRatioControl) ideogramAspectRatioControl.classList.remove('hidden');
            if (ideogramExpandPromptControl) ideogramExpandPromptControl.classList.remove('hidden');
            if (ideogramStyleControl) ideogramStyleControl.classList.remove('hidden');
            if (ideogramNegativePromptControl) ideogramNegativePromptControl.classList.remove('hidden');
            if (imageSizeControl) imageSizeControl.classList.add('hidden'); // Hide image size as Ideogram uses aspect ratio
        } else if (e.target.value === 'fal-ai/flux-pro/v1.1-ultra') {
            if (imageSizeControl) imageSizeControl.classList.add('hidden'); // Ultra uses aspect ratio instead of dimensions
        } else {
            if (imageSizeControl) imageSizeControl.classList.remove('hidden');
        }
    });

    // Enhance prompt button handler
    enhancePromptButton?.addEventListener('click', async () => {
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
            showToast('Please enter a prompt to enhance', 'error');
            return;
        }

        // Show loading state
        const button = reEnhance ? reEnhancePromptButton : enhancePromptButton;
        const originalText = button.textContent;
        button.disabled = true;
        button.innerHTML = '<span class="loading loading-spinner"></span> Enhancing...';
        enhancedPromptContainer.classList.add('hidden');

        try {
            const formData = {
                topic: reEnhance ? enhancedPromptText.value : userInput.value,
                model: modelSelect.value,
                art_style: document.getElementById('artStyle').value,
                color_scheme: document.getElementById('colorScheme').value,
                lighting_mood: document.getElementById('lightingMood').value,
                subject_focus: document.getElementById('subjectFocus').value,
                background_style: document.getElementById('backgroundStyle').value,
                effects_filters: document.getElementById('effectsFilters').value
            };

            const response = await fetch('/generate/prompt', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.csrf_token
                },
                body: JSON.stringify(formData),
            });

            let data;
            const contentType = response.headers.get('content-type');
            
            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else {
                // If response is not JSON, it's likely an HTML error page
                const text = await response.text();
                console.error('Non-JSON response:', text);
                throw new Error('Server returned an error page instead of JSON response');
            }

            if (!response.ok) {
                throw new Error(data.error || data.details || 'Failed to enhance prompt');
            }

            if (data.prompt) {
                enhancedPromptText.value = data.prompt;
                enhancedPromptContainer.classList.remove('hidden');
                window.scrollTo({
                    top: enhancedPromptContainer.offsetTop,
                    behavior: 'smooth'
                });
                showToast('Prompt enhanced successfully!', 'success');
            } else {
                throw new Error('Invalid response from server');
            }
        } catch (error) {
            console.error('Error enhancing prompt:', error);
            showToast(error.message, 'error');
        } finally {
            // Reset button state
            button.disabled = false;
            button.textContent = originalText;
        }
    }

    async function generateImage() {
        if (!enhancedPromptText.value.trim()) {
            showToast('Please enhance the prompt before generating an image.', 'error');
            return;
        }

        const loadingIndicator = document.getElementById('loadingIndicator');
        if (loadingIndicator) {
            loadingIndicator.classList.remove('hidden');
        }
        if (imageResultContainer) {
            imageResultContainer.classList.add('hidden');
        }

        const imageSizeKey = document.getElementById('imageSize').value;
        const dimensions = IMAGE_SIZES[imageSizeKey] || IMAGE_SIZES.square;
        const selectedModel = modelSelect.value;

        console.log('Generating image with model:', selectedModel);

        try {
            const formData = {
                prompt: enhancedPromptText.value,
                model: selectedModel,
                art_style: document.getElementById('artStyle').value,
                num_images: 1,
                enable_safety_checker: true
            };

            // Add model-specific parameters
            if (selectedModel === 'fal-ai/recraft-v3') {
                formData.style = document.getElementById('recraftStyle').value;
                formData.colors = getSelectedColors();
                formData.style_id = null;
                formData.image_size = dimensions;
            } else if (selectedModel === 'fal-ai/flux-pro/v1.1-ultra') {
                formData.aspect_ratio = document.getElementById('aspectRatio').value;
            } else if (selectedModel === 'fal-ai/bytedance/seedream/v4/text-to-image') {
                // Add Seedream V4 specific parameters
                const presetElement = document.getElementById('seedreamImageSizePreset');
                const maxImagesElement = document.getElementById('seedreamMaxImages');
                const widthElement = document.getElementById('seedreamWidth');
                const heightElement = document.getElementById('seedreamHeight');

                formData.seedream_image_size_preset = presetElement ? presetElement.value : 'default';
                formData.seedream_max_images = maxImagesElement ? parseInt(maxImagesElement.value) : 1;

                if (formData.seedream_image_size_preset === 'custom') {
                    formData.seedream_width = widthElement ? parseInt(widthElement.value) : 1024;
                    formData.seedream_height = heightElement ? parseInt(heightElement.value) : 1024;
                }

                console.log('Seedream V4 parameters:', {
                    preset: formData.seedream_image_size_preset,
                    max_images: formData.seedream_max_images,
                    width: formData.seedream_width,
                    height: formData.seedream_height
                });
            } else if (selectedModel === 'fal-ai/ideogram/v2' || selectedModel === 'fal-ai/ideogram/v2a') {
                // Add Ideogram V2/V2a specific parameters
                const aspectRatioElement = document.getElementById('ideogramAspectRatio');
                const expandPromptElement = document.getElementById('ideogramExpandPrompt');
                const styleElement = document.getElementById('ideogramStyle');
                const negativePromptElement = document.getElementById('ideogramNegativePrompt');
                
                // Set default values if elements don't exist
                formData.aspect_ratio = aspectRatioElement ? aspectRatioElement.value : '1:1';
                formData.expand_prompt = expandPromptElement ? expandPromptElement.checked : true;
                formData.style = styleElement ? styleElement.value : 'auto';
                
                if (negativePromptElement && negativePromptElement.value.trim()) {
                    formData.negative_prompt = negativePromptElement.value;
                } else {
                    formData.negative_prompt = '';
                }
                
                console.log(`Ideogram ${selectedModel} parameters:`, {
                    aspect_ratio: formData.aspect_ratio,
                    expand_prompt: formData.expand_prompt,
                    style: formData.style,
                    negative_prompt: formData.negative_prompt
                });
            } else if (selectedModel === 'fal-ai/imagen4/preview') {
                // Add Imagen4 specific parameters
                const aspectRatioElement = document.getElementById('imagen4AspectRatio');
                const negativePromptElement = document.getElementById('imagen4NegativePrompt');
                
                formData.aspect_ratio = aspectRatioElement ? aspectRatioElement.value : '1:1';
                
                if (negativePromptElement && negativePromptElement.value.trim()) {
                    formData.negative_prompt = negativePromptElement.value;
                }
                
                console.log('Imagen4 parameters:', {
                    aspect_ratio: formData.aspect_ratio,
                    negative_prompt: formData.negative_prompt
                });
            } else if (selectedModel === 'fal-ai/ideogram/v3') {
                // Add Ideogram V3 specific parameters
                const imageSizeElement = document.getElementById('ideogramV3ImageSize');
                const expandPromptElement = document.getElementById('ideogramV3ExpandPrompt');
                const negativePromptElement = document.getElementById('ideogramV3NegativePrompt');
                const renderingSpeedElement = document.getElementById('ideogramV3RenderingSpeed');
                
                formData.image_size = imageSizeElement ? imageSizeElement.value : 'square_hd';
                formData.expand_prompt = expandPromptElement ? expandPromptElement.checked : true;
                formData.rendering_speed = renderingSpeedElement ? renderingSpeedElement.value : 'BALANCED';
                
                if (negativePromptElement && negativePromptElement.value.trim()) {
                    formData.negative_prompt = negativePromptElement.value;
                }
                
                console.log('Ideogram V3 parameters:', {
                    image_size: formData.image_size,
                    expand_prompt: formData.expand_prompt,
                    rendering_speed: formData.rendering_speed,
                    negative_prompt: formData.negative_prompt
                });
            } else {
                formData.image_size = dimensions;
            }

            if (selectedModel === 'fal-ai/flux-lora' || selectedModel === 'fal-ai/flux-realism') {
                formData.num_inference_steps = parseInt(document.getElementById('numInferenceSteps').value);
                formData.guidance_scale = parseFloat(document.getElementById('guidanceScale').value);
            }

            if (selectedModel === 'fal-ai/flux-lora' && document.getElementById('loraPath').value) {
                formData.loras = [{
                    path: document.getElementById('loraPath').value,
                    scale: parseFloat(document.getElementById('loraScale').value)
                }];
            }

            const seed = document.getElementById('seed').value;
            if (seed) {
                formData.seed = parseInt(seed);
            }

            console.log('Sending request with data:', formData);

            const response = await fetch('/generate/image', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.csrf_token
                },
                body: JSON.stringify(formData),
            });

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || `HTTP error! status: ${response.status}`);
            }

            if (data.images && data.images.length > 0) {
                displayGeneratedImage(data);
                showToast('Image generated successfully!', 'success');
                // Update credits display if provided
                if (data.credits_remaining !== undefined) {
                    updateCreditsDisplay(data.credits_remaining);
                }
            } else {
                throw new Error(data.error || 'Invalid response from server');
            }
        } catch (error) {
            console.error('Error generating image:', error);
            handleAPIError(error);
        } finally {
            if (loadingIndicator) {
                loadingIndicator.classList.add('hidden');
            }
        }
    }

    function displayGeneratedImage(data) {
        if (!imageContainer) return;
        
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
            downloadContainer.className = 'card-actions justify-end mt-4 space-x-4';
            
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
        
        if (imageResultContainer) {
            imageResultContainer.classList.remove('hidden');
            window.scrollTo({
                top: imageResultContainer.offsetTop,
                behavior: 'smooth'
            });
        }
    }

    // Initialize controls based on default model
    window.addEventListener('DOMContentLoaded', function() {
        const model = document.getElementById('model');
        if (model) {
            const event = new Event('change');
            model.dispatchEvent(event);
        }
    });
});
