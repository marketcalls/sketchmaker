# Sketch Maker AI

A sophisticated web application that leverages multiple AI providers and models to generate artwork, banners, and custom visual content from text descriptions. Features include custom model training, multiple format support, and a comprehensive gallery system.

🎨 **Try it Live**: [https://sketch.marketcalls.in/](https://sketch.marketcalls.in/)

![SketchMaker AI Dashboard](https://marketcalls.in/wp-content/uploads/2024/11/SketchMaker-AI.webp)

## 🚀 Core Features

### 👗 Virtual Try-On
- AI-powered clothing visualization on your photos
- Dual image upload system (person + clothing)
- Intelligent fitting and pose adaptation
- Background transfer options
- Custom styling instructions
- Multiple variation generation

### 🤖 Multi-Provider AI Support (Powered by LiteLLM)
Unified AI gateway supporting 100+ LLM providers through [LiteLLM](https://github.com/BerriAI/litellm):

- **OpenAI**: GPT-5.1, GPT-5, GPT-5 Mini, O4 Mini, O3, GPT-OSS (Open Source)
- **Anthropic**: Claude Opus 4.5, Sonnet 4.5, Haiku 4.5 (December 2025 versions)
- **Google Gemini**: Gemini 3 Pro, Gemini 3 Flash, Gemini 3 Deep Think, Gemini 2.5
- **Groq**: Compound Beta, GPT-OSS, Kimi K2 (Moonshot), Qwen 3 32B, Llama 3.3
- **xAI (Grok)**: Grok 3, Grok 2 with web search support
- **Cerebras**: Qwen3 Coder 480B, Llama 4 Maverick (2,500+ tokens/sec)
- **OpenRouter**: Access 500+ models through a single API key

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

### 👗 Virtual Try-On - AI-Powered Fashion Visualization
**Experience clothes before you buy them with cutting-edge AI technology**

Virtual Try-On revolutionizes online shopping by allowing users to see themselves wearing any clothing item instantly. Simply upload your photo and an image of the clothing to see a realistic visualization.

#### Key Features:
- **Dual Image Upload**: Upload your photo and the clothing item separately
- **Intelligent Fitting**: AI automatically adjusts the clothing to fit your body shape and pose
- **Background Options**: Choose to keep your original background or use the clothing image's setting
- **Custom Instructions**: Add specific instructions for styling, fit adjustments, or accessories
- **Multiple Variations**: Generate up to 4 different styling variations
- **High-Quality Results**: Photorealistic rendering with proper lighting and shadows

#### How It Works:
1. Navigate to `/virtual` or click "Virtual" in the navigation menu
2. Upload your full-body photo (works best with clear, well-lit images)
3. Upload the clothing/dress image (product photos on clean backgrounds work best)
4. Optional: Add custom instructions like "make it fit perfectly" or "add matching accessories"
5. Optional: Enable "Use dress background" to place yourself in the clothing photo's environment
6. Click "Try On Dress" and wait 30-60 seconds for AI processing
7. Download or save your virtual try-on results

#### Perfect For:
- **E-commerce**: Preview clothes before purchasing
- **Fashion Design**: Visualize designs on different body types
- **Personal Styling**: Experiment with different looks
- **Social Media**: Create fashion content without physical photoshoots
- **Virtual Wardrobes**: Build digital clothing collections

### 📸 Magix - AI Photography Studio
**Powered by Google's Nano Banana Pro with 2000+ Word Prompts**

Magix transforms your photos into stunning professional portraits with 22 specialized photography styles. Features comprehensive prompts (400-600 words each) leveraging Nano Banana Pro's full capabilities, with **100% facial feature preservation**.

#### 🚀 Automatic Image Optimization
Magix includes intelligent image optimization that automatically processes images before AI manipulation:

**Key Features:**
- **Smart Compression**: Automatically reduces file sizes while maintaining visual quality
- **Dimension Optimization**: Resizes images to optimal dimensions (max 1536x1536)
- **Format Conversion**: Converts images to JPEG for optimal processing speed
- **EXIF Orientation Fix**: Automatically corrects image orientation from phone cameras
- **Progressive Loading**: Uses progressive JPEG encoding for faster web display

**Optimization Specifications:**
- **Maximum Dimensions**: 1536x1536 pixels (maintains aspect ratio)
- **Quality Level**: 90% JPEG quality for optimal balance
- **File Size Target**: Under 4MB for efficient processing
- **Resolution Options**: 1K, 2K, 4K output quality
- **Aspect Ratios**: Auto, 1:1, 4:5, 9:16, 16:9, 21:9, and more

#### ⭐ **Main Portrait Styles** (Always Visible)

| Style | Description |
|-------|-------------|
| **Studio Portrait** | Professional studio photography with clean background, soft three-point lighting, polished look |
| **Cinematic Portrait** | Movie-scene quality with dramatic lighting, shallow depth of field, atmospheric mood |
| **Corporate Headshot** | LinkedIn-ready professional headshots with clean backgrounds and executive presence |
| **Fashion Editorial** | High-fashion magazine quality with dramatic lighting and Vogue-worthy styling |
| **Influencer** | Instagram-ready photos with trendy aesthetics and scroll-stopping appeal |
| **Founder Headshot** | Pitch-deck ready photos conveying visionary leadership for startups |

#### 🎨 **Additional Portrait Styles** (16 More in Expandable Section)

- **Environmental Portrait** - Contextual portraits in meaningful real-world settings
- **Lifestyle Portrait** - Authentic, candid-feeling photos with warm atmosphere
- **Street Portrait** - Urban photography with authentic city backdrops
- **Low-Key Dramatic** - Portraits dominated by shadows with high contrast
- **High-Key Bright** - Bright, airy portraits with minimal shadows
- **Black & White** - Timeless monochrome with rich tonal range
- **Beauty Close-Up** - Professional beauty photography emphasizing facial features
- **Athletic Portrait** - Dynamic sports photography showcasing strength
- **Creative Color** - Bold artistic portraits with neon gels and vibrant colors
- **Vintage Retro** - Nostalgic film photography aesthetics (70s, 80s, Polaroid)
- **Minimalist** - Maximum impact through simplicity and negative space
- **Cultural Portrait** - Celebrating heritage with traditional styling
- **Conceptual Art** - Artistic portraits with symbolic elements
- **Luxury Elite** - Premium portraits exuding wealth and sophistication
- **Stylized Avatar** - Artistic character transformation (3D, anime, comic)
- **Photo Restoration** - Enhance and restore image quality

#### 🎯 **100% Facial Feature Preservation**
Every prompt includes comprehensive facial preservation instructions:
- Exact face shape and bone structure
- Eye shape, color, size, and spacing
- Nose and mouth shape
- Eyebrow shape and position
- Skin texture and natural marks
- Hairline shape
- Overall facial proportions

#### 🛠️ **Mode-Specific Controls**
- **Corporate**: Background style (neutral, white, gradient, office blur)
- **Influencer**: Aesthetic (glamorous, natural, golden hour, urban chic)
- **Founder**: Leadership vibe (visionary, approachable CEO, tech innovator)
- **Avatar**: Style (semi-realistic, 3D Pixar, anime, comic book, fantasy)

#### ✨ **Key Features**
- **Comprehensive Prompts**: 400-600 words per mode with detailed specifications
- **Mode Description Panel**: Shows exactly what photos you'll create when selecting a style
- **Real-time Preview**: Visual progress tracking with descriptive updates
- **Batch Processing**: Handle multiple images simultaneously
- **Continue Editing**: Chain edits together for iterative workflows

### 🎯 Explainer Tool - Visual Content Creation
**Create stunning infographics, diagrams, and visual explanations with AI**

Transform complex ideas into professional visual content using the Nano Banana Pro AI model with support for 2000+ word detailed prompts.

#### Content Types:
- **Concept Explainer**: Educational breakdowns of complex topics
- **Infographic**: Data visualization, statistics, timelines
- **Flowchart/Diagram**: Process flows, decision trees, architectures
- **Kids Explainer**: Child-friendly illustrations with simple language
- **Technical Diagram**: System architectures, workflows, code concepts
- **Comparison Chart**: Side-by-side comparisons, pros/cons
- **Step-by-Step Guide**: Numbered tutorials, how-to guides
- **Startup Pitchdeck**: Investor presentations, startup visuals

#### Key Features:
- **AI Prompt Enhancement**: Optional AI-powered prompt improvement for better results
- **2000+ Word Prompts**: Detailed descriptions for complex visuals
- **Multiple Visual Styles**: Professional, Vibrant, Educational, Playful, Technical, Minimalist
- **Flexible Aspect Ratios**: Square (1:1), Landscape (16:9, 4:3), Portrait (9:16), Ultra-wide (21:9)
- **Resolution Options**: 1K, 2K, 4K output quality
- **Multiple Formats**: PNG, JPEG, WebP export

![AI Generated Infographic](https://marketcalls.in/wp-content/uploads/2024/08/Converge-2024.jpg)

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

### 🔒 Privacy & Data Protection
**Your Images, Your Control - Complete Privacy Guaranteed**

#### Local Storage & Processing
- **100% Self-Hosted**: All images stored on YOUR server, never on third-party clouds
- **Local Database**: Image metadata, prompts, and galleries stay in your database
- **No External Analytics**: Zero tracking, no telemetry, no data collection
- **Private Galleries**: User images are isolated and access-controlled

#### Image Privacy Features
- **Encrypted Storage**: Optional encryption for sensitive images
- **User Isolation**: Each user's images are completely separate
- **No Training on Your Data**: Your images and prompts never train external models
- **Secure Deletion**: When you delete an image, it's gone from your server permanently
- **Access Control**: Granular permissions for sharing and viewing

#### API Privacy
- **Direct API Calls**: Images sent directly to AI providers (FAL, OpenAI, etc.) for processing only
- **No Intermediaries**: No middle servers, no proxies storing your data
- **Temporary Processing**: AI providers process and immediately discard your images
- **API Key Security**: All API keys encrypted with Fernet encryption
- **Admin-Controlled**: Only admins manage API keys, users never see them

#### Compliance & Business Use
- **GDPR Ready**: Full control over data deletion and user data exports
- **Corporate Safe**: Keep proprietary designs and brand assets secure
- **NDA Compliant**: Perfect for agencies working with client materials
- **Audit Trail**: Complete logs of who accessed what and when
- **Backup Control**: You decide when and how to backup your data

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
- **AI Gateway**: LiteLLM (unified interface for 100+ LLM providers)
- **API Clients**: OpenAI, Anthropic, Google Gemini, Groq, xAI, Cerebras, OpenRouter, FAL

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

## 📸 Using Magix AI Photography Studio

### Accessing Magix
1. Navigate to `/magix` in your Sketch Maker application
2. Or click on "Magix" from the navigation menu

### Quick Start Guide

1. **Select a Portrait Style**: Choose from 6 main styles or expand "More Styles" for 16 additional options
2. **Read the Description**: The mode description panel explains exactly what photos you'll create
3. **Upload Your Photo**: Drag and drop or click to upload your image
4. **Choose Resolution & Aspect Ratio**:
   - Resolution: 1K (Standard), 2K (High Quality), 4K (Ultra HD)
   - Aspect Ratio: Auto, 1:1 (Square), 4:5 (Portrait), 9:16 (Story), 16:9 (Wide), etc.
5. **Add Custom Instructions** (Optional): Add specific details like "black background" or "outdoor setting"
6. **Generate**: Click Generate and watch real-time progress
7. **Download or Continue**: Save your results or use as input for further editing

### Example Usage by Style

**Studio Portrait:**
- Just upload - the comprehensive prompt handles everything
- Optional: "with blue gradient background" or "dramatic side lighting"

**Cinematic Portrait:**
- Optional: "teal and orange color grading" or "noir style"
- Optional: "Blade Runner aesthetic" or "moody atmospheric"

**Corporate Headshot:**
- Select background style from dropdown (neutral, white, office blur)
- Optional: "confident smile" or "professional but approachable"

**Fashion Editorial:**
- Optional: "Vogue cover style" or "high contrast dramatic"
- Optional: "bold red lips emphasis" or "avant-garde styling"

**Influencer:**
- Select aesthetic from dropdown (glamorous, natural, golden hour, etc.)
- Optional: "lifestyle cafe setting" or "outdoor golden hour"

**Founder Headshot:**
- Select leadership vibe (visionary, tech innovator, approachable CEO)
- Optional: "modern tech office background" or "startup energy"

**Black & White:**
- Optional: "high contrast dramatic" or "soft romantic"
- Optional: "Avedon style" or "classic portraiture"

**Creative Color:**
- Optional: "neon pink and blue" or "cyberpunk aesthetic"
- Optional: "split lighting with gels"

### Pro Tips
- **Facial features are automatically preserved** - no need to specify
- **Prompts are comprehensive** (400-600 words) - you only need to add specifics
- **Chain edits together** using "Continue Editing" for iterative refinement
- **Use 4K resolution** for print-quality output

## 🚀 Quick Start

### Try the Live Demo
Experience Sketch Maker AI instantly without installation:
👉 **[https://sketch.marketcalls.in/](https://sketch.marketcalls.in/)**

- Test all features with demo credits
- No installation required
- See the interface and capabilities
- Create sample images and banners

## 📋 Installation

### Prerequisites
- Python 3.12+
- pip (Python package manager)
- Virtual environment (recommended)
- Git (for cloning the repository)

### Step-by-Step Installation

1. **Clone the repository**:
```bash
git clone https://github.com/marketcalls/sketchmaker.git
cd sketchmaker
```

2. **Create and activate virtual environment**:
```bash
python -m venv venv
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Set up environment variables** (Optional - for production):
```bash
# Create .env file
cp .env.example .env  # If example exists
# Or create new .env file and add configuration
```

5. **Initialize the database**:
```bash
# Set up subscription system
python setup_subscriptions.py

# This will:
# - Create all database tables
# - Initialize default subscription plans (Free, Premium, Professional)
# - Assign free plans to existing users
# - Set up the APScheduler for automatic credit resets
```

6. **Run database migrations** (for existing installations):
```bash
cd migrations
uv run migrate_all.py
cd ..

# Or using Flask-Migrate directly:
flask db upgrade
```

This adds support for new LiteLLM providers:
- xAI (Grok)
- Cerebras
- OpenRouter

7. **Run the application**:
```bash
python app.py
```

The application will be available at `http://127.0.0.1:5000`

## ⚙️ Configuration

### Initial Setup (First User = Superadmin)
The first user to register automatically becomes the superadmin with full system access.

### 🔑 API Configuration (Admin Only)
Administrators configure API keys centrally for all users via LiteLLM:

1. Login as admin
2. Navigate to **Admin → API Key Management**
3. Configure required keys:
   - **FAL API Key** (required for image generation)
   - At least one AI provider key:
     - OpenAI API Key
     - Anthropic API Key
     - Google Gemini API Key
     - Groq API Key
     - xAI (Grok) API Key
     - Cerebras API Key
     - OpenRouter API Key
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
   http://127.0.0.1:5000/auth/google/callback (development)
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
  - Explainers: Default 1 credit (configurable)
  - Magix Edits: Default 1 credit (configurable)
  - Virtual Try-On: Default 1 credit (configurable)
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
5. **Create Explainers**: Design infographics and visual content with AI (uses 1 credit)
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

### AI Services & Infrastructure
- **[LiteLLM](https://github.com/BerriAI/litellm)** - Unified AI gateway for 100+ LLM providers (MIT License)
- OpenAI for GPT-5, O3, and GPT-OSS models
- Anthropic for Claude 4.5 models
- Google for Gemini 3 models
- Groq for ultra-fast inference
- xAI for Grok models
- Cerebras for record-breaking inference speeds
- OpenRouter for multi-model access
- FAL for image generation

## 📞 Support

For issues, questions, or contributions:
- Open an issue on [GitHub](https://github.com/marketcalls/sketchmaker/issues)
- Submit pull requests for improvements
- Check documentation for common solutions

---

**Note**: This application requires API keys from AI service providers. Costs are managed centrally by administrators to prevent individual user charges.