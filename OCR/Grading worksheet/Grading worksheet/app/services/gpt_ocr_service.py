import os
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from PIL import Image
import io
import base64
import openai

logger = logging.getLogger(__name__)

@dataclass
class OCRResult:
    text: str
    confidence: float = 1.0
    bbox: List[tuple] = field(default_factory=list)
    language: str = "en"
    processing_time: float = 0.0
    raw_response: Optional[Dict] = None

class GPTOCRService:
    def __init__(self, api_key: str = None, model: str = "gpt-4o"):
        """
        Initialize the GPT OCR Service.
        Args:
            api_key: OpenAI API key. If not provided, will try to get from environment.
            model: OpenAI Vision model name.
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.model = model
        if not self.api_key:
            raise ValueError("OpenAI API key not set")
        openai.api_key = self.api_key
        logger.info(f"Using OpenAI model: {self.model}")

    def image_to_base64(self, image_path: str) -> str:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')

    def ocr_image(self, image_path: str, prompt: Optional[str] = None) -> OCRResult:
        """
        Perform OCR on a handwritten image using GPT Vision API.
        Args:
            image_path: Path to the image file.
            prompt: Optional prompt to guide GPT (e.g., 'Read the handwritten text in this image.')
        Returns:
            OCRResult with recognized text.
        """
        import time
        start = time.time()
        base64_image = self.image_to_base64(image_path)
        # Default to a clean alphanumeric transcription prompt
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
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}
                ],
                max_tokens=1024,
                temperature=0
            )
            text = response.choices[0].message.content.strip()
            elapsed = time.time() - start
            return OCRResult(text=text, processing_time=elapsed, raw_response=response.model_dump())
        except Exception as e:
            logger.error(f"GPT OCR failed: {e}")
            return OCRResult(text="", confidence=0.0, processing_time=0.0, raw_response={"error": str(e)})
