export function showLoading(loadingIndicator) {
    loadingIndicator.classList.remove('hidden');
}

export function hideLoading(loadingIndicator) {
    loadingIndicator.classList.add('hidden');
}

export function showResultContainer(resultContainer, prompt) {
    const promptElement = document.getElementById('generatedPrompt');
    promptElement.textContent = prompt;
    resultContainer.classList.remove('hidden');
    window.scrollTo({
        top: resultContainer.offsetTop,
        behavior: 'smooth'
    });
}

export function displayGeneratedImages(imageResultContainer, imageContainer, data) {
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