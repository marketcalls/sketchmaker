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

### 🖼️ Magix - AI Image Enhancement
- **Intelligent Context-Aware Enhancement**: Upload an image and describe modifications in natural language
- **Multiple Aspect Ratios**: Support for 10 different aspect ratios including:
  - Default (maintains original), 21:9, 16:9, 4:3, 3:2, 1:1, 2:3, 3:4, 9:16, 9:21
- **Advanced Controls**:
  - Adjustable guidance scale (1-10) for prompt adherence control
  - Seed support for reproducible results
  - Real-time generation progress tracking
- **Smart AI Understanding**: 
  - Recognizes objects and spatial relationships in your image
  - Seamlessly blends new elements while maintaining style consistency
  - Understands complex prompts like "add a sunset", "place a donut next to the flour", etc.
- **Professional UI**: Large image preview with side-by-side comparison
- **Multiple format support**: JPEG, PNG, WebP (up to 25MB)
- **High-quality downloads**: Export enhanced images in original quality
- **Gallery Integration**: All generated images automatically saved to your personal gallery with prompts
- **Powered by**: Latest Flux Pro Kontext model for superior results

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
- **Credit-Based System**: Monthly credit allocations with dynamic cost configuration
- **Automatic Free Plan Assignment**: New users automatically enrolled in Free Plan
- **Three-tier Plans**:
  - **Free**: 3 credits/month, basic features (auto-assigned to new users)
  - **Premium**: 100 credits/month, all models, LoRA training
  - **Professional**: 1000 credits/month, API access, priority support
- **Dynamic Credit Costs**: Administrators can configure credit costs per feature
- **Personalized Reset Dates**: Credits reset based on subscription start date
- **Automatic Scheduling**: APScheduler handles all credit resets
- **Usage Tracking**: Complete audit trail with metadata
- **Admin Controls**: Plan assignment, credit modification, reports, dynamic cost configuration

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
- **Dynamic Credit Configuration**: Real-time credit cost adjustments per feature
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
| **Free** | 3 | Basic models, Standard resolution |
| **Premium** | 100 | All models, LoRA training, High resolution |
| **Professional** | 1000 | API access, Ultra-high resolution, Priority support |

#### Dynamic Credit System
- **Configurable Costs**: Administrators can adjust credit costs per feature
  - AI Images: Default 1 credit (configurable)
  - Banners: Default 0.5 credits (configurable)
  - Magix Edits: Default 1 credit (configurable)
  - LoRA Training: Default 40 credits (configurable)
- **Automatic resets**: Based on individual subscription dates
- **Real-time tracking**: Dashboard shows remaining credits
- **Usage history**: Complete audit trail
- **Immediate Updates**: Credit cost changes reflect instantly across all interfaces

## 📖 Usage Guide

### For Users
1. **Register/Login**: Create account or login with Google
2. **Automatic Free Plan**: Get 3 credits automatically upon registration
3. **Check Credits**: View remaining credits on dashboard
4. **Generate Images**: 
   - Enter prompt description
   - Select model and parameters
   - Click generate (uses 1 credit)
5. **Create Banners**: Design SVG banners with AI (uses 0.5 credits)
6. **Edit Images**: Use Magix for inpainting (uses 1 credit)
7. **Train Models**: Upload images for custom LoRA (uses 40 credits)
8. **View Gallery**: Access all your creations

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
   - Configure dynamic credit costs

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