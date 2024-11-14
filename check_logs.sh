#!/bin/bash

# Exit on error
set -e

# Set variables
LOG_DIR="/var/log/gunicorn"
NGINX_ERROR_LOG="/var/log/nginx/error.log"
NGINX_ACCESS_LOG="/var/log/nginx/access.log"
APP_ROOT="/var/python/sketchmaker/sketchmaker"

echo "=== Checking Application Logs ==="

# Check if we can access the log directory
if [ ! -r "$LOG_DIR" ]; then
    echo "Cannot read log directory at $LOG_DIR"
    echo "Current permissions:"
    ls -la "$LOG_DIR"
    echo "Current user:"
    whoami
    echo "User groups:"
    groups
fi

# Check Gunicorn logs
echo -e "\n=== Checking Gunicorn Logs ==="
if [ -f "$LOG_DIR/gunicorn.error.log" ]; then
    echo "Last 50 lines of gunicorn error log:"
    echo "-----------------------------------"
    tail -n 50 "$LOG_DIR/gunicorn.error.log"
    
    echo -e "\nChecking for specific errors:"
    echo "-------------------------------"
    echo "Permission denied errors:"
    grep -i "permission denied" "$LOG_DIR/gunicorn.error.log" | tail -n 5
    
    echo -e "\nFile operation errors:"
    grep -i "error" "$LOG_DIR/gunicorn.error.log" | grep -i "file\|directory\|permission" | tail -n 5
else
    echo "No gunicorn error log found at $LOG_DIR/gunicorn.error.log"
fi

# Check Nginx error log
echo -e "\n=== Checking Nginx Error Log ==="
if [ -f "$NGINX_ERROR_LOG" ]; then
    echo "Last 50 lines of nginx error log:"
    echo "--------------------------------"
    tail -n 50 "$NGINX_ERROR_LOG"
    
    echo -e "\nChecking for specific errors:"
    echo "-------------------------------"
    echo "Permission denied errors:"
    grep -i "permission denied" "$NGINX_ERROR_LOG" | tail -n 5
    
    echo -e "\nProxy errors:"
    grep -i "proxy" "$NGINX_ERROR_LOG" | grep -i "error" | tail -n 5
else
    echo "No nginx error log found at $NGINX_ERROR_LOG"
fi

# Check Nginx access log for recent 500 errors
echo -e "\n=== Checking Recent 500 Errors in Nginx Access Log ==="
if [ -f "$NGINX_ACCESS_LOG" ]; then
    echo "Recent 500 errors (last 10):"
    grep " 500 " "$NGINX_ACCESS_LOG" | tail -n 10
else
    echo "No nginx access log found at $NGINX_ACCESS_LOG"
fi

# Check static directory permissions
echo -e "\n=== Checking Static Directory Permissions ==="
STATIC_DIR="$APP_ROOT/static"
echo "Static directory permissions:"
ls -la "$STATIC_DIR"

for dir in "images" "uploads" "training_files"; do
    echo -e "\n$dir directory permissions:"
    ls -la "$STATIC_DIR/$dir"
done

# Check socket file
echo -e "\n=== Checking Socket File ==="
SOCKET_FILE="$APP_ROOT/sketchmaker.sock"
if [ -e "$SOCKET_FILE" ]; then
    echo "Socket file permissions:"
    ls -la "$SOCKET_FILE"
else
    echo "Socket file not found at $SOCKET_FILE"
fi

# Check SELinux context if applicable
if command -v sestatus >/dev/null 2>&1; then
    echo -e "\n=== Checking SELinux Context ==="
    echo "SELinux status:"
    sestatus
    
    echo -e "\nSELinux context for static directories:"
    for dir in "images" "uploads" "training_files"; do
        echo -e "\n$dir directory context:"
        ls -Z "$STATIC_DIR/$dir"
    done
fi

echo -e "\n=== Summary ==="
echo "To fix permission issues:"
echo "1. Run check_permissions.sh script"
echo "2. Ensure gunicorn is running as www-data user"
echo "3. Check if SELinux is blocking access"
echo "4. Verify nginx configuration"
echo "5. Make sure all directories exist with correct permissions"

echo -e "\nTo apply fixes:"
echo "1. sudo ./check_permissions.sh"
echo "2. sudo systemctl restart gunicorn"
echo "3. sudo systemctl restart nginx"
