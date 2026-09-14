import os
import uuid
import time
import json
import logging
import cv2
import numpy as np
from PIL import Image
import io
import requests
from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict, Tuple, Any
from functools import wraps

logger = logging.getLogger(__name__)

# Import AI enhancer with error handling
try:
    from .ai_enhancer import AIEnhancer, GrokEnhancer

    AI_ENHANCER_AVAILABLE = True
except ImportError:
    AI_ENHANCER_AVAILABLE = False
    logger.warning("AI enhancer not available. Some features may be limited.")



@dataclass
class OCRResult:
    text: str
    confidence: float = 1.0
    bbox: List[tuple] = field(default_factory=list)
    language: str = "en"
    processing_time: float = 0.0
    raw_response: Optional[Dict] = None


class RapidOCRService:
    def __init__(self, api_key: str = None, host: str = None,
                 use_ai_enhancement: bool = True, ai_model: str = "gpt-3.5-turbo"):
        """
        Initialize the RapidOCR Service with optional AI enhancement.

        Args:
            api_key: RapidAPI key. If not provided, will try to get from environment.
            host: RapidAPI host URL
            use_ai_enhancement: Whether to use AI for post-processing OCR results
            ai_model: Which AI model to use ('gpt-3.5-turbo', 'gpt-4', or 'grok')
        """
        self.api_key = api_key or os.getenv('RAPIDAPI_KEY')
        self.host = host or os.getenv('RAPIDAPI_HOST') or "pen-to-print-handwriting-ocr.p.rapidapi.com"
        self.base_url = f"https://{self.host}"
        self.use_ai_enhancement = use_ai_enhancement and AI_ENHANCER_AVAILABLE
        self.ai_model = ai_model

        if not self.api_key:
            raise ValueError("RapidAPI key not set")

        logger.info(f"Using host: {self.host}")

        # Initialize AI enhancer if enabled
        self.ai_enhancer = None
        if self.use_ai_enhancement:
            try:
                if self.ai_model.lower() == 'grok':
                    self.ai_enhancer = GrokEnhancer()
                else:
                    self.ai_enhancer = AIEnhancer(model=ai_model)
                logger.info(f"AI enhancement enabled using {self.ai_model}")
            except Exception as e:
                logger.warning(f"Failed to initialize AI enhancer: {str(e)}")
                self.use_ai_enhancement = False

    def log_execution_time(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            start = time.time()
            result = func(self, *args, **kwargs)
            print(f"{func.__name__} took {time.time() - start:.2f}s")
            return result

        return wrapper

    def _read_image_file(self, image_path: Union[str, bytes, np.ndarray]) -> bytes:
        if isinstance(image_path, bytes):
            return image_path
        if isinstance(image_path, np.ndarray):
            success, buf = cv2.imencode('.jpg', image_path)
            if not success:
                raise ValueError("Failed to encode numpy array")
            return buf.tobytes()
        # Assume string path
        with open(image_path, 'rb') as f:
            return f.read()

    def _validate_image(self, image_bytes: bytes) -> bool:
        try:
            Image.open(io.BytesIO(image_bytes)).verify()
            return True
        except Exception:
            return False

    def _preprocess_image(self, image_bytes: bytes, config: dict = None) -> bytes:
        """
        Preprocess the input image to enhance OCR accuracy.

        Args:
            image_bytes: Input image as bytes
            config: Dictionary containing preprocessing configuration
                - denoise: bool - Apply non-local means denoising
                - deskew: bool - Auto-rotate image to correct skew
                - contrast: float - Contrast enhancement factor (1.0 = no change)
                - sharpen: bool - Apply sharpening filter
                - threshold: str - Thresholding method ('adaptive' or 'otsu')

        Returns:
            Processed image as bytes
        """
        if config is None:
            config = {
                'denoise': True,
                'deskew': True,
                'contrast': 1.2,
                'sharpen': True,
                'threshold': 'adaptive'
            }

        try:
            # Convert to PIL Image
            image = Image.open(io.BytesIO(image_bytes))

            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Convert to OpenCV format (BGR)
            img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Denoising
            if config.get('denoise', True):
                gray = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)

            # Deskew
            if config.get('deskew', True):
                coords = np.column_stack(np.where(gray > 0))
                angle = cv2.minAreaRect(coords)[-1]
                if angle < -45:
                    angle = -(90 + angle)
                else:
                    angle = -angle
                (h, w) = gray.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

            # Contrast enhancement
            if config.get('contrast', 1.0) != 1.0:
                # Apply contrast enhancement directly to grayscale
                gray = cv2.convertScaleAbs(gray, alpha=config['contrast'], beta=0)
                # Apply CLAHE for better contrast
                clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
                gray = clahe.apply(gray)

            # Sharpening
            if config.get('sharpen', True):
                kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
                gray = cv2.filter2D(gray, -1, kernel)

            # Thresholding
            if config.get('threshold') == 'adaptive':
                gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                             cv2.THRESH_BINARY, 11, 2)
            elif config.get('threshold') == 'otsu':
                _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Morphological operations
            kernel = np.ones((1, 1), np.uint8)
            gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
            gray = cv2.dilate(gray, kernel, iterations=1)
            gray = cv2.erode(gray, kernel, iterations=1)

            # Convert back to bytes
            success, buf = cv2.imencode('.png', gray)
            if not success:
                return image_bytes

            return buf.tobytes()

        except Exception as e:
            logger.warning(f"Preprocessing failed: {str(e)}")
            return image_bytes

    @log_execution_time
    def process_image(self, image_path: Union[str, bytes, np.ndarray], language: str = 'eng',
                      preprocess_config: dict = None) -> OCRResult:
        """
        Process an image through OCR with optional preprocessing.

        Args:
            image_path: Path to image, image bytes, or numpy array
            language: Language code for OCR (default: 'eng')
            preprocess_config: Configuration for image preprocessing steps
                Set to None to disable preprocessing

        Returns:
            OCRResult object containing extracted text and metadata
        """
        start_time = time.time()
        image_bytes = self._read_image_file(image_path)
        if not image_bytes:
            raise ValueError("Empty image data")

        # Save original for debugging
        with open("debug_original.jpg", "wb") as f:
            f.write(image_bytes)

        # Validate image
        if not self._validate_image(image_bytes):
            raise ValueError("Invalid image data")

        # Apply preprocessing if config is provided (not None)
        if preprocess_config is not None:
            try:
                processed_bytes = self._preprocess_image(image_bytes, preprocess_config)
                if processed_bytes and processed_bytes != image_bytes:
                    with open("debug_processed.jpg", "wb") as f:
                        f.write(processed_bytes)
                    image_bytes = processed_bytes
            except Exception as e:
                logger.warning(f"Image preprocessing failed, continuing with original image: {str(e)}")
        # Prepare request
        url = f"{self.base_url}/recognize/"
        files_list = [
            ('srcImg', ('image.jpg', image_bytes, 'image/jpeg')),
            ('image', ('image.jpg', image_bytes, 'image/jpeg')),
            ('file', ('image.jpg', image_bytes, 'image/jpeg')),
            ('upload', ('image.jpg', image_bytes, 'image/jpeg'))
        ]
        headers = {
            'x-rapidapi-host': self.host,
            'x-rapidapi-key': self.api_key,
        }
        data = {
            'includeSubScan': '0',
            'Session': str(uuid.uuid4()),
            'language': language
        }
        for files in files_list:
            try:
                response = requests.post(url, headers=headers, data=data, files={'srcImg': files[1]}, timeout=60)
                if response.status_code == 200:
                    result_json = response.json()
                    text = self._extract_text(result_json)
                    return OCRResult(
                        text=text,
                        confidence=1.0,
                        language=language,
                        processing_time=time.time() - start_time,
                        raw_response=result_json
                    )
            except Exception:
                continue
        raise Exception("All API attempts failed")

    def _postprocess_text(self, text: str, language: str = "en") -> str:
        """
        Post-process the extracted text using AI enhancement if enabled.

        Args:
            text: The raw extracted text
            language: The language of the text

        Returns:
            Enhanced and cleaned text
        """
        if not text.strip() or not self.use_ai_enhancement or not self.ai_enhancer:
            return text

        try:
            # Clean up common OCR artifacts
            text = text.replace('|', 'I')  # Common OCR mistake

            # Use AI for advanced cleaning and enhancement
            enhanced_text = self.ai_enhancer.enhance_text(
                text=text,
                language=language,
                instructions="""
                You are an expert in post-processing OCR text. Your task is to clean and correct 
                the extracted text while preserving the original meaning and formatting.

                Please:
                1. Fix obvious OCR errors and typos
                2. Maintain original line breaks and paragraphs
                3. Preserve numbers, dates, and special characters
                4. Do not add any information not present in the original
                5. Keep the original language and terminology
                """
            )
            return enhanced_text.strip()

        except Exception as e:
            logger.error(f"Error in AI text enhancement: {str(e)}")
            return text

    def _extract_text(self, result_json: dict) -> str:
        """
        Extract text from the API response and apply post-processing.

        Args:
            result_json: The JSON response from the OCR API

        Returns:
            Extracted and enhanced text
        """
        # Try multiple response formats
        if 'value' in result_json:
            raw_text = result_json['value']
        elif 'data' in result_json and 'text' in result_json['data']:
            raw_text = result_json['data']['text']
        elif 'text' in result_json:
            raw_text = result_json['text']
        elif 'results' in result_json and isinstance(result_json['results'], list):
            raw_text = '\n'.join([r.get('text', '') for r in result_json['results']])
        elif 'recognized_text' in result_json:
            raw_text = result_json['recognized_text']
        else:
            return "No text detected"

        # Get language from response or use default
        language = result_json.get('language', 'en')

        # Apply AI enhancement if enabled
        if self.use_ai_enhancement and self.ai_enhancer:
            return self._postprocess_text(raw_text, language)

        return raw_text
