"""
Configuration utilities for the Handwriting OCR application.

This module provides functions for loading and validating configuration settings.
"""
import os
from typing import Any, Dict, List, Optional, Type, TypeVar, get_type_hints
from pydantic import BaseModel, ValidationError, validator
from dotenv import load_dotenv

from app.utils.logger import get_logger

logger = get_logger(__name__)

class AppConfig(BaseModel):
    """Application configuration model."""
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    
    # Application settings
    APP_NAME: str = "Handwriting OCR"
    APP_VERSION: str = "1.0.0"
    SECRET_KEY: str = "your-secret-key-here"
    
    # CORS settings
    CORS_ORIGINS: List[str] = ["*"]
    CORS_METHODS: List[str] = ["*"]
    CORS_HEADERS: List[str] = ["*"]
    
    # File upload settings
    UPLOAD_FOLDER: str = "uploads"
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS: List[str] = ["png", "jpg", "jpeg", "bmp", "tiff"]
    
    # OCR settings
    DEFAULT_LANGUAGES: List[str] = ["en"]
    GPU_ENABLED: bool = True
    MODEL_DIR: str = "models"
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"
    ERROR_LOG_FILE: str = "logs/error.log"
    
    # Validation
    @validator("DEFAULT_LANGUAGES", pre=True)
    def parse_languages(cls, v: Any) -> List[str]:
        """Parse comma-separated languages into a list."""
        if isinstance(v, str):
            return [lang.strip() for lang in v.split(",") if lang.strip()]
        return v
    
    @validator("CORS_ORIGINS", "CORS_METHODS", "CORS_HEADERS", pre=True)
    def parse_list_fields(cls, v: Any) -> List[str]:
        """Parse comma-separated strings into lists."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v or []
    
    @validator("PORT", "MAX_CONTENT_LENGTH", pre=True)
    def parse_int_fields(cls, v: Any) -> int:
        """Parse string values to integers."""
        if isinstance(v, str):
            try:
                return int(v)
            except (ValueError, TypeError):
                logger.warning(f"Could not parse {v} as integer, using default")
        return v
    
    @validator("DEBUG", "GPU_ENABLED", pre=True)
    def parse_bool_fields(cls, v: Any) -> bool:
        """Parse string values to booleans."""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "t", "y", "yes")
        return bool(v)

def load_config(env_file: str = ".env") -> AppConfig:
    """Load and validate configuration from environment variables.
    
    Args:
        env_file: Path to the .env file
        
    Returns:
        Validated AppConfig instance
        
    Raises:
        RuntimeError: If configuration validation fails
    """
    try:
        # Load environment variables from .env file
        load_dotenv(env_file)
        
        # Get all fields from the AppConfig model
        config_data = {}
        for field in AppConfig.__annotations__:
            env_value = os.getenv(field)
            if env_value is not None:
                config_data[field] = env_value
        
        # Create and validate the config
        return AppConfig(**config_data)
    except ValidationError as e:
        error_messages = []
        for error in e.errors():
            loc = ".".join(str(loc) for loc in error["loc"])
            msg = error["msg"]
            error_messages.append(f"{loc}: {msg}")
        
        error_msg = "\n".join(["Configuration validation failed:"] + error_messages)
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = f"Failed to load configuration: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e

def get_config() -> AppConfig:
    """Get the application configuration.
    
    This function caches the config in a module-level variable.
    
    Returns:
        AppConfig: The application configuration
    """
    if not hasattr(get_config, "_config"):
        get_config._config = load_config()  # type: ignore
    return get_config._config  # type: ignore

def get_setting(key: str, default: Any = None) -> Any:
    """Get a specific setting from the configuration.
    
    Args:
        key: The setting key
        default: Default value if the key is not found
        
    Returns:
        The setting value or default
    """
    config = get_config()
    return getattr(config, key, default)
