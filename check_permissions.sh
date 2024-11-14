#!/bin/bash

# Exit on error
set -e

# Set variables
APP_ROOT="/var/python/sketchmaker/sketchmaker"
STATIC_ROOT="$APP_ROOT/static"
WEB_USER="www-data"
WEB_GROUP="www-data"

# Function to check and fix directory permissions
check_dir_permissions() {
    local dir="$1"
    local expected_perms="$2"
    local actual_perms=$(stat -c "%a" "$dir")
    
    echo "Checking $dir"
    echo "Current permissions: $actual_perms (expected: $expected_perms)"
    echo "Owner: $(stat -c "%U" "$dir")"
    echo "Group: $(stat -c "%G" "$dir")"
    
    if [ "$actual_perms" != "$expected_perms" ]; then
        echo "Fixing permissions for $dir to $expected_perms"
        sudo chmod "$expected_perms" "$dir"
    fi
    
    if [ "$(stat -c "%U" "$dir")" != "$WEB_USER" ] || [ "$(stat -c "%G" "$dir")" != "$WEB_GROUP" ]; then
        echo "Fixing ownership for $dir to $WEB_USER:$WEB_GROUP"
        sudo chown "$WEB_USER:$WEB_GROUP" "$dir"
    fi
}

# Function to check and fix file permissions
check_file_permissions() {
    local file="$1"
    local expected_perms="$2"
    local actual_perms=$(stat -c "%a" "$file")
    
    echo "Checking $file"
    echo "Current permissions: $actual_perms (expected: $expected_perms)"
    echo "Owner: $(stat -c "%U" "$file")"
    echo "Group: $(stat -c "%G" "$file")"
    
    if [ "$actual_perms" != "$expected_perms" ]; then
        echo "Fixing permissions for $file to $expected_perms"
        sudo chmod "$expected_perms" "$file"
    fi
    
    if [ "$(stat -c "%U" "$file")" != "$WEB_USER" ] || [ "$(stat -c "%G" "$file")" != "$WEB_GROUP" ]; then
        echo "Fixing ownership for $file to $WEB_USER:$WEB_GROUP"
        sudo chown "$WEB_USER:$WEB_GROUP" "$file"
    fi
}

echo "Checking static directory structure..."

# Check main static directory
check_dir_permissions "$STATIC_ROOT" "755"

# Check css directory
check_dir_permissions "$STATIC_ROOT/css" "755"
find "$STATIC_ROOT/css" -type f -exec bash -c 'check_file_permissions "$0" "644"' {} \;

# Check js directory
check_dir_permissions "$STATIC_ROOT/js" "755"
find "$STATIC_ROOT/js" -type f -exec bash -c 'check_file_permissions "$0" "644"' {} \;

# Check and fix writable directories
for dir in "images" "uploads" "training_files"; do
    DIR_PATH="$STATIC_ROOT/$dir"
    echo "Checking $dir directory..."
    
    # Create directory if it doesn't exist
    if [ ! -d "$DIR_PATH" ]; then
        echo "Creating $DIR_PATH"
        sudo mkdir -p "$DIR_PATH"
    fi
    
    # Set permissions (775 for writable directories)
    check_dir_permissions "$DIR_PATH" "775"
    
    # Set permissions for all files in the directory
    if [ -n "$(ls -A $DIR_PATH 2>/dev/null)" ]; then
        find "$DIR_PATH" -type f -exec bash -c 'check_file_permissions "$0" "664"' {} \;
    fi
done

# Check if gunicorn can write to these directories
echo "Testing write permissions..."
for dir in "images" "uploads" "training_files"; do
    DIR_PATH="$STATIC_ROOT/$dir"
    TEST_FILE="$DIR_PATH/test_write_$$"
    
    echo "Testing write access to $dir..."
    if sudo -u $WEB_USER touch "$TEST_FILE" 2>/dev/null; then
        echo "✓ Write test passed for $dir"
        sudo rm "$TEST_FILE"
    else
        echo "✗ Write test failed for $dir"
        echo "Running debug commands..."
        ls -la "$DIR_PATH"
        sudo -u $WEB_USER -v
        id $WEB_USER
        groups $WEB_USER
    fi
done

# Check SELinux if enabled
if command -v getenforce >/dev/null 2>&1; then
    echo "Checking SELinux status..."
    SELINUX_STATUS=$(getenforce)
    echo "SELinux is: $SELINUX_STATUS"
    
    if [ "$SELINUX_STATUS" = "Enforcing" ]; then
        echo "Setting SELinux context for static directories..."
        for dir in "images" "uploads" "training_files"; do
            DIR_PATH="$STATIC_ROOT/$dir"
            sudo semanage fcontext -a -t httpd_sys_rw_content_t "$DIR_PATH(/.*)?"
            sudo restorecon -Rv "$DIR_PATH"
        done
    fi
fi

echo "Permission check complete!"
echo "If you're still having issues, check the following:"
echo "1. Gunicorn service user matches $WEB_USER"
echo "2. Nginx user matches $WEB_USER"
echo "3. Application is running with correct permissions"
echo "4. Firewall and SELinux settings"
echo "5. Check logs at:"
echo "   - /var/log/nginx/error.log"
echo "   - /var/log/gunicorn/gunicorn.error.log"
