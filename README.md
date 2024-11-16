# Sketch Maker AI

A sophisticated web application that leverages multiple AI providers and models to generate artwork, banners, and custom visual content from text descriptions. Features include custom model training, multiple format support, and a comprehensive gallery system.

## Core Features

### Multi-Provider AI Support
- OpenAI: Advanced language models for prompt enhancement
- Anthropic: State-of-the-art language models with Claude capabilities
- Google Gemini: Next-generation AI with multimodal understanding
- Groq: High-performance inference with ultra-low latency

### Banner Generation
- SVG banner creation with precise control
- Multiple style presets (modern, minimalist, artistic, corporate, playful, tech, elegant)
- Dynamic text alignment and positioning
- Automatic viewBox and preserveAspectRatio handling
- Support for gradients, patterns, and effects

### Image Generation (FAL Integration)
- Flux Pro: High-quality standard image generation
- Flux Pro Ultra: Advanced generation with aspect ratio control
- Flux Lora: Custom model training support
- Flux Dev: Development and testing environment
- Flux Realism: Enhanced photorealistic generation
- Recraft V3: Advanced style control with color customization

### Custom Model Training
- Support for 5-20 training images
- Automatic mask generation
- Real-time training progress monitoring
- Webhook integration for status updates
- Training history management
- Easy access to trained model files
- Trigger word management

### Gallery & Asset Management
- Personal image galleries
- Multiple format support (WebP, PNG, JPEG)
- Automatic format conversion
- Secure download system
- Image metadata tracking
- Creation history

### Advanced Security
- Role-based access control (User/Admin/Superadmin)
- Secure API key management
- Rate limiting protection
- First-user superadmin privileges
- User account management
- Activity monitoring

### Email System
- Support for both SMTP and Amazon SES
- HTML email templates
- Welcome emails for new users
- Password reset functionality with OTP
- Test email functionality
- Email service status monitoring

### User Management
- User registration with approval system
- Role management (User/Admin/Superadmin)
- Account status control
- Password reset with email verification
- User search functionality
- Bulk user management

## Tech Stack

### Backend
- Python 3.12+
- Flask Web Framework
- SQLAlchemy ORM
- Flask-Login for authentication
- Flask-Limiter for rate limiting
- Boto3 for AWS services
- Multiple AI provider SDKs

### Frontend
- HTML5/CSS3
- JavaScript (ES6+)
- DaisyUI components
- Tailwind CSS
- GSAP animations
- Responsive design

### Database
- SQLite (development)
- PostgreSQL (production ready)

### Email Services
- SMTP support
- Amazon SES integration
- HTML email templates
- Email queue management

### Security
- Rate limiting
- Secure password hashing
- Role-based access control
- API key management

### Development Tools
- Python virtual environment
- Git version control
- VSCode integration


## Installation

1. Clone the repository:
```bash
git clone https://github.com/marketcalls/sketchmaker.git
cd sketchmaker
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Initialize the database:
```bash
flask shell
>>> from app import db
>>> db.create_all()
>>> exit()
```

5. Run the application:
```bash
python app.py
```

## Configuration

### Required API Keys
Configure these in the admin settings after first login:
- OpenAI , Anthropic , Google Gemini , Groq API key (configure any one)
- FAL API key

### Email Configuration
Configure either SMTP or Amazon SES:

#### SMTP Settings
- SMTP Host
- SMTP Port
- SMTP Username
- SMTP Password
- TLS Support

#### Amazon SES Settings
- AWS Access Key
- AWS Secret Key
- AWS Region

## Usage Guide

1. Initial Setup:
   - Register first user (becomes superadmin)
   - Configure API keys in settings
   - Set up email service
   - Select preferred AI provider

2. Content Generation:
   - Create banners with custom styles
   - Generate images with various models
   - Train custom models
   - Manage gallery content

3. Admin Functions:
   - Manage users and roles
   - Configure email settings
   - Monitor system settings
   - Track user activity

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the AGPL v3.0 License - see the [LICENSE](LICENSE) file for details.

## Author

[marketcalls](https://github.com/marketcalls)

## Credits

### Icons and Images
- Favicon and logo: [Sketch book icons created by RA_IC0N21 - Flaticon](https://www.flaticon.com/free-icons/sketch-book)
