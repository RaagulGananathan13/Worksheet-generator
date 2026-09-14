"""
Response utilities for the Handwriting OCR API.

This module provides helper functions for generating consistent API responses.
"""
from typing import Any, Dict, List, Optional, Union
from fastapi.responses import JSONResponse
from fastapi import status

class APIResponse:
    """A class to handle consistent API responses."""
    
    @staticmethod
    def success(
        data: Any = None,
        message: str = "Operation completed successfully",
        status_code: int = status.HTTP_200_OK,
        meta: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """Generate a success response.
        
        Args:
            data: The data to include in the response
            message: A success message
            status_code: HTTP status code
            meta: Additional metadata
            
        Returns:
            JSONResponse: A formatted success response
        """
        response_data: Dict[str, Any] = {
            "status": "success",
            "message": message,
        }
        
        if data is not None:
            response_data["data"] = data
            
        if meta:
            response_data["meta"] = meta
            
        return JSONResponse(
            content=response_data,
            status_code=status_code
        )
    
    @staticmethod
    def error(
        message: str = "An error occurred",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        errors: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        error_code: Optional[str] = None
    ) -> JSONResponse:
        """Generate an error response.
        
        Args:
            message: An error message
            status_code: HTTP status code
            errors: Additional error details
            error_code: A custom error code
            
        Returns:
            JSONResponse: A formatted error response
        """
        response_data: Dict[str, Any] = {
            "status": "error",
            "message": message,
        }
        
        if error_code:
            response_data["code"] = error_code
            
        if errors is not None:
            response_data["errors"] = errors
            
        return JSONResponse(
            content=response_data,
            status_code=status_code
        )
    
    @staticmethod
    def not_found(message: str = "The requested resource was not found") -> JSONResponse:
        """Generate a 404 Not Found response.
        
        Args:
            message: Error message
            
        Returns:
            JSONResponse: A 404 error response
        """
        return APIResponse.error(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="not_found"
        )
    
    @staticmethod
    def unauthorized(message: str = "Authentication required") -> JSONResponse:
        """Generate a 401 Unauthorized response.
        
        Args:
            message: Error message
            
        Returns:
            JSONResponse: A 401 error response
        """
        return APIResponse.error(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="unauthorized"
        )
    
    @staticmethod
    def forbidden(message: str = "Insufficient permissions") -> JSONResponse:
        """Generate a 403 Forbidden response.
        
        Args:
            message: Error message
            
        Returns:
            JSONResponse: A 403 error response
        """
        return APIResponse.error(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="forbidden"
        )
    
    @staticmethod
    def bad_request(
        message: str = "Invalid request", 
        errors: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """Generate a 400 Bad Request response.
        
        Args:
            message: Error message
            errors: Validation errors
            
        Returns:
            JSONResponse: A 400 error response
        """
        return APIResponse.error(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            errors=errors,
            error_code="bad_request"
        )
    
    @staticmethod
    def server_error(message: str = "Internal server error") -> JSONResponse:
        """Generate a 500 Internal Server Error response.
        
        Args:
            message: Error message
            
        Returns:
            JSONResponse: A 500 error response
        """
        return APIResponse.error(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="internal_server_error"
        )
    
    @staticmethod
    def created(
        data: Any = None, 
        message: str = "Resource created successfully"
    ) -> JSONResponse:
        """Generate a 201 Created response.
        
        Args:
            data: The created resource
            message: Success message
            
        Returns:
            JSONResponse: A 201 success response
        """
        return APIResponse.success(
            data=data,
            message=message,
            status_code=status.HTTP_201_CREATED
        )
    
    @staticmethod
    def no_content() -> JSONResponse:
        """Generate a 204 No Content response.
        
        Returns:
            JSONResponse: A 204 response with no content
        """
        return JSONResponse(
            status_code=status.HTTP_204_NO_CONTENT
        )
    
    @staticmethod
    def paginated(
        items: List[Any],
        total: int,
        page: int,
        per_page: int,
        message: str = "Data retrieved successfully"
    ) -> JSONResponse:
        """Generate a paginated response.
        
        Args:
            items: List of items for the current page
            total: Total number of items
            page: Current page number
            per_page: Number of items per page
            message: Success message
            
        Returns:
            JSONResponse: A paginated response
        """
        total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1
        
        meta = {
            "pagination": {
                "total": total,
                "count": len(items),
                "per_page": per_page,
                "current_page": page,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1
            }
        }
        
        return APIResponse.success(
            data=items,
            message=message,
            meta=meta
        )
