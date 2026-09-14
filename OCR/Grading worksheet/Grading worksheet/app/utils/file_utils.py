# ""
# File handling utilities for the Handwriting OCR application.
#
# This module provides functions for handling file uploads, validation, and processing.
# """
# import os
# import uuid
# from pathlib import Path
# from typing import Tuple, Optional
# from fastapi import UploadFile, HTTPException
# import imghdr
# from PIL import Image
# import io
#
# from app.config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, MAX_CONTENT_LENGTH
#
# def allowed_file(filename: str) -> bool:
#     """Check if the file has an allowed extension.
#
#     Args:
#         filename: Name of the file to check
#
#     Returns:
#         bool: True if the file extension is allowed, False otherwise
#     """
#     return '.' in filename and \
#            filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
#
# def save_upload_file(upload_file: UploadFile) -> Tuple[str, str]:
#     """Save an uploaded file to the uploads folder.
#
#     Args:
#         upload_file: The uploaded file object from FastAPI
#
#     Returns:
#         Tuple containing (saved_file_path, original_filename)
#
#     Raises:
#         HTTPException: If the file is not allowed or there's an error saving
#     """
#     try:
#         # Check if the file is empty
#         if upload_file.filename == '':
#             raise HTTPException(status_code=400, detail="No selected file")
#
#         # Check if the file has an allowed extension
#         if not allowed_file(upload_file.filename):
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
#             )
#
#         # Generate a unique filename to prevent overwriting
#         file_ext = Path(upload_file.filename).suffix
#         unique_filename = f"{uuid.uuid4().hex}{file_ext}"
#         file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
#
#         # Save the file
#         with open(file_path, "wb") as buffer:
#             # Read the file in chunks to handle large files
#             while True:
#                 chunk = upload_file.file.read(8192)  # 8KB chunks
#                 if not chunk:
#                     break
#                 buffer.write(chunk)
#
#         # Verify the file is a valid image
#         if not is_valid_image(file_path):
#             os.remove(file_path)  # Clean up invalid file
#             raise HTTPException(status_code=400, detail="Invalid image file")
#
#         return file_path, upload_file.filename
#
#     except Exception as e:
#         # Clean up in case of any error
#         if 'file_path' in locals() and os.path.exists(file_path):
#             os.remove(file_path)
#         raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")
#
# def is_valid_image(file_path: str) -> bool:
#     """Check if the file is a valid image.
#
#     Args:
#         file_path: Path to the file to check
#
#     Returns:
#         bool: True if the file is a valid image, False otherwise
#     """
#     try:
#         # Check file size
#         if os.path.getsize(file_path) > MAX_CONTENT_LENGTH:
#             return False
#
#         # Check if the file is a valid image
#         with Image.open(file_path) as img:
#             img.verify()  # Verify it's an image
#
#         # Check the file extension matches the actual content
#         file_ext = Path(file_path).suffix[1:].lower()
#         if file_ext == 'jpg':
#             file_ext = 'jpeg'  # PIL uses 'jpeg' not 'jpg'
#
#         with open(file_path, 'rb') as f:
#             image_type = imghdr.what(f)
#
#         if not image_type:
#             return False
#
#         # Check if the detected image type matches the extension
#         return image_type.lower() == file_ext.lower()
#
#     except Exception:
#         return False
#
# def convert_to_jpg(input_path: str, output_path: Optional[str] = None) -> str:
#     """Convert an image to JPG format.
#
#     Args:
#         input_path: Path to the input image
#         output_path: Path to save the converted image. If None, a temporary file is created.
#
#     Returns:
#         Path to the converted image
#     """
#     if output_path is None:
#         output_path = f"{os.path.splitext(input_path)[0]}.jpg"
#
#     try:
#         with Image.open(input_path) as img:
#             # Convert to RGB if needed (for PNG with transparency)
#             if img.mode in ('RGBA', 'P'):
#                 img = img.convert('RGB')
#             img.save(output_path, 'JPEG', quality=95)
#
#         # Remove the original file if it's not the same as the output
#         if input_path != output_path and os.path.exists(input_path):
#             os.remove(input_path)
#
#         return output_path
#     except Exception as e:
#         raise Exception(f"Error converting image to JPG: {str(e)}")
#
# def cleanup_file(file_path: str) -> None:
#     """Safely remove a file if it exists.
#
#     Args:
#         file_path: Path to the file to remove
#     """
#     try:
#         if file_path and os.path.exists(file_path):
#             os.remove(file_path)
#     except Exception:
#         pass  # Ignore errors during cleanup
