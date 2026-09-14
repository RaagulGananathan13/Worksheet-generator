"""
Image processing utilities for the Handwriting OCR application.

This module provides functions for enhancing and preprocessing images to improve OCR accuracy.
"""
import cv2
import numpy as np
from typing import Tuple, Optional, Dict, Any
from PIL import Image, ImageEnhance, ImageOps, ImageFilter
import imutils
from skimage import exposure
import logging

logger = logging.getLogger(__name__)

class ImageEnhancer:
    """A class for enhancing image quality for better OCR results."""
    
    @staticmethod
    def adjust_brightness_contrast(
        image: np.ndarray, 
        alpha: float = 1.2, 
        beta: int = 10
    ) -> np.ndarray:
        """Adjust the brightness and contrast of an image.
        
        Args:
            image: Input image (BGR or grayscale)
            alpha: Contrast control (1.0 means no change)
            beta: Brightness control (0 means no change)
            
        Returns:
            Enhanced image
        """
        if len(image.shape) == 3:
            # Convert to grayscale for processing
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        # Apply contrast and brightness
        enhanced = cv2.convertScaleAbs(gray, alpha=alpha, beta=beta)
        
        return enhanced
    
    @staticmethod
    def remove_noise(
        image: np.ndarray, 
        kernel_size: Tuple[int, int] = (3, 3)
    ) -> np.ndarray:
        """Remove noise from an image using median blur.
        
        Args:
            image: Input image (grayscale)
            kernel_size: Size of the kernel for median blur
            
        Returns:
            Denoised image
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        return cv2.medianBlur(gray, kernel_size[0])
    
    @staticmethod
    def enhance_edges(image: np.ndarray) -> np.ndarray:
        """Enhance edges in an image using unsharp masking.
        
        Args:
            image: Input image (BGR or grayscale)
            
        Returns:
            Image with enhanced edges
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        # Apply Gaussian blur
        blurred = cv2.GaussianBlur(gray, (0, 0), 3)
        
        # Apply unsharp masking
        unsharp = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)
        
        return unsharp
    
    @staticmethod
    def adjust_gamma(image: np.ndarray, gamma: float = 1.0) -> np.ndarray:
        """Adjust the gamma of an image.
        
        Args:
            image: Input image (BGR or grayscale)
            gamma: Gamma value (1.0 means no change)
            
        Returns:
            Gamma-corrected image
        """
        if len(image.shape) == 3:
            # Convert to grayscale for processing
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        # Build a lookup table mapping the pixel values [0, 255] to their adjusted gamma values
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 
                         for i in np.arange(0, 256)]).astype("uint8")
        
        # Apply gamma correction using the lookup table
        return cv2.LUT(gray, table)
    
    @staticmethod
    def adaptive_threshold(
        image: np.ndarray, 
        block_size: int = 11,
        c: int = 2
    ) -> np.ndarray:
        """Apply adaptive thresholding to an image.
        
        Args:
            image: Input image (grayscale)
            block_size: Size of a pixel neighborhood for threshold calculation
            c: Constant subtracted from the mean or weighted mean
            
        Returns:
            Thresholded image
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 
            block_size, c
        )
        
        return thresh
    
    @staticmethod
    def deskew(image: np.ndarray) -> np.ndarray:
        """Deskew an image to align text horizontally.
        
        Args:
            image: Input image (BGR or grayscale)
            
        Returns:
            Deskewed image
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        # Threshold the image, setting all foreground pixels to 255 and all background pixels to 0
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        
        # Find all non-zero coordinates in the thresholded image
        coords = np.column_stack(np.where(thresh > 0))
        
        # Compute the rotated bounding box that contains all coordinates
        angle = cv2.minAreaRect(coords)[-1]
        
        # The `cv2.minAreaRect` function returns values in the range [-90, 0); as the rectangle 
        # rotates clockwise the returned angle tends to 0
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
            
        # Rotate the image to deskew it
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            image, M, (w, h), 
            flags=cv2.INTER_CUBIC, 
            borderMode=cv2.BORDER_REPLICATE
        )
        
        return rotated
    
    @staticmethod
    def enhance_contrast(image: np.ndarray) -> np.ndarray:
        """Enhance the contrast of an image using CLAHE.
        
        Args:
            image: Input image (BGR or grayscale)
            
        Returns:
            Contrast-enhanced image
        """
        if len(image.shape) == 3:
            # Convert to LAB color space
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE to L channel
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            
            # Merge the CLAHE enhanced L channel with the a and b channels
            limg = cv2.merge((cl, a, b))
            
            # Convert back to BGR color space
            enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
        else:
            # For grayscale images
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(image)
            
        return enhanced
    
    @staticmethod
    def preprocess_for_ocr(
        image: np.ndarray, 
        denoise: bool = True,
        enhance_contrast: bool = True,
        deskew: bool = True,
        threshold: bool = True
    ) -> np.ndarray:
        """Apply a series of preprocessing steps to prepare an image for OCR.
        
        Args:
            image: Input image (BGR or file path)
            denoise: Whether to apply denoising
            enhance_contrast: Whether to enhance contrast
            deskew: Whether to deskew the image
            threshold: Whether to apply thresholding
            
        Returns:
            Preprocessed image
        """
        # If input is a file path, load the image
        if isinstance(image, str):
            image = cv2.imread(image)
            if image is None:
                raise ValueError(f"Could not read image at {image}")
        
        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        
        # Apply preprocessing steps
        processed = gray.copy()
        
        if denoise:
            processed = cv2.fastNlMeansDenoising(processed, None, 10, 7, 21)
        
        if enhance_contrast:
            processed = ImageEnhancer.enhance_contrast(processed)
            
        if deskew:
            processed = ImageEnhancer.deskew(processed)
            
        if threshold:
            processed = cv2.adaptiveThreshold(
                processed, 255, 
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, 
                11, 2
            )
        
        return processed

class ImageAlignmentError(Exception):
    """Exception raised when image alignment fails."""
    pass

class ImageAlignment:
    """A class for aligning images."""
    
    @staticmethod
    def align_images(template_img: np.ndarray, student_img: np.ndarray, max_features: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        """
        Align student's image to match the template image using feature matching.
        
        Args:
            template_img: The template image (numpy array in BGR format)
            student_img: The student's image to align (numpy array in BGR format)
            max_features: Maximum number of features to detect
            
        Returns:
            Tuple of (aligned_image, transformation_matrix)
            
        Raises:
            ImageAlignmentError: If alignment fails
        """
        try:
            # Convert images to grayscale
            gray_template = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
            gray_student = cv2.cvtColor(student_img, cv2.COLOR_BGR2GRAY)
            
            # Initialize ORB detector
            orb = cv2.ORB_create(max_features)
            
            # Find keypoints and descriptors
            kp1, des1 = orb.detectAndCompute(gray_template, None)
            kp2, des2 = orb.detectAndCompute(gray_student, None)
            
            if des1 is None or des2 is None or len(des1) < 4 or len(des2) < 4:
                raise ImageAlignmentError("Not enough features to match")
            
            # Create BFMatcher and match descriptors
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = matcher.match(des1, des2)
            
            if len(matches) < 4:
                raise ImageAlignmentError("Not enough matches found")
                
            # Sort matches by distance
            matches = sorted(matches, key=lambda x: x.distance)
            
            # Extract location of good matches
            points1 = np.zeros((len(matches), 2), dtype=np.float32)
            points2 = np.zeros((len(matches), 2), dtype=np.float32)
            
            for i, match in enumerate(matches):
                points1[i, :] = kp1[match.queryIdx].pt
                points2[i, :] = kp2[match.trainIdx].pt
            
            # Find homography
            h, mask = cv2.findHomography(points2, points1, cv2.RANSAC)
            
            if h is None:
                raise ImageAlignmentError("Failed to compute homography")
            
            # Warp the student image to align with template
            height, width = template_img.shape[:2]
            aligned_img = cv2.warpPerspective(student_img, h, (width, height))
            
            return aligned_img, h
            
        except cv2.error as e:
            logger.error(f"OpenCV error during image alignment: {str(e)}")
            raise ImageAlignmentError(f"Image alignment failed: {str(e)}")
        except Exception as e:
            logger.error(f"Error in image alignment: {str(e)}")
            raise ImageAlignmentError(f"Image processing error: {str(e)}")

    @staticmethod
    def preprocess_image(image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for better OCR results.
        
        Args:
            image: Input image in BGR format
            
        Returns:
            Preprocessed grayscale image
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Denoising
        denoised = cv2.fastNlMeansDenoising(thresh, None, 10, 7, 21)
        
        return denoised

    @staticmethod
    def scale_coordinates(coords: Dict[str, int], scale_x: float, scale_y: float) -> Dict[str, int]:
        """
        Scale coordinates based on the ratio between template and student image sizes.
        
        Args:
            coords: Dictionary containing 'x', 'y', 'width', 'height'
            scale_x: Scaling factor for x-coordinates
            scale_y: Scaling factor for y-coordinates
            
        Returns:
            Dictionary with scaled coordinates
        """
        return {
            'x': int(coords['x'] * scale_x),
            'y': int(coords['y'] * scale_y),
            'width': int(coords['width'] * scale_x),
            'height': int(coords['height'] * scale_y)
        }

    @staticmethod
    def scale_dot_position(dot_x, dot_y, template_width, template_height, student_width, student_height):
        """
        Scale a dot position from template coordinates to student image coordinates using the ratio method.

        Args:
            dot_x (float): X coordinate in template image
            dot_y (float): Y coordinate in template image
            template_width (int): Width of template image
            template_height (int): Height of template image
            student_width (int): Width of student image
            student_height (int): Height of student image
        Returns:
            (float, float): Scaled (x, y) coordinates in student image
        """
        width_ratio = student_width / template_width
        height_ratio = student_height / template_height
        scale = min(width_ratio, height_ratio)
        scaled_x = dot_x * scale
        scaled_y = dot_y * scale
        return scaled_x, scaled_y
