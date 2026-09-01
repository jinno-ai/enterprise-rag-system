"""
API v2 Routes Package

This package contains v2 API endpoints with enhanced features while
maintaining backward compatibility with v1.
"""

from fastapi import APIRouter

from app.api.routes.v2 import query, ingest, documents

# Create v2 router
router = APIRouter(prefix="/api/v2", tags=["API v2"])

# Include v2 route modules
router.include_router(query.router, prefix="/query", tags=["Query v2"])
router.include_router(ingest.router, prefix="/ingest", tags=["Ingest v2"])
router.include_router(documents.router, prefix="/documents", tags=["Documents v2"])

__all__ = ["router"]
