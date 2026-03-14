"""
Ingest API Routes v2

This module defines v2 API endpoints for document ingestion.
v2 includes enhanced features while maintaining backward compatibility with v1.
"""

from fastapi import APIRouter, HTTPException, status, UploadFile, File
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime


router = APIRouter(tags=["ingest v2"])


class IngestRequestV2(BaseModel):
    """Enhanced request model for v2 ingest endpoint"""
    documents: List[Dict[str, Any]] = Field(..., description="List of documents to ingest")
    collection: Optional[str] = Field(None, description="Collection/namespace for documents")
    chunk_size: int = Field(512, description="Chunk size for text splitting", ge=128, le=2048)
    chunk_overlap: int = Field(50, description="Overlap between chunks", ge=0, le=200)
    process_async: bool = Field(False, description="Process ingestion asynchronously")


class IngestResponseV2(BaseModel):
    """Enhanced response model for v2 ingest endpoint"""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Ingestion status")
    documents_processed: int
    chunks_created: int
    collection: Optional[str]
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None


@router.post("/", response_model=IngestResponseV2, status_code=status.HTTP_202_ACCEPTED)
async def ingest_documents_v2(request: IngestRequestV2) -> IngestResponseV2:
    """
    Ingest documents into the RAG system (v2)

    Enhanced v2 endpoint with async processing support

    Args:
        request: Ingest request with documents and parameters

    Returns:
        IngestResponseV2 with job tracking information
    """
    try:
        job_id = str(uuid.uuid4())

        # For now, return a mock response
        # In production, this would trigger async processing
        return IngestResponseV2(
            job_id=job_id,
            status="accepted",
            documents_processed=len(request.documents),
            chunks_created=len(request.documents) * 3,  # Mock calculation
            collection=request.collection,
            timestamp=datetime.utcnow().isoformat(),
            metadata={
                "chunk_size": request.chunk_size,
                "chunk_overlap": request.chunk_overlap,
                "async": request.process_async
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {str(e)}"
        )


@router.post("/upload", response_model=IngestResponseV2)
async def upload_document_v2(
    file: UploadFile = File(...),
    collection: Optional[str] = None,
    chunk_size: int = 512
) -> IngestResponseV2:
    """
    Upload and ingest a single document (v2)

    Enhanced v2 endpoint with file upload support

    Args:
        file: Uploaded file
        collection: Target collection
        chunk_size: Text chunking size

    Returns:
        IngestResponseV2 with job tracking information
    """
    try:
        job_id = str(uuid.uuid4())

        # Mock response for now
        return IngestResponseV2(
            job_id=job_id,
            status="accepted",
            documents_processed=1,
            chunks_created=3,
            collection=collection,
            timestamp=datetime.utcnow().isoformat(),
            metadata={"filename": file.filename, "chunk_size": chunk_size}
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check_v2() -> Dict[str, str]:
    """Health check endpoint for v2 ingest API"""
    return {
        "status": "healthy",
        "service": "RAG Ingest API v2",
        "version": "2.0"
    }
