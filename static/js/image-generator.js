export async function generateImages(prompt, imageSize) {
    const formData = {
        message: prompt,
        image_size: imageSize,
    };

    const response = await fetch('/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.csrf_token
        },
        body: JSON.stringify(formData),
    });

    const data = await response.json();
    if (data.image_url) {
        return data;
    } else {
        throw new Error('Invalid response from server');
    }
}