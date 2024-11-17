#!/bin/bash

# Function to validate domain name format
validate_domain() {
    if [[ $1 =~ ^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$ ]]; then
        return 0
    else
        return 1
    fi
}

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Check and install nginx if not present
if ! command -v nginx &> /dev/null; then
    echo "Nginx not found. Installing nginx..."
    apt-get update
    apt-get install -y nginx
    if [ $? -ne 0 ]; then
        echo "Failed to install nginx. Please check your internet connection and try again."
        exit 1
    fi
    echo "Nginx installed successfully!"
else
    echo "Nginx is already installed."
fi

# Install certbot and nginx plugin
echo "Installing certbot and nginx plugin..."
apt-get update
apt-get install -y certbot python3-certbot-nginx
if [ $? -ne 0 ]; then
    echo "Failed to install certbot. Please check your internet connection and try again."
    exit 1
fi
echo "Certbot installed successfully!"

# Ask for server name
while true; do
    read -p "Enter your server name (e.g., example.com): " server_name
    if validate_domain "$server_name"; then
        break
    else
        echo "Invalid domain format. Please enter a valid domain name."
    fi
done

# Create necessary directories if they don't exist
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

# Reload nginx to apply basic config
nginx -t && systemctl reload nginx

# Obtain SSL certificate
echo "Obtaining SSL certificate for $server_name..."
certbot --nginx -d $server_name --non-interactive --agree-tos --email admin@$server_name

# Now update nginx config with full configuration including SSL
cp "$(dirname "$0")/sketchmaker" "/etc/nginx/sites-available/sketchmaker"
sed -i "s/server_name .*/server_name $server_name;/g" "/etc/nginx/sites-available/sketchmaker"

# Update SSL certificate paths in nginx config
sed -i "s|ssl_certificate .*|ssl_certificate /etc/letsencrypt/live/$server_name/fullchain.pem;|g" "/etc/nginx/sites-available/sketchmaker"
sed -i "s|ssl_certificate_key .*|ssl_certificate_key /etc/letsencrypt/live/$server_name/privkey.pem;|g" "/etc/nginx/sites-available/sketchmaker"

# Copy systemd service file
cp "$(dirname "$0")/sketchmaker.service" "/etc/systemd/system/"

# Set proper permissions
chown -R www-data:www-data /var/log/gunicorn
chmod -R 755 /var/log/gunicorn

# Setup auto-renewal for SSL certificate
echo "0 0 * * * root certbot renew --quiet" > /etc/cron.d/certbot-renewal

# Reload systemd and nginx
systemctl daemon-reload
systemctl enable sketchmaker
systemctl start sketchmaker
nginx -t && systemctl restart nginx

echo "Setup completed successfully!"
echo "Your server is configured with domain: $server_name"
echo "SSL certificate has been installed and auto-renewal has been configured"
echo "Please ensure your DNS is properly configured to point to this server"
echo "You can test your SSL setup at https://www.ssllabs.com/ssltest/analyze.html?d=$server_name"
