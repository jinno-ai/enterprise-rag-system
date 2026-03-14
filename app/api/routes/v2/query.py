"""
Query API Routes v2

This module defines v2 API endpoints for querying the RAG system.
v2 includes enhanced features while maintaining backward compatibility with v1.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime

from app.services.rag_pipeline import RAGResponse


router = APIRouter(tags=["query v2"])


class QueryRequestV2(BaseModel):
    """Request model for v2 query endpoint with enhanced parameters"""
    query: str = Field(..., description="The question to ask", min_length=1)
    collection: Optional[str] = Field(None, description="Collection/namespace to search in")
    top_k: int = Field(5, description="Number of documents to retrieve", ge=1, le=20)
    use_hybrid: bool = Field(True, description="Use hybrid search (semantic + keyword)")
    filters: Optional[Dict[str, Any]] = Field(None, description="Metadata filters")
    include_metadata: bool = Field(False, description="Include additional metadata in response")
    response_format: str = Field("standard", description="Response format: standard, detailed, concise")


class QueryResponseV2(BaseModel):
    """Enhanced response model for v2 query endpoint"""
    query_id: str = Field(..., description="Unique identifier for this query")
    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    latency_ms: int
    tokens_used: int
    model_version: str = Field(..., description="API version identifier")
    timestamp: str = Field(..., description="Query execution timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata if requested")


class BatchQueryRequestV2(BaseModel):
    """Enhanced request model for v2 batch query endpoint"""
    queries: List[str] = Field(..., description="List of questions to ask")
    collection: Optional[str] = None
    top_k: int = Field(5, ge=1, le=20)
    parallel: bool = Field(False, description="Execute queries in parallel")
    include_metadata: bool = Field(False, description="Include metadata in responses")


@router.post("/", response_model=QueryResponseV2, status_code=status.HTTP_200_OK)
async def query_v2(request: QueryRequestV2) -> QueryResponseV2:
    """
    Query the RAG system with a question (v2)

    Enhanced v2 endpoint with additional features:
    - Unique query ID for tracking
    - Timestamp information
    - Optional metadata inclusion
    - Multiple response formats

    Args:
        request: Query request with question and parameters

    Returns:
        QueryResponseV2 with enhanced response information
    """
    try:
        # Get RAG pipeline instance (should be injected via dependency)
        from app.main import get_rag_pipeline

        pipeline = get_rag_pipeline()

        # Execute query
        result = pipeline.query(
            question=request.query,
            top_k=request.top_k,
            use_hybrid=request.use_hybrid,
            filter_dict=request.filters
        )

        # Generate metadata if requested
        metadata = None
        if request.include_metadata:
            metadata = {
                "collection": request.collection,
                "search_type": "hybrid" if request.use_hybrid else "semantic",
                "top_k": request.top_k,
                "response_format": request.response_format
            }

        return QueryResponseV2(
            query_id=str(uuid.uuid4()),
            answer=result.answer,
            sources=result.sources,
            confidence=result.confidence,
            latency_ms=result.latency_ms,
            tokens_used=result.tokens_used,
            model_version="2.0",
            timestamp=datetime.utcnow().isoformat(),
            metadata=metadata
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(e)}"
        )


@router.post("/batch", response_model=List[QueryResponseV2])
async def batch_query_v2(request: BatchQueryRequestV2) -> List[QueryResponseV2]:
    """
    Query the RAG system with multiple questions (v2)

    Enhanced v2 endpoint with parallel execution support

    Args:
        request: Batch query request with parallel option

    Returns:
        List of QueryResponseV2 objects
    """
    try:
        from app.main import get_rag_pipeline

        pipeline = get_rag_pipeline()

        # Execute batch query (parallelism would be implemented in the pipeline)
        results = pipeline.batch_query(
            questions=request.queries,
            top_k=request.top_k
        )

        responses = []
        for idx, result in enumerate(results):
            # Generate metadata if requested
            metadata = None
            if request.include_metadata:
                metadata = {
                    "collection": request.collection,
                    "query_index": idx,
                    "parallel": request.parallel
                }

            responses.append(QueryResponseV2(
                query_id=str(uuid.uuid4()),
                answer=result.answer,
                sources=result.sources,
                confidence=result.confidence,
                latency_ms=result.latency_ms,
                tokens_used=result.tokens_used,
                model_version="2.0",
                timestamp=datetime.utcnow().isoformat(),
                metadata=metadata
            ))

        return responses

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch query failed: {str(e)}"
        )


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check_v2() -> Dict[str, str]:
    """Health check endpoint for v2 API"""
    return {
        "status": "healthy",
        "service": "RAG Query API v2",
        "version": "2.0"
    }
