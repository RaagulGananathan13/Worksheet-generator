import uvicorn
import base64
import tempfile
from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Form, status, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Dict, Optional, Any, Union, Tuple
from pydantic import BaseModel
import uuid
import shutil
import cv2
import numpy as np
from datetime import datetime
import json
import os
from app.services.gpt_ocr_service import GPTOCRService
from app.services.answer_box_service import AnswerBoxDetector, AnswerBoxGrader
from app.services.dotted_line_service import DottedLineDetector, DottedLineTemplate
from app.services.blank_line_service import BlankLineDetector
from app.services.sa_service import ShortAnswerTemplateManager, ShortAnswerGrader
import logging

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Initialize OCR service (GPT OCR)
def get_ocr_service() -> GPTOCRService:
    """Get an instance of the GPT OCR service"""
    return GPTOCRService(
        api_key=os.getenv('OPENAI_API_KEY'),
        model=os.getenv('OPENAI_VISION_MODEL', 'gpt-4o')
    )


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Basic Template Creator API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve debug images
@app.get("/debug/{filename}")
async def get_debug_image(filename: str):
    """Serve debug images for development."""
    debug_path = Path("debug") / filename
    if not debug_path.exists():
        raise HTTPException(status_code=404, detail="Debug image not found")
    return FileResponse(debug_path)

# Set up templates
templates = Jinja2Templates(directory="templates")

# Create necessary directories
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "data" / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


# Models
class TemplateField(BaseModel):
    field_id: str
    x: int
    y: int
    width: int
    height: int
    page: int = 0
    field_type: str = "text"
    expected_answer: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class Question(BaseModel):
    text: str
    answer: str
    points: int
    x: int
    y: int
    width: int
    height: int


class TemplateCreate(BaseModel):
    id: str
    worksheetId: str
    title: str
    questions: List[Question]
    imageData: str
    createdAt: str


# Endpoints
@app.get("/", response_class=HTMLResponse)
async def answer_box_creator(request: Request):
    """Serve the answer box creator interface"""
    return templates.TemplateResponse("answer_box_creator.html", {"request": request})


@app.get("/answer-box-creator", response_class=HTMLResponse)
async def answer_box_creator(request: Request):
    """Serve the answer box creator interface"""
    return templates.TemplateResponse("answer_box_creator.html", {"request": request})


@app.get("/unified-setup", response_class=HTMLResponse)
async def unified_template_setup(request: Request):
    """Serve the unified template setup interface"""
    return templates.TemplateResponse("unified_setup.html", {"request": request})


@app.get("/dotted-line-setup", response_class=HTMLResponse)
async def dotted_line_setup(request: Request):
    """Serve the dotted line setup interface"""
    return templates.TemplateResponse("dotted_line_setup.html", {"request": request})


@app.get("/blank-line-setup", response_class=HTMLResponse)
async def blank_line_setup(request: Request):
    return templates.TemplateResponse("blank_line_setup.html", {"request": request, "title": "Blank Line Setup"})

@app.get("/sa-setup", response_class=HTMLResponse)
def sa_setup(request: Request):
    """Serve the Short Answer Setup UI."""
    return templates.TemplateResponse("sa_setup.html", {"request": request})


@app.get("/unified-grader", response_class=HTMLResponse)
def unified_grader(request: Request):
    """Serve a single page to select template type, pick template, upload sheet and grade."""
    return templates.TemplateResponse("unified_grader.html", {"request": request})

@app.post("/api/template")
async def create_template(
        template_data: TemplateCreate,
        request: Request
):
    """
    Create a new worksheet template
    """
    try:
        # Create template directory
        template_id = template_data.id or f"template_{int(datetime.utcnow().timestamp())}"
        template_dir = TEMPLATES_DIR / template_id
        template_dir.mkdir(exist_ok=True, parents=True)

        # Process and save image
        if template_data.imageData.startswith("data:image"):
            import base64
            try:
                # Extract the base64 data from the data URL
                header, encoded = template_data.imageData.split(",", 1)
                image_data = base64.b64decode(encoded)

                # Save the image
                with open(template_dir / "worksheet.png", "wb") as f:
                    f.write(image_data)
            except Exception as e:
                logger.error(f"Error processing image: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid image data: {str(e)}"
                )

        # Prepare template metadata
        metadata = {
            "id": template_id,
            "worksheet_id": template_data.worksheetId,
            "title": template_data.title,
            "created_at": template_data.createdAt,
            "questions": [
                {
                    "text": q.text,
                    "answer": q.answer,
                    "points": q.points,
                    "area": {
                        "x": q.x,
                        "y": q.y,
                        "width": q.width,
                        "height": q.height
                    }
                }
                for q in template_data.questions
            ]
        }

        # Save metadata
        with open(template_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Template {template_id} created successfully")
        return {"status": "success", "template_id": template_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating template: {str(e)}")
        # Clean up if something went wrong
        if 'template_dir' in locals() and template_dir.exists():
            shutil.rmtree(template_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create template: {str(e)}"
        )


@app.get("/api/templates")
async def list_templates():
    """List all available templates"""
    try:
        templates_list = []
        for template_dir in TEMPLATES_DIR.glob("*"):
            if template_dir.is_dir():
                metadata_file = template_dir / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, "r") as f:
                        template_data = json.load(f)
                        # Format the response to match frontend expectations
                        templates_list.append({
                            "id": template_data.get("id"),
                            "title": template_data.get("title"),
                            "worksheetId": template_data.get("worksheet_id"),
                            "createdAt": template_data.get("created_at"),
                            "previewUrl": f"/api/templates/{template_data['id']}/preview"
                        })
        return {"status": "success", "templates": templates_list}
    except Exception as e:
        logger.error(f"Error listing templates: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list templates: {str(e)}"
        )


@app.get("/api/templates/{template_id}")
async def get_template(template_id: str):
    """Get a specific template by ID"""
    try:
        template_dir = TEMPLATES_DIR / template_id
        if not template_dir.exists() or not template_dir.is_dir():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template with ID {template_id} not found"
            )

        metadata_file = template_dir / "metadata.json"
        if not metadata_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metadata not found for template {template_id}"
            )

        with open(metadata_file, "r") as f:
            template_data = json.load(f)

        # Add the image URL to the response
        template_data["imageUrl"] = f"/api/templates/{template_id}/image"

        return {"status": "success", "template": template_data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template {template_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get template: {str(e)}"
        )


@app.get("/api/templates/{template_id}/image")
async def get_template_image(template_id: str):
    """Get the image for a specific template"""
    try:
        image_path = TEMPLATES_DIR / template_id / "worksheet.png"
        if not image_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Image not found for template {template_id}"
            )

        return FileResponse(image_path, media_type="image/png")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting image for template {template_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get template image: {str(e)}"
        )


@app.get("/api/templates/{template_id}/preview")
async def get_template_preview(template_id: str):
    """Get a preview image for a template (smaller version)"""
    try:
        image_path = TEMPLATES_DIR / template_id / "worksheet.png"
        if not image_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Image not found for template {template_id}"
            )

        # For now, just return the original image
        # In a production environment, you might want to generate and cache thumbnails
        return FileResponse(image_path, media_type="image/png")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting preview for template {template_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get template preview: {str(e)}"
        )


# Initialize services
answer_grader = AnswerBoxGrader()
dotted_line_detector = DottedLineDetector()
blank_line_detector = BlankLineDetector()
blank_line_grader = None
blank_line_template = None
dotted_line_template = DottedLineTemplate()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/templates", StaticFiles(directory="templates"), name="templates")

# Create uploads directory if it doesn't exist
os.makedirs("uploads", exist_ok=True)


class GradeRequest(BaseModel):
    worksheet_id: str
    student_name: str = "Anonymous"


@app.post("/api/grade-worksheet")
async def grade_worksheet_endpoint(
        worksheet_id: str = Form(...),
        student_name: str = Form("Anonymous"),
        submission_image: UploadFile = File(...),
        ocr_service: GPTOCRService = Depends(get_ocr_service)
):
    """
    Grade a student's worksheet submission by:
    1. Saving the uploaded worksheet image
    2. Loading the template metadata
    3. For each question, extracting the answer using OCR
    4. Comparing with correct answers
    5. Returning detailed grading results
    """
    try:
        # 1. Save the uploaded image
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"submission_{worksheet_id}_{timestamp}{Path(submission_image.filename).suffix}"
        file_path = UPLOADS_DIR / filename

        # Read the image data for processing
        image_data = await submission_image.read()

        # Save a copy of the original submission
        with open(file_path, "wb") as buffer:
            buffer.write(image_data)

        # 2. Load the template metadata
        template_dir = TEMPLATES_DIR / worksheet_id
        if not template_dir.exists():
            raise HTTPException(status_code=404, detail=f"Template with ID {worksheet_id} not found")

        metadata_file = template_dir / "metadata.json"
        if not metadata_file.exists():
            raise HTTPException(status_code=404, detail=f"Metadata not found for template {worksheet_id}")

        with open(metadata_file, "r") as f:
            template_data = json.load(f)

        # Convert image to OpenCV format for processing
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file")

        results = []
        total_score = 0
        max_score = 0

        # 3. Process each question
        for i, question in enumerate(template_data.get("questions", []), 1):
            try:
                # Extract the answer region from the image
                # Check if coordinates are in an 'area' object or directly in the question
                if 'area' in question and isinstance(question['area'], dict):
                    area = question['area']
                    x, y = area.get('x', 0), area.get('y', 0)
                    width, height = area.get('width', 0), area.get('height', 0)
                else:
                    x, y = question.get('x', 0), question.get('y', 0)
                    width, height = question.get('width', 0), question.get('height', 0)

                # Log the extracted coordinates for debugging
                logger.info(f"Question {i} - Coordinates: x={x}, y={y}, width={width}, height={height}")

                # Check if coordinates are valid (within image bounds)
                h, w = img.shape[:2]
                if x < 0 or y < 0 or width <= 0 or height <= 0:
                    logger.warning(
                        f"Invalid coordinates for question {i}: "
                        f"x={x}, y={y}, width={width}, height={height} (image size: {w}x{h}). "
                        f"Question data: {json.dumps(question, default=str, indent=2)}"
                    )
                    continue

                if (x + width) > w or (y + height) > h:
                    logger.warning(
                        f"Question {i} coordinates extend beyond image boundaries: "
                        f"x={x}, y={y}, width={width}, height={height} (image size: {w}x{h})"
                    )
                    # Continue anyway but log a warning

                # Extract the answer region (with some padding)
                padding = 10
                h, w = img.shape[:2]
                x1 = max(0, x - padding)
                y1 = max(0, y - padding)
                x2 = min(w, x + width + padding)
                y2 = min(h, y + height + padding)

                answer_region = img[y1:y2, x1:x2]

                # Convert back to bytes for OCR
                _, buffer = cv2.imencode('.jpg', answer_region)
                answer_image_bytes = buffer.tobytes()

                # Use GPT OCR to extract text from the answer region (verbatim)
                # Save the cropped region to a temporary file and pass the path to GPTOCRService
                import tempfile, os
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                    tmp.write(answer_image_bytes)
                    tmp_path = tmp.name
                try:
                    # Rely on GPTOCRService default verbatim prompt
                    ocr_result = ocr_service.ocr_image(tmp_path)
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

                # Clean up the extracted text - keep only English letters and numbers
                student_answer = ''
                if ocr_result and hasattr(ocr_result, 'text'):
                    # Keep only alphanumeric characters and spaces
                    cleaned_text = ''.join(c.upper() for c in ocr_result.text if c.isalnum() or c.isspace())
                    # Remove extra whitespace and normalize
                    student_answer = ' '.join(cleaned_text.split())

                correct_answer = str(question.get("answer", "")).strip().upper()

                # Simple answer comparison (case-insensitive)
                is_correct = student_answer == correct_answer
                score = question.get("points", 1) if is_correct else 0

                # Provide feedback based on correctness
                if not student_answer:
                    feedback = "No answer detected"
                elif is_correct:
                    feedback = "Correct!"
                else:
                    feedback = f"Incorrect. Expected: {correct_answer}"

                results.append({
                    "question_number": i,
                    "question_text": question.get("text", f"Question {i}"),
                    "correct_answer": correct_answer,
                    "student_answer": student_answer or "[No answer detected]",
                    "is_correct": is_correct,
                    "score": score,
                    "max_score": question.get("points", 1),
                    "feedback": feedback
                })

                total_score += score
                max_score += question.get("points", 1)

            except Exception as e:
                logger.error(f"Error processing question {i}: {str(e)}")
                results.append({
                    "question_number": i,
                    "question_text": question.get("text", f"Question {i}"),
                    "error": f"Error processing answer: {str(e)}",
                    "score": 0,
                    "max_score": question.get("points", 1)
                })

        # 4. Return the results
        return {
            "status": "success",
            "student_name": student_name,
            "worksheet_id": worksheet_id,
            "submission_time": datetime.utcnow().isoformat(),
            "submission_image": f"/uploads/{filename}",
            "results": results,
            "total_score": total_score,
            "max_score": max_score,
            "percentage": round((total_score / max_score * 100) if max_score > 0 else 0, 2)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error grading worksheet: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error grading worksheet: {str(e)}")


@app.get("/api/templates/worksheet/{template_identifier}")
async def get_template(template_identifier: str):
    """
    Get a template by either its ID or worksheet ID.
    First tries to match by template ID, then falls back to worksheet ID.
    """
    try:
        # Clean the input - remove any 'ID: ' prefix and trim whitespace
        template_identifier = template_identifier.replace('ID:', '').strip()

        # Try to find by template ID first (exact match with directory name)
        template_dir = TEMPLATES_DIR / template_identifier
        if template_dir.exists() and template_dir.is_dir():
            metadata_file = template_dir / "metadata.json"
            if metadata_file.exists():
                with open(metadata_file, "r") as f:
                    template_data = json.load(f)
                    return {"status": "success", "template": template_data}

        # If not found by template ID, try to find by worksheet_id in metadata
        for dir_path in TEMPLATES_DIR.glob("*"):
            if not dir_path.is_dir():
                continue

            metadata_file = dir_path / "metadata.json"
            if not metadata_file.exists():
                continue

            try:
                with open(metadata_file, "r") as f:
                    template_data = json.load(f)
                    if str(template_data.get("worksheet_id")) == str(template_identifier) or \
                            str(template_data.get("id")) == str(template_identifier):
                        return {"status": "success", "template": template_data}
            except Exception as e:
                logger.warning(f"Error reading metadata from {metadata_file}: {str(e)}")
                continue

        raise HTTPException(
            status_code=404,
            detail=f"Template not found for identifier: {template_identifier}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting template: {str(e)}")


@app.post("/api/ocr-preview")
async def ocr_preview(
        image: UploadFile = File(...),
        template_id: str = Form(...),
        ocr_service: GPTOCRService = Depends(get_ocr_service)
):
    """
    Process an image with OCR for each question area defined in the template.
    Returns extracted text for each question area.
    """
    try:
        # Read the uploaded image
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Could not read the uploaded image")

        # Get the template data
        template_identifier = template_id.replace('ID:', '').strip()
        template_response = await get_template(template_identifier)

        if not isinstance(template_response, dict) or template_response.get("status") != "success":
            raise HTTPException(status_code=404, detail="Template not found")

        template = template_response.get("template", {})

        if not template.get("questions"):
            raise HTTPException(status_code=400, detail="No questions defined in template")

        # Convert to RGB for consistent ROI extraction
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        results = []

        # Process each question area
        for i, question in enumerate(template["questions"]):
            try:
                area = question.get("area", {})
                x, y, w, h = area.get("x", 0), area.get("y", 0), area.get("width", 0), area.get("height", 0)

                # Skip if area is not properly defined
                if w <= 0 or h <= 0:
                    results.append({
                        "question_id": i + 1,
                        "text": "",
                        "confidence": 0,
                        "error": "Invalid area dimensions"
                    })
                    continue

                # Extract the region of interest
                roi = img_rgb[y:y + h, x:x + w]

                # Save ROI to a temporary file and OCR with GPT
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_roi:
                    cv2.imwrite(tmp_roi.name, cv2.cvtColor(roi, cv2.COLOR_RGB2BGR))
                    temp_roi_path = tmp_roi.name
                try:
                    ocr_result = ocr_service.ocr_image(temp_roi_path)
                finally:
                    if os.path.exists(temp_roi_path):
                        try:
                            os.unlink(temp_roi_path)
                        except Exception:
                            pass

                # Clean up the extracted text - keep only English letters
                cleaned_text = ''
                if ocr_result and hasattr(ocr_result, 'text'):
                    # Keep only English letters (case-insensitive)
                    cleaned_text = ''.join(c for c in ocr_result.text if c.isalpha())
                    # If multiple characters, take the first one (most confident)
                    cleaned_text = cleaned_text[0].upper() if cleaned_text else ''

                results.append({
                    "question_id": i + 1,
                    "text": cleaned_text if cleaned_text else "No text",
                    "confidence": float(ocr_result.confidence) if hasattr(ocr_result,
                                                                          'confidence') and ocr_result.confidence else 0.0,
                    "area": area
                })

            except Exception as e:
                logger.error(f"Error processing question {i + 1}: {str(e)}")
                results.append({
                    "question_id": i + 1,
                    "text": "",
                    "confidence": 0,
                    "error": str(e)
                })

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in OCR preview: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")


# Template Management Endpoints

@app.get("/api/answer-boxes/templates", response_model=List[Dict[str, Any]])
async def list_answer_box_templates():
    """List all available answer box templates"""
    try:
        templates_dir = Path("data/answer_templates")
        
        # Create the directory if it doesn't exist
        templates_dir.mkdir(parents=True, exist_ok=True)
        
        templates = []
        
        # Check if directory exists and is accessible
        if not templates_dir.exists():
            logger.warning(f"Templates directory {templates_dir} does not exist")
            return []
            
        # Get all template files
        template_files = list(templates_dir.glob("tpl_*.json"))
        
        if not template_files:
            logger.info(f"No template files found in {templates_dir}")
            return []
        
        for file in template_files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    template_data = json.load(f)
                    templates.append({
                        "id": file.stem.replace('tpl_', ''),  # Remove 'tpl_' prefix from ID
                        "name": template_data.get("template_name", file.stem.replace('tpl_', '')),
                        "created_at": template_data.get("created_at", ""),
                        "num_questions": len(template_data.get("boxes", [])),
                        "image_path": f"/api/answer-boxes/templates/{file.stem}/image"
                    })
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON in template {file}: {str(e)}")
                continue
            except Exception as e:
                logger.error(f"Error loading template {file}: {str(e)}")
                continue
        
        logger.info(f"Successfully loaded {len(templates)} templates")
        return templates
        
    except PermissionError as e:
        error_msg = f"Permission denied when accessing templates directory: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=403, detail=error_msg)
    except Exception as e:
        error_msg = f"Failed to list templates: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/answer-boxes/templates/{template_id}", response_model=Dict[str, Any])
async def get_answer_box_template(template_id: str):
    """Get a specific answer box template by ID"""
    try:
        # Ensure the template ID starts with 'tpl_'
        template_id = template_id if template_id.startswith('tpl_') else f"tpl_{template_id}"
        template_path = Path(f"data/answer_templates/{template_id}.json")
        
        # Check if template file exists
        if not template_path.exists():
            # Try without the tpl_ prefix if not found
            alt_template_path = Path(f"data/answer_templates/{template_id.replace('tpl_', '')}.json")
            if alt_template_path.exists():
                template_path = alt_template_path
            else:
                raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
        
        # Load template data
        with open(template_path, 'r', encoding='utf-8') as f:
            template_data = json.load(f)
        
        # Get the correct template ID without path
        template_id = template_path.stem
        
        # Prepare response
        response = {
            "id": template_id.replace('tpl_', ''),  # Remove 'tpl_' prefix from ID
            "name": template_data.get("template_name", template_id.replace('tpl_', '')),
            "created_at": template_data.get("created_at", ""),
            "boxes": template_data.get("boxes", []),
            "image_path": f"/api/answer-boxes/templates/{template_id}/image"
        }
        
        # Include image data if available in the template
        if "image_data" in template_data:
            response["image_data"] = template_data["image_data"]
            
        logger.info(f"Successfully loaded template: {template_id}")
        return response
            
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON format in template {template_id}: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to load template {template_id}: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/api/answer-boxes/templates/{template_id}/image")
async def get_template_image(template_id: str):
    """Get the image for a specific template"""
    try:
        # Ensure the template ID starts with 'tpl_'
        template_id = template_id if template_id.startswith('tpl_') else f"tpl_{template_id}"
        template_path = Path(f"data/answer_templates/{template_id}.json")
        
        # Check if template file exists
        if not template_path.exists():
            # Try without the tpl_ prefix if not found
            alt_template_path = Path(f"data/answer_templates/{template_id.replace('tpl_', '')}.json")
            if alt_template_path.exists():
                template_path = alt_template_path
                template_id = template_path.stem
            else:
                raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
        
        # Load template data
        with open(template_path, 'r', encoding='utf-8') as f:
            template_data = json.load(f)
        
        # Check if image data exists in the template
        if "image_data" not in template_data:
            raise HTTPException(status_code=404, detail=f"No image data found for template {template_id}")
        
        # Extract image data (assuming base64 encoded)
        image_data = template_data["image_data"]
        if "," in image_data:  # Handle data URL format
            image_data = image_data.split(",", 1)[1]
        
        # Decode base64 image
        try:
            image_bytes = base64.b64decode(image_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image data: {str(e)}")
        
        # Determine content type
        content_type = template_data.get("image_content_type", "image/png")
        
        return Response(content=image_bytes, media_type=content_type)
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to load template image {template_id}: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


# Answer Box Endpoints

class AnswerBoxTemplate(BaseModel):
    template_id: str
    image_path: str
    questions: List[Dict[str, Any]]
    created_at: str

class AnswerBoxDetectionRequest(BaseModel):
    image_path: str

class AnswerBoxGradeRequest(BaseModel):
    template_id: str
    student_image_path: str

@app.post("/api/answer-boxes/detect")
async def detect_answer_boxes(
    file: UploadFile = File(...)
):
    """
    Detect answer boxes in an uploaded image using color-based detection.
    
    Args:
        file: The uploaded image file
        
    Returns:
        JSON response with list of detected answer boxes or error message
    """
    temp_path = None
    try:
        logger.info("Starting answer box detection with color-based detector")
        
        # Read the file content once
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        # Create a temporary file for the uploaded image
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(file_content)
            temp_path = Path(temp_file.name)
        
        # Use the color-based detector
        detector = AnswerBoxDetector()
        boxes = detector.detect_boxes(str(temp_path))
        
        if not boxes:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No answer boxes detected. "
                    "Possible reasons:\n"
                    "1. The image quality may be too low\n"
                    "2. No answer boxes are visible\n"
                    "3. The image may be rotated incorrectly\n"
                    "Please try with a clearer image or adjust the detection parameters."
                )
            )
        
        # Convert to the expected format
        result = []
        for i, box in enumerate(boxes):
            # Get bounding rectangle from contour
            x, y, w, h = cv2.boundingRect(box.contour)
            result.append({
                'id': box.id,
                'x': int(x),
                'y': int(y),
                'width': int(w),
                'height': int(h),
                'confidence': 1.0,  # Original detector doesn't provide confidence
                'class_id': 0,
                'class_name': 'answer_box',
                'color': box.color
            })
        
        logger.info(f"Detection successful. Found {len(result)} boxes.")
        return {"boxes": result, "detector": "color"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Detection failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect answer boxes: {str(e)}"
        )
    finally:
        # Clean up the temporary file if it exists
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
                logger.debug(f"Removed temporary file: {temp_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {temp_path}: {str(e)}")
                logger.error(f"Error removing temporary file {temp_path}: {str(e)}")

@app.post("/api/answer-boxes/templates", response_model=Dict[str, str])
async def create_answer_box_template(
    template_name: str = Form(...),
    image: UploadFile = File(...),
    boxes: str = Form("[]"),
    answers: str = Form("{}")
):
    """
    Create a new answer box template from an uploaded image.
    
    Args:
        template_name: Name for the new template
        image: The template image with answer boxes
        boxes: JSON string of box data with coordinates and sizes
        answers: JSON string of {question_id: answer} pairs
    """
    try:
        # Create template id
        template_id = f"tpl_{int(datetime.utcnow().timestamp())}"

        # Ensure answer templates images directory exists (AnswerBoxGrader sets this up)
        images_dir = answer_grader.images_dir if hasattr(answer_grader, 'images_dir') else Path("data/answer_templates/images")
        images_dir.mkdir(parents=True, exist_ok=True)

        # Save the uploaded image into data/answer_templates/images with consistent name
        image_extension = Path(image.filename).suffix or '.png'
        image_filename = f"worksheet_{template_id}{image_extension}"
        image_path = images_dir / image_filename

        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        # Parse boxes and answers JSON
        try:
            boxes_data = json.loads(boxes)
            answers_dict = json.loads(answers)
            logger.info(f"Received {len(boxes_data)} boxes and {len(answers_dict)} answers")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON data: {str(e)}"
            )

        # Read image dimensions
        img = cv2.imread(str(image_path))
        if img is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not read the uploaded image"
            )
        height, width = img.shape[:2]

        # Create template data
        template_data = {
            "id": template_id,
            "name": template_name,
            "created_at": datetime.utcnow().isoformat(),
            # Point to the new images location under data/answer_templates/images
            "image_path": str(image_path),
            "image_dimensions": {
                "width": width,
                "height": height
            },
            "questions": []
        }

        # Add box data to template
        for i, box in enumerate(boxes_data, 1):
            question_id = f"Q{i}"
            x, y, w, h = box.get('x', 0), box.get('y', 0), box.get('width', 0), box.get('height', 0)
            
            # Calculate relative positions
            rel_x = x / width if width > 0 else 0
            rel_y = y / height if height > 0 else 0
            rel_w = w / width if width > 0 else 0
            rel_h = h / height if height > 0 else 0
            
            question_data = {
                "id": question_id,
                "color": box.get('color', 'green'),
                "expected_answer": answers_dict.get(question_id, ""),
                "position": {
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h
                },
                "relative_position": {
                    "x": rel_x,
                    "y": rel_y,
                    "width": rel_w,
                    "height": rel_h
                },
                "area": w * h
            }
            template_data["questions"].append(question_data)

        # Save the template
        template_json_path = answer_grader.templates_dir / f"{template_id}.json"
        with open(template_json_path, 'w') as f:
            json.dump(template_data, f, indent=2)
            
        logger.info(f"Saved template {template_id} with {len(template_data['questions'])} boxes")
        
        logger.info(f"Created answer box template {template_id} with {len(answers_dict)} answers")
        return {"status": "success", "template_id": template_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating answer box template: {str(e)}", exc_info=True)
        # No per-template directory is created under data/templates now; nothing to remove there.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create template: {str(e)}"
        )

@app.get("/api/answer-boxes/templates/{template_id}", response_model=Dict[str, Any])
async def get_answer_box_template(template_id: str):
    """Get an answer box template by ID."""
    try:
        template_path = Path(f"data/answer_templates/{template_id}.json")
        if not template_path.exists():
            raise HTTPException(status_code=404, detail="Template not found")
            
        with open(template_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/answer-boxes/grade", response_model=Dict[str, Any])
async def grade_answer_sheet(
    template_id: str = Form(...),
    student_image: UploadFile = File(...),
    ocr_service: GPTOCRService = Depends(get_ocr_service)
):
    """
    Grade a student's answer sheet against a template.
    
    Args:
        template_id: ID of the template to use
        student_image: The student's answer sheet image
    """
    try:
        # Save uploaded student image
        upload_dir = Path("uploads/student_answers")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        student_image_path = upload_dir / f"{int(datetime.now().timestamp())}_{student_image.filename}"
        with open(student_image_path, "wb") as buffer:
            shutil.copyfileobj(student_image.file, buffer)
        
        # Grade the answers
        results = answer_grader.grade_answers(
            template_id=template_id,
            student_image_path=str(student_image_path),
            ocr_service=ocr_service
        )
        
        return results
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Dotted Line Detection Endpoints

@app.post("/api/dotted-lines/detect")
async def detect_dotted_lines(
    image: UploadFile = File(...),
    dot_size: int = Form(2),
    dot_interval: int = Form(10),
    min_line_length: int = Form(50)
):
    """
    Detect dotted lines in an uploaded image.
    
    Args:
        image: The uploaded image file
        dot_size: Expected size of dots in pixels
        dot_interval: Expected interval between dots in pixels
        min_line_length: Minimum length of a line to be considered valid
        
    Returns:
        JSON with detected lines information
    """
    try:
        # Save the uploaded file temporarily
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        
        file_path = temp_dir / f"temp_{uuid.uuid4()}.png"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        
        # Configure detector with parameters
        detector = DottedLineDetector(
            min_line_length=min_line_length,
            dot_interval=dot_interval,
            dot_size=dot_size
        )
        
        # Detect lines
        lines = detector.detect_lines(str(file_path))
        
        # Convert lines to serializable format
        serializable_lines = [{
            'id': line.id,
            'start_point': line.start_point,
            'end_point': line.end_point,
            'line_type': line.line_type,
            'length': line.length,
            'metadata': line.metadata or {}
        } for line in lines]
        
        # Clean up
        file_path.unlink()
        
        return JSONResponse({
            'status': 'success',
            'lines': serializable_lines
        })
        
    except Exception as e:
        logger.error(f"Error detecting dotted lines: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error detecting dotted lines: {str(e)}")


@app.post("/api/dotted-lines/templates")
async def create_dotted_line_template(
    template_name: str = Form(...),
    image: UploadFile = File(...),
    lines: str = Form("[]")
):
    """
    Create a new template with detected dotted lines.
    
    Args:
        template_name: Name for the template
        image: The template image
        lines: JSON string of detected lines with coordinates
        
    Returns:
        JSON with created template information
    """
    try:
        # Create template ID
        template_id = f"dotted_{int(datetime.utcnow().timestamp())}"

        # Create dotted_templates dirs
        dotted_templates_dir = Path("data/dotted_templates")
        images_dir = dotted_templates_dir / "images"
        dotted_templates_dir.mkdir(exist_ok=True, parents=True)
        images_dir.mkdir(exist_ok=True, parents=True)

        # Save the uploaded image to data/dotted_templates/images
        image_extension = Path(image.filename).suffix or '.png'
        image_filename = f"worksheet_{template_id}{image_extension}"
        image_path = images_dir / image_filename

        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        # Parse lines JSON
        try:
            # First try to parse as JSON string
            if isinstance(lines, str):
                lines_data = json.loads(lines)
            else:
                lines_data = lines
                
            if not isinstance(lines_data, list):
                raise ValueError("Lines must be a list")
                
            logger.info(f"Received {len(lines_data)} dotted lines")
            logger.debug(f"Lines data: {lines_data}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data: {str(e)}")
            logger.error(f"Raw lines data: {lines}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Invalid JSON data", "details": str(e)}
            )

        # Read image dimensions
        img = cv2.imread(str(image_path))
        if img is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not read the uploaded image"
            )
        height, width = img.shape[:2]
        
        # Create template data structure
        template_data = {
            "id": template_id,
            "name": template_name,
            "created_at": datetime.utcnow().isoformat(),
            # Store images under data/dotted_templates/images like other modules
            "image_path": str(image_path),
            "image_dimensions": {
                "width": width,
                "height": height
            },
            "questions": []
        }

        # Process each line
        for i, line in enumerate(lines_data, 1):
            pos = line.get('position', {})
            x1, y1 = pos.get('x', 0), pos.get('y', 0)
            x2, y2 = pos.get('x2', 0), pos.get('y2', 0)
            
            # Generate a unique ID if not provided
            line_id = line.get('id', f"Q{i}")
            
            # Calculate relative positions
            rel_x1 = x1 / width if width > 0 else 0
            rel_y1 = y1 / height if height > 0 else 0
            rel_x2 = x2 / width if width > 0 else 0
            rel_y2 = y2 / height if height > 0 else 0
            
            line_data = {
                "id": line_id,
                "color": line.get('color', 'green'),
                "expected_answer": line.get('expected_answer', ''),
                "position": {
                    "x": x1,
                    "y": y1,
                    "x2": x2,
                    "y2": y2,
                    "length": pos.get('length', 0)
                },
                "relative_position": {
                    "x": rel_x1,
                    "y": rel_y1,
                    "x2": rel_x2,
                    "y2": rel_y2,
                    "length": pos.get('length', 0) / max(width, height) if max(width, height) > 0 else 0
                },
                "metadata": line.get('metadata', {})
            }
            template_data["questions"].append(line_data)

        # Save the template as a single JSON file in the dotted_templates directory
        template_json_path = dotted_templates_dir / f"{template_id}.json"
        with open(template_json_path, 'w') as f:
            json.dump(template_data, f, indent=2)
            
        logger.info(f"Saved dotted line template {template_id} with {len(template_data['questions'])} questions")
        return {
            "status": "success",
            "template_id": template_id,
            "id": template_id,  # For backward compatibility
            "data": template_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating dotted line template: {str(e)}", exc_info=True)
        # Clean up if something went wrong
        if 'image_path' in locals() and image_path.exists():
            image_path.unlink()
        if 'template_json_path' in locals() and template_json_path.exists():
            template_json_path.unlink()
            
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create template: {str(e)}"
        )


@app.get("/api/dotted-lines/templates")
async def list_dotted_line_templates():
    """List all available dotted line templates"""
    try:
        templates = dotted_line_template.list_templates()
        return JSONResponse({
            'status': 'success',
            'templates': templates
        })
    except Exception as e:
        logger.error(f"Error listing templates: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing templates: {str(e)}")


@app.get("/api/dotted-lines/templates/{template_id}")
async def get_dotted_line_template(template_id: str):
    """Get a specific dotted line template by ID"""
    try:
        template = dotted_line_template.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
            
        return JSONResponse({
            'status': 'success',
            'template': template
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting template: {str(e)}")


@app.delete("/api/dotted-lines/templates/{template_id}")
async def delete_dotted_line_template(template_id: str):
    """Delete a dotted line template"""
    try:
        success = dotted_line_template.delete_template(template_id)
        if not success:
            raise HTTPException(status_code=404, detail="Template not found")
            
        return JSONResponse({
            'status': 'success',
            'message': 'Template deleted successfully'
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting template: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting template: {str(e)}")


@app.post("/api/dotted-lines/grade")
async def grade_dotted_line_worksheet(
    template_id: str = Form(...),
    student_image: UploadFile = File(...),
    student_name: str = Form("Anonymous"),
    ocr_service: GPTOCRService = Depends(get_ocr_service)
):
    """
    Grade a student's worksheet with dotted lines against a template.
    
    Args:
        template_id: ID of the dotted line template
        student_image: The student's completed worksheet image
        student_name: Name of the student (optional)
        
    Returns:
        JSON with grading results including detected answers and correctness
    """
    try:
        # 1. Load the template
        template = dotted_line_template.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # 2. Save the uploaded student image
        upload_dir = Path("uploads/student_answers")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = int(datetime.now().timestamp())
        student_image_path = upload_dir / f"dotted_{timestamp}_{student_image.filename}"
        with open(student_image_path, "wb") as buffer:
            shutil.copyfileobj(student_image.file, buffer)
        
        # 3. Load and validate student's image
        student_img = cv2.imread(str(student_image_path))
        if student_img is None:
            raise HTTPException(status_code=400, detail="Could not read student's image")
        
        student_height, student_width = student_img.shape[:2]
        
        # 4. Get template dimensions for scaling if needed
        template_width = template.get('image_dimensions', {}).get('width', student_width)
        template_height = template.get('image_dimensions', {}).get('height', student_height)
        
        # Calculate scale factors (if template dimensions are available)
        width_scale = student_width / template_width if template_width else 1.0
        height_scale = student_height / template_height if template_height else 1.0
        
        # 5. Process each question in the template
        results = {
            'template_id': template_id,
            'graded_at': datetime.utcnow().isoformat(),
            'student_name': student_name,
            'image_path': str(student_image_path),
            'answers': []
        }
        
        for question in template.get('questions', []):
            question_id = question.get('id', '')
            expected_answer = question.get('expected_answer', '').strip().lower()
            
            # Skip questions without expected answers
            if not expected_answer:
                logger.warning(f"Skipping question {question_id}: No expected answer provided")
                continue
                
            # Get the relative position of the answer region
            rel_pos = question.get('relative_position', {})
            
            try:
                # Calculate absolute positions in the student's image
                x1 = int(rel_pos.get('x', 0) * student_width)
                y1 = int(rel_pos.get('y', 0) * student_height)
                x2 = int(rel_pos.get('x2', 0) * student_width)
                y2 = int(rel_pos.get('y2', 0) * student_height)
                
                # Add 70px padding to top and 10px to bottom of answer region
                top_padding = 70  # 70px top padding
                bottom_padding = 20  # 10px bottom padding
                
                x1 = max(0, x1)  # No horizontal padding
                y1 = max(0, y1 - top_padding)  # Top padding
                x2 = min(student_width, x2)  # No horizontal padding
                y2 = min(student_height, y2 + bottom_padding)  # Bottom padding
                
                # Ensure valid region
                if x2 <= x1 or y2 <= y1:
                    raise ValueError(f"Invalid region dimensions: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
                
                # Extract and preprocess the answer region
                answer_region = student_img[y1:y2, x1:x2]
                
                # Save to temporary file for OCR
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_img:
                    temp_path = temp_img.name
                    cv2.imwrite(temp_path, answer_region)
                
                try:
                    # Perform OCR on the answer region using GPT OCR
                    ocr_result = ocr_service.ocr_image(temp_path)
                    detected_text = ocr_result.text.strip().lower() if ocr_result and hasattr(ocr_result, 'text') else ''
                    
                    # Clean and normalize the detected text
                    detected_text = ' '.join(detected_text.split())  # Normalize whitespace
                    detected_text = ''.join(c for c in detected_text if c.isalnum() or c.isspace())
                    
                    # Check if expected answer is contained within the detected text (case-insensitive)
                    # This makes the grading more lenient and forgiving of OCR errors
                    is_correct = expected_answer.lower() in detected_text.lower() if expected_answer else False
                    
                    # Add to results
                    results['answers'].append({
                        'question_id': question_id,
                        'expected': expected_answer,
                        'actual': detected_text,
                        'is_correct': is_correct,
                        'position': {
                            'x': x1,
                            'y': y1,
                            'x2': x2,
                            'y2': y2
                        },
                        'metadata': {
                            'confidence': getattr(ocr_result, 'confidence', 0) if ocr_result else 0,
                            'processing_time': getattr(ocr_result, 'processing_time', 0) if ocr_result else 0
                        }
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing question {question_id}: {str(e)}")
                    # Include position data in the error response
                    results['answers'].append({
                        'question_id': question_id,
                        'expected': expected_answer,
                        'actual': f"Error: {str(e)}",
                        'is_correct': False,
                        'error': str(e),
                        'position': {
                            'x': x1,
                            'y': y1,
                            'x2': x2,
                            'y2': y2
                        },
                        'metadata': {
                            'confidence': 0,
                            'processing_time': 0
                        }
                    })
                finally:
                    # Clean up temporary file
                    if os.path.exists(temp_path):
                        try:
                            os.unlink(temp_path)
                        except Exception as e:
                            logger.warning(f"Failed to remove temporary file {temp_path}: {str(e)}")
            
            except Exception as e:
                logger.error(f"Error processing question {question_id}: {str(e)}")
                results['answers'].append({
                    'question_id': question_id,
                    'expected': expected_answer,
                    'actual': f"Error: {str(e)}",
                    'is_correct': False,
                    'error': str(e),
                    'position': {
                        'x': x1,
                        'y': y1,
                        'x2': x2,
                        'y2': y2
                    },
                    'metadata': {
                        'confidence': 0,
                        'processing_time': 0
                    }
                })
        
        # Calculate overall score
        total_questions = len(results['answers'])
        correct_answers = sum(1 for a in results['answers'] if a.get('is_correct', False))
        results['score'] = {
            'correct': correct_answers,
            'total': total_questions,
            'percentage': round((correct_answers / total_questions) * 100, 2) if total_questions > 0 else 0
        }
        
        return JSONResponse(results)
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error grading worksheet: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/api/blank-lines/detect")
async def detect_blank_lines(image: UploadFile = File(...)):
    """
    Detect blank (underscore-style) answer fields in a worksheet image.
    Returns a list of detected blank lines with their coordinates and sizes.
    """
    import numpy as np
    import cv2
    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(status_code=400, detail="Could not decode image")
        blanks = blank_line_detector.detect_blank_lines(img)
        return {"success": True, "lines": blanks, "count": len(blanks)}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Directory for blank line templates
BLANK_TEMPLATE_DIR = Path("data/blank_templates")
BLANK_TEMPLATE_IMG_DIR = BLANK_TEMPLATE_DIR / "images"
BLANK_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
BLANK_TEMPLATE_IMG_DIR.mkdir(parents=True, exist_ok=True)

@app.post("/api/blank-lines/templates")
async def create_blank_line_template(
    template_name: str = Form(...),
    image: UploadFile = File(...),
    lines: str = Form(...)
):
    """
    Save a blank line template (name, image, lines) as JSON and image file.
    """
    import json
    from datetime import datetime
    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file")
        # Save image
        template_id = f"blank_{int(datetime.utcnow().timestamp())}"
        
        img_path = BLANK_TEMPLATE_IMG_DIR / f"{template_id}.png"
        cv2.imwrite(str(img_path), img)
        
        # Save JSON
        lines_data = json.loads(lines)
        # Ensure id is q1, q2, ... and expectedAnswer is present
        for idx, l in enumerate(lines_data):
            l['id'] = f"q{idx+1}"
            if 'expectedAnswer' not in l:
                l['expectedAnswer'] = ''
        template_data = {
            "id": template_id,
            "name": template_name,
            "created_at": datetime.utcnow().isoformat(),
            "image_path": str(img_path),
            "lines": lines_data
        }
        json_path = BLANK_TEMPLATE_DIR / f"{template_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(template_data, f, ensure_ascii=False, indent=2)
        return {"status": "success", "template_id": template_id, "template": template_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/blank-lines/templates")
async def list_blank_line_templates():
    """List all blank line templates."""
    import json
    templates = []
    for f in BLANK_TEMPLATE_DIR.glob("blank_*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                templates.append({
                    "id": data.get("id"),
                    "name": data.get("name"),
                    "created_at": data.get("created_at")
                })
        except Exception:
            continue
    return templates

@app.get("/api/blank-lines/templates/{template_id}")
async def get_blank_line_template(template_id: str):
    import json
    json_path = BLANK_TEMPLATE_DIR / f"{template_id}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Optionally, return base64 image for preview
    img_path = Path(data["image_path"])
    img_b64 = None
    if img_path.exists():
        with open(img_path, "rb") as imgf:
            img_b64 = base64.b64encode(imgf.read()).decode("utf-8")
    data["image_b64"] = img_b64
    return data


@app.post("/api/blank-lines/grade")
async def grade_blank_line_worksheet(
    template_id: str = Form(...),
    student_image: UploadFile = File(...),
    student_name: str = Form("Anonymous"),
    ocr_service: GPTOCRService = Depends(get_ocr_service)
):
    """
    Grade a student's worksheet with blank lines against a template.
    
    Args:
        template_id: ID of the blank line template
        student_image: The student's completed worksheet image
        student_name: Name of the student (optional)
        
    Returns:
        JSON with grading results including detected answers and correctness
    """
    try:
        # 1. Load the template
        template = await get_blank_line_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # 2. Save the uploaded student image
        upload_dir = Path("uploads/student_answers/blank_line")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = int(datetime.now().timestamp())
        student_image_path = upload_dir / f"blank_{timestamp}_{student_image.filename}"
        with open(student_image_path, "wb") as buffer:
            shutil.copyfileobj(student_image.file, buffer)
        
        # 3. Load and validate student's image
        student_img = cv2.imread(str(student_image_path))
        if student_img is None:
            raise HTTPException(status_code=400, detail="Could not read student's image")
        
        student_height, student_width = student_img.shape[:2]
        
        # 4. Get template image dimensions for scaling if needed
        template_img = cv2.imread(template['image_path'])
        if template_img is None:
            raise HTTPException(status_code=500, detail="Could not read template image")
            
        template_height, template_width = template_img.shape[:2]
        
        # Calculate scale factors
        width_scale = student_width / template_width
        height_scale = student_height / template_height
        
        # 5. Process each question in the template
        results = {
            'template_id': template_id,
            'graded_at': datetime.utcnow().isoformat(),
            'student_name': student_name,
            'image_path': str(student_image_path),
            'answers': []
        }
        
        for line in template.get('lines', []):
            question_id = line.get('id', '')
            expected_answer = line.get('expectedAnswer', '').strip().lower()
            
            # Skip questions without expected answers
            if not expected_answer:
                logger.warning(f"Skipping question {question_id}: No expected answer provided")
                continue
                
            # Get the position of the answer region
            x1 = int(line.get('x', 0) * width_scale)
            y1 = int(line.get('y', 0) * height_scale)
            x2 = int((line.get('x', 0) + line.get('width', 0)) * width_scale)
            y2 = int((line.get('y', 0) + line.get('height', 0)) * height_scale)
            
            # Add 70px padding to top and 20px to bottom of answer region
            top_padding = 70  # 70px top padding
            bottom_padding = 20  # 20px bottom padding
            
            x1 = max(0, x1)  # No horizontal padding
            y1 = max(0, y1 - top_padding)  # Top padding
            x2 = min(student_width, x2)  # No horizontal padding
            y2 = min(student_height, y2 + bottom_padding)  # Bottom padding
            
            # Ensure valid region
            if x2 <= x1 or y2 <= y1:
                logger.warning(f"Invalid region dimensions for question {question_id}: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
                continue
            
            # Extract and preprocess the answer region
            answer_region = student_img[y1:y2, x1:x2]
            
            # Save to temporary file for OCR
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_img:
                temp_path = temp_img.name
                cv2.imwrite(temp_path, answer_region)
            
            try:
                # Perform OCR on the answer region using GPT OCR
                ocr_result = ocr_service.ocr_image(temp_path)
                detected_text = ocr_result.text.strip().lower() if ocr_result and hasattr(ocr_result, 'text') else ''
                
                # Clean and normalize the detected text
                detected_text = ' '.join(detected_text.split())  # Normalize whitespace
                detected_text = ''.join(c for c in detected_text if c.isalnum() or c.isspace())
                
                # Check if expected answer is contained within the detected text (case-insensitive)
                is_correct = expected_answer.lower() in detected_text.lower() if expected_answer else False
                
                # Add to results
                results['answers'].append({
                    'question_id': question_id,
                    'expected': expected_answer,
                    'actual': detected_text,
                    'is_correct': is_correct,
                    'position': {
                        'x': x1,
                        'y': y1,
                        'x2': x2,
                        'y2': y2
                    },
                    'metadata': {
                        'confidence': getattr(ocr_result, 'confidence', 0) if ocr_result else 0,
                        'processing_time': getattr(ocr_result, 'processing_time', 0) if ocr_result else 0
                    }
                })
                
            except Exception as e:
                logger.error(f"Error processing question {question_id}: {str(e)}")
                # Include position data in the error response
                results['answers'].append({
                    'question_id': question_id,
                    'expected': expected_answer,
                    'actual': f"Error: {str(e)}",
                    'is_correct': False,
                    'error': str(e),
                    'position': {
                        'x': x1,
                        'y': y1,
                        'x2': x2,
                        'y2': y2
                    },
                    'metadata': {
                        'confidence': 0,
                        'processing_time': 0
                    }
                })
            finally:
                # Clean up temporary file
                if os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception as e:
                        logger.warning(f"Failed to remove temporary file {temp_path}: {str(e)}")
        
        # Calculate overall score
        total_questions = len(results['answers'])
        correct_answers = sum(1 for a in results['answers'] if a.get('is_correct', False))
        results['score'] = {
            'correct': correct_answers,
            'total': total_questions,
            'percentage': round((correct_answers / total_questions) * 100, 2) if total_questions > 0 else 0
        }
        
        return JSONResponse(results)
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error grading worksheet: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(status_code=500, detail=error_msg)
    return data

@app.post("/api/sa-boxes/detect")
async def detect_sa_boxes(file: UploadFile = File(...)):
    """
    Detect answer boxes in an uploaded image (short answer setup).
    """
    try:
        # Save uploaded file to a temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        # Use AnswerBoxDetector from answer_box_service (imported in sa_service.py)
        from app.services.sa_service import AnswerBoxDetector
        detector = AnswerBoxDetector()
        boxes = detector.detect_boxes(tmp_path)
        # Convert to dicts for JSON
        box_dicts = []
        for i, box in enumerate(boxes):
            # box.contour is np.ndarray, can't be serialized; skip it
            box_dicts.append({
                "id": f"box_{i+1}",
                "x": int(box.contour[:, 0, 0].min()),
                "y": int(box.contour[:, 0, 1].min()),
                "width": int(box.contour[:, 0, 0].max() - box.contour[:, 0, 0].min()),
                "height": int(box.contour[:, 0, 1].max() - box.contour[:, 0, 1].min()),
                "color": box.color
            })
        os.unlink(tmp_path)
        return {"boxes": box_dicts}
    except Exception as e:
        logging.exception("SA box detection failed")
        raise HTTPException(status_code=500, detail=f"Failed to detect answer boxes: {str(e)}")


@app.post("/api/sa-boxes/templates")
async def create_sa_template(
        template_id: str = Form(...),
        template_name: str = Form(...),
        created_at: str = Form(...),
        image_path: str = Form(...),
        image_dimensions: str = Form(...),
        image: UploadFile = File(...),
        boxes: str = Form(...),
        answers: str = Form(...)
):
    """
    Save a short answer template (boxes + model answers) with metadata.
    """
    try:
        # Save image to disk (optional, for later use/display)
        img_save_dir = Path("data/sa_templates/images")
        img_save_dir.mkdir(parents=True, exist_ok=True)

        # Save the uploaded image
        image_path = img_save_dir / f"{template_id}_{image.filename}"
        with open(image_path, "wb") as f:
            f.write(await image.read())

        # Parse the form data
        box_list = json.loads(boxes)
        answer_dict = json.loads(answers)

        # Create a new answer dictionary with full answers from box data
        full_answer_dict = {}
        for box in box_list:
            if 'id' in box and 'answer' in box:
                full_answer_dict[box['id']] = box['answer']

        # Use the full answers instead of the separate answers dict
        image_dimensions_dict = json.loads(image_dimensions)

        # Save the template with metadata
        mgr = ShortAnswerTemplateManager()
        mgr.save_template(
            template_id=template_id,
            boxes=box_list,
            model_answers=full_answer_dict,  # Use full answers here
            image_dimensions=image_dimensions_dict,
            template_name=template_name,
            created_at=created_at,
            image_path=str(image_path)
        )
        return {
            "template_id": template_id,
            "message": "Template saved successfully with metadata"
        }
    except Exception as e:
        logging.exception("Failed to save SA template")
        raise HTTPException(status_code=500, detail=f"Failed to save template: {str(e)}")

@app.get("/api/sa-boxes/templates")
async def list_sa_templates():
    """
    List all short answer templates (GET).
    """
    try:
        template_dir = Path("data/sa_templates")
        templates = []
        for p in template_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    templates.append({
                        "id": p.stem,
                        "name": data.get("template_name", p.stem)
                    })
            except Exception:
                continue
        return templates
    except Exception as e:
        logging.exception("Failed to list SA templates")
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}")

@app.get("/api/sa-boxes/templates/{template_id}")
async def get_sa_template(template_id: str):
    """
    Get a specific short answer template by ID.
    """
    template_path = Path(f"data/sa_templates/{template_id}.json")
    if not template_path.exists():
        template_path = Path(f"data/sa_templates/tpl_{template_id}.json")
        if not template_path.exists():
            raise HTTPException(status_code=404, detail="Template not found")
    with open(template_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/sa-boxes/grade")
async def grade_sa_worksheet(
    template_id: str = Form(...),
    student_image: UploadFile = File(...),
    student_name: str = Form("Anonymous"),
    similarity_threshold: float = Form(0.75),
    partial_threshold: float = Form(0.4),
    full_threshold: Optional[float] = Form(None),
    ocr_service: GPTOCRService = Depends(get_ocr_service)
):
    """
    Grade a student's short answer worksheet against a template.
    
    Args:
        template_id: ID of the template to use
        student_image: The student's completed worksheet image
        student_name: Name of the student (optional)
        
    Returns:
        JSON with grading results including detected answers and correctness
    """
    import tempfile
    import shutil
    
    temp_dir = Path(tempfile.mkdtemp())
    try:
        # Save uploaded file to temp location
        img_path = temp_dir / student_image.filename
        with open(img_path, "wb") as buffer:
            shutil.copyfileobj(student_image.file, buffer)
        
        # Load template
        template_path = Path("data/sa_templates") / f"{template_id}.json"
        if not template_path.exists():
            raise HTTPException(status_code=404, detail="Template not found")
            
        with open(template_path, "r", encoding="utf-8") as f:
            template = json.load(f)
        
        # Initialize grader with semantic grading enabled and configured thresholds
        # full_threshold defaults to similarity_threshold if not explicitly provided
        eff_full_threshold = full_threshold if full_threshold is not None else similarity_threshold
        grader = ShortAnswerGrader(
            ocr_service,
            similarity_threshold=eff_full_threshold,
            use_semantic=True,
            partial_threshold=partial_threshold,
            full_threshold=eff_full_threshold,
            leniency_bias=0.20
        )

        # Run grading (await the async call)
        grading_results = await grader.grade(str(img_path), template)
        
        # Log the grading results for debugging
        logger.info(f"Grading results: {json.dumps(grading_results, indent=2)}")

        # Ensure the response has the expected format
        if isinstance(grading_results, dict) and 'answers' in grading_results:
            # If answers is already in the correct format, use it as is
            answers = grading_results['answers']
        else:
            # Otherwise, convert to the expected format
            answers = grading_results.get('answers', [])
            
        # Calculate score
        total_questions = len(answers)
        correct_answers = sum(1 for a in answers if a.get('is_correct', False))
        
        # Build response
        summary = grading_results.get('summary', {}) if isinstance(grading_results, dict) else {}
        # Compute credit-based percentage if summary present
        sum_credits = float(summary.get('sum_credits', correct_answers))
        max_credits = float(summary.get('max_credits', total_questions or 1))
        credit_percentage = round((sum_credits / max_credits) * 100, 2) if max_credits > 0 else 0.0

        response = {
            "student_name": student_name,
            "template_id": template_id,
            "graded_at": datetime.now().isoformat(),
            "answers": answers,
            "score": correct_answers,
            "total": total_questions,
            "summary": summary,
            "percentage": credit_percentage
        }
        
        logger.info(f"Final grading response: {json.dumps(response, indent=2)}")
        return response
        
    except Exception as e:
        logger.error(f"Error grading worksheet: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)

# GPT OCR Test Route
@app.get("/gpt-ocr-test", response_class=HTMLResponse)
def gpt_ocr_test_page(request: Request):
    return templates.TemplateResponse("gpt_ocr_test.html", {"request": request})

@app.post("/gpt-ocr", response_class=HTMLResponse)
def gpt_ocr_extract(request: Request, image: UploadFile = File(...)):
    ocr_text = None
    error = None
    try:
        # Save uploaded image to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(image.file.read())
            tmp_path = tmp.name
        # Run GPT OCR
        gpt_ocr = GPTOCRService()
        result = gpt_ocr.ocr_image(tmp_path)
        ocr_text = result.text
        os.remove(tmp_path)
    except Exception as e:
        error = str(e)
    return templates.TemplateResponse("gpt_ocr_test.html", {"request": request, "ocr_text": ocr_text, "error": error})

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
