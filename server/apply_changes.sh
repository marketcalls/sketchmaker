#!/bin/bash

# Exit on error
set -e

echo "Stopping services..."
sudo systemctl stop sketchmaker
sudo systemctl stop nginx

echo "Creating backup directory..."
sudo mkdir -p /var/python/sketchmaker/sketchmaker/instance/backups
sudo chown -R www-data:www-data /var/python/sketchmaker/sketchmaker/instance

echo "Updating database schema..."
cd /var/python/sketchmaker/sketchmaker
source ../venv/bin/activate
python update_schema.py

echo "Setting permissions..."
sudo chown -R www-data:www-data /var/python/sketchmaker/sketchmaker/instance
sudo chmod -R 775 /var/python/sketchmaker/sketchmaker/instance

echo "Starting services..."
sudo systemctl start sketchmaker
sudo systemctl start nginx

echo "Checking service status..."
sudo systemctl status sketchmaker --no-pager
sudo systemctl status nginx --no-pager

echo "Done! Check the logs for any errors:"
echo "sudo tail -f /var/log/nginx/error.log /var/log/gunicorn/gunicorn.error.log"
