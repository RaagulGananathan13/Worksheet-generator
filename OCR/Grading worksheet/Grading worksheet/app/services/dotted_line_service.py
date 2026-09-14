import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path
import json
import logging
from datetime import datetime
import os

# Set up logging
logger = logging.getLogger(__name__)

@dataclass
class DottedLine:
    """Represents a detected dotted line in a worksheet."""
    id: str
    start_point: Tuple[int, int]  # (x1, y1)
    end_point: Tuple[int, int]    # (x2, y2)
    line_type: str  # 'horizontal' or 'vertical'
    length: float
    page: int = 0
    metadata: Optional[Dict] = None

class DottedLineDetector:
    """
    Detects and processes dotted lines in worksheet images.
    """
    
    def __init__(self, 
                 min_line_length: int = 5,  # Length to identify valid lines
                 max_line_gap: int = 1,     # Increased to handle potential gaps in dots
                 dot_interval: int = 2,     # Expected space between dots in pixels
                 dot_size: int = 2):         # Typical dot size in the template
        """
        Initialize the dotted line detector.
        
        Args:
            min_line_length: Minimum length of a line to be considered valid (pixels)
            max_line_gap: Maximum gap between dots to be considered part of the same line (pixels)
            dot_interval: Expected interval between dots in pixels
            dot_size: Expected size of each dot in pixels
        """
        self.min_line_length = min_line_length
        self.max_line_gap = max_line_gap
        self.dot_interval = dot_interval
        self.dot_size = dot_size
    
    def preprocess_image(self, image_path: str) -> np.ndarray:
        """
        Preprocess the image to enhance dotted line detection.
        Optimized for template with evenly spaced dotted lines.
        
        Args:
            image_path: Path to the input image
            
        Returns:
            Processed binary image with enhanced dots
        """
        # Read the image
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not read image at {image_path}")
            
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply adaptive thresholding to binarize the image
        # Using a larger block size to handle varying background
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 7
        )
        
        # Create a kernel for morphological operations
        # Using a horizontal line kernel to connect dots horizontally
        kernel_size = max(3, self.dot_size)
        kernel = np.ones((1, kernel_size * 3), np.uint8)
        
        # Apply morphological operations to enhance dots
        # Using closing to connect nearby dots
        processed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        # Apply erosion to remove small noise
        kernel_erode = np.ones((2, 2), np.uint8)
        processed = cv2.erode(processed, kernel_erode, iterations=1)
        
        # Apply dilation to enhance remaining dots
        processed = cv2.dilate(processed, kernel_erode, iterations=1)
        
        return processed
    
    def _is_text_line(self, binary: np.ndarray, x1: int, y1: int, x2: int, y2: int, line_height: int = 10) -> bool:
        """
        Check if a line is likely part of text by analyzing the region around it.
        
        Args:
            binary: Binary image
            x1, y1, x2, y2: Line coordinates
            line_height: Height of the region to analyze above and below the line
            
        Returns:
            bool: True if the line is likely part of text, False otherwise
        """
        try:
            # Create a region of interest around the line
            h, w = binary.shape
            y_center = (y1 + y2) // 2
            
            # Define the region to analyze (slightly above and below the line)
            y_start = max(0, y_center - line_height)
            y_end = min(h, y_center + line_height + 1)
            x_start = max(0, min(x1, x2) - 10)
            x_end = min(w, max(x1, x2) + 10)
            
            if y_start >= y_end or x_start >= x_end:
                return False
                
            roi = binary[y_start:y_end, x_start:x_end]
            
            # If ROI is empty, skip
            if roi.size == 0:
                return False
                
            # Calculate the density of white pixels in the region
            white_pixels = np.sum(roi > 0)
            total_pixels = roi.size
            density = white_pixels / total_pixels if total_pixels > 0 else 0
            
            # If the density is too high, it's likely text
            return density > 0.2  # Adjust threshold as needed
            
        except Exception as e:
            logger.warning(f"Error in text detection: {str(e)}")
            return False

    def detect_lines(self, image_path: str) -> List[DottedLine]:
        """
        Detect horizontal dotted lines in an image, filtering out text lines.
        
        Args:
            image_path: Path to the input image
            
        Returns:
            List of detected horizontal DottedLine objects
        """
        logger.info(f"Detecting horizontal lines in {image_path}")
        
        try:
            # Read and preprocess the image
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Could not read image at {image_path}")
                
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Create a clean binary version for text detection
            binary_text = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 11, 2
            )
            
            # Create a separate binary version for line detection
            binary_lines = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 11, 2
            )
            
            # Use horizontal kernel to connect dots into lines
            kernel = np.ones((1, 20), np.uint8)
            dilated = cv2.dilate(binary_lines, kernel, iterations=1)
            
            # Detect edges using Canny
            edges = cv2.Canny(dilated, 50, 150, apertureSize=3)
            
            # Detect lines using HoughLinesP with optimized parameters for horizontal lines
            lines = cv2.HoughLinesP(
                edges, 1, np.pi/180, 
                threshold=30,      
                minLineLength=100,  
                maxLineGap=20      
            )
            
            if lines is None:
                logger.warning("No horizontal lines detected in the image")
                return []
                
            # Process and filter horizontal lines
            result = []
            for i, line in enumerate(lines):
                x1, y1, x2, y2 = line[0]
                
                # Calculate angle (in degrees) and filter for horizontal lines only
                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                
                # Only keep nearly horizontal lines (within 5 degrees of horizontal)
                if abs(angle) > 5 and abs(angle) < 175:
                    continue
                    
                # Sort points left to right
                if x1 > x2:
                    x1, x2 = x2, x1
                    y1, y2 = y2, y1
                
                # Skip if this is likely part of text
                if self._is_text_line(binary_text, x1, y1, x2, y2):
                    logger.debug(f"Skipping line at y={y1} - likely part of text")
                    continue
                
                # Calculate line length
                length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                
                # Skip very short lines that might be part of characters
                if length < 150:  # Minimum length for a valid line
                    continue
                
                result.append(DottedLine(
                    id=f"line_{i+1}",
                    start_point=(int(x1), int(y1)),
                    end_point=(int(x2), int(y2)),
                    line_type='horizontal',
                    length=length,
                    metadata={
                        'angle': angle,
                        'detection_method': 'hough_lines_horizontal'
                    }
                ))
            
            # Sort lines by y-coordinate (top to bottom)
            result.sort(key=lambda line: line.start_point[1])
            
            # Remove lines that are too close to each other (likely duplicates)
            filtered_result = []
            prev_y = -100  # Initialize with a value that won't match the first line
            min_y_distance = 10  # Minimum vertical distance between lines
            
            for line in result:
                current_y = line.start_point[1]
                if abs(current_y - prev_y) > min_y_distance:
                    filtered_result.append(line)
                    prev_y = current_y
            
            logger.info(f"Detected {len(filtered_result)} horizontal lines after filtering")
            return filtered_result
            
        except Exception as e:
            logger.error(f"Error detecting horizontal lines: {str(e)}", exc_info=True)
            return []
    
    def _group_dots_into_lines(self, dots: np.ndarray, 
                              line_type: str = 'horizontal') -> List[Dict]:
        """
        Group dots into lines based on their positions.
        
        Args:
            dots: Array of dots in format [[x, y, radius], ...]
            line_type: 'horizontal' or 'vertical' line detection
            
        Returns:
            List of line dictionaries with start, end, dots, etc.
        """
        if len(dots) == 0:
            return []
            
        # Sort dots by primary axis (x for horizontal, y for vertical)
        primary_axis = 0 if line_type == 'vertical' else 1
        secondary_axis = 1 - primary_axis
        dots_sorted = sorted(dots, key=lambda x: (x[primary_axis], x[secondary_axis]))
        
        lines = []
        current_line = {
            'dots': [],
            'start': None,
            'end': None,
            'length': 0,
            'avg_interval': 0
        }
        
        for dot in dots_sorted:
            x, y, r = int(dot[0]), int(dot[1]), int(dot[2])
            
            if not current_line['dots']:
                # First dot in line
                current_line['dots'].append((x, y))
                current_line['start'] = (x, y)
                current_line['end'] = (x, y)
            else:
                # Get last dot in current line
                last_x, last_y = current_line['dots'][-1]
                
                # Calculate distances along primary and secondary axes
                primary_dist = abs((x if primary_axis == 0 else y) - 
                                 (last_x if primary_axis == 0 else last_y))
                secondary_dist = abs((y if primary_axis == 0 else x) - 
                                   (last_y if primary_axis == 0 else last_x))
                
                # Check if dot should be part of current line
                max_secondary_diff = self.max_line_gap * 1.5  # Be more lenient with secondary axis
                max_primary_diff = self.dot_interval * 3  # Allow larger gaps for dotted lines
                
                if (secondary_dist <= max_secondary_diff and 
                    primary_dist <= max_primary_diff and
                    primary_dist > 0):  # Prevent duplicate points
                    current_line['dots'].append((x, y))
                    current_line['end'] = (x, y)
                else:
                    # Finalize current line and start new one
                    if len(current_line['dots']) >= 2:  # Only keep lines with at least 2 dots
                        self._finalize_line(current_line, line_type)
                        lines.append(current_line)
                    
                    current_line = {
                        'dots': [(x, y)],
                        'start': (x, y),
                        'end': (x, y),
                        'length': 0,
                        'avg_interval': 0
                    }
        
        # Add the last line if it has enough dots
        if len(current_line['dots']) >= 2:
            self._finalize_line(current_line, line_type)
            lines.append(current_line)
        
        # Filter out lines that are too short
        lines = [line for line in lines if line['length'] >= self.min_line_length]
        
        # Sort lines by position along primary axis
        lines.sort(key=lambda l: l['start'][primary_axis])
        
        # Merge nearby lines that might be part of the same line
        if len(lines) > 1:
            merged_lines = [lines[0]]
            for line in lines[1:]:
                last_line = merged_lines[-1]
                
                # Calculate distances between line ends
                dist = abs((line['start'][primary_axis] - last_line['end'][primary_axis]))
                secondary_dist = abs((line['start'][secondary_axis] - last_line['end'][secondary_axis]))
                
                # If lines are close enough, merge them
                if (dist <= self.dot_interval * 4 and 
                    secondary_dist <= self.max_line_gap * 2):
                    last_line['dots'].extend(line['dots'])
                    last_line['end'] = line['end']
                    self._finalize_line(last_line, line_type)
                else:
                    merged_lines.append(line)
            
            lines = merged_lines
        
        return lines
    
    def _finalize_line(self, line: Dict, line_type: str) -> None:
        """Calculate final properties of a line."""
        if len(line['dots']) < 2:
            line['length'] = 0
            line['avg_interval'] = 0
            return
            
        # Sort dots along the line
        axis = 0 if line_type == 'vertical' else 1
        line['dots'].sort(key=lambda p: p[axis])
        
        # Calculate length
        if line_type == 'horizontal':
            line['length'] = line['dots'][-1][0] - line['dots'][0][0]
        else:  # vertical
            line['length'] = line['dots'][-1][1] - line['dots'][0][1]
        
        # Calculate average interval between dots
        intervals = []
        for i in range(1, len(line['dots'])):
            if line_type == 'horizontal':
                interval = line['dots'][i][0] - line['dots'][i-1][0]
            else:  # vertical
                interval = line['dots'][i][1] - line['dots'][i-1][1]
            intervals.append(interval)
        
        line['avg_interval'] = sum(intervals) / len(intervals) if intervals else 0
        
        # Update start and end points
        line['start'] = line['dots'][0]
        line['end'] = line['dots'][-1]


class DottedLineTemplate:
    """Manages templates containing dotted lines for answer spaces."""
    
    def __init__(self, template_dir: str = "data/dotted_templates"):
        """Initialize the dotted line template manager."""
        self.template_dir = Path(template_dir)
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self.detector = DottedLineDetector()
    
    def create_template(self, image_path: str, template_name: str) -> Dict:
        """Create a new template from an image with dotted lines."""
        # Generate template ID
        template_id = f"dotted_{len(self.list_templates()) + 1}"
        
        # Create template directory
        template_dir = self.template_dir / template_id
        template_dir.mkdir(exist_ok=True)
        
        # Save the image
        image_filename = f"template{os.path.splitext(image_path)[1]}"
        image_dest = template_dir / image_filename
        shutil.copy2(image_path, image_dest)
        
        # Create template data
        template_data = {
            'id': template_id,
            'name': template_name,
            'image_path': str(image_dest.absolute()),
            'lines': [],
            'created_at': datetime.now().isoformat()
        }
        
        # Save template data
        with open(template_dir / 'template.json', 'w') as f:
            json.dump(template_data, f, indent=2)
        
        return template_data
    
    def get_template(self, template_id: str) -> Optional[Dict]:
        """Get a template by ID."""
        # Check new format (directory with template.json)
        template_file = self.template_dir / template_id / 'template.json'
        if template_file.exists():
            with open(template_file, 'r') as f:
                return json.load(f)
                
        # Check old format (direct JSON file)
        template_file = self.template_dir / f"{template_id}.json"
        if template_file.exists():
            with open(template_file, 'r') as f:
                template_data = json.load(f)
                # Add required fields if missing
                if 'id' not in template_data:
                    template_data['id'] = template_id
                if 'name' not in template_data:
                    template_data['name'] = f"Template {template_id}"
                return template_data
                
        return None
    
    def list_templates(self) -> List[Dict]:
        """List all available templates."""
        templates = []
        
        # Check for new format (directory with template.json)
        for template_dir in self.template_dir.glob('*'):
            if template_dir.is_dir():
                template_file = template_dir / 'template.json'
                if template_file.exists():
                    with open(template_file, 'r') as f:
                        try:
                            templates.append(json.load(f))
                        except json.JSONDecodeError as e:
                            logger.warning(f"Invalid JSON in {template_file}: {e}")
        
        # Check for old format (direct JSON files)
        for template_file in self.template_dir.glob('*.json'):
            if template_file.is_file():
                with open(template_file, 'r') as f:
                    try:
                        template_data = json.load(f)
                        # Add required fields if missing
                        if 'id' not in template_data:
                            template_data['id'] = template_file.stem
                        if 'name' not in template_data:
                            # Extract numeric part from the ID (e.g., '1750288414' from 'dotted_1750288414')
                            numeric_id = template_file.stem.split('_')[-1] if '_' in template_file.stem else template_file.stem
                            template_data['name'] = numeric_id
                        templates.append(template_data)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON in {template_file}: {e}")
        
        return templates
    
    def delete_template(self, template_id: str) -> bool:
        """Delete a template."""
        template_dir = self.template_dir / template_id
        if template_dir.exists() and template_dir.is_dir():
            import shutil
            shutil.rmtree(template_dir)
            return True
        return False
