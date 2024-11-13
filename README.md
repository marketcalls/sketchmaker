# Sketch Maker AI

A modern web application that uses AI to generate artwork from text descriptions, with support for multiple AI models, artistic styles, and image formats.

## Features

- Multiple AI Model Support:
  - Flux Pro: Standard image generation
  - Flux Pro Ultra: High-quality generation with aspect ratio control
  - Flux Lora: Custom model fine-tuning support
  - Flux Dev: Development and testing
  - Flux Realism: Enhanced realism in generated images

- AI-powered Features:
  - Smart prompt enhancement using OpenAI
  - Image generation from enhanced prompts
  - Support for various aspect ratios and image sizes
  - 25+ artistic styles to choose from

- User Experience:
  - Secure API key management with show/hide functionality
  - Comprehensive error handling for API issues
  - User authentication and personal galleries
  - Multiple download formats (WebP, PNG, JPEG)
  - Dark/Light theme support
  - Responsive modern UI using daisyUI and Tailwind CSS

- Technical Features:
  - Rate limiting to prevent abuse
  - Graceful error handling for API failures
  - Model-specific parameter optimization
  - Automatic image format conversion

## Setup

1. Clone the repository:
```bash
git clone https://github.com/marketcalls/sketchmaker.git
cd sketchmaker
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.sample .env
```
Edit `.env` and add your:
- OpenAI API key (for prompt enhancement)
- FAL API key (for image generation)
- Secret key for Flask sessions
- Other required configuration

5. Initialize the database:
```bash
flask shell
>>> from app import db
>>> db.create_all()
>>> exit()
```

6. Run the application:
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Usage

1. Register for an account or login if you already have one
2. Add your API keys in the settings page:
   - OpenAI API key for prompt enhancement
   - FAL API key for image generation
3. Navigate to the dashboard
4. Enter a description of the artwork you want to generate
5. Choose an AI model:
   - Flux Pro for standard generation
   - Flux Pro Ultra for aspect ratio control
   - Flux Lora for custom model support
   - Flux Realism for enhanced realism
6. Select additional parameters:
   - Artistic style
   - Image size or aspect ratio
   - Model-specific settings
7. Click "Generate" to create your artwork
8. Download your image in your preferred format (WebP, PNG, or JPEG)
9. View all your generated images in your personal gallery

## Project Structure

```
sketchmaker/
├── app.py              # Main application file
├── models.py           # Database models
├── requirements.txt    # Project dependencies
├── blueprints/        # Route handlers
│   ├── auth.py        # Authentication routes
│   ├── core.py        # Core routes
│   ├── download.py    # Image download handling
│   ├── gallery.py     # Gallery routes
│   ├── generate.py    # Image generation routes
│   ├── clients.py     # API client handling
│   ├── image_generator.py  # Image generation logic
│   └── prompt_generator.py # Prompt enhancement logic
├── static/            # Static files
│   ├── css/          # Stylesheets
│   ├── js/           # JavaScript files
│   └── images/       # Generated images
└── templates/         # HTML templates
    ├── auth/         # Authentication templates
    ├── partials/     # Reusable template parts
    └── *.html        # Main templates
```

## Technologies Used

- Flask (Python web framework)
- SQLite & SQLAlchemy (Database)
- Flask-Login (Authentication)
- OpenAI API (Prompt enhancement)
- FAL API (Image generation)
- daisyUI & Tailwind CSS (UI components)
- Pillow (PIL) (Image processing)

## Error Handling

The application includes comprehensive error handling for:
- Invalid or missing API keys
- Rate limiting issues
- Network failures
- Invalid parameters
- Server errors

Each error is handled gracefully with clear user feedback and guidance for resolution.

## Contributing

1. Fork the repository
2. Create a new branch for your feature
3. Commit your changes
4. Push to your branch
5. Create a pull request

## License

This project is licensed under the AGPL v3.0 License - see the LICENSE file for details.
