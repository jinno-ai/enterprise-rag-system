"""
Document Preview Generation Service

This module provides functionality to generate automatic previews/snippets
for indexed documents. Previews improve user experience by showing concise
summaries of document contents before full retrieval.

Features:
- Generate text previews with configurable length
- Extract key sentences using extractive summarization
- Preserve document structure and formatting
- Support for multiple document types
- Cache previews for performance
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import re
import logging
from datetime import datetime, timezone
from app.services.document_loader import Document

logger = logging.getLogger(__name__)


@dataclass
class DocumentPreview:
    """Preview data for a document"""
    doc_id: str
    preview_text: str
    preview_length: int
    original_length: int
    compression_ratio: float
    key_sentences: List[str]
    metadata: Dict[str, Any]
    generated_at: datetime


class PreviewGenerator:
    """
    Generate document previews using extractive summarization.

    Extracts the most representative sentences from documents to create
    concise previews while preserving key information.
    """

    def __init__(
        self,
        max_preview_length: int = 300,
        min_sentences: int = 1,
        max_sentences: int = 3,
        sentence_delimiters: Optional[List[str]] = None
    ):
        """
        Initialize preview generator.

        Args:
            max_preview_length: Maximum length of preview in characters
            min_sentences: Minimum number of sentences in preview
            max_sentences: Maximum number of sentences in preview
            sentence_delimiters: Characters that mark sentence boundaries
        """
        self.max_preview_length = max_preview_length
        self.min_sentences = min_sentences
        self.max_sentences = max_sentences
        self.sentence_delimiters = sentence_delimiters or ['.', '!', '?', '\n']

    def generate_preview(
        self,
        document: Document,
        preserve_structure: bool = True
    ) -> DocumentPreview:
        """
        Generate a preview for a document.

        Args:
            document: The document to generate preview for
            preserve_structure: Whether to preserve paragraph structure

        Returns:
            DocumentPreview object with generated preview
        """
        try:
            # Split text into sentences
            sentences = self._split_into_sentences(document.content)

            if not sentences:
                return self._empty_preview(document)

            # Score sentences by relevance
            scored_sentences = self._score_sentences(sentences)

            # Select top sentences
            selected_sentences = self._select_top_sentences(
                scored_sentences,
                self.max_sentences
            )

            # Build preview text
            preview_text = self._build_preview(
                selected_sentences,
                preserve_structure
            )

            # Truncate if necessary
            if len(preview_text) > self.max_preview_length:
                preview_text = self._truncate_preview(preview_text)

            # Calculate compression ratio
            compression_ratio = len(preview_text) / max(len(document.content), 1)

            return DocumentPreview(
                doc_id=document.doc_id,
                preview_text=preview_text.strip(),
                preview_length=len(preview_text),
                original_length=len(document.content),
                compression_ratio=compression_ratio,
                key_sentences=selected_sentences[:self.max_sentences],
                metadata=document.metadata.copy(),
                generated_at=datetime.now(timezone.utc)
            )

        except Exception as e:
            logger.error(f"Error generating preview for {document.doc_id}: {e}")
            return self._fallback_preview(document)

    def generate_batch_previews(
        self,
        documents: List[Document],
        preserve_structure: bool = True
    ) -> List[DocumentPreview]:
        """
        Generate previews for multiple documents.

        Args:
            documents: List of documents to generate previews for
            preserve_structure: Whether to preserve paragraph structure

        Returns:
            List of DocumentPreview objects
        """
        previews = []

        for doc in documents:
            try:
                preview = self.generate_preview(doc, preserve_structure)
                previews.append(preview)
            except Exception as e:
                logger.error(f"Failed to generate preview for {doc.doc_id}: {e}")
                # Add fallback preview
                previews.append(self._fallback_preview(doc))

        logger.info(f"Generated {len(previews)} previews")
        return previews

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using delimiters"""
        sentences = []
        current = ""

        for char in text:
            current += char
            if char in self.sentence_delimiters:
                sentence = current.strip()
                if len(sentence) > 10:  # Filter out very short fragments
                    sentences.append(sentence)
                current = ""

        # Add remaining text
        if current.strip():
            sentences.append(current.strip())

        return sentences

    def _score_sentences(self, sentences: List[str]) -> List[tuple]:
        """
        Score sentences based on multiple factors:
        - Length (prefer medium-length sentences)
        - Position (prefer earlier sentences)
        - Keyword density
        """
        scored = []

        for i, sentence in enumerate(sentences):
            score = 0.0

            # Position score: earlier sentences get higher scores
            position_score = 1.0 / (i + 1)
            score += position_score * 0.4

            # Length score: prefer medium-length sentences (30-100 chars)
            length = len(sentence)
            if 30 <= length <= 100:
                score += 0.3
            elif length > 10:
                score += 0.1

            # Keyword score: bonus for important words
            important_words = [
                'important', 'key', 'main', 'significant', 'critical',
                'essential', 'primary', 'major', 'conclusion', 'summary',
                'therefore', 'however', 'furthermore', 'moreover'
            ]
            sentence_lower = sentence.lower()
            keyword_count = sum(1 for word in important_words if word in sentence_lower)
            score += keyword_count * 0.1

            # Capitalization score: sentences starting with capital letter
            if sentence and sentence[0].isupper():
                score += 0.1

            scored.append((sentence, score))

        # Sort by score (descending)
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _select_top_sentences(
        self,
        scored_sentences: List[tuple],
        max_count: int
    ) -> List[str]:
        """Select top N sentences from scored list"""
        selected = []

        for sentence, score in scored_sentences[:max_count]:
            selected.append(sentence)

        # Ensure minimum number of sentences
        while len(selected) < self.min_sentences and len(selected) < len(scored_sentences):
            idx = len(selected)
            selected.append(scored_sentences[idx][0])

        return selected

    def _build_preview(
        self,
        sentences: List[str],
        preserve_structure: bool
    ) -> str:
        """Build preview text from selected sentences"""
        if preserve_structure:
            # Join with spaces to maintain flow
            preview = " ".join(sentences)
        else:
            # Join with newlines for list format
            preview = "\n".join(sentences)

        return preview

    def _truncate_preview(self, text: str) -> str:
        """Truncate preview to max length, preserving word boundaries"""
        if len(text) <= self.max_preview_length:
            return text

        # Reserve 3 characters for "..."
        max_len = self.max_preview_length - 3

        # Truncate at word boundary
        truncated = text[:max_len]
        last_space = truncated.rfind(' ')

        if last_space > max_len * 0.8:
            truncated = truncated[:last_space]

        return truncated.strip() + "..."

    def _empty_preview(self, document: Document) -> DocumentPreview:
        """Return empty preview for empty documents"""
        return DocumentPreview(
            doc_id=document.doc_id,
            preview_text="[Empty document]",
            preview_length=0,
            original_length=len(document.content),
            compression_ratio=0.0,
            key_sentences=[],
            metadata=document.metadata.copy(),
            generated_at=datetime.now(timezone.utc)
        )

    def _fallback_preview(self, document: Document) -> DocumentPreview:
        """Return fallback preview when generation fails"""
        # Take first N characters as fallback
        fallback_text = document.content[:self.max_preview_length]
        if len(document.content) > self.max_preview_length:
            fallback_text += "..."

        return DocumentPreview(
            doc_id=document.doc_id,
            preview_text=fallback_text,
            preview_length=len(fallback_text),
            original_length=len(document.content),
            compression_ratio=len(fallback_text) / max(len(document.content), 1),
            key_sentences=[fallback_text[:100]],
            metadata=document.metadata.copy(),
            generated_at=datetime.now(timezone.utc)
        )


class PreviewCache:
    """
    Simple in-memory cache for document previews.

    For production use, consider using Redis or similar.
    """

    def __init__(self, max_size: int = 1000):
        """Initialize preview cache"""
        self._cache: Dict[str, DocumentPreview] = {}
        self._max_size = max_size

    def get(self, doc_id: str) -> Optional[DocumentPreview]:
        """Get cached preview for document"""
        return self._cache.get(doc_id)

    def set(self, preview: DocumentPreview) -> None:
        """Cache a document preview"""
        # Simple LRU: if cache is full, remove oldest entry
        if len(self._cache) >= self._max_size:
            # Remove first (oldest) entry
            self._cache.pop(next(iter(self._cache)))

        self._cache[preview.doc_id] = preview

    def clear(self) -> None:
        """Clear all cached previews"""
        self._cache.clear()

    def size(self) -> int:
        """Get current cache size"""
        return len(self._cache)


# Global preview cache instance
_preview_cache: Optional[PreviewCache] = None


def get_preview_cache() -> PreviewCache:
    """Get global preview cache instance"""
    global _preview_cache
    if _preview_cache is None:
        _preview_cache = PreviewCache()
    return _preview_cache


def generate_document_preview(
    document: Document,
    use_cache: bool = True,
    **generator_kwargs
) -> DocumentPreview:
    """
    Generate preview for a document with optional caching.

    Args:
        document: Document to generate preview for
        use_cache: Whether to use preview cache
        **generator_kwargs: Additional arguments for PreviewGenerator

    Returns:
        DocumentPreview object
    """
    if use_cache:
        cache = get_preview_cache()
        cached = cache.get(document.doc_id)
        if cached is not None:
            return cached

    generator = PreviewGenerator(**generator_kwargs)
    preview = generator.generate_preview(document)

    if use_cache:
        cache = get_preview_cache()
        cache.set(preview)

    return preview
