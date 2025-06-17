# Sketch Maker AI

A sophisticated web application that leverages multiple AI providers and models to generate artwork, banners, and custom visual content from text descriptions. Features include custom model training, multiple format support, and a comprehensive gallery system.

![SketchMaker AI Dashboard](https://marketcalls.in/wp-content/uploads/2024/11/SketchMaker-AI.webp)

## Core Features

### Multi-Provider AI Support
- OpenAI: Advanced language models for prompt enhancement
- Anthropic: State-of-the-art language models with Claude capabilities
- Google Gemini: Next-generation AI with multimodal understanding
- Groq: High-performance inference with ultra-low latency

![AI Generated Social Media Expert](https://marketcalls.in/wp-content/uploads/2024/08/The-Social-Media-Expert.png)

### Image Magix
- Interactive image editing with AI-powered generation
- Draw and mask specific areas for targeted modifications
- Real-time canvas interface with undo/redo functionality
- Precise brush control for detailed selections
- AI-powered content generation in marked areas
- Integration with FAL's flux-pro/v1/fill model
- Support for multiple image formats (JPEG, PNG, WebP)
- Download generated results in high quality

### Banner Generation
- SVG banner creation with precise control
- Multiple style presets (modern, minimalist, artistic, corporate, playful, tech, elegant)
- Dynamic text alignment and positioning
- Automatic viewBox and preserveAspectRatio handling
- Support for gradients, patterns, and effects

![AI Generated Banner](https://marketcalls.in/wp-content/uploads/2024/08/Converge-2024.jpg)

### Image Generation (FAL Integration)
- Flux Pro: High-quality standard image generation
- Flux Pro Ultra: Advanced generation with aspect ratio control
- Flux Lora: Custom model training support
- Flux Dev: Development and testing environment
- Flux Realism: Enhanced photorealistic generation
- Recraft V3: Advanced style control with color customization

![AI Generated LinkedIn Headshot](https://marketcalls.in/wp-content/uploads/2024/08/0f811820-55c0-4f5d-823a-967ed102ba64.webp)

### Custom Model Training
- Support for 5-20 training images
- Automatic mask generation
- Real-time training progress monitoring
- Webhook integration for status updates
- Training history management
- Easy access to trained model files
- Trigger word management

![AI Generated Thumbnail](https://marketcalls.in/wp-content/uploads/2024/08/thumbnail-1.png)

### Gallery & Asset Management
- Personal image galleries
- Multiple format support (WebP, PNG, JPEG)
- Automatic format conversion
- Secure download system
- Image metadata tracking
- Creation history

![AI Generated Art](https://marketcalls.in/wp-content/uploads/2024/08/bannana.jpeg)

### Advanced Security
- Role-based access control (User/Admin/Superadmin)
- Secure API key management
- Rate limiting protection
- First-user superadmin privileges
- User account management
- Activity monitoring

### Authentication System
- Multiple authentication methods:
  * Regular username/password authentication
  * Google OAuth integration
  * Configurable authentication controls
- Admin authentication controls:
  * Enable/disable regular authentication
  * Enable/disable Google authentication
  * Configure Google OAuth credentials
  * Manage authentication settings through admin interface
- Google OAuth features:
  * Secure OAuth 2.0 implementation
  * Automatic account creation for new Google users
  * Account linking for existing users
  * Profile information synchronization
  * Secure callback handling
- Authentication security:
  * Password strength requirements
  * Secure password hashing
  * Rate limiting on login attempts
  * Session management
  * Account recovery options

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
- Fabric.js for canvas manipulation

![AI Generated Portrait](https://marketcalls.in/wp-content/uploads/2024/08/Man-with-a-Cat.jpg)

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

### Authentication Configuration
Configure authentication settings in the admin interface (/admin/manage/auth):

#### Regular Authentication
- Enable/disable username/password authentication
- Configure password requirements
- Manage user registration settings

#### Google OAuth Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing one
3. Configure OAuth consent screen:
   - Select "External" user type
   - Add required app information
   - Add scopes: email and profile
4. Create OAuth credentials:
   - Create OAuth client ID
   - Select "Web application"
   - Add authorized JavaScript origins:
     ```
     http://localhost:5000 (development)
     https://your-domain.com (production)
     ```
   - Add authorized redirect URIs:
     ```
     http://localhost:5000/auth/google/callback (development)
     https://your-domain.com/auth/google/callback (production)
     ```
5. Copy Client ID and Client Secret
6. Configure in admin interface:
   - Enable Google authentication
   - Add Google Client ID
   - Add Google Client Secret

### Required API Keys
Configure these in the admin settings after first login:
- OpenAI, Anthropic, Google Gemini, Groq API key (configure any one)
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
   - Configure authentication methods
   - Set up Google OAuth (if needed)
   - Select preferred AI provider

2. Content Generation:
   - Create banners with custom styles
   - Generate images with various models
   - Use Image Magix for targeted edits
   - Train custom models
   - Manage gallery content

3. Admin Functions:
   - Manage users and roles
   - Configure email settings
   - Configure authentication settings
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
- Favicon and logo: [Sketch book icons created by RA_IC0N21 - Flaticon](https://www.flaticon.com/packs/design-thinking-14670943)
