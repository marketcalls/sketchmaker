export async function generatePrompt(formData, regenerate = false) {
    const response = await fetch('/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.csrf_token
        },
        body: JSON.stringify({ ...formData, regenerate_prompt: regenerate }),
    });

    const data = await response.json();
    if (data.prompt) {
        return data.prompt;
    } else {
        throw new Error('Invalid response from server');
    }
}