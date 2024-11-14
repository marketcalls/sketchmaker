document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('trainingForm');
    const imageUpload = document.getElementById('imageUpload');
    const imagePreview = document.getElementById('imagePreview');
    const progressSection = document.getElementById('trainingProgress');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const logsContainer = document.getElementById('logsContainer');
    const resultsSection = document.getElementById('trainingResults');
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

    async function checkTrainingStatus(trainingId) {
        try {
            const response = await fetch(`/api/training/${trainingId}`);
            if (!response.ok) {
                throw new Error('Failed to fetch training status');
            }

            const data = await response.json();
            
            // Update logs if available
            if (data.logs) {
                logsContainer.textContent = data.logs;
                logsContainer.scrollTop = logsContainer.scrollHeight;
                
                // Extract progress from logs
                const progressMatch = data.logs.match(/(\d+)%\|/);
                if (progressMatch) {
                    const progress = parseInt(progressMatch[1]);
                    progressBar.style.width = `${progress}%`;
                    progressText.textContent = `Training Progress: ${progress}%`;
                }
            }
            
            // Check training status
            if (data.status === 'completed') {
                clearInterval(statusCheckInterval);
                showResults(data);
                return true;
            } else if (data.status === 'failed') {
                clearInterval(statusCheckInterval);
                showError('Training failed. Please check the logs for details.');
                return true;
            }
            
            return false;
        } catch (error) {
            console.error('Status check error:', error);
            // Don't clear interval - keep checking
            return false;
        }
    }

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
        resultsSection.classList.add('hidden');
        startButton.disabled = true;
        spinner.classList.remove('hidden');
        progressText.textContent = 'Uploading images...';
        progressBar.style.width = '10%';
        logsContainer.textContent = 'Starting upload...\n';
        
        try {
            // First, upload images
            const formData = new FormData();
            Array.from(files).forEach(file => {
                formData.append('files[]', file);
            });
            
            const uploadResponse = await fetch('/api/training/upload', {
                method: 'POST',
                body: formData
            });
            
            if (!uploadResponse.ok) {
                const errorData = await uploadResponse.json();
                throw new Error(errorData.error || 'Upload failed');
            }
            
            const uploadResult = await uploadResponse.json();
            if (uploadResult.error) {
                throw new Error(uploadResult.error);
            }

            progressText.textContent = 'Starting training...';
            progressBar.style.width = '20%';
            logsContainer.textContent += 'Upload complete. Starting training...\n';
            
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
            
            if (!trainingResponse.ok) {
                const errorData = await trainingResponse.json();
                throw new Error(errorData.error || 'Training failed to start');
            }
            
            const result = await trainingResponse.json();
            if (result.error) {
                throw new Error(result.error);
            }

            // Start polling for status updates
            const trainingId = result.training_id;
            statusCheckInterval = setInterval(() => checkTrainingStatus(trainingId), 5000);
            
        } catch (error) {
            console.error('Training error:', error);
            showError(error.message);
            startButton.disabled = false;
            spinner.classList.add('hidden');
        }
    });

    function showError(message) {
        progressText.textContent = `Error: ${message}`;
        progressText.classList.add('text-error');
        logsContainer.textContent += `\nError: ${message}`;
        logsContainer.scrollTop = logsContainer.scrollHeight;
    }

    function showResults(data) {
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

    // Copy text to clipboard
    window.copyText = function(text) {
        navigator.clipboard.writeText(text).then(() => {
            alert('Copied to clipboard!');
        });
    };

    // Copy element content to clipboard
    window.copyToClipboard = function(elementId) {
        const element = document.getElementById(elementId);
        const text = element.textContent;
        navigator.clipboard.writeText(text).then(() => {
            const btn = element.parentElement.querySelector('.btn');
            const originalText = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(() => {
                btn.textContent = originalText;
            }, 2000);
        });
    };

    // Show training details
    window.showTrainingDetails = async function(trainingId) {
        try {
            const response = await fetch(`/api/training/${trainingId}`);
            if (!response.ok) {
                throw new Error('Failed to fetch training details');
            }

            const data = await response.json();
            
            document.getElementById('modalTriggerWord').textContent = data.trigger_word;
            document.getElementById('modalLogs').textContent = data.logs || 'No logs available';
            document.getElementById('modalConfigUrl').textContent = data.config_url || '';
            document.getElementById('modalWeightsUrl').textContent = data.weights_url || '';
            
            document.getElementById('trainingDetailsModal').showModal();
        } catch (error) {
            console.error('Error fetching training details:', error);
            alert('Error loading training details');
        }
    };
});
