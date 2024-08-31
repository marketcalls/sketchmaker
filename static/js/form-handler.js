export function initializeForm() {
    const form = document.getElementById('imageGenForm');
    const imageSizeSelect = document.getElementById('imageSize');
    const customSizeInputs = document.getElementById('customSizeInputs');

    // Toggle custom size inputs visibility
    imageSizeSelect.addEventListener('change', (e) => {
        if (e.target.value === 'custom') {
            customSizeInputs.classList.remove('hidden');
        } else {
            customSizeInputs.classList.add('hidden');
        }
    });

    return form;
}