"""
SketchMaker AI Version Management

This module handles version information for the SketchMaker AI application.
Version follows semantic versioning: MAJOR.MINOR.PATCH.BUILD
"""

import os
from datetime import datetime

# Version Information
VERSION_MAJOR = 1
VERSION_MINOR = 0
VERSION_PATCH = 0
VERSION_BUILD = 0

# Full version string
VERSION = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}.{VERSION_BUILD}"

# Build information
BUILD_DATE = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
BUILD_HASH = os.getenv('BUILD_HASH', 'local-dev')

# Product information
PRODUCT_NAME = "SketchMaker AI"
PRODUCT_CODENAME = "Genesis"
PRODUCT_DESCRIPTION = "Advanced AI-Powered Image Generation Platform"

# Copyright and legal
COPYRIGHT_YEAR = "2024-2025"
COPYRIGHT_HOLDER = "SketchMaker AI"
LICENSE = "Proprietary"

def get_version():
    """Get the current version string"""
    return VERSION

def get_version_info():
    """Get detailed version information as a dictionary"""
    return {
        'version': VERSION,
        'major': VERSION_MAJOR,
        'minor': VERSION_MINOR,
        'patch': VERSION_PATCH,
        'build': VERSION_BUILD,
        'build_date': BUILD_DATE,
        'build_hash': BUILD_HASH,
        'product_name': PRODUCT_NAME,
        'product_codename': PRODUCT_CODENAME,
        'description': PRODUCT_DESCRIPTION,
        'copyright': f"© {COPYRIGHT_YEAR} {COPYRIGHT_HOLDER}",
        'license': LICENSE
    }

def get_short_version():
    """Get short version string (MAJOR.MINOR.PATCH)"""
    return f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"

def get_display_version():
    """Get user-friendly version string for display"""
    return f"{PRODUCT_NAME} v{VERSION}"

def is_development():
    """Check if this is a development build"""
    return BUILD_HASH == 'local-dev'

def is_stable():
    """Check if this is a stable release"""
    return VERSION_PATCH == 0 and VERSION_BUILD == 0

# Version history tracking
VERSION_HISTORY = [
    {
        'version': '1.0.0.0',
        'codename': 'Genesis',
        'release_date': '2025-06-18',
        'description': 'Initial release with comprehensive AI image generation capabilities',
        'features': [
            'Multi-provider AI image generation (OpenAI, Anthropic, Google, Groq)',
            'Advanced prompt enhancement and generation',
            'Custom LoRA model training',
            'Banner and image generation tools',
            'Comprehensive admin management system',
            'User subscription and credit management',
            'Gallery and image management',
            'Email notification system',
            'Role-based access control',
            'API key management',
            'Scheduled background jobs',
            'CSRF protection and security features'
        ],
        'breaking_changes': [],
        'bug_fixes': [],
        'known_issues': []
    }
]

def get_latest_release():
    """Get information about the latest release"""
    return VERSION_HISTORY[0] if VERSION_HISTORY else None

def get_version_history():
    """Get complete version history"""
    return VERSION_HISTORY