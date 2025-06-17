# Sketch Maker AI

A sophisticated web application that leverages multiple AI providers and models to generate artwork, banners, and custom visual content from text descriptions. Features include custom model training, multiple format support, and a comprehensive gallery system.

![SketchMaker AI Dashboard](https://marketcalls.in/wp-content/uploads/2024/11/SketchMaker-AI.webp)

## 🚀 Core Features

### 🤖 Multi-Provider AI Support
- **OpenAI**: GPT-4.1, GPT-4.1 Mini, GPT-4.1 Nano (Latest models)
- **Anthropic**: Claude Opus 4, Sonnet 4, Haiku 3.5 (June 2025 versions)
- **Google Gemini**: Gemini 2.5 Pro, Flash, Flash Lite Preview
- **Groq**: Compound Beta, Llama 3.3 70B Versatile, and more

![AI Generated Social Media Expert](https://marketcalls.in/wp-content/uploads/2024/08/The-Social-Media-Expert.png)

### 🎨 Advanced Image Generation
- **Multiple Models**:
  - Flux Pro v1.1 & v1.1 Ultra (High-quality generation)
  - Flux LoRA (Custom style training)
  - Flux Dev & Realism
  - Ideogram v2 & v2a
  - Recraft V3 (Advanced style control)
- **Format Support**: PNG, WebP, JPEG with automatic conversion
- **Advanced Controls**: Resolution, style, inference steps, guidance scale
- **Batch Generation**: Multiple images per request

### 🖼️ Image Magix (AI Inpainting)
- Interactive image editing with AI-powered generation
- Draw and mask specific areas for targeted modifications
- Real-time canvas interface with undo/redo functionality
- Precise brush control for detailed selections
- AI-powered content generation in marked areas
- Integration with FAL's flux-pro/v1/fill model
- Support for multiple image formats (JPEG, PNG, WebP)
- Download generated results in high quality

### 🎯 Banner Generation
- SVG banner creation with precise control
- Multiple style presets (modern, minimalist, artistic, corporate, playful, tech, elegant)
- Dynamic text alignment and positioning
- Automatic viewBox and preserveAspectRatio handling
- Support for gradients, patterns, and effects
- Auto-conversion to PNG, WebP, JPEG formats

![AI Generated Banner](https://marketcalls.in/wp-content/uploads/2024/08/Converge-2024.jpg)

### 🎓 Custom LoRA Training
- Upload 5-20 images for custom style training
- Automatic mask generation
- Real-time training progress monitoring
- Webhook integration for status updates
- Training history management
- Easy access to trained model files
- Trigger word management for custom styles


### 💎 Subscription Management System
- **Credit-Based System**: Monthly credit allocations
- **Three-tier Plans**:
  - **Free**: 10 credits/month, basic features
  - **Premium**: 100 credits/month, all models, LoRA training
  - **Pro**: 1000 credits/month, API access, priority support
- **Personalized Reset Dates**: Credits reset based on subscription start date
- **Automatic Scheduling**: APScheduler handles all credit resets
- **Usage Tracking**: Complete audit trail with metadata
- **Admin Controls**: Plan assignment, credit modification, reports

### 🔐 Advanced Security & Authentication
- **Multiple Auth Methods**:
  - Username/password authentication
  - Google OAuth integration
  - OTP-based password reset
- **Role-Based Access**:
  - Regular users
  - Admins
  - Superadmins
- **Security Features**:
  - Encrypted API key storage (Fernet encryption)
  - Rate limiting protection
  - CSRF protection
  - Secure password hashing
  - User approval system

### 👨‍💼 Comprehensive Admin Panel
- **User Management**: Role assignment, approval system, activity monitoring
- **API Management**: 
  - Centralized encrypted API key configuration
  - Dynamic model management (add/update/remove models)
  - Default provider/model selection
  - API health monitoring
- **Subscription Controls**: Plan management, credit adjustments, usage analytics
- **System Configuration**: Email settings, authentication controls, rate limits

![AI Generated Thumbnail](https://marketcalls.in/wp-content/uploads/2024/08/thumbnail-1.png)

### 📧 Email System
- Support for both SMTP and Amazon SES
- HTML email templates
- Welcome emails for new users
- Password reset functionality with OTP
- Test email functionality
- Email service status monitoring

### 🖼️ Gallery & Asset Management
- Personal image galleries
- Public gallery view
- Multiple format support (WebP, PNG, JPEG)
- Automatic format conversion
- Secure download system
- Image metadata tracking
- Creation history

![AI Generated Art](https://marketcalls.in/wp-content/uploads/2024/08/bannana.jpeg)

## 🛠️ Tech Stack

### Backend
- **Framework**: Flask 3.0.3
- **Database**: SQLAlchemy with SQLite/PostgreSQL support
- **Authentication**: Flask-Login, OAuth 2.0
- **Task Scheduling**: APScheduler
- **Encryption**: Cryptography (Fernet)
- **API Clients**: OpenAI, Anthropic, Google Generative AI, Groq, FAL

### Frontend
- **CSS Framework**: Tailwind CSS with DaisyUI components
- **JavaScript**: Vanilla ES6+ with modular architecture
- **Canvas**: Fabric.js for image editing
- **Animations**: GSAP
- **Image Processing**: Pillow, CairoSVG

### Infrastructure
- **Rate Limiting**: Flask-Limiter
- **Migrations**: Alembic
- **Environment**: python-dotenv
- **File Storage**: Local filesystem with multi-format support

## 📋 Installation

### Prerequisites
- Python 3.12+
- pip (Python package manager)
- Virtual environment (recommended)

### Step-by-Step Installation

1. **Clone the repository**:
```bash
git clone https://github.com/marketcalls/sketchmaker.git
cd sketchmaker
```

2. **Create and activate virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Initialize the database**:
```bash
# Automated setup (recommended)
python setup_subscriptions.py

# This will:
# - Create all database tables
# - Initialize default subscription plans
# - Assign free plans to existing users
# - Set up the credit reset scheduler
```

5. **Run the application**:
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## ⚙️ Configuration

### Initial Setup (First User = Superadmin)
The first user to register automatically becomes the superadmin with full system access.

### 🔑 API Configuration (Admin Only)
Administrators configure API keys centrally for all users:

1. Login as admin
2. Navigate to **Admin → API Key Management**
3. Configure required keys:
   - **FAL API Key** (required for image generation)
   - At least one AI provider key:
     - OpenAI API Key
     - Anthropic API Key
     - Google Gemini API Key
     - Groq API Key
4. Select default provider and model
5. Test each API connection

### 🤖 Model Management (NEW)
Admins can dynamically manage AI models without code changes:

1. Navigate to **Admin → API Key Management → Manage Models**
2. **Add New Models**: Click "Add Model" and fill in:
   - Model name (e.g., "gpt-4.1")
   - Display name and description
   - Provider selection
   - Context window size
   - Mark as "latest" if applicable
3. **Edit Models**: Update descriptions, status, or ordering
4. **Remove Models**: Delete deprecated models

### 🔐 Authentication Configuration

#### Google OAuth Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create OAuth credentials
3. Add authorized redirect URIs:
   ```
   http://localhost:5000/auth/google/callback (development)
   https://your-domain.com/auth/google/callback (production)
   ```
4. Configure in admin panel:
   - Enable Google authentication
   - Add Client ID and Secret

### 📧 Email Configuration
Configure in **Admin → Email Settings**:

#### SMTP Settings
- SMTP Host (e.g., smtp.gmail.com)
- SMTP Port (e.g., 587)
- Username and Password
- TLS/SSL settings

#### Amazon SES
- AWS Access Key
- AWS Secret Key
- AWS Region

### 💳 Subscription System

#### Default Plans
| Plan | Monthly Credits | Features |
|------|----------------|----------|
| **Free** | 10 | Basic models, Standard resolution |
| **Premium** | 100 | All models, LoRA training, High resolution |
| **Pro** | 1000 | API access, Ultra-high resolution, Priority support |

#### Credit System
- **Simple model**: 1 credit per image (any model/size)
- **Automatic resets**: Based on individual subscription dates
- **Real-time tracking**: Dashboard shows remaining credits
- **Usage history**: Complete audit trail

## 📖 Usage Guide

### For Users
1. **Register/Login**: Create account or login with Google
2. **Check Credits**: View remaining credits on dashboard
3. **Generate Images**: 
   - Enter prompt description
   - Select model and parameters
   - Click generate (uses 1 credit)
4. **Create Banners**: Design SVG banners with AI
5. **Edit Images**: Use Magix for inpainting
6. **Train Models**: Upload images for custom LoRA
7. **View Gallery**: Access all your creations

### For Administrators
1. **Initial Setup**:
   - Configure API keys (centralized)
   - Set up email service
   - Configure authentication methods
   - Initialize subscription plans

2. **User Management**:
   - Approve new registrations
   - Assign roles and plans
   - Monitor usage
   - Adjust credits

3. **System Monitoring**:
   - View scheduled jobs
   - Check API status
   - Generate usage reports
   - Manage models dynamically

### API Rate Limits
- Default: 60 requests per minute
- Configurable per user role
- Automatic rate limit headers

## 🚧 Troubleshooting

### Common Issues

1. **"No API keys configured"**
   - Admin must configure API keys in Admin → API Key Management

2. **"No credits remaining"**
   - Contact admin for plan upgrade or credit adjustment

3. **"Generation failed"**
   - Check if API keys are valid
   - Verify selected model is active
   - Check rate limits

4. **Database Issues**
   - Run migrations: `python setup_subscriptions.py`
   - Check database permissions

### Logs
- Application logs: Check console output
- Error logs: Stored in Flask debug mode
- API logs: Available in admin panel

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Development Guidelines
- Follow PEP 8 for Python code
- Use meaningful commit messages
- Add tests for new features
- Update documentation
- Ensure backward compatibility

## 📄 License

This project is licensed under the AGPL v3.0 License - see the [LICENSE](LICENSE) file for details.

## 👥 Author

Created and maintained by [marketcalls](https://github.com/marketcalls)

## 🙏 Credits

### Icons and Images
- Favicon and logo: [Sketch book icons created by RA_IC0N21 - Flaticon](https://www.flaticon.com/packs/design-thinking-14670943)

### AI Services
- OpenAI for GPT models
- Anthropic for Claude models
- Google for Gemini models
- Groq for Llama models
- FAL for image generation

## 📞 Support

For issues, questions, or contributions:
- Open an issue on [GitHub](https://github.com/marketcalls/sketchmaker/issues)
- Submit pull requests for improvements
- Check documentation for common solutions

---

**Note**: This application requires API keys from AI service providers. Costs are managed centrally by administrators to prevent individual user charges.