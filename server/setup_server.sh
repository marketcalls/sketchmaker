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

    echo "Checking permissions..."
    echo "----------------------"

    # Check log files
    echo "Log Files:"
    ls -l "$LOG_DIR/gunicorn.error.log"
    ls -l "$LOG_DIR/gunicorn.access.log"

    # Check write permissions
    echo -e "\nTesting write permissions..."
    su www-data -s /bin/bash -c "echo 'test' >> '$LOG_DIR/gunicorn.error.log'" && echo "✓ error log is writable" || echo "✗ error log is not writable"
    su www-data -s /bin/bash -c "echo 'test' >> '$LOG_DIR/gunicorn.access.log'" && echo "✓ access log is writable" || echo "✗ access log is not writable"

    echo -e "\nDirectory setup and permission checks completed."
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

# Install Python dependencies
pip install -r requirements.txt
pip install gunicorn eventlet

# Setup directories and permissions
setup_directories_and_permissions

# Create necessary nginx directories
mkdir -p /etc/nginx/sites-available
mkdir -p /etc/nginx/sites-enabled

# Copy nginx configuration and update domain
cp server/sketchmaker /etc/nginx/sites-available/sketchmaker
sed -i "s/server_name .*/server_name $server_name;/g" /etc/nginx/sites-available/sketchmaker

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

# Update SSL certificate paths in nginx config
sed -i "s|ssl_certificate .*|ssl_certificate /etc/letsencrypt/live/$server_name/fullchain.pem;|g" /etc/nginx/sites-available/sketchmaker
sed -i "s|ssl_certificate_key .*|ssl_certificate_key /etc/letsencrypt/live/$server_name/privkey.pem;|g" /etc/nginx/sites-available/sketchmaker

# Copy systemd service file
cp server/sketchmaker.service /etc/systemd/system/

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
