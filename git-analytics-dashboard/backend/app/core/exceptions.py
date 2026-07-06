"""
Custom Exception Handlers for FastAPI
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundException(AppException):
    """Resource not found."""

    def __init__(self, resource: str = "Resource", resource_id: str = ""):
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} with id '{resource_id}' not found"
        super().__init__(message=message, status_code=404)


class ConflictException(AppException):
    """Resource already exists."""

    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message=message, status_code=409)


class ValidationException(AppException):
    """Validation error."""

    def __init__(self, message: str = "Validation error"):
        super().__init__(message=message, status_code=422)


class GitException(AppException):
    """Git operation error."""

    def __init__(self, message: str = "Git operation failed"):
        super().__init__(message=message, status_code=500)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers."""

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "message": exc.message,
                "data": None,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "Internal server error",
                "data": None,
            },
        )
