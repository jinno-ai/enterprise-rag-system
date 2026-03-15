"""
Document Chunking Strategies

This module provides multiple document chunking strategies for RAG applications:
- Fixed-size chunking: Simple character-based chunking with overlap
- Recursive character chunking: Smart chunking using separators
- Semantic chunking: Content-aware chunking based on semantic similarity

Each strategy is optimized for different document types and use cases.
"""

from typing import List, Dict, Any, Optional, Protocol
from dataclasses import dataclass, field
from enum import Enum
import logging
import re

logger = logging.getLogger(__name__)


class ChunkingStrategy(str, Enum):
    """Chunking strategy types"""
    FIXED = "fixed"
    RECURSIVE = "recursive"
    SENTENCE = "sentence"  # Sentence-based chunking (groups sentences into chunks)


@dataclass
class Chunk:
    """A chunk of text with metadata"""
    content: str
    chunk_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary"""
        return {
            "content": self.content,
            "chunk_id": self.chunk_id,
            "metadata": self.metadata
        }


@dataclass
class ChunkingConfig:
    """Configuration for document chunking"""
    chunk_size: int = 1000
    chunk_overlap: int = 200
    strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE

    def __post_init__(self):
        """Validate configuration"""
        if not 100 <= self.chunk_size <= 100_000:
            raise ValueError(
                f"Chunk size must be between 100 and 100000, got {self.chunk_size}"
            )
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError(
                f"Overlap must be between 0 and chunk_size (got {self.chunk_overlap})"
            )
        if not isinstance(self.strategy, ChunkingStrategy):
            raise ValueError(
                f"Invalid strategy: {self.strategy}. Must be ChunkingStrategy enum"
            )


@dataclass
class ChunkingResult:
    """Result of chunking a document"""
    doc_id: str
    chunks: List[Chunk]
    total_chunks: int
    strategy_used: ChunkingStrategy

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary"""
        return {
            "doc_id": self.doc_id,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "total_chunks": self.total_chunks,
            "strategy_used": self.strategy_used.value
        }


class BaseChunkingStrategy(Protocol):
    """Base protocol for chunking strategies"""

    def chunk(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """Split text into chunks"""
        ...


class FixedSizeChunkingStrategy:
    """
    Fixed-size chunking strategy.

    Splits text into chunks of fixed character length with overlap.
    Simple and predictable, but may break at arbitrary points.
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """
        Split text into fixed-size chunks with overlap.

        Args:
            text: Text to chunk
            metadata: Optional metadata to attach to chunks

        Returns:
            List of chunks
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}
        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]

            # Create chunk with metadata
            chunk_metadata = {
                **metadata,
                "chunk_index": chunk_index,
                "chunk_strategy": "fixed",
                "chunk_id": f"{metadata.get('source', 'doc')}_chunk_{chunk_index}"
            }

            chunk = Chunk(
                content=chunk_text,
                chunk_id=chunk_metadata["chunk_id"],
                metadata=chunk_metadata
            )
            chunks.append(chunk)

            # Move start position with overlap
            start += (self.chunk_size - self.chunk_overlap)
            chunk_index += 1

        # Update total chunks in metadata
        for chunk in chunks:
            chunk.metadata["total_chunks"] = len(chunks)

        logger.debug(f"Created {len(chunks)} fixed-size chunks")
        return chunks


class RecursiveCharacterChunkingStrategy:
    """
    Recursive character chunking strategy.

    Tries to split text at meaningful boundaries (paragraphs, sentences, words)
    before falling back to character-level splitting. Preserves context better
    than fixed-size chunking.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Optional[List[str]] = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def chunk(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """
        Split text using recursive separator-based approach.

        Args:
            text: Text to chunk
            metadata: Optional metadata to attach to chunks

        Returns:
            List of chunks
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}

        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        chunks = self._recursive_split(text, self.separators)

        # Add metadata to chunks
        chunked_docs = []
        for i, chunk_text in enumerate(chunks):
            chunk_metadata = {
                **metadata,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "chunk_strategy": "recursive",
                "chunk_id": f"{metadata.get('source', 'doc')}_chunk_{i}"
            }

            chunk = Chunk(
                content=chunk_text.strip(),
                chunk_id=chunk_metadata["chunk_id"],
                metadata=chunk_metadata
            )
            chunked_docs.append(chunk)

        logger.debug(f"Created {len(chunked_docs)} recursive chunks")
        return chunked_docs

    def _recursive_split(
        self,
        text: str,
        separators: List[str],
        is_last: bool = False
    ) -> List[str]:
        """
        Recursively split text using separators.

        Args:
            text: Text to split
            separators: List of separators to try (in order)
            is_last: Whether this is the last separator to try

        Returns:
            List of text chunks
        """
        # Base case: if text is short enough, return as single chunk
        if len(text) <= self.chunk_size:
            return [text]

        # Try each separator
        for i, separator in enumerate(separators):
            if separator == "":
                # Last resort: split by character
                return self._split_by_character(text)

            if separator in text:
                # Split by this separator
                parts = text.split(separator)
                chunks = []
                current_chunk = ""

                for part in parts:
                    # Check if adding this part (with separator) exceeds chunk size
                    test_length = len(current_chunk) + len(part) + (len(separator) if current_chunk else 0)

                    if test_length > self.chunk_size and current_chunk:
                        # Save current chunk
                        chunks.append(current_chunk)
                        # Start new chunk with overlap
                        overlap_text = self._get_overlap(current_chunk)
                        current_chunk = overlap_text + separator + part if overlap_text else part
                    else:
                        # Add to current chunk
                        if current_chunk:
                            current_chunk += separator + part
                        else:
                            current_chunk = part

                # Add last chunk
                if current_chunk:
                    chunks.append(current_chunk)

                # If we successfully created multiple chunks, return them
                if len(chunks) > 1 or (len(chunks) == 1 and len(chunks[0]) <= self.chunk_size):
                    return chunks

        # Fallback to character-level splitting
        return self._split_by_character(text)

    def _split_by_character(self, text: str) -> List[str]:
        """Split text by character position (last resort)"""
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start += (self.chunk_size - self.chunk_overlap)

        return chunks

    def _get_overlap(self, text: str) -> str:
        """Get overlap text from end of chunk"""
        if len(text) <= self.chunk_overlap:
            return text
        return text[-self.chunk_overlap:]


class SentenceBasedChunkingStrategy:
    """
    Sentence-based chunking strategy.

    Splits text into sentences and groups them into chunks of target size.
    Preserves sentence boundaries better than character-based splitting.

    Note: This is a simplified approach. For true semantic chunking with
    embedding-based similarity detection, use a dedicated semantic analysis
    service or implement custom logic with embeddings.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Initialize fallback strategy
        self._fallback_strategy = RecursiveCharacterChunkingStrategy(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

    def chunk(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """
        Split text by grouping sentences into chunks.

        Args:
            text: Text to chunk
            metadata: Optional metadata to attach to chunks

        Returns:
            List of chunks
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}

        try:
            # Split into sentences and group into chunks
            chunks = self._sentence_based_split(text, metadata)
            return chunks

        except Exception as e:
            # Fall back to recursive chunking on error
            logger.warning(f"Sentence-based chunking failed, falling back to recursive: {e}")
            return self._fallback_strategy.chunk(text, metadata)

    def _sentence_based_split(
        self,
        text: str,
        metadata: Dict[str, Any]
    ) -> List[Chunk]:
        """
        Perform sentence-based splitting.

        Groups sentences into chunks based on size while preserving
        sentence boundaries.
        """
        # Split into sentences (simplified)
        sentences = self._split_into_sentences(text)

        if len(sentences) <= 1:
            # Single sentence - return as single chunk
            chunk_metadata = {
                **metadata,
                "chunk_index": 0,
                "total_chunks": 1,
                "chunk_strategy": "semantic",
                "chunk_id": f"{metadata.get('source', 'doc')}_chunk_0"
            }
            return [Chunk(
                content=text,
                chunk_id=chunk_metadata["chunk_id"],
                metadata=chunk_metadata
            )]

        # Group sentences into chunks based on size
        chunks = []
        current_chunk = []
        current_length = 0
        chunk_index = 0

        for sentence in sentences:
            sentence_length = len(sentence)

            # Check if adding sentence would exceed chunk size
            if current_length + sentence_length > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_text = " ".join(current_chunk)
                chunk_metadata = {
                    **metadata,
                    "chunk_index": chunk_index,
                    "chunk_strategy": "semantic",
                    "chunk_id": f"{metadata.get('source', 'doc')}_chunk_{chunk_index}"
                }

                chunk = Chunk(
                    content=chunk_text,
                    chunk_id=chunk_metadata["chunk_id"],
                    metadata=chunk_metadata
                )
                chunks.append(chunk)

                # Start new chunk with overlap
                overlap_sentences = self._get_overlap_sentences(current_chunk)
                current_chunk = overlap_sentences + [sentence]
                current_length = sum(len(s) for s in current_chunk)
                chunk_index += 1
            else:
                current_chunk.append(sentence)
                current_length += sentence_length

        # Add final chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunk_metadata = {
                **metadata,
                "chunk_index": chunk_index,
                "total_chunks": chunk_index + 1,
                "chunk_strategy": "semantic",
                "chunk_id": f"{metadata.get('source', 'doc')}_chunk_{chunk_index}"
            }

            chunk = Chunk(
                content=chunk_text,
                chunk_id=chunk_metadata["chunk_id"],
                metadata=chunk_metadata
            )
            chunks.append(chunk)

        # Update total chunks
        for chunk in chunks:
            chunk.metadata["total_chunks"] = len(chunks)

        logger.debug(f"Created {len(chunks)} sentence-based chunks")
        return chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences (simplified)"""
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text.strip())

        # Split by sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)

        # Filter out empty sentences
        return [s for s in sentences if s.strip()]

    def _get_overlap_sentences(self, sentences: List[str]) -> List[str]:
        """Get overlap sentences from previous chunk"""
        if not sentences:
            return []

        # Calculate how many sentences for overlap
        total_length = sum(len(s) for s in sentences)
        if total_length <= self.chunk_overlap:
            return sentences

        # Get sentences that fit within overlap
        overlap_sentences = []
        current_length = 0

        for sentence in reversed(sentences):
            if current_length + len(sentence) <= self.chunk_overlap:
                overlap_sentences.insert(0, sentence)
                current_length += len(sentence)
            else:
                break

        return overlap_sentences


class DocumentChunker:
    """
    Main document chunking interface.

    Provides a unified interface for chunking documents using different strategies.
    """

    def __init__(self, config: ChunkingConfig):
        self.config = config
        self.strategy = get_chunker_for_strategy(config)

    def chunk_documents(self, documents: List[Any]) -> List[ChunkingResult]:
        """
        Chunk multiple documents.

        Args:
            documents: List of documents to chunk
                     (Document objects from document_loader or similar)

        Returns:
            List of ChunkingResult objects
        """
        results = []

        for doc in documents:
            try:
                # Get content and metadata from document
                if hasattr(doc, 'content'):
                    content = doc.content
                    doc_metadata = getattr(doc, 'metadata', {})
                    doc_id = getattr(doc, 'doc_id', None)
                else:
                    raise ValueError(f"Unsupported document type: {type(doc)}")

                # Add original doc ID to metadata
                doc_metadata['original_doc_id'] = doc_id or 'unknown'

                # Chunk the document
                chunks = self.strategy.chunk(content, metadata=doc_metadata)

                # Create result
                result = ChunkingResult(
                    doc_id=doc_id or 'unknown',
                    chunks=chunks,
                    total_chunks=len(chunks),
                    strategy_used=self.config.strategy
                )
                results.append(result)

                logger.info(f"Chunked document {doc_id} into {len(chunks)} chunks")

            except Exception as e:
                logger.error(f"Failed to chunk document {getattr(doc, 'doc_id', 'unknown')}: {e}")
                raise

        return results


def get_chunker_for_strategy(config: ChunkingConfig) -> BaseChunkingStrategy:
    """
    Factory function to get chunker instance for a strategy.

    Args:
        config: Chunking configuration

    Returns:
        Chunking strategy instance

    Raises:
        ValueError: If strategy is unknown
    """
    if config.strategy == ChunkingStrategy.FIXED:
        return FixedSizeChunkingStrategy(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap
        )
    elif config.strategy == ChunkingStrategy.RECURSIVE:
        return RecursiveCharacterChunkingStrategy(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap
        )
    elif config.strategy == ChunkingStrategy.SENTENCE:
        return SentenceBasedChunkingStrategy(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap
        )
    else:
        raise ValueError(f"Unknown chunking strategy: {config.strategy}")
