import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import json
from pathlib import Path
from datetime import datetime
import logging
import os
import tempfile
import shutil

# Set up logging
logger = logging.getLogger(__name__)

@dataclass
class AnswerBox:
    id: str
    color: str
    contour: np.ndarray
    answer: str = ""

class AnswerBoxDetector:
    def __init__(self, min_box_area: int = 2000):

        self.min_box_area = min_box_area
        self.min_aspect_ratio = 0.3  # Minimum width/height ratio
        self.max_aspect_ratio = 4.0  # Maximum width/height ratio
        self.min_fill_ratio = 0.4    # Minimum contour area / bounding box area
        self.max_contour_approximation = 0.02  # Maximum approximation factor for contour simplification

    def detect_boxes(self, image_path: str) -> List[AnswerBox]:
        """
        Detect answer boxes in an image using color-based detection.

        Args:
            image_path: Path to the input image

        Returns:
            List of detected AnswerBox objects
        """
        print(f"[DEBUG] Starting box detection for: {image_path}")

        try:
            # Read and preprocess image
            print(f"[DEBUG] Reading image from: {image_path}")
            image = cv2.imread(image_path)
            if image is None:
                error_msg = f"Could not read image at {image_path}. File may not exist or is corrupted."
                print(f"[ERROR] {error_msg}")
                raise ValueError(error_msg)

            print(f"[DEBUG] Image loaded successfully. Dimensions: {image.shape}")

            # Check if image has content
            if image.size == 0:
                raise ValueError("Image is empty")

            # Create debug directory
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            timestamp = int(datetime.now().timestamp())

            # Save original image for debugging
            cv2.imwrite(str(debug_dir / f"{timestamp}_original.png"), image)

            # Convert to HSV color space
            print("[DEBUG] Converting to HSV color space")
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

            # Define color ranges (in HSV)
            print("[DEBUG] Defining color ranges")
            color_ranges = {
                'green': [
                    (np.array([35, 50, 50]), np.array([85, 255, 255]))
                ],
                'orange': [
                    (np.array([5, 100, 100]), np.array([25, 255, 255]))  # Orange color range
                ]
            }

            print(f"[DEBUG] Color ranges defined")

            # Create masks for each color
            print("[DEBUG] Creating color masks")
            masks = {}

            # Create masks for each color range
            for color, ranges in color_ranges.items():
                masks[color] = cv2.inRange(hsv, ranges[0][0], ranges[0][1])

            # Debug: Save masks for inspection
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            timestamp = int(datetime.now().timestamp())

            for color, mask in masks.items():
                cv2.imwrite(str(debug_dir / f"{timestamp}_{color}_mask.png"), mask)
            cv2.imwrite(str(debug_dir / f"{timestamp}_original.png"), image)

            # Get color masks for processing
            green_mask = masks.get('green', np.zeros_like(masks.get('green')))
            orange_mask = masks.get('orange', np.zeros_like(masks.get('orange')))
            
            green_pixels = np.count_nonzero(green_mask)
            orange_pixels = np.count_nonzero(orange_mask)
            
            print(f"[DEBUG] Masks created - Green: {green_pixels}px, Orange: {orange_pixels}px")

            if green_pixels == 0 and orange_pixels == 0:
                print("[WARNING] No colored pixels detected. Check if the image has green/orange boxes.")
                # Try with different color ranges if needed
                # For light colors, adjust the Value (V) channel
                light_orange_lower = np.array([5, 50, 50])
                light_orange_upper = np.array([25, 255, 255])
                light_green_lower = np.array([35, 30, 30])
                light_green_upper = np.array([85, 255, 255])

                orange_mask = cv2.inRange(hsv, light_orange_lower, light_orange_upper)
                green_mask = cv2.inRange(hsv, light_green_lower, light_green_upper)
                
                print(f"[DEBUG] Trying with adjusted color ranges")

            # Find contours for each color
            print("[DEBUG] Finding contours")
            green_contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            orange_contours, _ = cv2.findContours(orange_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            print(f"[DEBUG] Found {len(green_contours)} green and {len(orange_contours)} orange contours")

            # Process and combine boxes
            answer_boxes = []
            
            # Function to check if a box overlaps significantly with existing boxes
            def is_overlapping(new_box, existing_boxes, threshold=0.3):
                x, y, w, h = cv2.boundingRect(new_box.contour)
                new_rect = (x, y, x + w, y + h)
                
                for box in existing_boxes:
                    ex, ey, ew, eh = cv2.boundingRect(box.contour)
                    exist_rect = (ex, ey, ex + ew, ey + eh)
                    
                    # Calculate intersection
                    x_overlap = max(0, min(new_rect[2], exist_rect[2]) - max(new_rect[0], exist_rect[0]))
                    y_overlap = max(0, min(new_rect[3], exist_rect[3]) - max(new_rect[1], exist_rect[1]))
                    overlap_area = x_overlap * y_overlap
                    
                    # Calculate area of new box
                    new_area = w * h
                    
                    # If overlap is significant, return True
                    if overlap_area > 0 and (overlap_area / new_area) > threshold:
                        return True
                return False

            # Process orange boxes
            print("[DEBUG] Processing orange contours")
            for i, contour in enumerate(orange_contours):
                try:
                    area = cv2.contourArea(contour)
                    x, y, w, h = cv2.boundingRect(contour)
                    perimeter = cv2.arcLength(contour, True)
                    
                    # Skip very small contours
                    if area < self.min_box_area or perimeter == 0:
                        continue
                        
                    # Approximate the contour to a polygon
                    epsilon = 0.02 * perimeter  # 2% of perimeter for approximation
                    approx = cv2.approxPolyDP(contour, epsilon, True)
                    
                    # Calculate shape properties
                    aspect_ratio = float(w) / h
                    contour_area_ratio = area / (w * h)
                    hull = cv2.convexHull(contour)
                    hull_area = cv2.contourArea(hull)
                    solidity = float(area) / hull_area if hull_area > 0 else 0
                    
                    # Check if contour is approximately rectangular (4 or 5 vertices after approximation)
                    is_rectangular = len(approx) in [4, 5]  # Allow for slight deviations from perfect rectangle
                    
                    # Calculate extent (ratio of contour area to bounding rectangle area)
                    rect_area = w * h
                    extent = float(area) / rect_area if rect_area > 0 else 0
                    
                    # More strict validation for boxes
                    is_valid_box = (
                        area < (image.shape[0] * image.shape[1] * 0.2) and  # Max 20% of image area
                        self.min_aspect_ratio < aspect_ratio < self.max_aspect_ratio and
                        extent > 0.7 and  # At least 70% of the bounding box should be filled
                        solidity > 0.8 and  # Contour should be mostly convex
                        is_rectangular and  # Should have approximately 4 sides
                        contour_area_ratio > self.min_fill_ratio
                    )
                    
                    print(f"[DEBUG] Orange contour {i}: area={area}, "
                          f"aspect={aspect_ratio:.2f}, fill={contour_area_ratio:.2f}, "
                          f"extent={extent:.2f}, solidity={solidity:.2f}, "
                          f"sides={len(approx)}, valid={is_valid_box}")

                    if is_valid_box:
                        # Create a new box
                        new_box = AnswerBox(
                            id=f"Q{len(answer_boxes) + 1}",
                            color="orange",
                            contour=contour
                        )
                        
                        # Check for significant overlap with existing boxes
                        if not is_overlapping(new_box, answer_boxes):
                            print(f"[DEBUG] Adding orange box: {x},{y} {w}x{h}")
                            answer_boxes.append(new_box)
                except Exception as e:
                    print(f"[WARNING] Error processing orange contour {i}: {str(e)}")
                    continue

            # Process green boxes
            print("[DEBUG] Processing green contours")
            for i, contour in enumerate(green_contours):
                try:
                    area = cv2.contourArea(contour)
                    x, y, w, h = cv2.boundingRect(contour)
                    perimeter = cv2.arcLength(contour, True)
                    
                    # Skip very small contours
                    if area < self.min_box_area or perimeter == 0:
                        continue
                        
                    # Approximate the contour to a polygon
                    epsilon = 0.02 * perimeter
                    approx = cv2.approxPolyDP(contour, epsilon, True)
                    
                    # Calculate shape properties
                    aspect_ratio = float(w) / h
                    contour_area_ratio = area / (w * h)
                    hull = cv2.convexHull(contour)
                    hull_area = cv2.contourArea(hull)
                    solidity = float(area) / hull_area if hull_area > 0 else 0
                    
                    # Check if contour is approximately rectangular
                    is_rectangular = len(approx) in [4, 5]
                    
                    # Calculate extent
                    rect_area = w * h
                    extent = float(area) / rect_area if rect_area > 0 else 0
                    
                    # Validate box properties
                    is_valid_box = (
                        area < (image.shape[0] * image.shape[1] * 0.2) and
                        self.min_aspect_ratio < aspect_ratio < self.max_aspect_ratio and
                        extent > 0.7 and
                        solidity > 0.8 and
                        is_rectangular and
                        contour_area_ratio > self.min_fill_ratio
                    )
                    
                    print(f"[DEBUG] Green contour {i}: area={area}, "
                          f"aspect={aspect_ratio:.2f}, fill={contour_area_ratio:.2f}, "
                          f"extent={extent:.2f}, solidity={solidity:.2f}, "
                          f"sides={len(approx)}, valid={is_valid_box}")

                    if is_valid_box:
                        new_box = AnswerBox(
                            id=f"Q{len(answer_boxes) + 1}",
                            color="green",
                            contour=contour
                        )
                        
                        # Check for significant overlap with existing boxes
                        if not is_overlapping(new_box, answer_boxes):
                            print(f"[DEBUG] Adding green box: {x},{y} {w}x{h}")
                            answer_boxes.append(new_box)
                except Exception as e:
                    print(f"[WARNING] Error processing green contour {i}: {str(e)}")
                    continue

            print(f"[DEBUG] Found {len(answer_boxes)} valid boxes")

            # Sort boxes left-to-right, top-to-bottom
            try:
                answer_boxes.sort(key=lambda box: (cv2.boundingRect(box.contour)[1],
                                                 cv2.boundingRect(box.contour)[0]))

                # Reassign IDs in sorted order
                for i, box in enumerate(answer_boxes, 1):
                    box.id = f"Q{i}"

                return answer_boxes

            except Exception as e:
                print(f"[ERROR] Error sorting boxes: {str(e)}")
                return answer_boxes  # Return unsorted if there's an error

        except Exception as e:
            print(f"[ERROR] Error in detect_boxes: {str(e)}")
            import traceback
            traceback.print_exc()
            raise ValueError(f"Error processing image: {str(e)}")


class AnswerBoxGrader:
    def __init__(self, templates_dir: str = "data/answer_templates"):
        """
        Initialize the answer box grader.

        Args:
            templates_dir: Directory to store answer templates
        """
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        # Ensure an images subdirectory exists for storing template images
        self.images_dir = self.templates_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.detector = AnswerBoxDetector()

    def create_template(self, template_image_path: str, answers: Dict[str, str] = None) -> str:
        """
        Create a new answer template from an image.

        Args:
            template_image_path: Path to the template image
            answers: Optional dictionary of {question_id: answer} pairs

        Returns:
            Template ID
        """
        # Read the image to get dimensions
        image = cv2.imread(template_image_path)
        if image is None:
            raise ValueError(f"Could not read image at {template_image_path}")

        height, width = image.shape[:2]

        # Detect boxes
        answer_boxes = self.detector.detect_boxes(template_image_path)

        # Create template data
        template_id = f"tpl_{int(datetime.now().timestamp())}"
        # Copy the template image to the images directory with a consistent name
        src_path = Path(template_image_path)
        ext = src_path.suffix if src_path.suffix else ".png"
        dest_filename = f"worksheet_{template_id}{ext}"
        dest_path = self.images_dir / dest_filename
        try:
            shutil.copyfile(src_path, dest_path)
        except Exception:
            # Fallback: write via cv2 if direct copy fails
            cv2.imwrite(str(dest_path), image)
        template_data = {
            "id": template_id,
            "name": "",  # Will be set by the API endpoint
            "created_at": datetime.utcnow().isoformat(),
            # Store images under data/answer_templates/images
            "image_path": str(dest_path),
            "image_dimensions": {
                "width": width,
                "height": height
            },
            "questions": []
        }

        # Add question data with coordinates
        for i, box in enumerate(answer_boxes, 1):
            # Get the bounding rectangle
            x, y, w, h = cv2.boundingRect(box.contour)

            # Calculate relative coordinates (0-1 range)
            rel_x = x / width
            rel_y = y / height
            rel_width = w / width
            rel_height = h / height

            question_data = {
                "id": f"Q{i}",
                "color": box.color,
                "expected_answer": answers.get(box.id, "") if answers else "",
                "position": {
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h
                },
                "relative_position": {
                    "x": rel_x,
                    "y": rel_y,
                    "width": rel_width,
                    "height": rel_height
                },
                "area": w * h
            }
            template_data["questions"].append(question_data)
            logger.info(f"Added box {i}: x={x}, y={y}, w={w}, h={h}, area={w*h}")

        # Save template
        template_path = self.templates_dir / f"{template_id}.json"
        with open(template_path, 'w') as f:
            json.dump(template_data, f, indent=2)

        logger.info(f"Saved template {template_id} with {len(template_data['questions'])} boxes")

        return template_id

    def grade_answers(self, template_id: str, student_image_path: str, ocr_service) -> Dict:
        """
        Grade a student's answers against a template using the template's dimensions
        and relative positions to extract answers.

        Args:
            template_id: ID of the template to use
            student_image_path: Path to the student's answer sheet
            ocr_service: OCR service instance for text extraction

        Returns:
            Dictionary with grading results
        """
        # Load template
        template_path = self.templates_dir / f"{template_id}.json"
        if not template_path.exists():
            raise FileNotFoundError(f"Template {template_id} not found")

        with open(template_path, 'r') as f:
            template = json.load(f)

        # Read student image to get dimensions
        student_image = cv2.imread(student_image_path)
        if student_image is None:
            raise ValueError(f"Could not read student image at {student_image_path}")

        student_height, student_width = student_image.shape[:2]

        # Get template dimensions
        template_width = template["image_dimensions"]["width"]
        template_height = template["image_dimensions"]["height"]

        # Calculate scale factors
        width_scale = student_width / template_width
        height_scale = student_height / template_height

        # Grade each answer
        results = {
            "template_id": template_id,
            "graded_at": datetime.utcnow().isoformat(),
            "answers": []
        }

        for question in template["questions"]:
            # Get the absolute position in the student's image using relative positions
            rel_pos = question["relative_position"]

            # Calculate position and size in student's image with padding
            padding_percent = 0.15  # 15% padding on all sides
            x = int((rel_pos["x"] - rel_pos["width"] * padding_percent/2) * student_width)
            y = int((rel_pos["y"] - rel_pos["height"] * padding_percent/2) * student_height)
            width = int(rel_pos["width"] * (1 + padding_percent) * student_width)
            height = int(rel_pos["height"] * (1 + padding_percent) * student_height)
            
            # Ensure we don't go out of image bounds
            x = max(0, x)
            y = max(0, y)
            width = min(width, student_width - x)
            height = min(height, student_height - y)

            # Create a mock AnswerBox with the calculated position
            # This is needed because _extract_text_from_box expects an AnswerBox object
            mock_contour = np.array([
                [x, y],
                [x + width, y],
                [x + width, y + height],
                [x, y + height]
            ], dtype=np.int32)

            mock_box = AnswerBox(
                id=question["id"],
                color=question["color"],
                contour=mock_contour
            )

            try:
                # Extract text from the calculated box position
                student_answer = self._extract_text_from_box(student_image_path, mock_box, ocr_service)

                # Compare with expected answer (case-insensitive)
                is_correct = student_answer.lower() == question["expected_answer"].lower()

                results["answers"].append({
                    "question_id": question["id"],
                    "expected": question["expected_answer"],
                    "actual": student_answer,
                    "is_correct": is_correct,
                    "color": question["color"],
                    "position": {
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height
                    }
                })

            except Exception as e:
                logger.error(f"Error processing question {question['id']}: {str(e)}")
                results["answers"].append({
                    "question_id": question["id"],
                    "expected": question["expected_answer"],
                    "actual": "Error processing answer",
                    "is_correct": False,
                    "color": question["color"],
                    "position": {
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height
                    },
                    "error": str(e)
                })

        return results

    def _extract_text_from_box(self, image_path: str, box: AnswerBox, ocr_service) -> str:
        """Extract text from a specific box in the image."""
        # Read image
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not read image at {image_path}")

        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(box.contour)

        # Extract region of interest with some padding
        padding = 10
        roi = image[max(0, y-padding):min(y+h+padding, image.shape[0]),
                   max(0, x-padding):min(x+w+padding, image.shape[1])]

        # Save ROI to temporary file for OCR (GPT OCR expects a file path)
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            cv2.imwrite(tmp.name, roi)
            temp_path = tmp.name

        try:
            # Use GPT OCR service to extract text
            result = ocr_service.ocr_image(temp_path)
            return result.text.strip() if hasattr(result, "text") and result.text else ""
        finally:
            # Clean up temporary file
            if Path(temp_path).exists():
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

