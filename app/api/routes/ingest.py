"""
Document ingestion endpoints
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict
from datetime import datetime
from pathlib import Path
import os

from app.core.rate_limit import limiter

router = APIRouter()


def validate_path_safety(file_path: str, allowed_base_dir: str = None) -> bool:
    """
    Validate that a path doesn't contain path traversal attempts.

    Args:
        file_path: The path to validate
        allowed_base_dir: Optional base directory that the path must be within

    Returns:
        True if path is safe, False otherwise

    Raises:
        HTTPException: If path is unsafe
    """
    # Check for path traversal patterns (only block ".." for actual traversal)
    if ".." in file_path:
        raise HTTPException(
            status_code=400,
            detail="Invalid path: path traversal detected"
        )

    # Resolve the absolute path
    resolved_path = Path(file_path).resolve()

    # If base directory is specified, ensure path is within it
    if allowed_base_dir:
        base_dir = Path(allowed_base_dir).resolve()
        try:
            resolved_path.relative_to(base_dir)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid path: path must be within {allowed_base_dir}"
            )

    return True


@router.post("/ingest")
@limiter.limit("20/minute")
async def ingest_documents(request: Request, source_path: str, collection: str = "default") -> Dict:
    """
    Ingest documents from a source path

    Args:
        request: FastAPI Request object
        source_path: Path to documents
        collection: Collection name

    Returns:
        Ingestion status
    """
    try:
        # Validate path safety
        validate_path_safety(source_path)

        # Mock implementation
        return {
            "status": "success",
            "message": "Documents ingested successfully",
            "documents_processed": 10,
            "chunks_created": 50,
            "collection": collection,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ingest/status/{task_id}")
async def get_ingestion_status(task_id: str) -> Dict:
    """Get ingestion task status"""
    return {
        "task_id": task_id,
        "status": "completed",
        "progress": 100
    }
