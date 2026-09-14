"""
Application configuration settings.

This module contains configuration settings for the Handwriting OCR application.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory of the application
BASE_DIR = Path(__file__).resolve().parent.parent

# Server configuration
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 8000))
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

# RapidAPI configuration
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
RAPIDAPI_HOST = os.getenv('RAPIDAPI_HOST', 'microsoft-computer-vision3.p.rapidapi.com')

# OCR configuration
DEFAULT_LANGUAGES = os.getenv('DEFAULT_LANGUAGES', 'eng').split(',')

# File upload settings
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', str(BASE_DIR / 'uploads'))
MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16MB max file size
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'tiff'}

# OCR processing parameters
OCR_PARAMS = {
    'language': 'eng',
    'isOverlayRequired': True,
    'iscreatesearchablepdf': False,
    'issearchablepdfhidetextlayer': False
}

# Create upload directory
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
