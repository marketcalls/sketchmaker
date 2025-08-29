# Sketch Maker AI

A sophisticated web application that leverages multiple AI providers and models to generate artwork, banners, and custom visual content from text descriptions. Features include custom model training, multiple format support, and a comprehensive gallery system.

![SketchMaker AI Dashboard](https://marketcalls.in/wp-content/uploads/2024/11/SketchMaker-AI.webp)

## 🚀 Core Features

### 🤖 Multi-Provider AI Support
- **OpenAI**: GPT-5, GPT-5 Mini, GPT-5 Nano (Latest generation models)
- **OpenAI Legacy**: GPT-4.1, GPT-4.1 Mini, GPT-4.1 Nano
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

### 🎯 Nano Studio - Revolutionary AI Image Manipulation
**Powered by Google Gemini 2.5 Flash Image (Nano Banana)**

Nano Studio represents the cutting edge of AI image manipulation, offering unprecedented control and quality through seven specialized modes:

#### 🎬 **Director Mode** - Sequential Editing with Version Control
- Chain multiple edits while maintaining perfect consistency
- Visual timeline with edit history thumbnails
- Branch different edit paths and rollback to any point
- Perfect for iterative creative workflows

#### 🔮 **3D Vision Mode** - Multi-View Generation
- Generate 360° turntable views from a single image
- Create character sheets with multiple poses
- Product visualization from different angles
- "Show me the back" feature with accurate physics understanding

#### 📚 **Story Mode** - Comic Strip & Narrative Creation
- Automatic 4-6 panel comic generation
- Perfect character consistency across all panels
- Story progression with narrative understanding
- Add speech bubbles and visual effects

#### 🎨 **Style Transfer Mode** - Advanced Artistic Transformations
- Transform images into any artistic style (anime, oil painting, sketch, etc.)
- Mix multiple styles with precise control sliders
- Preserve specific elements while styling others
- Material changes (glass, metal, wood, ice transformations)

#### 🔧 **Restoration Mode** - Fix and Enhance Photos
- Automatic damage and tear repair
- Intelligent colorization of black & white photos
- Upscale and enhance detail quality
- Remove artifacts and noise while preserving authenticity

#### 💼 **Professional Mode** - Content Creation Tools
- YouTube thumbnail generation with smart templates
- Instant background removal and replacement
- Edit text within existing images
- Brand asset and social media content generation

#### ⚡ **Physics Mode** - Realistic Effects & Simulations
- Add physically accurate reflections and shadows
- Weather effects (rain, snow, lightning)
- Liquid and particle simulations
- Time progression effects (aging, decay, growth)

**Key Advantages of Nano Studio:**
- **Perfect Physics Understanding**: Accurately predicts reflections, shadows, and physical interactions
- **Character Consistency**: Maintains exact character features across multiple edits
- **3D Understanding**: Can rotate objects and show different angles accurately
- **Style Preservation**: Maintains original image style when adding new elements
- **Batch Processing**: Handle multiple images simultaneously
- **Real-time Progress**: Visual progress tracking with descriptive updates

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

### 📱 Responsive Design & Mobile Experience
- **Mobile-First Architecture**: Optimized for phones, tablets, and desktops
- **Responsive Navigation**: Slide-out drawer menu for mobile devices
- **Adaptive Tables**: Intelligent column hiding and dropdown actions on small screens
- **Touch-Friendly Interface**: Larger tap targets and optimized spacing
- **Responsive Forms**: Single-column layouts on mobile, multi-column on desktop
- **Smart Typography**: Fluid text sizing across all breakpoints
- **Optimized Modals**: Full-screen modals on mobile for better usability
- **Progressive Enhancement**: Enhanced features for larger screens

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
- **Responsive Design**: Mobile-first approach with breakpoints at sm (640px), md (768px), lg (1024px)

### Infrastructure
- **Rate Limiting**: Flask-Limiter
- **Migrations**: Alembic
- **Environment**: python-dotenv
- **File Storage**: Local filesystem with multi-format support

## 🎯 Using Nano Studio

### Accessing Nano Studio
1. Navigate to `/magix` in your Sketch Maker application
2. Or click on "Nano Studio" from the dashboard

### Quick Start Guide

1. **Select a Mode**: Choose from the 7 available modes based on your needs
2. **Upload Image(s)**: Drag and drop or click to upload (supports batch processing)
3. **Enter Prompt**: Describe what you want to create or modify
4. **Adjust Settings** (Optional):
   - Temperature: Controls creativity (0-2)
   - Number of images: Generate multiple variations (1-4)
   - Seed: For reproducible results
5. **Generate**: Click the Generate button and watch the real-time progress
6. **Download or Continue**: Save your results or use them as input for further editing

### Example Prompts by Mode

**Director Mode:**
- "First add a sunset, then add birds flying, finally add a lighthouse"
- "Remove the person, then change the sky to night, then add stars"

**3D Vision Mode:**
- "Show this product from 5 different angles"
- "Create a character sheet with front, side, and back views"
- "Rotate this object 180 degrees"

**Story Mode:**
- "Create a 4-panel comic about a cat's adventure"
- "Show this character's day from morning to night"

**Style Transfer Mode:**
- "Convert this to anime style"
- "Make it look like an oil painting"
- "Transform to pixel art"

**Restoration Mode:**
- "Repair all damage and colorize this old photo"
- "Remove scratches and enhance details"
- "Upscale and improve quality"

**Professional Mode:**
- "Create a YouTube thumbnail with dramatic text"
- "Remove background and add professional gradient"
- "Change the text to say 'HUGE NEWS'"

**Physics Mode:**
- "Add realistic water reflection"
- "Make it rain with proper physics"
- "Add fire effect with smoke"

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