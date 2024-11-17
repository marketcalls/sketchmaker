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

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}Starting Sketchmaker Installation...${NC}"

# Create temporary directory
TMP_DIR=$(mktemp -d)
cd "$TMP_DIR"

# Download setup script
echo "Downloading setup script..."
curl -fsSL https://raw.githubusercontent.com/marketcalls/sketchmaker/master/server/setup_server.sh -o setup_server.sh

if [ ! -f setup_server.sh ]; then
    echo -e "${RED}Failed to download setup script${NC}"
    exit 1
fi

# Make script executable
chmod +x setup_server.sh

# Run setup script
./setup_server.sh

# Cleanup
cd - > /dev/null
rm -rf "$TMP_DIR"
