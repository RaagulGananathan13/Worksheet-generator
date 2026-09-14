# main_ocr.py
import os
import uvicorn
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import Grok OCR service
from app.services.grok_ocr_service import GrokOCRService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Check for required env vars
if not os.getenv('GROK_API_KEY'):
    logger.error("Missing required environment variable: GROK_API_KEY")
    raise RuntimeError("Missing required environment variable: GROK_API_KEY")

logger.info("Using Grok OCR engine")

app = FastAPI(
    title="Handwriting OCR API",
    description="API for Handwriting OCR functionality",
    version="1.0.0"
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)


# Dependency for OCR service
def get_ocr_service() -> GrokOCRService:
    """Get an instance of the Grok OCR service"""
    return GrokOCRService(
        api_key=os.getenv('GROK_API_KEY'),
        model=os.getenv('GROK_MODEL', 'grok-1')
    )


# Configure templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="templates/static"), name="static")

# Create required directories
for directory in ["data/templates", "static/templates", "uploads", "debug"]:
    Path(directory).mkdir(parents=True, exist_ok=True)


# Main route that serves index.html
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main application page"""
    return templates.TemplateResponse("index.html", {"request": request})


# OCR Endpoint
@app.post("/api/ocr")
async def process_ocr(
        request: Request,
        file: UploadFile = File(...),
        languages: str = Form("eng"),
        detail: str = Form("1"),
        preprocess: str = Form("false"),
        denoise: str = Form("false"),
        deskew: str = Form("false"),
        sharpen: str = Form("false"),
        contrast: str = Form("1.0"),
        threshold: str = Form("otsu"),
        ocr: GrokOCRService = Depends(get_ocr_service)
):
    """
    Process an image with OCR to extract text.

    This endpoint accepts an image file and optional preprocessing parameters,
    processes the image, and returns the extracted text along with confidence scores.
    """
    logger.info(f"Received OCR request with file: {file.filename}")
    logger.info(f"Using {ocr.__class__.__name__} for OCR processing")
    logger.info(f"Request headers: {dict(request.headers)}")

    # Log form data
    form_data = await request.form()
    logger.info(f"Form data: {dict(form_data)}")

    try:
        # Read the uploaded file
        image_data = await file.read()
        if not image_data:
            raise HTTPException(status_code=400, detail="Empty file uploaded")

        logger.info(f"Read {len(image_data)} bytes from uploaded file")

        # Save the uploaded file for debugging
        debug_dir = Path("debug")
        debug_dir.mkdir(exist_ok=True)
        debug_path = debug_dir / f"upload_{int(time.time())}.jpg"
        with open(debug_path, "wb") as f:
            f.write(image_data)
        logger.info(f"Saved uploaded file to {debug_path}")

        # Process the image with GPT OCR
        logger.info("Starting GPT OCR processing...")
        start_time = time.time()

        # Strict verbatim prompt: no corrections or rephrasing
        prompt = (
            "You are an OCR engine. Transcribe the text in the image VERBATIM. "
            "Do NOT correct grammar, spelling, casing, or punctuation. "
            "Preserve original line breaks and spacing as much as possible. "
            "Include all symbols exactly as seen. "
            "Do not add any commentary or formatting—return ONLY the raw transcribed text."
        )
        result = ocr.ocr_image(str(debug_path), prompt=prompt)

        processing_time = time.time() - start_time
        logger.info(f"OCR processing completed in {processing_time:.2f} seconds")

        response_data = {
            'status': 'success',
            'text': result.text,
            'confidence': result.confidence,
            'processing_time': processing_time,
            'language': result.language,
            'debug': {
                'file_saved': str(debug_path),
                'file_size': len(image_data),
                'content_type': file.content_type
            }
        }

        logger.info(f"OCR result: {response_data}")
        return response_data

    except HTTPException as he:
        logger.error(f"HTTP Error in OCR processing: {str(he)}", exc_info=True)
        raise he
    except Exception as e:
        error_msg = f"Error in OCR processing: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )
    finally:
        if not file.file.closed:
            await file.close()


if __name__ == "__main__":
    uvicorn.run("main_ocr:app", host="0.0.0.0", port=8002, reload=True)