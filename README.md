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

### Subscription Management System
- **Admin-managed subscriptions**: No external payment gateways required
- **Three-tier system**: Free (10), Premium (100), Pro (1000) monthly credits
- **Credit-based usage**: 1 credit per image generation
- **Personalized reset schedule**: Credits reset monthly based on individual subscription start dates
- **Automatic scheduling**: APScheduler handles all credit resets without manual intervention
- **Usage tracking**: Complete audit trail of all activities with detailed metadata
- **Admin controls**: Plan assignment, credit modification, usage reports, job monitoring
- **Real-time monitoring**: Dashboard shows remaining credits, plan status, and next reset date

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
- APScheduler for background tasks
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

4. Initialize the database and subscription system:
```bash
# Option 1: Use the automated setup script (recommended)
python setup_subscriptions.py

# Option 2: Manual setup
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

### Required API Keys (Admin Only)
Administrators configure these centrally for all users:
- **AI Providers**: OpenAI, Anthropic, Google Gemini, or Groq API key (at least one required)
- **Image Generation**: FAL API key (required for all image features)
- **Cost Control**: Centralized management prevents individual API key costs

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

### Subscription System Configuration

#### Initial Setup
The subscription system is automatically configured when you run the setup script:

```bash
python setup_subscriptions.py
```

This script will:
1. Create necessary database tables
2. Initialize default subscription plans (Free, Premium, Pro)
3. Assign free plans to all existing users
4. Display setup summary and statistics

#### Default Subscription Plans

| Plan | Monthly Credits | Features |
|------|----------------|----------|
| **Free** | 10 credits | Basic models, Standard resolution, Community support |
| **Premium** | 100 credits | All models, High resolution, Priority support, Custom LoRA training |
| **Pro** | 1000 credits | All models, Ultra-high resolution, Dedicated support, API access |

#### Automatic Credit Reset System
The subscription system uses APScheduler for intelligent, personalized credit management:

**How It Works:**
- Each user's credits reset monthly based on their individual subscription start date
- If you subscribe on January 15th, your credits reset on the 15th of every month
- APScheduler runs as a background service within the Flask application
- No external cron jobs or server configuration required

**Key Benefits:**
- **Fair allocation**: Users get their full monthly allowance regardless of when they join
- **Zero maintenance**: Completely automatic with no admin intervention needed
- **Precise scheduling**: Handles edge cases like month-end dates (Jan 31 → Feb 28)
- **Persistent**: Survives application restarts and continues scheduling
- **Transparent**: Users see exact reset dates and countdown on their dashboard

**Admin Features:**
- Monitor all scheduled resets via the admin panel
- Force manual credit reset for any user if needed
- View upcoming reset schedule with exact dates and times
- Automatic scheduling when assigning new subscription plans

#### Admin Management

**Access Subscription Management:**
1. Login as admin/superadmin
2. Navigate to **Admin → Manage Subscriptions**

**Assign Subscription Plans:**
1. Go to subscription management page
2. Click "Change Plan" for any user
3. Select desired plan and add optional notes
4. Click "Assign Plan"

**Modify User Credits:**
1. Click "Modify Credits" for any user
2. Choose to "Add Credits" or "Set Credits To" a specific amount
3. Enter the credit amount
4. Click "Update Credits"

**View Usage Reports:**
1. Click "View Reports" from subscription management
2. Review plan distribution and top users
3. Export reports as CSV for external analysis

**Manage Subscription Plans:**
1. Go to **Admin → Manage Subscriptions → Manage Plans**
2. Edit existing plans (credits, features, descriptions)
3. Add new custom plans
4. Activate/deactivate plans as needed

**Monitor Scheduled Jobs:**
1. Go to **Admin → Manage Subscriptions → Scheduled Jobs**
2. View all upcoming credit resets
3. See exact reset dates and times for each user
4. Force manual credit reset if needed

#### User Experience

**Dashboard Display:**
- Current plan and remaining credits prominently displayed
- Progress bar shows monthly usage with visual indicators
- Complete list of plan features and benefits
- **Personalized reset information**: "Next reset: February 15, 2025" and "Days until reset: 12"
- Real-time credit updates after each generation

**Credit Usage:**
- **Simple model**: 1 credit per image generated (regardless of model or complexity)
- Credits deducted immediately after successful generation
- Real-time credit balance updates in the UI
- Users prevented from generating when credits are exhausted
- Clear error messages guide users to contact admin for plan upgrades

**Usage Tracking & Analytics:**
- Complete audit trail of all credit usage with timestamps
- Detailed metadata for each action (model used, prompt, generation parameters)
- Monthly usage statistics and patterns
- Admin can view individual user usage history and trends
- Automatic logging of credit resets and manual adjustments

## Usage Guide

1. Initial Setup:
   - Register first user (becomes superadmin)
   - Run subscription setup: `python setup_subscriptions.py`
   - **Configure API keys via Admin → API Key Management** (admin only)
   - Set up email service
   - Configure authentication methods
   - Set up Google OAuth (if needed)
   - Credit resets are automatically scheduled (no additional setup needed)

2. Content Generation:
   - Check credit balance on dashboard
   - Create banners with custom styles
   - Generate images with various models (uses credits)
   - Use Image Magix for targeted edits
   - Train custom models
   - Manage gallery content

3. Admin Functions:
   - Manage users and roles
   - **Configure API keys centrally for all users**
   - **Assign subscription plans to users**
   - **Monitor credit usage and generate reports**
   - **Modify user credits manually**
   - Configure email settings
   - Configure authentication settings
   - Monitor system settings
   - Track user activity

4. Subscription Management:
   - **Users**: View plan status and remaining credits with personalized reset dates
   - **Admins**: Assign plans, modify credits, view usage reports, monitor scheduled jobs
   - **System**: Automatic personalized credit resets via APScheduler

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
