async function handleTrainingResponse(response) {
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
        throw new Error('Server returned non-JSON response');
    }
    
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || 'Training failed');
    }
    return data;
}

async function checkTrainingStatus(trainingId) {
    try {
        const response = await fetch(`/api/training/${trainingId}`);
        const data = await handleTrainingResponse(response);
        
        // Update logs if available
        if (data.logs) {
            document.getElementById('logsContainer').textContent = data.logs;
            document.getElementById('logsContainer').scrollTop = document.getElementById('logsContainer').scrollHeight;
            
            // Extract progress from logs
            const progressMatch = data.logs.match(/(\d+)%\|/);
            if (progressMatch) {
                const progress = parseInt(progressMatch[1]);
                document.getElementById('progressBar').style.width = `${progress}%`;
                document.getElementById('progressText').textContent = `Training Progress: ${progress}%`;
            }
        }
        
        // Check if training is complete
        if (data.status === 'completed') {
            showResults(data);
            return true;
        } else if (data.status === 'failed') {
            showError('Training failed. Please check the logs for details.');
            return true;
        }
        
        return false;
    } catch (error) {
        console.error('Status check error:', error);
        showError(error.message);
        return false;
    }
}

async function startTraining(formData) {
    try {
        // Upload images
        const uploadResponse = await fetch('/api/training/upload', {
            method: 'POST',
            body: formData
        });
        
        const uploadResult = await handleTrainingResponse(uploadResponse);
        
        // Start training
        const trainingResponse = await fetch('/api/training/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                images_data_url: uploadResult.images_data_url,
                trigger_word: document.getElementById('triggerWord').value,
                steps: parseInt(document.getElementById('steps').value),
                create_masks: document.getElementById('createMasks').checked
            })
        });
        
        const result = await handleTrainingResponse(trainingResponse);
        return result.training_id;
        
    } catch (error) {
        console.error('Training error:', error);
        showError(error.message);
        throw error;
    }
}

function showError(message) {
    const progressText = document.getElementById('progressText');
    const startButton = document.getElementById('startTraining');
    const spinner = startButton.querySelector('.loading');
    
    progressText.textContent = `Error: ${message}`;
    progressText.classList.add('text-error');
    startButton.disabled = false;
    spinner.classList.add('hidden');
    
    // Add error to logs
    const logsContainer = document.getElementById('logsContainer');
    logsContainer.textContent += `\nError: ${message}`;
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

function showResults(data) {
    const resultsSection = document.getElementById('trainingResults');
    const startButton = document.getElementById('startTraining');
    const spinner = startButton.querySelector('.loading');
    
    resultsSection.classList.remove('hidden');
    startButton.disabled = false;
    spinner.classList.add('hidden');
    
    if (data.config_url) {
        document.getElementById('configUrl').textContent = data.config_url;
    }
    if (data.weights_url) {
        document.getElementById('weightsUrl').textContent = data.weights_url;
    }
    if (data.result) {
        document.getElementById('outputJson').textContent = JSON.stringify(data.result, null, 2);
    }
    
    // Reload the page after 2 seconds to show updated history
    setTimeout(() => {
        window.location.reload();
    }, 2000);
}

// Initialize training form handling
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('trainingForm');
    const imageUpload = document.getElementById('imageUpload');
    const imagePreview = document.getElementById('imagePreview');
    const progressSection = document.getElementById('trainingProgress');
    const startButton = document.getElementById('startTraining');
    const spinner = startButton.querySelector('.loading');
    let statusCheckInterval = null;
    
    // Handle image preview
    imageUpload.addEventListener('change', function() {
        imagePreview.innerHTML = '';
        if (this.files.length < 5 || this.files.length > 20) {
            alert('Please select between 5 and 20 images');
            this.value = '';
            return;
        }

        Array.from(this.files).forEach(file => {
            const reader = new FileReader();
            reader.onload = function(e) {
                const div = document.createElement('div');
                div.className = 'relative aspect-square';
                div.innerHTML = `
                    <img src="${e.target.result}" alt="Preview" 
                         class="w-full h-full object-cover rounded-lg" />
                `;
                imagePreview.appendChild(div);
            };
            reader.readAsDataURL(file);
        });
    });
    
    // Handle form submission
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const files = imageUpload.files;
        if (files.length < 5 || files.length > 20) {
            alert('Please select between 5 and 20 images');
            return;
        }
        
        // Show progress section and hide results
        progressSection.classList.remove('hidden');
        document.getElementById('trainingResults').classList.add('hidden');
        startButton.disabled = true;
        spinner.classList.remove('hidden');
        document.getElementById('progressText').textContent = 'Uploading images...';
        document.getElementById('progressBar').style.width = '10%';
        document.getElementById('logsContainer').textContent = 'Starting upload...\n';
        
        try {
            // Prepare form data
            const formData = new FormData();
            Array.from(files).forEach(file => {
                formData.append('files[]', file);
            });
            
            // Start training process
            const trainingId = await startTraining(formData);
            
            // Start polling for status updates
            statusCheckInterval = setInterval(async () => {
                const isComplete = await checkTrainingStatus(trainingId);
                if (isComplete) {
                    clearInterval(statusCheckInterval);
                }
            }, 5000);
            
        } catch (error) {
            clearInterval(statusCheckInterval);
            showError(error.message);
        }
    });
});
