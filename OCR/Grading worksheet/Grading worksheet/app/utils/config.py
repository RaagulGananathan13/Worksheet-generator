"""
Configuration module for the Handwriting OCR application.
Handles environment variables and provides configuration settings.
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# RapidAPI Configuration
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
RAPIDAPI_HOST = os.getenv('RAPIDAPI_HOST', 'pen-to-print-handwriting-ocr.p.rapidapi.com')

# Application Configuration
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
DEFAULT_LANGUAGE = os.getenv('DEFAULT_LANGUAGE', 'eng')

# File Upload Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
