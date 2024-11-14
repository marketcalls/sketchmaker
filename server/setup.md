# Server Setup Instructions

This guide details how to deploy the Sketch Maker AI application on an Ubuntu server.

## Prerequisites

1. Ubuntu Server (20.04 LTS or newer)
2. Python 3.8+
3. Nginx
4. Git

## Initial Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3-pip python3-venv nginx git

# Create application directory
sudo mkdir -p /var/python/sketchmaker
cd /var/python/sketchmaker

# Clone repository
git clone https://github.com/yourusername/sketchmaker.git
cd sketchmaker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install gunicorn
```

## Directory Setup and Permissions

1. Run the prestart script:
```bash
chmod +x prestart.sh
sudo ./prestart.sh
```

This script will:
- Create necessary directories
- Set proper permissions
- Configure log files
- Set up SELinux contexts (if applicable)

## Environment Configuration

1. Create and edit .env file:
```bash
cp .env.sample .env
nano .env
```

2. Update the following variables:
```
SECRET_KEY=your_secure_secret_key
DB_PATH=sqlite:///instance/sketchmaker.db
```

## Gunicorn Setup

1. Create Gunicorn systemd service:
```bash
sudo nano /etc/systemd/system/sketchmaker.service
```

2. Add the following content:
```ini
[Unit]
Description=Sketchmaker Gunicorn Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/python/sketchmaker/sketchmaker
Environment="PATH=/var/python/sketchmaker/venv/bin"
ExecStart=/var/python/sketchmaker/venv/bin/gunicorn --workers 4 --bind unix:sketchmaker.sock -m 007 app:app --error-logfile /var/log/gunicorn/gunicorn.error.log --access-logfile /var/log/gunicorn/gunicorn.log

[Install]
WantedBy=multi-user.target
```

## Nginx Configuration

1. Create Nginx configuration:
```bash
sudo nano /etc/nginx/sites-available/sketchmaker
```

2. Add the following content:
```nginx
server {
    listen 80;
    server_name your_domain.com;

    location / {
        proxy_pass http://unix:/var/python/sketchmaker/sketchmaker/sketchmaker.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 32M;
    }

    location /static {
        alias /var/python/sketchmaker/sketchmaker/static;
        expires 30d;
    }
}
```

3. Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/sketchmaker /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # Remove default site if exists
```

## Database Setup

1. Initialize the database:
```bash
flask shell
>>> from app import db
>>> db.create_all()
>>> exit()
```

## Start Services

1. Start and enable Gunicorn service:
```bash
sudo systemctl start sketchmaker
sudo systemctl enable sketchmaker
```

2. Restart Nginx:
```bash
sudo systemctl restart nginx
```

## Verify Installation

1. Check service status:
```bash
sudo systemctl status sketchmaker
sudo systemctl status nginx
```

2. Check logs:
```bash
tail -f /var/log/gunicorn/gunicorn.log
tail -f /var/log/gunicorn/gunicorn.error.log
```

## Maintenance

### Updating the Application

```bash
cd /var/python/sketchmaker/sketchmaker
git pull
source ../venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart sketchmaker
```

### Log Rotation

Logs are automatically rotated by the system. To check the configuration:
```bash
cat /etc/logrotate.d/gunicorn
```

### Backup

1. Database backup:
```bash
cp /var/python/sketchmaker/sketchmaker/instance/sketchmaker.db /backup/sketchmaker_$(date +%Y%m%d).db
```

2. Generated files backup:
```bash
tar -czf /backup/sketchmaker_files_$(date +%Y%m%d).tar.gz /var/python/sketchmaker/sketchmaker/static/images /var/python/sketchmaker/sketchmaker/static/training_files
```

## Troubleshooting

1. Permission issues:
```bash
# Re-run prestart script
sudo ./prestart.sh
```

2. Socket issues:
```bash
sudo systemctl restart sketchmaker
sudo systemctl restart nginx
```

3. Log access:
```bash
# If logs are inaccessible
sudo chown -R www-data:www-data /var/log/gunicorn
sudo chmod -R 664 /var/log/gunicorn/*
