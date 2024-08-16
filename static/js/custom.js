// Custom JavaScript for Sketch Maker AI

document.addEventListener('DOMContentLoaded', () => {
    // Animate header elements
    gsap.from('nav a', { duration: 0.5, y: -20, opacity: 0, ease: 'power2.out', stagger: 0.1 });
    gsap.from('h1, h2', { duration: 0.5, y: 20, opacity: 0, ease: 'power2.out', delay: 0.2 });

    // Animate form elements
    gsap.from('form .form-input, form .btn-primary', { duration: 0.5, y: 20, opacity: 0, ease: 'power2.out', stagger: 0.1, delay: 0.4 });

    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });

    // Add hover effect to buttons
    document.querySelectorAll('.btn-primary').forEach(button => {
        button.addEventListener('mouseenter', () => {
            gsap.to(button, { duration: 0.3, scale: 1.05, ease: 'power2.out' });
        });
        button.addEventListener('mouseleave', () => {
            gsap.to(button, { duration: 0.3, scale: 1, ease: 'power2.out' });
        });
    });
});

// Function to show loading indicator
function showLoading() {
    const loadingIndicator = document.getElementById('loadingIndicator');
    if (loadingIndicator) {
        loadingIndicator.classList.remove('hidden');
        gsap.from(loadingIndicator, { duration: 0.5, opacity: 0, ease: 'power2.out' });
    }
}

// Function to hide loading indicator
function hideLoading() {
    const loadingIndicator = document.getElementById('loadingIndicator');
    if (loadingIndicator) {
        gsap.to(loadingIndicator, { duration: 0.5, opacity: 0, ease: 'power2.out', onComplete: () => {
            loadingIndicator.classList.add('hidden');
        }});
    }
}

// Add these functions to your existing JavaScript code that handles form submission and API calls
// For example:
// document.querySelector('form').addEventListener('submit', (e) => {
//     e.preventDefault();
//     showLoading();
//     // Your API call logic here
//     // When the API call is complete, call hideLoading();
// });