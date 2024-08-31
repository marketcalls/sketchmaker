document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('imageGenForm');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const resultContainer = document.getElementById('resultContainer');
    const imageResultContainer = document.getElementById('imageResultContainer');
    const imageContainer = document.getElementById('imageContainer');
    const imageSizeSelect = document.getElementById('imageSize');

    // Animation for page load
    gsap.from('header', { duration: 1, y: -50, opacity: 0, ease: 'power3.out' });
    gsap.from('main', { duration: 1, y: 50, opacity: 0, ease: 'power3.out', delay: 0.3 });

    // Form submission handler
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        await handleGeneratePrompt();
    });

    async function handleGeneratePrompt(regenerate = false) {
        showLoading(loadingIndicator);
        resultContainer.classList.add('hidden');
        imageResultContainer.classList.add('hidden');

        const formData = {
            message: document.getElementById('userInput').value,
            art_style: document.getElementById('artStyle').value,
            color_scheme: document.getElementById('colorScheme').value,
            lighting_mood: document.getElementById('lightingMood').value,
            subject_focus: document.getElementById('subjectFocus').value,
            background_style: document.getElementById('backgroundStyle').value,
            effects_filters: document.getElementById('effectsFilters').value,
            regenerate_prompt: regenerate
        };

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
                showResultContainer(resultContainer, data.prompt);
            } else {
                throw new Error('Invalid response from server');
            }
        } catch (error) {
            console.error('Error generating prompt:', error);
            alert('An error occurred while generating the prompt. Please try again.');
        } finally {
            hideLoading(loadingIndicator);
        }
    }

    async function handleGenerateImages() {
        showLoading(loadingIndicator);
        imageResultContainer.classList.add('hidden');

        const prompt = document.getElementById('generatedPrompt').textContent;
        const imageSize = imageSizeSelect.value;

        const formData = {
            message: prompt,
            image_size: imageSize,
        };

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
                displayGeneratedImages(imageResultContainer, imageContainer, data);
            } else {
                throw new Error('Invalid response from server');
            }
        } catch (error) {
            console.error('Error generating images:', error);
            alert('An error occurred while generating the images. Please try again.');
        } finally {
            hideLoading(loadingIndicator);
        }
    }

    // Attach event listeners to the Approve and Regenerate buttons
    document.getElementById('approve-prompt').addEventListener('click', handleGenerateImages);
    document.getElementById('regenerate-prompt').addEventListener('click', () => handleGeneratePrompt(true));
});

function showLoading(loadingIndicator) {
    loadingIndicator.classList.remove('hidden');
}

function hideLoading(loadingIndicator) {
    loadingIndicator.classList.add('hidden');
}

function showResultContainer(resultContainer, prompt) {
    const promptElement = document.getElementById('generatedPrompt');
    promptElement.textContent = prompt;
    resultContainer.classList.remove('hidden');
    window.scrollTo({
        top: resultContainer.offsetTop,
        behavior: 'smooth'
    });
}

function displayGeneratedImages(imageResultContainer, imageContainer, data) {
    imageContainer.innerHTML = '';
    const imageUrls = Array.isArray(data.image_url) ? data.image_url : [data.image_url];
    
    imageUrls.forEach((url, index) => {
        const imgContainer = document.createElement('div');
        imgContainer.className = 'bg-white rounded-lg shadow-lg overflow-hidden mb-8';
        
        const imgWrapper = document.createElement('div');
        imgWrapper.className = 'relative';
        
        const imgElement = document.createElement('img');
        imgElement.src = url;
        imgElement.alt = 'Generated Thumbnail';
        imgElement.className = 'w-full h-auto';
        
        // Determine if the image is small
        const isSmallImage = data.width < 512 || data.height < 512;
        
        if (isSmallImage) {
            imgWrapper.className += ' flex justify-center items-center p-4';
            imgElement.className += ' max-w-full max-h-[512px] object-contain';
        } else {
            imgElement.className += ' object-cover';
        }
        
        imgWrapper.appendChild(imgElement);
        imgContainer.appendChild(imgWrapper);
        
        const infoContainer = document.createElement('div');
        infoContainer.className = 'p-4';
        
        const dimensionsElement = document.createElement('p');
        dimensionsElement.className = 'text-sm text-gray-600 mb-4';
        dimensionsElement.textContent = `Dimensions: ${data.width}x${data.height}`;
        infoContainer.appendChild(dimensionsElement);
        
        const downloadContainer = document.createElement('div');
        downloadContainer.className = 'flex justify-center space-x-4';
        
        ['webp', 'png', 'jpeg'].forEach(format => {
            const downloadButton = document.createElement('a');
            downloadButton.href = `/download?url=${encodeURIComponent(url)}&format=${format}`;
            downloadButton.className = 'bg-blue-500 text-white py-2 px-4 rounded hover:bg-blue-600 transition duration-300 text-sm font-medium';
            downloadButton.textContent = format.toUpperCase();
            downloadButton.download = `thumbnail_${index + 1}.${format}`;
            downloadContainer.appendChild(downloadButton);
        });
        
        infoContainer.appendChild(downloadContainer);
        imgContainer.appendChild(infoContainer);
        imageContainer.appendChild(imgContainer);
    });
    
    imageResultContainer.classList.remove('hidden');
    window.scrollTo({
        top: imageResultContainer.offsetTop,
        behavior: 'smooth'
    });
}

// Function to update image size (if needed)
function updateImageSize() {
    // Implement any additional logic for updating image size here
    console.log('Image size updated');
}