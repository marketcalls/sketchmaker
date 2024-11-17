#!/bin/bash

# Set app root and log directory
APP_ROOT="/var/python/sketchmaker/sketchmaker"
LOG_DIR="/var/log/gunicorn"

echo "Setting up directories and permissions..."

# Create necessary directories
mkdir -p "$APP_ROOT/static/images"
mkdir -p "$APP_ROOT/static/uploads"
mkdir -p "$APP_ROOT/static/training_files/uploads"
mkdir -p "$APP_ROOT/static/training_files/models"
mkdir -p "$APP_ROOT/static/training_files/temp"
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
chmod -R 755 "$APP_ROOT/static"
chmod -R 775 "$APP_ROOT/static/images"
chmod -R 775 "$APP_ROOT/static/uploads"
chmod -R 775 "$APP_ROOT/static/training_files"
chmod -R 775 "$APP_ROOT/instance"
chmod -R 775 "$LOG_DIR"
chmod 664 "$LOG_DIR/gunicorn.error.log"
chmod 664 "$LOG_DIR/gunicorn.access.log"

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

echo -e "\nSetup and checks completed."
