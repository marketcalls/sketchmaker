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
    let consecutiveErrorCount = 0;
    const MAX_ERRORS = 5;

    // Add image preview functionality
    imageUpload.addEventListener('change', function(e) {
        imagePreview.innerHTML = ''; // Clear existing previews
        const files = e.target.files;

        if (files.length < 5 || files.length > 20) {
            alert('Please select between 5 and 20 images');
            e.target.value = ''; // Clear the file input
            return;
        }

        // Create container for images
        const container = document.createElement('div');
        Object.assign(container.style, {
            display: 'flex',
            flexWrap: 'wrap',
            gap: '12px',
            justifyContent: 'flex-start',
            alignItems: 'flex-start',
            maxWidth: '1024px',
            margin: '0 auto',
            padding: '16px'
        });
        imagePreview.appendChild(container);

        Array.from(files).forEach(file => {
            if (!file.type.startsWith('image/')) {
                return; // Skip non-image files
            }

            const reader = new FileReader();
            reader.onload = function(e) {
                // Create fixed-size container for each image
                const imageBox = document.createElement('div');
                Object.assign(imageBox.style, {
                    width: '250px',
                    height: '250px',
                    backgroundColor: 'var(--fallback-b3,oklch(var(--b3)))',
                    borderRadius: '8px',
                    overflow: 'hidden',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flex: '0 0 auto'
                });

                // Create and set up image
                const img = document.createElement('img');
                img.src = e.target.result;
                Object.assign(img.style, {
                    maxWidth: '100%',
                    maxHeight: '100%',
                    objectFit: 'contain',
                    display: 'block'
                });

                // Assemble the components
                imageBox.appendChild(img);
                container.appendChild(imageBox);
            };

            reader.onerror = function() {
                console.error('Error reading file:', file.name);
            };

            reader.readAsDataURL(file);
        });
    });

    function extractProgressFromLogs(logs) {
        if (!logs) return null;
        
        // Convert logs to string if it's not already
        const logsStr = typeof logs === 'string' ? logs : formatLogs(logs);
        
        // Look for completion indicators
        if (logsStr.includes('Model saved to')) {
            return 100;
        }
        
        // Look for progress patterns
        const progressPatterns = [
            /(\d+)\/100\s+\[[\d:]+<?,\s+[\d.]+s\/it\]/,  // Matches "95/100 [01:43<00:05, 1.13s/it]"
            /(\d+)%\|/,  // Matches "95%|"
            /(\d+)\/100/  // Simple fraction match
        ];
        
        for (const pattern of progressPatterns) {
            const match = logsStr.match(new RegExp(pattern, 'g'));
            if (match) {
                // Get the last (most recent) match
                const lastMatch = match[match.length - 1];
                const progressMatch = lastMatch.match(/\d+/);
                if (progressMatch) {
                    return parseInt(progressMatch[0]);
                }
            }
        }
        
        return null;
    }

    function formatLogs(logs) {
        if (!logs) return '';
        
        // Handle array of log objects
        if (Array.isArray(logs)) {
            return logs.map(log => {
                if (typeof log === 'object' && log.message) {
                    return log.message;
                }
                return JSON.stringify(log);
            }).join('\n');
        }
        // Handle string logs
        else if (typeof logs === 'string') {
            return logs;
        }
        // Handle other types
        return JSON.stringify(logs, null, 2);
    }

    async function checkTrainingStatus(trainingId) {
        try {
            const response = await fetch(`/api/training/${trainingId}`);
            if (!response.ok) {
                throw new Error('Failed to fetch training status');
            }

            const data = await response.json();
            
            // Update logs if available
            if (data.logs) {
                const formattedLogs = formatLogs(data.logs);
                logsContainer.textContent = formattedLogs;
                logsContainer.scrollTop = logsContainer.scrollHeight;
                
                // Extract progress
                const progress = extractProgressFromLogs(formattedLogs);
                if (progress !== null) {
                    progressBar.style.width = `${progress}%`;
                    progressText.textContent = `Training Progress: ${progress}%`;
                    
                    // Check for completion based on logs
                    if (progress === 100 && formattedLogs.includes('Model saved to')) {
                        clearInterval(statusCheckInterval);
                        data.status = 'completed';
                    }
                }
            }
            
            // Check training status
            if (data.status === 'completed' || (data.logs && data.logs.includes('Model saved to'))) {
                clearInterval(statusCheckInterval);
                showResults(data);
                return true;
            } else if (data.status === 'failed') {
                clearInterval(statusCheckInterval);
                showError('Training failed. Please check the logs for details.');
                return true;
            }
            
            // Reset error count on successful status check
            consecutiveErrorCount = 0;
            return false;
        } catch (error) {
            console.error('Status check error:', error);
            consecutiveErrorCount++;
            
            // If we've had too many consecutive errors, stop checking
            if (consecutiveErrorCount >= MAX_ERRORS) {
                clearInterval(statusCheckInterval);
                showError('Lost connection to server. Please check the training status in your history.');
            }
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

            // Reset error count
            consecutiveErrorCount = 0;

            // Start polling for status updates
            const trainingId = result.training_id;
            statusCheckInterval = setInterval(() => checkTrainingStatus(trainingId), 10000); // Check every 10 seconds
            
            // Do an immediate check
            await checkTrainingStatus(trainingId);
            
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
            document.getElementById('modalLogs').textContent = formatLogs(data.logs) || 'No logs available';
            document.getElementById('modalConfigUrl').textContent = data.config_url || '';
            document.getElementById('modalWeightsUrl').textContent = data.weights_url || '';
            
            document.getElementById('trainingDetailsModal').showModal();
        } catch (error) {
            console.error('Error fetching training details:', error);
            alert('Error loading training details');
        }
    };
});
