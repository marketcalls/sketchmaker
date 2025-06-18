# ⚙️ SketchMaker AI Installation Guide

## 🎯 Installation Overview

This comprehensive guide covers installing and configuring SketchMaker AI v1.0.0.0 from initial setup to production deployment.

## 📋 System Requirements

### **Minimum Requirements**
- **OS**: Ubuntu 20.04+, CentOS 8+, macOS 11+, Windows 10+
- **Python**: 3.8 or higher
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 10GB free space minimum
- **Network**: Internet connectivity for AI providers

### **Recommended Production Setup**
- **OS**: Ubuntu 22.04 LTS
- **Python**: 3.11+
- **RAM**: 16GB+
- **CPU**: 4+ cores
- **Storage**: 100GB+ SSD
- **Database**: PostgreSQL 13+
- **Web Server**: Nginx + Gunicorn

### **Development Requirements**
- **Git**: For cloning repository
- **Node.js**: For frontend development (optional)
- **Docker**: For containerized deployment (optional)

## 🚀 Quick Installation (Development)

### **1. Clone Repository**
```bash
git clone https://github.com/your-org/sketchmaker-ai.git
cd sketchmaker-ai/sketchmaker
```

### **2. Create Virtual Environment**
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

### **3. Install Dependencies**
```bash
# Install Python packages
pip install -r requirements.txt

# Install additional development dependencies (optional)
pip install pytest black flake8 pre-commit
```

### **4. Environment Configuration**
```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

**Basic .env Configuration**:
```env
# Basic Configuration
SECRET_KEY=your-super-secret-key-here
DEBUG=True
ENVIRONMENT=development

# Database Configuration
DB_PATH=sqlite:///sketchmaker.db

# Email Configuration (optional for development)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_USE_TLS=True

# AI Provider API Keys (add as needed)
OPENAI_API_KEY=sk-your-openai-key
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key
GOOGLE_API_KEY=your-google-api-key
GROQ_API_KEY=gsk_your-groq-key

# Rate Limiting
RATE_LIMIT_PER_MINUTE=20
RATE_LIMIT_PER_HOUR=200
RATE_LIMIT_PER_DAY=1000
```

### **5. Database Setup**
```bash
# Initialize database
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

# Create admin user (optional)
python setup_admin.py
```

### **6. Run Development Server**
```bash
# Start Flask development server
python app.py

# Or using Flask CLI
flask run --host=0.0.0.0 --port=5000
```

**Access Application**: http://localhost:5000

## 🏗️ Production Installation

### **1. System Preparation**

#### **Update System**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv nginx postgresql postgresql-contrib
```

#### **Create Application User**
```bash
sudo useradd -m -s /bin/bash sketchmaker
sudo usermod -aG sudo sketchmaker
sudo su - sketchmaker
```

### **2. Database Setup (PostgreSQL)**

#### **Install and Configure PostgreSQL**
```bash
# Create database and user
sudo -u postgres psql
```

```sql
CREATE DATABASE sketchmaker;
CREATE USER sketchmaker WITH ENCRYPTED PASSWORD 'secure-password';
GRANT ALL PRIVILEGES ON DATABASE sketchmaker TO sketchmaker;
\q
```

#### **Update Connection String**
```env
DB_PATH=postgresql://sketchmaker:secure-password@localhost/sketchmaker
```

### **3. Application Deployment**

#### **Clone and Setup**
```bash
cd /opt
sudo git clone https://github.com/your-org/sketchmaker-ai.git
sudo chown -R sketchmaker:sketchmaker sketchmaker-ai
cd sketchmaker-ai/sketchmaker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### **Production Environment Configuration**
```env
# Production .env
SECRET_KEY=generate-a-very-secure-key-here
DEBUG=False
ENVIRONMENT=production

# Database
DB_PATH=postgresql://sketchmaker:secure-password@localhost/sketchmaker

# Security
CSRF_SESSION_KEY=another-secure-key

# Email (production SMTP)
MAIL_SERVER=your-smtp-server.com
MAIL_PORT=587
MAIL_USERNAME=noreply@yourdomain.com
MAIL_PASSWORD=secure-email-password
MAIL_USE_TLS=True
MAIL_DEFAULT_SENDER=SketchMaker AI <noreply@yourdomain.com>

# AI Providers
OPENAI_API_KEY=sk-your-production-openai-key
ANTHROPIC_API_KEY=sk-ant-your-production-anthropic-key
GOOGLE_API_KEY=your-production-google-api-key
GROQ_API_KEY=gsk_your-production-groq-key

# Rate Limiting (production values)
RATE_LIMIT_PER_MINUTE=50
RATE_LIMIT_PER_HOUR=500
RATE_LIMIT_PER_DAY=5000
RATE_LIMIT_STORAGE=redis://localhost:6379
```

#### **Database Migration**
```bash
flask db upgrade
python setup_subscriptions.py
```

### **4. Web Server Configuration**

#### **Gunicorn Setup**
```bash
# Install Gunicorn
pip install gunicorn

# Create Gunicorn configuration
cat > gunicorn.conf.py << EOF
bind = "127.0.0.1:8000"
workers = 4
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 2
max_requests = 1000
max_requests_jitter = 100
preload_app = True
EOF
```

#### **Systemd Service**
```bash
sudo cat > /etc/systemd/system/sketchmaker.service << EOF
[Unit]
Description=SketchMaker AI Gunicorn process
After=network.target

[Service]
Type=notify
User=sketchmaker
Group=sketchmaker
RuntimeDirectory=sketchmaker
WorkingDirectory=/opt/sketchmaker-ai/sketchmaker
Environment=PATH=/opt/sketchmaker-ai/sketchmaker/venv/bin
ExecStart=/opt/sketchmaker-ai/sketchmaker/venv/bin/gunicorn --config gunicorn.conf.py app:app
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable sketchmaker
sudo systemctl start sketchmaker
```

#### **Nginx Configuration**
```bash
sudo cat > /etc/nginx/sites-available/sketchmaker << EOF
server {
    listen 80;
    server_name your-domain.com;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # File upload limit
    client_max_body_size 25M;
    
    # Static files
    location /static {
        alias /opt/sketchmaker-ai/sketchmaker/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Application
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120;
        proxy_connect_timeout 120;
        proxy_send_timeout 120;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/sketchmaker /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### **5. SSL/TLS Setup (Let's Encrypt)**

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

## 🐳 Docker Installation

### **1. Docker Compose Setup**

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "5000:5000"
    environment:
      - FLASK_ENV=production
      - DB_PATH=postgresql://sketchmaker:password@db:5432/sketchmaker
    depends_on:
      - db
      - redis
    volumes:
      - ./static:/app/static
      - ./instance:/app/instance
    restart: unless-stopped

  db:
    image: postgres:13
    environment:
      POSTGRES_DB: sketchmaker
      POSTGRES_USER: sketchmaker
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl
    depends_on:
      - web
    restart: unless-stopped

volumes:
  postgres_data:
```

**Dockerfile**:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
```

### **2. Build and Deploy**
```bash
# Build and start containers
docker-compose up -d

# Initialize database
docker-compose exec web flask db upgrade
docker-compose exec web python setup_subscriptions.py
```

## 🔧 Configuration Details

### **Environment Variables**

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SECRET_KEY` | Flask secret key | None | Yes |
| `DEBUG` | Debug mode | False | No |
| `DB_PATH` | Database URL | sqlite:/// | Yes |
| `MAIL_SERVER` | SMTP server | None | No |
| `OPENAI_API_KEY` | OpenAI API key | None | Recommended |
| `RATE_LIMIT_PER_MINUTE` | Rate limit | 20 | No |

### **Database Configuration**

#### **SQLite (Development)**
```env
DB_PATH=sqlite:///sketchmaker.db
```

#### **PostgreSQL (Production)**
```env
DB_PATH=postgresql://user:pass@host:port/dbname
```

#### **MySQL (Alternative)**
```env
DB_PATH=mysql://user:pass@host:port/dbname
```

### **AI Provider Setup**

#### **OpenAI Configuration**
1. Visit https://platform.openai.com/api-keys
2. Create new secret key
3. Add to environment: `OPENAI_API_KEY=sk-...`

#### **Anthropic Configuration**
1. Visit https://console.anthropic.com/
2. Generate API key
3. Add to environment: `ANTHROPIC_API_KEY=sk-ant-...`

#### **Google AI Configuration**
1. Visit https://makersuite.google.com/app/apikey
2. Create API key
3. Add to environment: `GOOGLE_API_KEY=...`

#### **Groq Configuration**
1. Visit https://console.groq.com/keys
2. Create API key
3. Add to environment: `GROQ_API_KEY=gsk_...`

## ✅ Post-Installation Setup

### **1. Create Admin User**
```bash
python -c "
from models import User, db
from app import create_app

app = create_app()
with app.app_context():
    admin = User(
        username='admin',
        email='admin@yourcompany.com',
        role='superadmin'
    )
    admin.set_password('secure-admin-password')
    db.session.add(admin)
    db.session.commit()
    print('Admin user created')
"
```

### **2. Verify Installation**
```bash
# Check service status
sudo systemctl status sketchmaker

# Check logs
sudo journalctl -u sketchmaker -f

# Test application
curl -I http://your-domain.com
```

### **3. Configure API Keys**
1. Login as admin
2. Navigate to Admin → API Key Management
3. Add API keys for each provider
4. Test connections

### **4. Set Up Monitoring**
```bash
# Install monitoring tools
pip install prometheus-flask-exporter

# Configure log rotation
sudo cat > /etc/logrotate.d/sketchmaker << EOF
/var/log/sketchmaker/*.log {
    daily
    missingok
    rotate 14
    compress
    notifempty
    create 644 sketchmaker sketchmaker
}
EOF
```

## 🔍 Troubleshooting

### **Common Issues**

#### **Database Connection Failed**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check connection
psql -h localhost -U sketchmaker -d sketchmaker
```

#### **AI Provider Connection Failed**
- Verify API keys are correct
- Check network connectivity
- Review rate limits

#### **Static Files Not Loading**
```bash
# Check file permissions
sudo chown -R sketchmaker:sketchmaker /opt/sketchmaker-ai
sudo chmod -R 755 /opt/sketchmaker-ai/sketchmaker/static
```

#### **Application Won't Start**
```bash
# Check logs
sudo journalctl -u sketchmaker -n 50

# Test manually
cd /opt/sketchmaker-ai/sketchmaker
source venv/bin/activate
python app.py
```

### **Log Locations**
- **Application**: `/var/log/sketchmaker/app.log`
- **Nginx**: `/var/log/nginx/access.log`, `/var/log/nginx/error.log`
- **Systemd**: `sudo journalctl -u sketchmaker`

---

*This installation guide covers SketchMaker AI v1.0.0.0. For updates and additional configuration options, check the documentation.*