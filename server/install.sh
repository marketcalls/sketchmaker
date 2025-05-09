#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print banner
echo -e "${BLUE}"
echo "███████╗██╗  ██╗███████╗████████╗ ██████╗██╗  ██╗███╗   ███╗ █████╗ ██╗  ██╗███████╗██████╗ "
echo "██╔════╝██║ ██╔╝██╔════╝╚══██╔══╝██╔════╝██║  ██║████╗ ████║██╔══██╗██║ ██╔╝██╔════╝██╔══██╗"
echo "███████╗█████╔╝ █████╗     ██║   ██║     ███████║██╔████╔██║███████║█████╔╝ █████╗  ██████╔╝"
echo "╚════██║██╔═██╗ ██╔══╝     ██║   ██║     ██╔══██║██║╚██╔╝██║██╔══██║██╔═██╗ ██╔══╝  ██╔══██╗"
echo "███████║██║  ██╗███████╗   ██║   ╚██████╗██║  ██║██║ ╚═╝ ██║██║  ██║██║  ██╗███████╗██║  ██║"
echo "╚══════╝╚═╝  ╚═╝╚══════╝   ╚═╝    ╚═════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝"
echo -e "${NC}"

# Function to validate domain name format
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

# Function to setup directories and permissions
setup_directories_and_permissions() {
    echo "Setting up directories and permissions..."
    
    # Set variables
    APP_ROOT="/var/python/sketchmaker/sketchmaker"
    STATIC_ROOT="$APP_ROOT/static"
    LOG_DIR="/var/log/gunicorn"

    # Create all necessary directories
    mkdir -p "$STATIC_ROOT/images"
    mkdir -p "$STATIC_ROOT/uploads"
    mkdir -p "$STATIC_ROOT/training_files/uploads"
    mkdir -p "$STATIC_ROOT/training_files/models"
    mkdir -p "$STATIC_ROOT/training_files/temp"
    mkdir -p "$APP_ROOT/instance"
    mkdir -p "$LOG_DIR"

    # Create log files if they don't exist
    touch "$LOG_DIR/gunicorn.error.log"
    touch "$LOG_DIR/gunicorn.access.log"

    # Set ownership
    chown -R www-data:www-data "$APP_ROOT"
    chown -R www-data:www-data "$LOG_DIR"
    chown www-data:www-data "$LOG_DIR/gunicorn.error.log"
    chown www-data:www-data "$LOG_DIR/gunicorn.access.log"

    # Set directory permissions
    chmod 755 "$APP_ROOT"
    chmod -R 755 "$STATIC_ROOT"
    chmod -R 775 "$STATIC_ROOT/images"
    chmod -R 775 "$STATIC_ROOT/uploads"
    chmod -R 775 "$STATIC_ROOT/training_files"
    chmod -R 775 "$APP_ROOT/instance"
    chmod -R 775 "$LOG_DIR"
    chmod 664 "$LOG_DIR/gunicorn.error.log"
    chmod 664 "$LOG_DIR/gunicorn.access.log"

    # Set app root permissions - 755 for directories 644 for files
    find "$APP_ROOT" -type d -exec chmod 755 {} \;
    find "$APP_ROOT" -type f -exec chmod 644 {} \;

    echo "Directory setup completed."
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# Get domain name
while true; do
    echo -e "${GREEN}Please enter your domain name for the installation:${NC}"
    read -p "Domain (e.g., example.com or sub.example.com): " server_name
    
    if [ -z "$server_name" ]; then
        echo -e "${RED}Domain name cannot be empty${NC}"
        continue
    fi
    
    if validate_domain "$server_name"; then
        break
    else
        echo -e "${RED}Invalid domain format. Please enter a valid domain name.${NC}"
    fi
done

echo -e "${GREEN}Starting installation for domain: $server_name${NC}"

# Update package lists
echo "Updating package lists..."
apt-get update

# Install required packages
echo "Installing required packages..."
install_package "software-properties-common"
install_package "python3-pip"
install_package "python3-venv"
install_package "git"

# Install Cairo and other required system libraries
echo "Installing Cairo and other dependencies..."
install_package "libcairo2-dev"
install_package "pkg-config"
install_package "python3-dev"
install_package "build-essential"
install_package "libffi-dev"
install_package "python3-cairo"
install_package "libcairo2"
install_package "libpango1.0-dev"
install_package "libjpeg-dev"
install_package "libgif-dev"
install_package "librsvg2-dev"

# Install nginx if not present
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    add-apt-repository -y ppa:nginx/stable
    apt-get update
    install_package "nginx"
fi

# Install certbot and nginx plugin
echo "Installing certbot and nginx plugin..."
if ! command -v certbot &> /dev/null; then
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

# Install Python dependencies
pip install wheel
pip install -r requirements.txt
pip install gunicorn eventlet

# Setup directories and permissions
setup_directories_and_permissions

# Create necessary nginx directories
mkdir -p /etc/nginx/sites-available
mkdir -p /etc/nginx/sites-enabled

# Create initial nginx configuration (HTTP only)
cat > "/etc/nginx/sites-available/sketchmaker" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $server_name;

    client_max_body_size 25M;
    client_body_timeout 300s;
    client_header_timeout 300s;
    keepalive_timeout 300s;
    send_timeout 300s;
    proxy_read_timeout 300s;
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;

    location / {
        proxy_pass http://unix:/var/python/sketchmaker/sketchmaker/sketchmaker.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /static {
        alias /var/python/sketchmaker/sketchmaker/static;
        expires 30d;
        add_header Cache-Control "public, no-transform";
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
    echo -e "${RED}Nginx configuration test failed. Please check the configuration.${NC}"
    exit 1
fi

# Copy systemd service file
cp server/sketchmaker.service /etc/systemd/system/

# Configure UFW if it's active
if command -v ufw >/dev/null 2>&1; then
    ufw allow 'Nginx Full'
    ufw allow OpenSSH
fi

# Reload and start services
systemctl daemon-reload
systemctl enable sketchmaker
systemctl start sketchmaker

# Now that basic setup is done, obtain SSL certificate
echo "Obtaining SSL certificate for $server_name..."
certbot --nginx -d $server_name --non-interactive --agree-tos --email admin@${server_name#*.}

# Setup auto-renewal for SSL certificate
echo "0 0 * * * root certbot renew --quiet" > /etc/cron.d/certbot-renewal

# Final nginx restart
systemctl restart nginx

echo -e "${GREEN}Setup completed successfully!${NC}"
echo "Your server is configured with domain: $server_name"
echo "SSL certificate has been installed and auto-renewal has been configured"
echo "Please ensure your DNS is properly configured to point to this server"
echo "You can test your SSL setup at https://www.ssllabs.com/ssltest/analyze.html?d=$server_name"

# Display service status
echo -e "\nChecking service status:"
systemctl status sketchmaker --no-pager
systemctl status nginx --no-pager

# Display helpful information
echo -e "\n${GREEN}Useful commands:${NC}"
echo "- Check gunicorn logs: tail -f /var/log/gunicorn/gunicorn.error.log"
echo "- Check nginx logs: tail -f /var/nginx/error.log"
echo "- Restart services: sudo systemctl restart sketchmaker nginx"
echo "- Check service status: sudo systemctl status sketchmaker nginx"
