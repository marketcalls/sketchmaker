# Sketchmaker Server Installation

Quick installation guide for setting up Sketchmaker on your server.

## Requirements

- Ubuntu server (20.04 LTS or newer)
- Domain name pointing to your server
- Root/sudo access

## Installation Steps

1. Download the installation script:
```bash
wget https://raw.githubusercontent.com/marketcalls/sketchmaker/master/server/install.sh
```

2. Make it executable:
```bash
chmod +x install.sh
```

3. Run the installation script:
```bash
sudo ./install.sh
```

When prompted, enter your domain name (e.g., sketch.example.com).

The script will automatically:
- Install all dependencies
- Set up the application
- Configure SSL
- Start all services

## Useful Commands

After installation:
```bash
# Check service status
sudo systemctl status sketchmaker
sudo systemctl status nginx

# View logs
tail -f /var/log/gunicorn/gunicorn.error.log
tail -f /var/nginx/error.log

# Restart services
sudo systemctl restart sketchmaker nginx
```

## Important Note

Make sure your domain's DNS is properly configured to point to your server's IP address before running the installation.
