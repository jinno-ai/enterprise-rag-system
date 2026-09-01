"""
Shared path validation utilities

This module provides common path validation functions used across API routes.
"""

from fastapi import HTTPException
from pathlib import Path
from typing import Optional


def validate_path_safety(file_path: str, allowed_base_dir: Optional[str] = None) -> None:
    """
    Validate that a path doesn't contain path traversal attempts.

    Args:
        file_path: The path to validate
        allowed_base_dir: Optional base directory that the path must be within

    Raises:
        HTTPException: If path is unsafe (contains traversal or outside allowed directory)

    Examples:
        >>> validate_path_safety("safe/path.txt")
        >>> validate_path_safety("../etc/passwd")  # Raises HTTPException
        >>> validate_path_safety("file.txt", "/home/user/docs")  # Validates within allowed dir
    """
    # Check for path traversal patterns
    if ".." in file_path:
        raise HTTPException(
            status_code=400,
            detail="Invalid path: path traversal detected"
        )

    # If base directory is specified, ensure path is within it
    if allowed_base_dir:
        resolved_path = Path(file_path).resolve()
        base_dir = Path(allowed_base_dir).resolve()
        try:
            resolved_path.relative_to(base_dir)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid path: must be within {allowed_base_dir}"
            )
