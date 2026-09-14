import cv2
import numpy as np
from typing import List, Dict, Optional, Tuple

class BlankLineDetector:
    """
    Detects various types of answer fields in worksheet images, including:
    - Traditional blank lines (underscores)
    - Solid horizontal lines
    - Other line-based answer fields
    """
    def __init__(self, min_line_length: int = 15, max_line_thickness: int = 6, debug: bool = False):
        self.min_line_length = min_line_length
        self.max_line_thickness = max_line_thickness
        self.debug = debug
        
    def _detect_solid_lines(self, image: np.ndarray) -> List[Dict]:
        """Detect solid horizontal orange lines."""
        # Convert to HSV color space for better color detection
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Define orange color range in HSV
        # Orange range 1: Lower bound (darker orange)
        lower_orange1 = np.array([0, 100, 100])
        upper_orange1 = np.array([20, 255, 255])
        # Orange range 2: Upper bound (lighter orange)
        lower_orange2 = np.array([160, 100, 100])
        upper_orange2 = np.array([180, 255, 255])
        
        # Create masks for orange color
        mask1 = cv2.inRange(hsv, lower_orange1, upper_orange1)
        mask2 = cv2.inRange(hsv, lower_orange2, upper_orange2)
        orange_mask = cv2.bitwise_or(mask1, mask2)
        
        # Apply morphological operations to enhance line detection
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 1))
        orange_lines = cv2.morphologyEx(orange_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        # Find contours of the detected orange lines
        contours, _ = cv2.findContours(orange_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        results = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            
            # Filter based on size and aspect ratio
            if w > self.min_line_length and h <= self.max_line_thickness * 2:
                # Calculate the average color in the detected region
                roi = image[y:y+h, x:x+w]
                avg_color = np.mean(roi, axis=(0, 1))
                
                # Convert BGR to HSV for the average color
                avg_hsv = cv2.cvtColor(np.uint8([[avg_color]]), cv2.COLOR_BGR2HSV)[0][0]
                
                # Check if the average color is in the orange range
                is_orange = ((lower_orange1[0] <= avg_hsv[0] <= upper_orange1[0] and
                            lower_orange1[1] <= avg_hsv[1] <= upper_orange1[1] and
                            lower_orange1[2] <= avg_hsv[2] <= upper_orange1[2]) or
                           (lower_orange2[0] <= avg_hsv[0] <= upper_orange2[0] and
                            lower_orange2[1] <= avg_hsv[1] <= upper_orange2[1] and
                            lower_orange2[2] <= avg_hsv[2] <= upper_orange2[2]))
                
                if is_orange:
                    results.append({
                        'x': int(x),
                        'y': int(y + h // 2),  # Center y
                        'width': int(w),
                        'height': int(h),
                        'type': 'orange_line'
                    })
                
        return results

    def detect_blank_lines(self, image: np.ndarray) -> List[Dict]:
        """
        Detect various types of answer fields in the given image.
        Args:
            image: Input image as a numpy array (BGR)
        Returns:
            List of dicts with line info: id, x, y, width, height, type
        """
        results = []
        debug_imgs = {}
        orig = image.copy()

        # Detect traditional blank lines (underscores)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                     cv2.THRESH_BINARY_INV, 15, 8)
        
        if self.debug:
            debug_imgs['binary'] = binary.copy()
            
        # Morphological closing to connect underscores
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        if self.debug:
            debug_imgs['closed'] = closed.copy()
            
        # Find contours for traditional blank lines
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = w / float(h) if h > 0 else 0
            
            # Heuristics for blank lines (short, thin, wide lines)
            if (w >= self.min_line_length and
                h <= self.max_line_thickness and
                aspect_ratio > 3 and
                y > 0 and x > 0):
                    
                results.append({
                    'x': int(x),
                    'y': int(y + h // 2),  # Center y
                    'width': int(w),
                    'height': int(h),
                    'type': 'blank_line'
                })
                
                if self.debug:
                    cv2.rectangle(orig, (x, y), (x + w, y + h), (0, 255, 0), 2)
        
        # Detect solid horizontal lines (new type)
        solid_lines = self._detect_solid_lines(image)
        results.extend(solid_lines)
        
        if self.debug:
            for line in solid_lines:
                x, y, w, h = line['x'], line['y'] - line['height']//2, line['width'], line['height']
                cv2.rectangle(orig, (x, y), (x + w, y + h), (255, 0, 0), 2)
        
        # Sort all results by position (top-to-bottom, left-to-right)
        results.sort(key=lambda b: (b['y'], b['x']))
        
        # Assign IDs in sorted order
        for idx, b in enumerate(results, 1):
            b['id'] = f'line_{idx}'
            
        if self.debug:
            debug_imgs['detected'] = orig
            
        return results

    def visualize(self, image: np.ndarray, blanks: List[Dict]) -> np.ndarray:
        """Draw rectangles on blanks for visualization."""
        vis = image.copy()
        for b in blanks:
            x, y, w, h = b['x'], b['y'] - h // 2, b['width'], b['height']
            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 2)
        return vis
