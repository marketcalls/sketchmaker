# Sketch Maker AI

A sophisticated web application that leverages multiple AI providers and models to generate artwork, banners, and custom visual content from text descriptions. Features include custom model training, multiple format support, and a comprehensive gallery system.

## Core Features

- Multi-Provider AI Support:
  - OpenAI: Advanced language models for prompt enhancement
  - Anthropic: State-of-the-art language models with Claude capabilities
  - Google Gemini: Next-generation AI with multimodal understanding
  - Groq: High-performance inference with ultra-low latency

- Banner Generation:
  - SVG banner creation with precise control
  - Multiple style presets (modern, minimalist, artistic, corporate, playful, tech, elegant)
  - Dynamic text alignment and positioning
  - Automatic viewBox and preserveAspectRatio handling
  - Support for gradients, patterns, and effects

- Image Generation (FAL Integration):
  - Flux Pro: High-quality standard image generation
  - Flux Pro Ultra: Advanced generation with aspect ratio control
  - Flux Lora: Custom model training support
  - Flux Dev: Development and testing environment
  - Flux Realism: Enhanced photorealistic generation
  - Recraft V3: Advanced style control with color customization

- Custom Model Training:
  - Support for 5-20 training images
  - Automatic mask generation
  - Real-time training progress monitoring
  - Webhook integration for status updates
  - Training history management
  - Easy access to trained model files
  - Trigger word management

- Gallery & Asset Management:
  - Personal image galleries
  - Multiple format support (WebP, PNG, JPEG)
  - Automatic format conversion
  - Secure download system
  - Image metadata tracking
  - Creation history

- Advanced Security:
  - Role-based access control (User/Admin)
  - Secure API key management
  - Rate limiting protection
  - First-user superadmin privileges
  - User account management
  - Activity monitoring

## Technical Architecture

### Blueprints Structure:
- `admin.py`: User and system management
- `auth.py`: Authentication and authorization
- `banner.py`: SVG banner generation
- `clients.py`: AI provider client management
- `core.py`: Core application routes
- `download.py`: Secure file downloads
- `gallery.py`: Image gallery management
- `generate.py`: Image generation coordination
- `image_generator.py`: FAL integration
- `prompt_generator.py`: AI prompt enhancement
- `training.py`: Custom model training

### Key Components:
- Flask web framework
- SQLAlchemy ORM
- Multiple AI provider integrations
- FAL API for image generation
- Webhook system for async updates
- Real-time training monitoring
- Secure file handling
- Rate limiting system

## Setup Instructions

1. Clone the repository:
\`\`\`bash
git clone https://github.com/yourusername/sketchmaker.git
cd sketchmaker
\`\`\`

2. Create and activate virtual environment:
\`\`\`bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
\`\`\`

3. Install dependencies:
\`\`\`bash
pip install -r requirements.txt
\`\`\`

4. Configure environment:
\`\`\`bash
cp .env.sample .env
# Edit .env with your API keys and settings
\`\`\`

5. Initialize database:
\`\`\`bash
flask shell
>>> from app import db
>>> db.create_all()
>>> exit()
\`\`\`

6. Run the application:
\`\`\`bash
python app.py
\`\`\`

## API Configuration

Required API keys:
- OpenAI API key (for GPT models)
- Anthropic API key (for Claude models)
- Google Gemini API key
- Groq API key
- FAL API key (for image generation)

Configure in Settings after first login.

## Usage Guide

1. Initial Setup:
   - Register first user (becomes superadmin)
   - Configure API keys in settings
   - Select preferred AI provider

2. Content Generation:
   - Create banners with custom styles
   - Generate images with various models
   - Train custom models
   - Manage gallery content

3. Admin Functions:
   - Manage users and roles
   - Monitor system settings
   - Track user activity
   - Configure global defaults

## Error Handling

Comprehensive error handling for:
- API authentication
- Rate limits
- Network issues
- File operations
- Training processes
- User permissions
- Input validation

## Production Deployment

Detailed deployment guide in [server/setup.md](server/setup.md) including:
- Nginx configuration
- Gunicorn setup
- SSL/TLS setup
- Backup procedures
- Monitoring setup

## Contributing

1. Fork the repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Create pull request

## License

This project is licensed under the AGPL v3.0 License - see LICENSE for details.
