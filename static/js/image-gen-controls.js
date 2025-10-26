// Fetch LoRA data when model is set to Flux Lora
async function fetchLoraData() {
    try {
        const response = await fetch('/api/lora-data');
        if (!response.ok) {
            throw new Error('Failed to fetch LoRA data');
        }
        const data = await response.json();
        return data.lora_data;
    } catch (error) {
        console.error('Error fetching LoRA data:', error);
        return [];
    }
}

// Update LoRA dropdown options
async function updateLoraDropdown() {
    const loraPicker = document.getElementById('loraPicker');
    const data = await fetchLoraData();
    
    // Clear existing options except the first one
    while (loraPicker.options.length > 1) {
        loraPicker.remove(1);
    }
    
    // Add new options
    data.forEach(item => {
        const option = document.createElement('option');
        option.value = item.weights_url;
        option.textContent = item.trigger_word;
        option.dataset.triggerWord = item.trigger_word;
        loraPicker.appendChild(option);
    });
}

// Handle LoRA selection change
document.getElementById('loraPicker').addEventListener('change', function(e) {
    const selectedOption = e.target.options[e.target.selectedIndex];
    const triggerWord = selectedOption.dataset.triggerWord || 'None';
    document.getElementById('selectedTriggerWord').textContent = triggerWord;
    
    // Update manual input if visible
    const loraPath = document.getElementById('loraPath');
    if (e.target.value) {
        loraPath.value = e.target.value;
    }

    // Update form data with LoRA information
    const formData = new FormData(document.getElementById('imageGenForm'));
    if (e.target.value) {
        formData.set('loras', JSON.stringify([{
            path: e.target.value,
            scale: parseFloat(document.getElementById('loraScale').value) || 1.0,
            trigger_word: triggerWord
        }]));
    }
});

// Handle LoRA scale change
document.getElementById('loraScale').addEventListener('change', function(e) {
    const loraPicker = document.getElementById('loraPicker');
    const selectedOption = loraPicker.options[loraPicker.selectedIndex];
    if (selectedOption && selectedOption.value) {
        const formData = new FormData(document.getElementById('imageGenForm'));
        formData.set('loras', JSON.stringify([{
            path: selectedOption.value,
            scale: parseFloat(e.target.value) || 1.0,
            trigger_word: selectedOption.dataset.triggerWord
        }]));
    }
});

// Toggle between dropdown and manual input
document.getElementById('toggleLoraInput').addEventListener('click', function() {
    const dropdownContainer = document.getElementById('loraDropdownContainer');
    const manualContainer = document.getElementById('loraManualContainer');
    const isManual = dropdownContainer.classList.contains('hidden');
    
    if (isManual) {
        dropdownContainer.classList.remove('hidden');
        manualContainer.classList.add('hidden');
        this.textContent = 'Manual Input';

        // Use dropdown value if available
        const loraPicker = document.getElementById('loraPicker');
        const selectedOption = loraPicker.options[loraPicker.selectedIndex];
        if (selectedOption && selectedOption.value) {
            const formData = new FormData(document.getElementById('imageGenForm'));
            formData.set('loras', JSON.stringify([{
                path: selectedOption.value,
                scale: parseFloat(document.getElementById('loraScale').value) || 1.0,
                trigger_word: selectedOption.dataset.triggerWord
            }]));
        }
    } else {
        dropdownContainer.classList.add('hidden');
        manualContainer.classList.remove('hidden');
        this.textContent = 'Use Dropdown';

        // Use manual input value if available
        const loraPath = document.getElementById('loraPath').value;
        if (loraPath) {
            const formData = new FormData(document.getElementById('imageGenForm'));
            formData.set('loras', JSON.stringify([{
                path: loraPath,
                scale: parseFloat(document.getElementById('loraScale').value) || 1.0
            }]));
        }
    }
});

// Update controls when model changes
document.getElementById('model').addEventListener('change', function(e) {
    const imageSizeControl = document.getElementById('imageSizeControl');
    const aspectRatioControl = document.getElementById('aspectRatioControl');
    const loraInputs = document.getElementById('loraInputs');
    const numInferenceStepsControl = document.getElementById('numInferenceSteps')?.closest('.form-control');
    const guidanceScaleControl = document.getElementById('guidanceScale')?.closest('.form-control');
    const recraftStyleControl = document.getElementById('recraftStyleControl');
    const recraftColorsControl = document.getElementById('recraftColorsControl');
    const characterCount = document.getElementById('characterCount');
    const enhancedCharacterCount = document.getElementById('enhancedCharacterCount');
    
    // Get Imagen4 controls
    const imagen4AspectRatioControl = document.getElementById('imagen4AspectRatioControl');
    const imagen4NegativePromptControl = document.getElementById('imagen4NegativePromptControl');
    
    // Get Ideogram V3 controls
    const ideogramV3ImageSizeControl = document.getElementById('ideogramV3ImageSizeControl');
    const ideogramV3ExpandPromptControl = document.getElementById('ideogramV3ExpandPromptControl');
    const ideogramV3NegativePromptControl = document.getElementById('ideogramV3NegativePromptControl');
    const ideogramV3RenderingSpeedControl = document.getElementById('ideogramV3RenderingSpeedControl');

    // Get Seedream V4 controls
    const seedreamImageSizeControl = document.getElementById('seedreamImageSizeControl');
    const seedreamCustomSizeControl = document.getElementById('seedreamCustomSizeControl');
    const seedreamMaxImagesControl = document.getElementById('seedreamMaxImagesControl');

    // Reset all controls first
    imageSizeControl?.classList.remove('hidden');
    aspectRatioControl?.classList.add('hidden');
    loraInputs?.classList.add('hidden');
    if (numInferenceStepsControl) numInferenceStepsControl.classList.remove('hidden');
    if (guidanceScaleControl) guidanceScaleControl.classList.remove('hidden');
    recraftStyleControl?.classList.add('hidden');
    recraftColorsControl?.classList.add('hidden');
    imagen4AspectRatioControl?.classList.add('hidden');
    imagen4NegativePromptControl?.classList.add('hidden');
    ideogramV3ImageSizeControl?.classList.add('hidden');
    ideogramV3ExpandPromptControl?.classList.add('hidden');
    ideogramV3NegativePromptControl?.classList.add('hidden');
    ideogramV3RenderingSpeedControl?.classList.add('hidden');
    seedreamImageSizeControl?.classList.add('hidden');
    seedreamCustomSizeControl?.classList.add('hidden');
    seedreamMaxImagesControl?.classList.add('hidden');
    if (characterCount) characterCount.classList.add('hidden');
    if (enhancedCharacterCount) enhancedCharacterCount.classList.add('hidden');

    // Apply model-specific controls
    switch(e.target.value) {
        case 'fal-ai/bytedance/seedream/v4/text-to-image':
            // Hide controls that don't apply to Seedream V4
            imageSizeControl?.classList.add('hidden');
            aspectRatioControl?.classList.add('hidden');
            if (numInferenceStepsControl) numInferenceStepsControl.classList.add('hidden');
            if (guidanceScaleControl) guidanceScaleControl.classList.add('hidden');

            // Show Seedream V4 specific controls
            seedreamImageSizeControl?.classList.remove('hidden');
            seedreamMaxImagesControl?.classList.remove('hidden');

            // Check if custom is already selected and show/hide accordingly
            const seedreamPreset = document.getElementById('seedreamImageSizePreset');
            if (seedreamPreset && seedreamPreset.value === 'custom') {
                seedreamCustomSizeControl?.classList.remove('hidden');
            }
            break;
        case 'fal-ai/flux-pro/v1.1-ultra':
            imageSizeControl?.classList.add('hidden');
            aspectRatioControl?.classList.remove('hidden');
            if (numInferenceStepsControl) numInferenceStepsControl.classList.add('hidden');
            if (guidanceScaleControl) guidanceScaleControl.classList.add('hidden');
            break;
        case 'fal-ai/flux-lora':
            loraInputs?.classList.remove('hidden');
            updateLoraDropdown(); // Fetch and update LoRA options
            break;
        case 'fal-ai/flux-pro/v1.1':
        case 'fal-ai/flux/dev':
            if (numInferenceStepsControl) numInferenceStepsControl.classList.add('hidden');
            if (guidanceScaleControl) guidanceScaleControl.classList.add('hidden');
            break;
        case 'fal-ai/recraft-v3':
            recraftStyleControl?.classList.remove('hidden');
            recraftColorsControl?.classList.remove('hidden');
            if (numInferenceStepsControl) numInferenceStepsControl.classList.add('hidden');
            if (guidanceScaleControl) guidanceScaleControl.classList.add('hidden');
            if (characterCount) characterCount.classList.remove('hidden');
            if (enhancedCharacterCount) enhancedCharacterCount.classList.remove('hidden');
            break;
        case 'fal-ai/imagen4/preview':
            imageSizeControl?.classList.add('hidden');
            imagen4AspectRatioControl?.classList.remove('hidden');
            imagen4NegativePromptControl?.classList.remove('hidden');
            if (numInferenceStepsControl) numInferenceStepsControl.classList.add('hidden');
            if (guidanceScaleControl) guidanceScaleControl.classList.add('hidden');
            break;
        case 'fal-ai/ideogram/v3':
            imageSizeControl?.classList.add('hidden');
            ideogramV3ImageSizeControl?.classList.remove('hidden');
            ideogramV3ExpandPromptControl?.classList.remove('hidden');
            ideogramV3NegativePromptControl?.classList.remove('hidden');
            ideogramV3RenderingSpeedControl?.classList.remove('hidden');
            if (numInferenceStepsControl) numInferenceStepsControl.classList.add('hidden');
            if (guidanceScaleControl) guidanceScaleControl.classList.add('hidden');
            break;
    }
    
    // Update character counts if the functions exist
    if (typeof updateCharacterCount === 'function') updateCharacterCount();
    if (typeof updateEnhancedCharacterCount === 'function') updateEnhancedCharacterCount();
    
    console.log('Model changed to:', e.target.value);
});

// Initialize controls based on default model
window.addEventListener('DOMContentLoaded', function() {
    const model = document.getElementById('model');
    if (model) {
        const event = new Event('change');
        model.dispatchEvent(event);
    }

    // Also initialize seedream preset handler
    const seedreamPreset = document.getElementById('seedreamImageSizePreset');
    if (seedreamPreset) {
        // Trigger initial state
        const presetEvent = new Event('change');
        seedreamPreset.dispatchEvent(presetEvent);
    }
});

// Art style tooltip functionality
function showArtStyleDescription() {
    const artStyle = document.getElementById('artStyle').value;
    const artStyleTooltip = document.getElementById('artStyleTooltip');
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

// Hide tooltip when clicking outside
document.addEventListener('click', function(event) {
    const artStyleTooltip = document.getElementById('artStyleTooltip');
    const artStyleSelect = document.getElementById('artStyle');
    if (artStyleTooltip && event.target !== artStyleSelect && event.target !== artStyleTooltip) {
        artStyleTooltip.classList.add('hidden');
    }
});

// Color picker functionality
document.getElementById('addColorBtn')?.addEventListener('click', function() {
    const colorPickers = document.getElementById('colorPickers');
    const colorPickerWrapper = document.createElement('div');
    colorPickerWrapper.className = 'flex items-center gap-2';

    const colorPicker = document.createElement('input');
    colorPicker.type = 'color';
    colorPicker.className = 'w-10 h-10 rounded cursor-pointer';

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn btn-sm btn-error';
    removeBtn.innerHTML = '×';
    removeBtn.onclick = function() {
        colorPickerWrapper.remove();
    };

    colorPickerWrapper.appendChild(colorPicker);
    colorPickerWrapper.appendChild(removeBtn);
    colorPickers.appendChild(colorPickerWrapper);
});

// Seedream V4 image size preset handler
document.getElementById('seedreamImageSizePreset')?.addEventListener('change', function(e) {
    const seedreamCustomSizeControl = document.getElementById('seedreamCustomSizeControl');
    if (e.target.value === 'custom') {
        seedreamCustomSizeControl?.classList.remove('hidden');
    } else {
        seedreamCustomSizeControl?.classList.add('hidden');
    }
});
