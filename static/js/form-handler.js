export function initializeForm() {
    const form = document.getElementById('imageGenForm');
    const modelSelect = document.getElementById('model');
    const imageSizeControl = document.getElementById('imageSizeControl');
    const aspectRatioControl = document.getElementById('aspectRatioControl');
    const numInferenceStepsControls = document.getElementById('numInferenceSteps').closest('.form-control');
    const guidanceScaleControls = document.getElementById('guidanceScale').closest('.form-control');
    const loraInputs = document.getElementById('loraInputs');

    // Function to update visible controls based on selected model
    function updateFormControls(modelValue) {
        console.log('Updating controls for model:', modelValue);
        
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
        console.log('Model changed to:', e.target.value);
        updateFormControls(e.target.value);
    });

    // Initialize controls based on default model
    updateFormControls(modelSelect.value);

    // Handle image generation
    document.getElementById('generateImage').addEventListener('click', async () => {
        const selectedModel = modelSelect.value;
        console.log('Preparing to generate image with model:', selectedModel);

        // Get the prompt from either enhanced or original input
        const prompt = document.getElementById('enhancedPromptText').value || document.getElementById('userInput').value;
        
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

        console.log('Sending request with data:', formData);

        try {
            const response = await fetch('/generate/image', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData),
            });

            const data = await response.json();
            if (data.error) {
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
            // Handle error...
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
