# Sketch Maker AI

A modern web application that uses AI to generate artwork from text descriptions, with support for multiple artistic styles and image formats.

## Features

- AI-powered image generation from text descriptions
- 25+ artistic styles to choose from
- User authentication and personal galleries
- Multiple download formats (WebP, PNG, JPEG)
- Dark/Light theme support
- Responsive modern UI using daisyUI and Tailwind CSS
- Rate limiting to prevent abuse
- Smart prompt generation assistance

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/sketchmaker.git
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
- OpenAI API key
- FAL API key
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
2. Navigate to the dashboard
3. Enter a description of the artwork you want to generate
4. Choose an artistic style
5. Click "Generate" to create your artwork
6. Download your image in your preferred format (WebP, PNG, or JPEG)
7. View all your generated images in your personal gallery

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
│   └── generate.py    # Image generation routes
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

- Flask
- SQLite & SQLAlchemy
- Flask-Login
- OpenAI API
- FAL API
- daisyUI & Tailwind CSS
- Pillow (PIL)

## Contributing

1. Fork the repository
2. Create a new branch for your feature
3. Commit your changes
4. Push to your branch
5. Create a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
