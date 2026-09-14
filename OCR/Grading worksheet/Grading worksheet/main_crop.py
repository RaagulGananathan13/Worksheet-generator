import os
import uvicorn
import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pathlib import Path
import base64
import tempfile
from typing import Optional

# Create necessary directories
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory="templates")

app = FastAPI(title="Image Cropper API")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

class ImageCropper:
    @staticmethod
    def detect_green_border(image_path: str, padding: int = 10) -> Optional[tuple]:
        """
        Detect green border in the image and return coordinates to crop.
        Returns (x, y, w, h) or None if no border found.
        """
        # Read the image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError("Could not read image")
        
        # Convert to HSV color space
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Define green color range in HSV
        lower_green = np.array([35, 50, 50])
        upper_green = np.array([85, 255, 255])
        
        # Create a mask for green color
        mask = cv2.inRange(hsv, lower_green, upper_green)
        
        # Find contours in the mask
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
            
        # Find the largest contour (should be the border)
        largest_contour = max(contours, key=cv2.contourArea)
        
        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        # Add padding
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(img.shape[1] - x, w + 2 * padding)
        h = min(img.shape[0] - y, h + 2 * padding)
        
        return (x, y, w, h)
    
    @staticmethod
    def crop_image(image_path: str, output_path: str, padding: int = 10) -> dict:
        """
        Crop the image to the green border and save the result.
        Returns a dictionary with status and result information.
        """
        try:
            # Read the image
            img = cv2.imread(image_path)
            if img is None:
                return {"status": "error", "message": "Could not read image"}
            
            # Get the border coordinates
            border = ImageCropper.detect_green_border(image_path, padding)
            if not border:
                return {
                    "status": "error", 
                    "message": "No green border detected"
                }
            
            x, y, w, h = border
            
            # Crop the image
            cropped_img = img[y:y+h, x:x+w]
            
            # Save the cropped image
            cv2.imwrite(output_path, cropped_img)
            
            return {
                "status": "success",
                "message": "Image cropped successfully",
                "crop_coordinates": {"x": x, "y": y, "width": w, "height": h},
                "original_size": {"width": img.shape[1], "height": img.shape[0]},
                "cropped_size": {"width": w, "height": h},
                "output_path": str(output_path)
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error processing image: {str(e)}"
            }

# Create instance of ImageCropper
image_cropper = ImageCropper()

# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("crop_ui.html", {"request": request})

@app.post("/crop-image")
async def crop_image(
    file: UploadFile = File(...),
    padding: int = 10
):
    try:
        # Save uploaded file temporarily
        file_ext = file.filename.split('.')[-1].lower()
        if file_ext not in ['jpg', 'jpeg', 'png']:
            raise HTTPException(status_code=400, detail="Invalid file format. Only JPG, JPEG, and PNG are supported.")
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as temp_file:
            # Save uploaded file to temp file
            contents = await file.read()
            temp_file.write(contents)
            temp_path = temp_file.name
        
        # Create output path
        output_filename = f"cropped_{file.filename}"
        output_path = UPLOAD_DIR / output_filename
        
        # Process the image
        result = image_cropper.crop_image(temp_path, str(output_path), padding)
        
        # Clean up temp file
        try:
            os.unlink(temp_path)
        except:
            pass
        
        # If there was an error, return it
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        
        # Return success response
        return {
            "status": "success",
            "message": result["message"],
            "crop_coordinates": result.get("crop_coordinates"),
            "original_size": result.get("original_size"),
            "cropped_size": result.get("cropped_size"),
            "image_url": f"/uploads/{output_filename}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount uploads directory
@app.on_event("startup")
async def startup_event():
    UPLOAD_DIR.mkdir(exist_ok=True)

# Serve uploaded files
@app.get("/uploads/{filename}")
async def get_uploaded_file(filename: str):
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

if __name__ == "__main__":
    uvicorn.run("main_crop:app", host="0.0.0.0", port=8004, reload=True)
