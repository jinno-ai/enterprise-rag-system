"""
Middleware package for Enterprise RAG System
"""

from app.middleware.compression import (
    CompressionMiddleware,
    MIN_COMPRESSION_SIZE,
)

__all__ = [
    "CompressionMiddleware",
    "MIN_COMPRESSION_SIZE",
]
