from typing import Any, Optional, Tuple
import cv2
import numpy as np
from typing import List, Dict
from dataclasses import dataclass
import json
from pathlib import Path
from datetime import datetime
import logging
from difflib import SequenceMatcher
import tempfile
import os
import openai
from openai import AsyncOpenAI
import asyncio

# Set up logging
logger = logging.getLogger(__name__)

@dataclass
class AnswerBox:
    id: str
    color: str  # 'red' or 'green'
    contour: np.ndarray
    answer: str = ""

class ShortAnswerTemplateManager:
    """
    Handles saving and loading of model answers for short answer templates.
    """
    def __init__(self, templates_dir: str = "data/sa_templates"):
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def save_template(self, template_id: str, boxes: List[Dict[str, Any]], model_answers: Dict[str, str], image_dimensions: Dict[str, int] = None, template_name: str = None, created_at: str = None, image_path: str = None):
        """
        Save detected boxes and their model answers.
        Automatically adds relative_position and area if image_dimensions are provided.
        Also stores template_id, name, created_at, image_path, and image_dimensions at the root level.
        """
        if image_dimensions is not None:
            width = image_dimensions.get('width')
            height = image_dimensions.get('height')
            for box in boxes:
                if width and height:
                    box['relative_position'] = {
                        'x': box['x'] / width,
                        'y': box['y'] / height,
                        'width': box['width'] / width,
                        'height': box['height'] / height
                    }
                    box['area'] = box['width'] * box['height']
        template_data = {
            "id": template_id,
            "name": template_name,
            "created_at": created_at,
            "image_path": image_path,
            "image_dimensions": image_dimensions,
            "boxes": boxes,
            "model_answers": model_answers
        }
        with open(self.templates_dir / f"{template_id}.json", "w", encoding="utf-8") as f:
            json.dump(template_data, f, ensure_ascii=False, indent=2)

    def load_template(self, template_id: str) -> Dict[str, Any]:
        """
        Load template data by ID.
        """
        with open(self.templates_dir / f"{template_id}.json", "r", encoding="utf-8") as f:
            return json.load(f)

class AnswerBoxDetector:
    def __init__(self, min_box_area: int = 2000):
        """
        Initialize the answer box detector.

        Args:
            min_box_area: Minimum area to be considered as a valid answer box
        """
        self.min_box_area = min_box_area
        self.min_aspect_ratio = 0.3  # Minimum width/height ratio
        self.max_aspect_ratio = 4.0  # Maximum width/height ratio
        self.min_fill_ratio = 0.4  # Minimum contour area / bounding box area
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
                    is_rectangular = len(approx) in [4, 5, 6, 7,
                                                     8]  # Allow for slight deviations from perfect rectangle

                    # Calculate extent (ratio of contour area to bounding rectangle area)
                    rect_area = w * h
                    extent = float(area) / rect_area if rect_area > 0 else 0

                    # More strict validation for boxes
                    is_valid_box = (
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
                    is_rectangular = len(approx) in [4, 5, 6, 7, 8]

                    # Calculate extent
                    rect_area = w * h
                    extent = float(area) / rect_area if rect_area > 0 else 0

                    # Validate box properties
                    is_valid_box = (
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


# --- Helper for extracting text from a box using OCR service ---
def extract_text_from_box_with_ocr(ocr_service, image_path: str, box: dict) -> str:
    """
    Crop the region specified by box from image_path and run OCR.
    """
    pos = box.get('position') or box.get('bbox') or box
    x, y, w, h = int(pos['x']), int(pos['y']), int(pos['width']), int(pos['height'])
    img = cv2.imread(image_path)
    if img is None:
        return ""
    crop = img[y:y+h, x:x+w]
    # Write crop to a temporary file and use GPT OCR on the file path
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        cv2.imwrite(tmp.name, crop)
        temp_path = tmp.name
    try:
        result = ocr_service.ocr_image(temp_path)
        return result.text if hasattr(result, 'text') else str(result)
    finally:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass

class SemanticGrader:
    """
    Handles semantic comparison of answers using OpenAI's API.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the semantic grader with optional API key.
        If no API key is provided, it will try to use OPENAI_API_KEY environment variable.
        """
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key is required for semantic grading")
        self.client = AsyncOpenAI(api_key=api_key)
    
    async def compare_answers(self, expected: str, actual: str) -> Tuple[float, str]:
        """
        Compare two answers semantically using OpenAI's API.
        Returns a tuple of (similarity_score, reasoning)
        """
        if not expected or not actual:
            return 0.0, "One or both answers are empty"
            
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": """You are an expert at comparing student answers for educational purposes. 
                    Your task is to determine how well the student's answer matches the expected answer.
                    Consider partial matches and be lenient with phrasing as long as the core concepts are present.
                    
                    Return a JSON with:
                    - 'score': A float between 0.0 and 1.0 where:
                      - 1.0 = Perfect match (all key concepts present, same meaning)
                      - 0.7-0.9 = Good match (most key concepts present, minor differences)
                      - 0.4-0.6 = Partial match (some key concepts present)
                      - 0.1-0.3 = Weak match (few key concepts present)
                      - 0.0 = No match
                    - 'reasoning': A brief explanation of the score
                    
                    Be generous with partial credit when the student shows understanding."""
                    },
                    {"role": "user", "content": f"""Compare these answers:
                    
                    EXPECTED: {expected}
                    STUDENT'S ANSWER: {actual}
                    
                    Analyze how well the student's answer matches the expected answer, 
                    considering partial understanding and different ways of expressing the same idea."""}
                ],
                temperature=0.1,  # Slight temperature for some flexibility
                response_format={"type": "json_object"}
            )
            
            # Parse the response
            response_content = response.choices[0].message.content
            try:
                result = json.loads(response_content)
                score = float(result.get('score', 0.0))
                reasoning = result.get('reasoning', 'No reasoning provided')
                
                # Ensure score is within valid range
                score = max(0.0, min(1.0, score))
                return score, reasoning
                
            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"Failed to parse response: {response_content}")
                # Fallback to a simple string similarity if parsing fails
                similarity = SequenceMatcher(None, expected.lower(), actual.lower()).ratio()
                return similarity, f"Fallback: {str(e)}"
            
        except Exception as e:
            logging.error(f"Error in semantic comparison: {str(e)}")
            return 0.0, f"Error during semantic comparison: {str(e)}"


class ShortAnswerGrader:
    """
    Grades short-answer worksheets using ratio-based field localisation.

    The template JSON stores the relative position (0-1 ratio) of every
    answer box inside `boxes[i].relative_position` as well as the image
    dimensions of the template that was used during setup.  At grading
    time the student's worksheet may have arbitrary resolution or aspect
    ratio but the *relative* layout remains the same, so we simply map
    the relative coordinates back into the student image to locate the
    corresponding region to crop and run OCR on.
    """

    def __init__(self, ocr_service, similarity_threshold: float = 0.7, use_semantic: bool = True,
                     partial_threshold: float = 0.4, full_threshold: float = None,
                     leniency_bias: float = 0.10, leniency_scale: float = 1.0,
                     prefer_keywords: bool = True):
        self.ocr_service = ocr_service
        # Backward compatibility: similarity_threshold maps to full_threshold if not provided explicitly
        self.full_threshold = full_threshold if full_threshold is not None else similarity_threshold
        self.partial_threshold = partial_threshold
        self.use_semantic = use_semantic
        self.semantic_grader = SemanticGrader() if use_semantic else None
        # Leniency settings: final_similarity = clamp(similarity * scale + bias)
        self.leniency_bias = float(leniency_bias)
        self.leniency_scale = float(leniency_scale)
        # Prefer keyword-based scoring when keywords are provided in the template
        self.prefer_keywords = bool(prefer_keywords)

    def _normalize_similarity(self, s: float) -> float:
        """
        Apply a simple affine transform to make scoring less strict.
        s' = clamp(s * leniency_scale + leniency_bias, 0, 1)

        Defaults (bias=0.10, scale=1.0) gently push mid-range scores up by 10 points.
        """
        try:
            s = float(s)
        except Exception:
            s = 0.0
        s = (s * self.leniency_scale) + self.leniency_bias
        # Clamp to [0, 1]
        if s < 0.0:
            s = 0.0
        elif s > 1.0:
            s = 1.0
        return s

    @staticmethod
    def _relative_to_absolute(rel: Dict[str, float], img_w: int, img_h: int) -> Dict[str, int]:
        """Convert a relative (0-1) position dict to absolute pixel coords."""
        return {
            "x": int(rel["x"] * img_w),
            "y": int(rel["y"] * img_h),
            "width": max(1, int(rel["width"] * img_w)),
            "height": max(1, int(rel["height"] * img_h))
        }

    def _extract_text(self, image, pos: Dict[str, int]) -> str:
        x, y, w, h = pos["x"], pos["y"], pos["width"], pos["height"]
        crop = image[y : y + h, x : x + w]
        if crop.size == 0:
            return ""
        ok, buf = cv2.imencode(".png", crop)
        if not ok:
            return ""
        # Persist to a temp file and call GPT OCR
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(buf.tobytes())
            temp_path = tmp.name
        try:
            res = self.ocr_service.ocr_image(temp_path)
            return res.text.strip() if hasattr(res, "text") else str(res).strip()
        finally:
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    async def _compare(self, expected: str, actual: str, keywords: str = "") -> Dict[str, Any]:
        """
        Compare answers and return a result dictionary.
        Prioritizes semantic comparison when full answers are available.
        Falls back to keyword matching or character-based comparison when needed.
        """
        expected = (expected or "").strip()
        actual = (actual or "").strip()
        
        # Initialize result
        result = {
            "similarity": 0.0,
            "is_correct": False,
            "method": "none",
            "reasoning": "",
            "category": "wrong",
            "credit": 0.0,
            "raw_similarity": 0.0
        }
        
        # If we have both expected and actual answers, decide comparison strategy
        # 1) Prefer keyword-based scoring when keywords are provided
        if keywords:
            keys = [k.strip().lower() for k in keywords.split(",") if k.strip()]
            if keys:
                actual_lower = actual.lower()
                hits = sum(1 for k in keys if k in actual_lower)
                similarity = hits / len(keys)
                norm = self._normalize_similarity(similarity)
                if norm >= self.full_threshold:
                    category, credit, is_correct = "very_good", 1.0, True
                elif norm >= self.partial_threshold:
                    category, credit, is_correct = "partially_correct", 0.5, False
                else:
                    category, credit, is_correct = "wrong", 0.0, False
                result.update({
                    "similarity": norm,
                    "raw_similarity": similarity,
                    "is_correct": is_correct,
                    "method": "keyword",
                    "reasoning": f"Matched {hits} out of {len(keys)} keywords",
                    "category": category,
                    "credit": credit
                })
                # Early return when we prefer keyword-based scoring
                if self.prefer_keywords:
                    return result
                # else fall through to semantic for refinement when available

        if expected and actual and self.use_semantic and self.semantic_grader:
            try:
                similarity, reasoning = await self.semantic_grader.compare_answers(expected, actual)
                norm = self._normalize_similarity(similarity)
                # Determine category/credit
                if norm >= self.full_threshold:
                    category, credit, is_correct = "very_good", 1.0, True
                elif norm >= self.partial_threshold:
                    category, credit, is_correct = "partially_correct", 0.5, False
                else:
                    category, credit, is_correct = "wrong", 0.0, False
                result.update({
                    "similarity": norm,
                    "raw_similarity": similarity,
                    "is_correct": is_correct,
                    "method": "semantic",
                    "reasoning": reasoning,
                    "category": category,
                    "credit": credit
                })
                return result
            except Exception as e:
                logging.error(f"Semantic comparison failed: {str(e)}")
        
        # Fall back to keyword matching if semantic comparison not available or failed
        # If we have not returned yet and keywords exist, use keyword scoring as fallback
        if keywords:
            keys = [k.strip().lower() for k in keywords.split(",") if k.strip()]
            if keys:
                actual_lower = actual.lower()
                hits = sum(1 for k in keys if k in actual_lower)
                similarity = hits / len(keys)
                norm = self._normalize_similarity(similarity)
                if norm >= self.full_threshold:
                    category, credit, is_correct = "very_good", 1.0, True
                elif norm >= self.partial_threshold:
                    category, credit, is_correct = "partially_correct", 0.5, False
                else:
                    category, credit, is_correct = "wrong", 0.0, False
                result.update({
                    "similarity": norm,
                    "raw_similarity": similarity,
                    "is_correct": is_correct,
                    "method": "keyword",
                    "reasoning": f"Matched {hits} out of {len(keys)} keywords",
                    "category": category,
                    "credit": credit
                })
                return result
        
        # Final fallback to character-based comparison
        if expected and actual:
            similarity = SequenceMatcher(None, expected.lower(), actual.lower()).ratio()
            norm = self._normalize_similarity(similarity)
            if norm >= self.full_threshold:
                category, credit, is_correct = "very_good", 1.0, True
            elif norm >= self.partial_threshold:
                category, credit, is_correct = "partially_correct", 0.5, False
            else:
                category, credit, is_correct = "wrong", 0.0, False
            result.update({
                "similarity": norm,
                "raw_similarity": similarity,
                "is_correct": is_correct,
                "method": "character",
                "reasoning": "Used character sequence matching",
                "category": category,
                "credit": credit
            })
        
        return result

    async def grade(self, student_image_path: str, template: Dict[str, Any]) -> Dict[str, Any]:
        """
        Grade the student worksheet against the supplied template.
        This is now an async method to support semantic comparison.
        """
        image = cv2.imread(student_image_path)
        if image is None or image.size == 0:
            raise ValueError("Unable to read student image for grading")
        img_h, img_w = image.shape[:2]

        results = []
        boxes = template.get("boxes") or template.get("questions") or []
        
        # Process all boxes to extract text first
        box_data = []
        for box in boxes:
            # Determine relative position data
            if "relative_position" in box and box["relative_position"]:
                rel = box["relative_position"]
            else:
                # Derive from absolute using original template dims
                img_dims = template.get("image_dimensions", {})
                tpl_w = img_dims.get("width") or 1
                tpl_h = img_dims.get("height") or 1
                rel = {
                    "x": box.get("x", 0) / tpl_w,
                    "y": box.get("y", 0) / tpl_h,
                    "width": box.get("width", 0) / tpl_w,
                    "height": box.get("height", 0) / tpl_h,
                }
            pos_abs = self._relative_to_absolute(rel, img_w, img_h)
            
            # Extract OCR text
            actual_answer = self._extract_text(image, pos_abs)
            expected_answer = template.get("model_answers", {}).get(box["id"], box.get("answer", ""))
            # Derive keywords: use provided keywords, otherwise auto-extract from expected answer
            kw = box.get("keywords", "").strip()
            if not kw and expected_answer:
                import re
                text = expected_answer.lower()
                text = re.sub(r"[^a-z0-9\s]", "", text)
                tokens = [t for t in text.split() if len(t) >= 4]
                stop = {"this","that","with","have","has","very","they","them","then","from","into","onto","over","under","your","yours","ours","also","such","like","look","looks","looked","there","their","these","those","about","more","most","some","many","much","just","only","been","being","were","will","would","could","should","wide"}
                keywords_list = []
                for t in tokens:
                    if t in stop:
                        continue
                    if t not in keywords_list:
                        keywords_list.append(t)
                # take top 6 keywords to keep it simple
                kw = ",".join(keywords_list[:6])

            box_data.append({
                "box": box,
                "pos_abs": pos_abs,
                "expected": expected_answer,
                "actual": actual_answer,
                "keywords": kw
            })
        
        # Process all comparisons (can be done in parallel if needed)
        for data in box_data:
            comparison = await self._compare(
                data["expected"],
                data["actual"],
                data["keywords"]
            )
            
            results.append({
                "question_id": data["box"]["id"],
                "expected": data["expected"],
                "actual": data["actual"],
                "similarity": comparison["similarity"],
                "is_correct": comparison["is_correct"],
                "grading_method": comparison["method"],
                "reasoning": comparison.get("reasoning", ""),
                "category": comparison.get("category", "wrong"),
                "credit": comparison.get("credit", 0.0),
                "position": data["pos_abs"]
            })

        score_correct = sum(1 for r in results if r["is_correct"])
        score_credits = sum(float(r.get("credit", 0.0)) for r in results)
        summary = {
            "correct": score_correct,
            "partial": sum(1 for r in results if r.get("category") == "partially_correct"),
            "wrong": sum(1 for r in results if r.get("category") == "wrong"),
            "sum_credits": score_credits,
            "max_credits": float(len(results))
        }
        return {
            "answers": results,
            "score": score_correct,
            "total": len(results),
            "summary": summary
        }

