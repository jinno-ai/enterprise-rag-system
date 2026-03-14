"""
Gzip Compression Middleware for FastAPI

This middleware provides gzip compression for API responses to reduce bandwidth
and improve performance for large JSON responses.
"""

import logging
from typing import Optional

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


# Minimum size threshold for compression (in bytes)
# Responses smaller than this won't be compressed to avoid CPU overhead
MIN_COMPRESSION_SIZE = 500


class CompressionMiddleware(GZipMiddleware):
    """
    Middleware to compress responses using gzip.

    Extends Starlette's GZipMiddleware with:
    - Configurable minimum size threshold (avoids CPU overhead for small responses)
    - Enhanced validation and logging

    Compresses responses larger than minimum_size when the client
    supports gzip encoding (indicated by 'Accept-Encoding: gzip' header).

    Note: Content-type filtering is handled internally by Starlette's GZipMiddleware.
    """

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = MIN_COMPRESSION_SIZE,
        compresslevel: int = 6,
    ) -> None:
        """
        Initialize the compression middleware.

        Args:
            app: The ASGI application to wrap
            minimum_size: Minimum response size (bytes) to trigger compression
            compresslevel: Gzip compression level (0-9, default 6)
                          0 = no compression, 1 = fastest, 9 = best compression

        Raises:
            ValueError: If compresslevel is not between 0 and 9
        """
        # Validate compression level BEFORE calling parent init
        if not isinstance(compresslevel, int) or compresslevel < 0 or compresslevel > 9:
            raise ValueError(
                f"compresslevel must be an integer between 0 and 9, got {compresslevel!r}"
            )

        # Store minimum size
        self.minimum_size = minimum_size

        # Initialize parent GZipMiddleware with our parameters
        super().__init__(app, minimum_size=minimum_size, compresslevel=compresslevel)

        logger.info(
            f"Compression middleware initialized: "
            f"min_size={minimum_size} bytes, level={compresslevel}"
        )
