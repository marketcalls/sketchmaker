#!/bin/bash

# Exit on error
set -e

# Set variables
APP_ROOT="/var/python/sketchmaker/sketchmaker"
STATIC_ROOT="$APP_ROOT/static"
UPLOAD_DIR="$STATIC_ROOT/uploads"
IMAGES_DIR="$STATIC_ROOT/images"
TRAINING_FILES_DIR="$STATIC_ROOT/training_files"
LOG_DIR="/var/log/gunicorn"
INSTANCE_DIR="$APP_ROOT/instance"

# Create necessary directories if they don't exist
echo "Creating necessary directories..."
sudo mkdir -p "$LOG_DIR"
sudo mkdir -p "$UPLOAD_DIR"
sudo mkdir -p "$IMAGES_DIR"
sudo mkdir -p "$TRAINING_FILES_DIR"
sudo mkdir -p "$INSTANCE_DIR"

# Set ownership to www-data
echo "Setting directory ownership..."
sudo chown -R www-data:www-data "$APP_ROOT"
sudo chown www-data:www-data "$LOG_DIR"

# Set directory permissions
echo "Setting directory permissions..."

# App root - 755 for directories, 644 for files
sudo find "$APP_ROOT" -type d -exec chmod 755 {} \;
sudo find "$APP_ROOT" -type f -exec chmod 644 {} \;

# Make prestart.sh executable
sudo chmod +x "$APP_ROOT/prestart.sh"

# Special permissions for directories that need write access
echo "Setting write permissions for specific directories..."
sudo chmod -R 775 "$UPLOAD_DIR"
sudo chmod -R 775 "$IMAGES_DIR"
sudo chmod -R 775 "$TRAINING_FILES_DIR"
sudo chmod -R 775 "$INSTANCE_DIR"
sudo chmod -R 775 "$LOG_DIR"

# Ensure .env file has restricted permissions if it exists
if [ -f "$APP_ROOT/.env" ]; then
    echo "Setting restricted permissions for .env file..."
    sudo chmod 640 "$APP_ROOT/.env"
fi

# Create required __init__.py files if they don't exist
touch "$APP_ROOT/__init__.py"
touch "$APP_ROOT/blueprints/__init__.py"

# Set SELinux context if SELinux is enabled
if command -v semanage &> /dev/null && command -v sestatus &> /dev/null && sestatus | grep -q "enabled"; then
    echo "Setting SELinux context..."
    sudo semanage fcontext -a -t httpd_sys_content_t "$APP_ROOT(/.*)?"
    sudo semanage fcontext -a -t httpd_sys_rw_content_t "$UPLOAD_DIR(/.*)?"
    sudo semanage fcontext -a -t httpd_sys_rw_content_t "$IMAGES_DIR(/.*)?"
    sudo semanage fcontext -a -t httpd_sys_rw_content_t "$TRAINING_FILES_DIR(/.*)?"
    sudo semanage fcontext -a -t httpd_sys_rw_content_t "$INSTANCE_DIR(/.*)?"
    sudo semanage fcontext -a -t httpd_log_t "$LOG_DIR(/.*)?"
    sudo restorecon -R "$APP_ROOT"
    sudo restorecon -R "$LOG_DIR"
fi

# Create log files if they don't exist
sudo touch "$LOG_DIR/gunicorn.log"
sudo touch "$LOG_DIR/gunicorn.error.log"
sudo chown www-data:www-data "$LOG_DIR/gunicorn.log"
sudo chown www-data:www-data "$LOG_DIR/gunicorn.error.log"
sudo chmod 664 "$LOG_DIR/gunicorn.log"
sudo chmod 664 "$LOG_DIR/gunicorn.error.log"

echo "Creating sqlite database directory if it doesn't exist..."
DB_DIR="$APP_ROOT/instance"
sudo mkdir -p "$DB_DIR"
sudo chown www-data:www-data "$DB_DIR"
sudo chmod 775 "$DB_DIR"

echo "Setup complete!"
echo "Remember to:"
echo "1. Update your .env file with proper configurations"
echo "2. Initialize the database using Flask-SQLAlchemy"
echo "3. Restart your Gunicorn service after making these changes"
