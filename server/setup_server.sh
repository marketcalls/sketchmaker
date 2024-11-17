#!/bin/bash

# Function to validate domain name format (including subdomains)
validate_domain() {
    if [[ $1 =~ ^([a-zA-Z0-9]([-a-zA-Z0-9]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$ ]]; then
        return 0
    else
        return 1
    fi
}

# Function to check and install packages
install_package() {
    if ! dpkg -l | grep -q "^ii  $1 "; then
        echo "Installing $1..."
        apt-get install -y "$1"
        if [ $? -ne 0 ]; then
            echo "Failed to install $1. Exiting..."
            exit 1
        fi
        echo "$1 installed successfully!"
    else
        echo "$1 is already installed."
    fi
}

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Ask for server name at the start
while true; do
    read -p "Enter your domain name (e.g., example.com or sub.example.com): " server_name
    if validate_domain "$server_name"; then
        break
    else
        echo "Invalid domain format. Please enter a valid domain name (e.g., example.com or sub.example.com)"
    fi
done

echo "Starting installation for domain: $server_name"

# Update package lists
echo "Updating package lists..."
apt-get update

# Install required packages
echo "Installing required packages..."
install_package "software-properties-common"
install_package "python3-pip"
install_package "python3-venv"
install_package "git"

# Install nginx if not present
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    # Add nginx stable repository
    add-apt-repository -y ppa:nginx/stable
    apt-get update
    install_package "nginx"
    
    # Create nginx directories if they don't exist
    mkdir -p /etc/nginx/sites-available
    mkdir -p /etc/nginx/sites-enabled
    mkdir -p /var/www/html
    
    # Create basic nginx.conf if it doesn't exist
    if [ ! -f "/etc/nginx/nginx.conf" ]; then
        cat > "/etc/nginx/nginx.conf" <<EOF
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 768;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    gzip on;

    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
EOF
    fi
fi

# Install certbot and nginx plugin
echo "Installing certbot and nginx plugin..."
if ! command -v certbot &> /dev/null; then
    # Add certbot repository
    add-apt-repository -y ppa:certbot/certbot
    apt-get update
    install_package "certbot"
    install_package "python3-certbot-nginx"
fi

# Create application directory and set it up
echo "Setting up application directory..."
mkdir -p /var/python/sketchmaker
cd /var/python/sketchmaker

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Clone repository
echo "Cloning repository..."
git clone https://github.com/marketcalls/sketchmaker
cd sketchmaker

# Configure git
git config --global --add safe.directory /var/python/sketchmaker/sketchmaker

# Set up environment file
cp .env.sample .env
# You might want to modify .env file here if needed
# sed -i 's/OLD_VALUE/NEW_VALUE/g' .env

# Make scripts executable and run them
chmod +x prestart.sh check_permissions.sh
./prestart.sh
./check_permissions.sh

# Install Python dependencies
pip install -r requirements.txt
pip install gunicorn eventlet

# Create necessary directories
mkdir -p /etc/nginx/sites-available
mkdir -p /etc/nginx/sites-enabled
mkdir -p /etc/systemd/system
mkdir -p /var/log/gunicorn

# First, create a basic nginx config for domain validation
cat > "/etc/nginx/sites-available/sketchmaker" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $server_name;
    root /var/www/html;
    
    location / {
        try_files \$uri \$uri/ =404;
    }
}
EOF

# Create symbolic link if it doesn't exist
if [ ! -L "/etc/nginx/sites-enabled/sketchmaker" ]; then
    ln -s "/etc/nginx/sites-available/sketchmaker" "/etc/nginx/sites-enabled/sketchmaker"
fi

# Remove default nginx site if it exists
if [ -L "/etc/nginx/sites-enabled/default" ]; then
    rm "/etc/nginx/sites-enabled/default"
fi

# Test nginx configuration and reload
nginx -t
if [ $? -eq 0 ]; then
    systemctl reload nginx
else
    echo "Nginx configuration test failed. Please check the configuration."
    exit 1
fi

# Obtain SSL certificate
echo "Obtaining SSL certificate for $server_name..."
certbot --nginx -d $server_name --non-interactive --agree-tos --email admin@${server_name#*.}

# Now update nginx config with full configuration including SSL
cp "$(dirname "$0")/sketchmaker" "/etc/nginx/sites-available/sketchmaker"
sed -i "s/server_name .*/server_name $server_name;/g" "/etc/nginx/sites-available/sketchmaker"

# Update SSL certificate paths in nginx config
sed -i "s|ssl_certificate .*|ssl_certificate /etc/letsencrypt/live/$server_name/fullchain.pem;|g" "/etc/nginx/sites-available/sketchmaker"
sed -i "s|ssl_certificate_key .*|ssl_certificate_key /etc/letsencrypt/live/$server_name/privkey.pem;|g" "/etc/nginx/sites-available/sketchmaker"

# Copy and configure systemd service
cat > "/etc/systemd/system/sketchmaker.service" <<EOF
[Unit]
Description=Sketchmaker Gunicorn Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/python/sketchmaker/sketchmaker
Environment="PATH=/var/python/sketchmaker/venv/bin"
ExecStart=/var/python/sketchmaker/venv/bin/gunicorn \
    --workers 2 \
    --threads 2 \
    --worker-class=gthread \
    --worker-connections=1000 \
    --bind unix:/var/python/sketchmaker/sketchmaker/sketchmaker.sock \
    --timeout 300 \
    --graceful-timeout 300 \
    --keep-alive 300 \
    --log-file=/var/log/gunicorn/gunicorn.error.log \
    --access-logfile=/var/log/gunicorn/gunicorn.access.log \
    --capture-output \
    app:app

Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# Set proper permissions
chown -R www-data:www-data /var/log/gunicorn
chmod -R 755 /var/log/gunicorn
chown -R www-data:www-data /var/python/sketchmaker

# Configure UFW if it's active
if command -v ufw >/dev/null 2>&1; then
    ufw allow 'Nginx Full'
    ufw allow OpenSSH
fi

# Setup auto-renewal for SSL certificate
echo "0 0 * * * root certbot renew --quiet" > /etc/cron.d/certbot-renewal

# Reload and start services
systemctl daemon-reload
systemctl enable sketchmaker
systemctl start sketchmaker
nginx -t && systemctl restart nginx

echo "Setup completed successfully!"
echo "Your server is configured with domain: $server_name"
echo "SSL certificate has been installed and auto-renewal has been configured"
echo "Please ensure your DNS is properly configured to point to this server"
echo "You can test your SSL setup at https://www.ssllabs.com/ssltest/analyze.html?d=$server_name"

# Display service status
echo -e "\nChecking service status:"
systemctl status sketchmaker --no-pager
systemctl status nginx --no-pager

# Display some helpful information
echo -e "\nUseful commands:"
echo "- Check gunicorn logs: tail -f /var/log/gunicorn/gunicorn.error.log"
echo "- Check nginx logs: tail -f /var/nginx/error.log"
echo "- Restart services: sudo systemctl restart sketchmaker nginx"
echo "- Check service status: sudo systemctl status sketchmaker nginx"
