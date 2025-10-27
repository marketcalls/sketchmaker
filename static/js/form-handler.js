export function initializeForm() {
    const form = document.getElementById('imageGenForm');
    const modelSelect = document.getElementById('model');
    const imageSizeControl = document.getElementById('imageSizeControl');
    const aspectRatioControl = document.getElementById('aspectRatioControl');
    const numInferenceStepsControls = document.getElementById('numInferenceSteps').closest('.form-control');
    const guidanceScaleControls = document.getElementById('guidanceScale').closest('.form-control');
    const loraInputs = document.getElementById('loraInputs');

    // Function to show error message
    function showError(message, details) {
        const errorAlert = document.createElement('div');
        errorAlert.className = 'alert alert-error mb-4';
        
        // Create error icon
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
        path.setAttribute('d', 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z');
        
        icon.appendChild(path);
        errorAlert.appendChild(icon);

        // Create error message
        const messageDiv = document.createElement('div');
        messageDiv.className = 'flex flex-col';
        
        const title = document.createElement('span');
        title.className = 'font-bold';
        title.textContent = message;
        messageDiv.appendChild(title);

        if (details) {
            const detailsSpan = document.createElement('span');
            detailsSpan.className = 'text-sm';
            detailsSpan.textContent = details;
            messageDiv.appendChild(detailsSpan);
        }

        errorAlert.appendChild(messageDiv);

        // Add close button
        const closeButton = document.createElement('button');
        closeButton.className = 'btn btn-circle btn-ghost btn-sm';
        closeButton.innerHTML = '✕';
        closeButton.onclick = () => errorAlert.remove();
        errorAlert.appendChild(closeButton);

        // Insert error alert at the top of the form
        form.insertBefore(errorAlert, form.firstChild);

        // Auto-remove after 10 seconds
        setTimeout(() => errorAlert.remove(), 10000);
    }

    // Function to update visible controls based on selected model
    function updateFormControls(modelValue) {
        
        // Reset all controls first
        imageSizeControl.classList.remove('hidden');
        aspectRatioControl.classList.add('hidden');
        numInferenceStepsControls.classList.remove('hidden');
        guidanceScaleControls.classList.remove('hidden');
        loraInputs.classList.add('hidden');

        switch(modelValue) {
            case 'fal-ai/flux-pro/v1.1':
            case 'fal-ai/flux/dev':
                // Show only image size controls
                numInferenceStepsControls.classList.add('hidden');
                guidanceScaleControls.classList.add('hidden');
                break;
            
            case 'fal-ai/flux-pro/v1.1-ultra':
                // Show aspect ratio instead of image size
                imageSizeControl.classList.add('hidden');
                aspectRatioControl.classList.remove('hidden');
                numInferenceStepsControls.classList.add('hidden');
                guidanceScaleControls.classList.add('hidden');
                break;
            
            case 'fal-ai/flux-lora':
                // Show all controls including LoRA inputs
                loraInputs.classList.remove('hidden');
                break;
            
            case 'fal-ai/flux-realism':
                // Show all controls except LoRA
                break;
        }
    }

    // Update controls when model changes
    modelSelect.addEventListener('change', (e) => {
        updateFormControls(e.target.value);
    });

    // Initialize controls based on default model
    updateFormControls(modelSelect.value);

    // Handle image generation
    document.getElementById('generateImage').addEventListener('click', async () => {
        const selectedModel = modelSelect.value;

        // Get the prompt from either enhanced or original input
        const prompt = document.getElementById('enhancedPromptText').value || document.getElementById('userInput').value;
        
        if (!prompt.trim()) {
            showError('No prompt provided', 'Please enter a prompt or enhance the existing one.');
            return;
        }

        // Show loading state
        const generateButton = document.getElementById('generateImage');
        const originalText = generateButton.textContent;
        generateButton.disabled = true;
        generateButton.innerHTML = '<span class="loading loading-spinner"></span> Generating...';
        
        // Prepare the base form data
        const formData = {
            prompt: prompt,
            model: selectedModel,
            num_images: 1,
            enable_safety_checker: true,
            seed: document.getElementById('seed').value || Math.floor(Math.random() * 1000000),
            artStyle: document.getElementById('artStyle').value
        };

        // Add model-specific parameters
        if (selectedModel === 'fal-ai/flux-pro/v1.1-ultra') {
            // For Ultra model, use aspect ratio
            formData.aspect_ratio = document.getElementById('aspectRatio').value;
            formData.output_format = 'jpeg';
            formData.safety_tolerance = '2';
        } else {
            // For other models, use image size
            const imageSizeKey = document.getElementById('imageSize').value;
            const dimensions = getImageDimensions(imageSizeKey);
            formData.image_size = { width: dimensions[0], height: dimensions[1] };
        }

        if (selectedModel === 'fal-ai/flux-lora' || selectedModel === 'fal-ai/flux-realism') {
            formData.num_inference_steps = parseInt(document.getElementById('numInferenceSteps').value);
            formData.guidance_scale = parseFloat(document.getElementById('guidanceScale').value);
            
            if (selectedModel === 'fal-ai/flux-lora' && document.getElementById('loraPath').value) {
                formData.loras = [{
                    path: document.getElementById('loraPath').value,
                    scale: parseFloat(document.getElementById('loraScale').value)
                }];
            }
        }

        try {
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
                throw new Error(data.error);
            }
            
            // Handle successful response
            if (data.images) {
                const resultContainer = document.getElementById('enhancedPromptContainer');
                resultContainer.classList.remove('hidden');
                // Additional result handling...
            }
        } catch (error) {
            console.error('Error generating image:', error);
            let errorMessage = 'Failed to generate image';
            let errorDetails = error.message;

            // Handle specific error types
            if (error.message.includes('API key')) {
                errorMessage = 'API Key Error';
                errorDetails = 'Please contact administrator';
            } else if (error.message.includes('rate limit')) {
                errorMessage = 'Rate Limit Exceeded';
                errorDetails = 'Please try again later';
            }

            showError(errorMessage, errorDetails);
        } finally {
            // Reset button state
            generateButton.disabled = false;
            generateButton.textContent = originalText;
        }
    });

    return form;
}

function getImageDimensions(sizeOption) {
    const dimensions = {
        'youtube_thumbnail': [1280, 704],
        'landscape_4_3': [1280, 960],
        'landscape_16_9': [1280, 720],
        'portrait_4_3': [960, 1280],
        'portrait_16_9': [720, 1280],
        'square': [1024, 1024],
        'square_hd': [1280, 1280],
        'instagram_post_square': [1080, 1080],
        'instagram_post_portrait': [1080, 1350],
        'instagram_story': [1080, 1920],
        'logo': [512, 512],
        'blog_banner': [1280, 640],
        'linkedin_post': [1200, 627],
        'facebook_post_landscape': [1200, 630],
        'twitter_header': [1500, 500]
    };

    return dimensions[sizeOption] || [1024, 1024]; // Default to square if size not found
}
