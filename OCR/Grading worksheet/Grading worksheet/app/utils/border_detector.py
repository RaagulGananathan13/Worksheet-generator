"""
Border detection and image cropping utilities.

This module provides functionality to detect colored borders in images and crop to those borders.
"""
import cv2
import numpy as np
from typing import Optional, Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)

class BorderDetector:
    """A class for detecting colored borders in images and cropping to those borders."""
    
    def __init__(self, 
                 color_lower: Tuple[int, int, int] = (35, 50, 50),
                 color_upper: Tuple[int, int, int] = (85, 255, 255),
                 min_contour_area: int = 10000):
        """
        Initialize the BorderDetector.
        
        Args:
            color_lower: Lower bound of the border color in HSV (default: green)
            color_upper: Upper bound of the border color in HSV (default: green)
            min_contour_area: Minimum area for a contour to be considered a valid border
        """
        self.color_lower = np.array(color_lower, dtype="uint8")
        self.color_upper = np.array(color_upper, dtype="uint8")
        self.min_contour_area = min_contour_area
    
    def detect_border(self, 
                     image_path: str, 
                     padding: int = 10) -> Optional[Tuple[int, int, int, int]]:
        """
        Detect a colored border in an image.
        
        Args:
            image_path: Path to the input image
            padding: Additional padding to add around the detected border (in pixels)
            
        Returns:
            Tuple of (x, y, width, height) of the bounding rectangle around the border,
            or None if no border is detected
        """
        try:
            # Read the image
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f"Could not read image at {image_path}")
                return None
                
            # Convert to HSV color space
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            
            # Create a mask for the specified color range
            mask = cv2.inRange(hsv, self.color_lower, self.color_upper)
            
            # Apply morphological operations to clean up the mask
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            
            # Find contours in the mask
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if not contours:
                logger.info("No contours found in the image")
                return None
                
            # Find the largest contour (should be the border)
            largest_contour = max(contours, key=cv2.contourArea)
            
            # Skip if the contour is too small
            if cv2.contourArea(largest_contour) < self.min_contour_area:
                logger.info(f"Contour area {cv2.contourArea(largest_contour)} is too small")
                return None
                
            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(largest_contour)
            
            # Add padding (ensure we don't go out of image bounds)
            height, width = image.shape[:2]
            x = max(0, x - padding)
            y = max(0, y - padding)
            w = min(width - x, w + 2 * padding)
            h = min(height - y, h + 2 * padding)
            
            return (x, y, w, h)
            
        except Exception as e:
            logger.error(f"Error detecting border: {str(e)}")
            return None
    
    def crop_to_border(self, 
                      image_path: str, 
                      output_path: str, 
                      padding: int = 10) -> Dict[str, Any]:
        """
        Crop an image to its colored border.
        
        Args:
            image_path: Path to the input image
            output_path: Path to save the cropped image
            padding: Additional padding to add around the detected border (in pixels)
            
        Returns:
            Dictionary containing:
            - status: "success" or "error"
            - message: Description of the result
            - crop_coordinates: (x, y, width, height) of the crop
            - original_size: (width, height) of the original image
            - cropped_size: (width, height) of the cropped image
        """
        try:
            # Read the image
            image = cv2.imread(image_path)
            if image is None:
                error_msg = "Could not read the input image"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}
                
            original_height, original_width = image.shape[:2]
            
            # Detect the border
            border = self.detect_border(image_path, padding)
            if not border:
                error_msg = "No valid border detected in the image"
                logger.warning(error_msg)
                return {"status": "error", "message": error_msg}
                
            x, y, w, h = border
            
            # Crop the image
            cropped = image[y:y+h, x:x+w]
            
            # Save the cropped image
            cv2.imwrite(output_path, cropped)
            
            return {
                "status": "success",
                "message": "Image cropped successfully",
                "crop_coordinates": {"x": x, "y": y, "width": w, "height": h},
                "original_size": {"width": original_width, "height": original_height},
                "cropped_size": {"width": w, "height": h},
                "output_path": output_path
            }
            
        except Exception as e:
            error_msg = f"Error processing image: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg
            }

# Default instance with green color detection
green_border_detector = BorderDetector(
    color_lower=(35, 50, 50),  # Green lower bound in HSV
    color_upper=(85, 255, 255),  # Green upper bound in HSV
    min_contour_area=10000
)
