"""
Dependency Injection for API routes
"""

from fastapi import Request
from app.services.rag_pipeline import RAGPipeline


def get_rag_pipeline(request: Request) -> RAGPipeline:
    """Get the RAG pipeline instance from the app state"""
    pipeline = getattr(request.app.state, "rag_pipeline", None)
    if pipeline is None:
        raise RuntimeError("RAG pipeline not initialized in app state")
    return pipeline
