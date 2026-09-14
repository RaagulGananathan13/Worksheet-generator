"""
OCR Services Module

This module contains services for performing Optical Character Recognition (OCR)
on handwritten documents.
"""

from .rapidapi_ocr_service import RapidOCRService, OCRResult

__all__ = ['RapidOCRService', 'OCRResult']
