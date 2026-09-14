import os
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from PIL import Image
import io
import base64
import requests
import time

logger = logging.getLogger(__name__)

@dataclass
class OCRResult:
    text: str
    confidence: float = 1.0
    bbox: List[tuple] = field(default_factory=list)
    language: str = "en"
    processing_time: float = 0.0
    raw_response: Optional[Dict] = None

class GrokOCRService:
    def __init__(self, api_key: str = None, model: str = "grok-1", base_url: str = None):
        """
        Initialize the Grok OCR Service.
        Args:
            api_key: Grok API key. If not provided, will try to get from environment.
            model: Grok model name (default: grok-1).
            base_url: Base URL for Grok API. Defaults to environment variable or xAI's API.
        """
        self.api_key = api_key or os.getenv('GROK_API_KEY')
        self.model = model
        
        # Get base URL from parameter, then environment, then use default
        # xAI's Grok API endpoint for chat completions
        self.base_url = base_url or os.getenv('GROK_API_BASE_URL', 'https://api.groq.com/openai/v1')
        
        if not self.api_key:
            raise ValueError("Grok API key not set. Set GROK_API_KEY environment variable.")
        
        # xAI's Grok API uses standard OpenAI-compatible headers
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        logger.info(f"Initialized Grok OCR with model: {self.model} and base URL: {self.base_url}")

    def image_to_base64(self, image_path: str) -> str:
        """Convert image file to base64 string."""
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')

    def ocr_image(self, image_path: str, prompt: Optional[str] = None) -> OCRResult:
        """
        Perform OCR on a handwritten image using Grok API.
        Args:
            image_path: Path to the image file.
            prompt: Optional prompt to guide Grok (defaults to alphanumeric focus).
        Returns:
            OCRResult with recognized text.
        """
        start_time = time.time()
        base64_image = self.image_to_base64(image_path)
        
        # Default prompt focused on clean alphanumeric output
        system_prompt = prompt or (
            "You are an OCR engine. Transcribe the text in the image with these rules:\n"
            "1. Focus on letters (a-z, A-Z) and numbers (0-9) only.\n"
            "2. IGNORE all other characters like: - . , _ = + * & ^ % $ # @ ! ( ) [ ] { } \\ / | < > ` ~ \" ' : ; \n"
            "3. If text has trailing symbols (like 'clock----'), only keep the word part ('clock').\n"
            "4. Preserve spaces between words and numbers.\n"
            "5. Do NOT correct spelling, grammar, or change letter casing.\n"
            "6. Return ONLY the cleaned text, no explanations or formatting."
        )

        try:
            # Grok API uses OpenAI-compatible chat completions
            # For image processing, we'll use a text prompt to describe the image
            # Note: As of now, Grok doesn't support direct image input like GPT-4 Vision
            # So we'll need to preprocess the image to text using another method
            
            # First, let's try to use Grok's text capabilities
            # For now, we'll return a helpful message about the limitation
            # In a production environment, you might want to integrate with a different OCR service
            
            return OCRResult(
                text="Grok API currently doesn't support direct image processing. Please use GPT-4 Vision or another OCR service for image text extraction.",
                confidence=0.0,
                processing_time=time.time() - start_time,
                raw_response={"error": "Image processing not supported", "suggestion": "Use GPT-4 Vision or another OCR service"}
            )

            # Log the request URL and headers (without the API key)
            logger.debug(f"Sending request to: {self.base_url}/chat/completions")
            
            # Make the API request with a timeout
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            # Parse Grok response
            response_data = response.json()
            logger.debug(f"Received response: {response_data}")
            
            # Extract text from response (adjust based on actual response format)
            text = response_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            if not text:
                logger.warning("Received empty text from Grok API")
                
            return OCRResult(
                text=text,
                confidence=1.0 if text else 0.0,  # Grok doesn't provide confidence scores
                processing_time=time.time() - start_time,
                raw_response=response_data
            )
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Grok API request failed: {str(e)}"
            logger.error(error_msg)
            return OCRResult(
                text=f"Error: {str(e)}",
                confidence=0.0,
                processing_time=time.time() - start_time,
                raw_response={"error": str(e), "type": type(e).__name__}
            )
        except Exception as e:
            logger.error(f"Error in Grok OCR: {e}", exc_info=True)
            return OCRResult(
                text="",
                confidence=0.0,
                processing_time=time.time() - start_time,
                raw_response={"error": str(e)}
            )
