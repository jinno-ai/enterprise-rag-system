"""
Unit tests for Document Preview Generation (Feature 20)

Tests the preview generation service that creates automatic previews/snippets
for indexed documents using extractive summarization.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from app.services.preview import (
    PreviewGenerator,
    DocumentPreview,
    PreviewCache,
    get_preview_cache,
    generate_document_preview
)
from app.services.document_loader import Document


@pytest.fixture
def sample_document():
    """Create a sample document for testing"""
    return Document(
        doc_id="test-doc-1",
        content=(
            "This is the first sentence of the document. It introduces the main topic. "
            "The second sentence provides additional details about the subject. "
            "This is an important sentence that contains key information. "
            "Another sentence with supporting details and examples. "
            "The final sentence concludes the document with a summary."
        ),
        metadata={
            "source": "test.txt",
            "filename": "test.txt",
            "file_type": "txt"
        }
    )


@pytest.fixture
def long_document():
    """Create a long document for testing truncation"""
    content = " ".join([f"This is sentence number {i} with some content." for i in range(100)])
    return Document(
        doc_id="long-doc-1",
        content=content,
        metadata={"source": "long.txt"}
    )


@pytest.fixture
def empty_document():
    """Create an empty document"""
    return Document(
        doc_id="empty-doc",
        content="",
        metadata={"source": "empty.txt"}
    )


@pytest.fixture
def short_document():
    """Create a very short document"""
    return Document(
        doc_id="short-doc",
        content="Short text.",
        metadata={"source": "short.txt"}
    )


class TestPreviewGenerator:
    """Tests for PreviewGenerator class"""

    def test_generator_initialization_default(self):
        """Test generator initialization with default parameters"""
        generator = PreviewGenerator()

        assert generator.max_preview_length == 300
        assert generator.min_sentences == 1
        assert generator.max_sentences == 3
        assert generator.sentence_delimiters == ['.', '!', '?', '\n']

    def test_generator_initialization_custom(self):
        """Test generator initialization with custom parameters"""
        generator = PreviewGenerator(
            max_preview_length=500,
            min_sentences=2,
            max_sentences=5,
            sentence_delimiters=['.', '\n']
        )

        assert generator.max_preview_length == 500
        assert generator.min_sentences == 2
        assert generator.max_sentences == 5
        assert generator.sentence_delimiters == ['.', '\n']

    def test_generate_preview_basic(self, sample_document):
        """Test basic preview generation"""
        generator = PreviewGenerator()
        preview = generator.generate_preview(sample_document)

        assert preview.doc_id == "test-doc-1"
        assert isinstance(preview.preview_text, str)
        assert len(preview.preview_text) > 0
        assert len(preview.preview_text) <= 300
        assert preview.original_length == len(sample_document.content)
        assert 0 < preview.compression_ratio <= 1.0
        assert len(preview.key_sentences) >= 1
        assert isinstance(preview.generated_at, datetime)

    def test_generate_preview_with_structure_preservation(self, sample_document):
        """Test preview generation with structure preservation"""
        generator = PreviewGenerator()
        preview = generator.generate_preview(sample_document, preserve_structure=True)

        # With structure preserved, should have spaces between sentences
        assert ". " in preview.preview_text or "! " in preview.preview_text

    def test_generate_preview_without_structure_preservation(self, sample_document):
        """Test preview generation without structure preservation"""
        generator = PreviewGenerator()
        preview = preview = generator.generate_preview(sample_document, preserve_structure=False)

        # Without structure, may have newlines
        assert isinstance(preview.preview_text, str)

    def test_generate_preview_truncates_long_document(self, long_document):
        """Test that long documents are truncated properly"""
        generator = PreviewGenerator(max_preview_length=200)
        preview = generator.generate_preview(long_document)

        assert len(preview.preview_text) <= 200
        # Preview should be truncated or compression ratio should be very low
        assert len(preview.preview_text) < len(long_document.content)
        assert preview.compression_ratio < 1.0

    def test_generate_preview_handles_empty_document(self, empty_document):
        """Test preview generation for empty documents"""
        generator = PreviewGenerator()
        preview = generator.generate_preview(empty_document)

        assert preview.doc_id == "empty-doc"
        assert preview.preview_text == "[Empty document]"
        assert preview.preview_length == 0
        assert preview.compression_ratio == 0.0
        assert len(preview.key_sentences) == 0

    def test_generate_preview_handles_short_document(self, short_document):
        """Test preview generation for very short documents"""
        generator = PreviewGenerator()
        preview = generator.generate_preview(short_document)

        assert preview.doc_id == "short-doc"
        assert len(preview.preview_text) > 0
        assert preview.original_length == len(short_document.content)

    def test_split_into_sentences_basic(self):
        """Test sentence splitting functionality"""
        generator = PreviewGenerator()
        text = "First sentence. Second sentence! Third sentence? Fourth sentence"

        sentences = generator._split_into_sentences(text)

        assert len(sentences) >= 3
        assert any("First sentence" in s for s in sentences)
        assert any("Second sentence" in s for s in sentences)

    def test_split_into_sentences_filters_short_fragments(self):
        """Test that very short fragments are filtered out"""
        generator = PreviewGenerator()
        text = "This is a valid sentence. A. Another valid sentence!"

        sentences = generator._split_into_sentences(text)

        # Single letter "A" should be filtered out
        assert len([s for s in sentences if s.strip() == "A"]) == 0
        assert len(sentences) >= 2

    def test_score_sentences(self):
        """Test sentence scoring algorithm"""
        generator = PreviewGenerator()
        sentences = [
            "First sentence.",
            "This is an important sentence with key information.",
            "Another sentence."
        ]

        scored = generator._score_sentences(sentences)

        assert len(scored) == 3
        assert all(isinstance(score, float) for _, score in scored)
        # Second sentence should have higher score due to keywords
        assert scored[1][1] > scored[2][1]

    def test_select_top_sentences(self):
        """Test selecting top sentences from scored list"""
        generator = PreviewGenerator()
        scored = [
            ("Sentence A", 0.9),
            ("Sentence B", 0.7),
            ("Sentence C", 0.5),
            ("Sentence D", 0.3)
        ]

        selected = generator._select_top_sentences(scored, max_count=2)

        assert len(selected) == 2
        assert "Sentence A" in selected
        assert "Sentence B" in selected

    def test_truncate_preview(self):
        """Test preview truncation at word boundaries"""
        generator = PreviewGenerator(max_preview_length=50)
        text = "This is a long sentence that needs to be truncated at a word boundary"

        truncated = generator._truncate_preview(text)

        assert len(truncated) <= 50
        assert truncated.endswith("...")
        # Should not cut mid-word (except for very long words)
        # The "..." is added after truncation

    def test_batch_preview_generation(self, sample_document, long_document):
        """Test generating previews for multiple documents"""
        generator = PreviewGenerator()
        documents = [sample_document, long_document]

        previews = generator.generate_batch_previews(documents)

        assert len(previews) == 2
        assert all(isinstance(p, DocumentPreview) for p in previews)
        assert previews[0].doc_id == "test-doc-1"
        assert previews[1].doc_id == "long-doc-1"


class TestDocumentPreview:
    """Tests for DocumentPreview dataclass"""

    def test_preview_initialization(self):
        """Test DocumentPreview initialization"""
        preview = DocumentPreview(
            doc_id="test-1",
            preview_text="Sample preview",
            preview_length=14,
            original_length=100,
            compression_ratio=0.14,
            key_sentences=["Sentence 1", "Sentence 2"],
            metadata={"source": "test.txt"},
            generated_at=datetime.now(timezone.utc)
        )

        assert preview.doc_id == "test-1"
        assert preview.preview_text == "Sample preview"
        assert preview.preview_length == 14
        assert preview.original_length == 100
        assert preview.compression_ratio == 0.14
        assert len(preview.key_sentences) == 2
        assert preview.metadata["source"] == "test.txt"

    def test_preview_with_metadata_copy(self, sample_document):
        """Test that preview metadata is a copy, not reference"""
        generator = PreviewGenerator()
        preview = generator.generate_preview(sample_document)

        # Modify original metadata
        sample_document.metadata["new_key"] = "new_value"

        # Preview metadata should be unchanged
        assert "new_key" not in preview.metadata


class TestPreviewCache:
    """Tests for PreviewCache class"""

    def test_cache_initialization(self):
        """Test cache initialization"""
        cache = PreviewCache(max_size=100)

        assert cache.size() == 0
        assert cache._max_size == 100

    def test_cache_set_and_get(self, sample_document):
        """Test setting and getting cached previews"""
        cache = PreviewCache()
        preview = DocumentPreview(
            doc_id="test-1",
            preview_text="Sample",
            preview_length=6,
            original_length=100,
            compression_ratio=0.06,
            key_sentences=["Sample"],
            metadata={},
            generated_at=datetime.now(timezone.utc)
        )

        cache.set(preview)
        retrieved = cache.get("test-1")

        assert retrieved is not None
        assert retrieved.doc_id == "test-1"
        assert retrieved.preview_text == "Sample"

    def test_cache_get_nonexistent(self):
        """Test getting non-existent preview returns None"""
        cache = PreviewCache()

        result = cache.get("nonexistent")

        assert result is None

    def test_cache_clear(self, sample_document):
        """Test clearing the cache"""
        cache = PreviewCache()
        preview = DocumentPreview(
            doc_id="test-1",
            preview_text="Sample",
            preview_length=6,
            original_length=100,
            compression_ratio=0.06,
            key_sentences=["Sample"],
            metadata={},
            generated_at=datetime.now(timezone.utc)
        )

        cache.set(preview)
        assert cache.size() == 1

        cache.clear()
        assert cache.size() == 0

    def test_cache_size_limit(self):
        """Test that cache respects max size limit"""
        cache = PreviewCache(max_size=3)

        # Add 5 previews
        for i in range(5):
            preview = DocumentPreview(
                doc_id=f"doc-{i}",
                preview_text=f"Preview {i}",
                preview_length=10,
                original_length=100,
                compression_ratio=0.1,
                key_sentences=[f"Sentence {i}"],
                metadata={},
                generated_at=datetime.now(timezone.utc)
            )
            cache.set(preview)

        # Cache should only keep 3 most recent
        assert cache.size() == 3


class TestGlobalPreviewCache:
    """Tests for global preview cache instance"""

    def test_get_preview_cache_singleton(self):
        """Test that get_preview_cache returns singleton instance"""
        import app.services.preview
        app.services.preview._preview_cache = None

        cache1 = get_preview_cache()
        cache2 = get_preview_cache()

        assert cache1 is cache2

    def test_generate_document_preview_with_cache(self, sample_document):
        """Test document preview generation with caching"""
        import app.services.preview
        app.services.preview._preview_cache = None

        # First call should generate and cache
        preview1 = generate_document_preview(sample_document, use_cache=True)

        # Second call should return cached version
        preview2 = generate_document_preview(sample_document, use_cache=True)

        assert preview1.doc_id == preview2.doc_id
        assert preview1.preview_text == preview2.preview_text

    def test_generate_document_preview_without_cache(self, sample_document):
        """Test document preview generation without caching"""
        import app.services.preview
        app.services.preview._preview_cache = None

        # Generate without cache
        preview1 = generate_document_preview(sample_document, use_cache=False)
        preview2 = generate_document_preview(sample_document, use_cache=False)

        # Should generate new previews each time
        assert preview1.doc_id == preview2.doc_id
        # Generated timestamp may differ slightly


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_preview_with_special_characters(self):
        """Test preview generation with special characters"""
        content = "Test with @special# $characters & symbols! Does it work?"
        doc = Document(doc_id="special", content=content, metadata={})

        generator = PreviewGenerator()
        preview = generator.generate_preview(doc)

        assert len(preview.preview_text) > 0
        assert preview.preview_length > 0

    def test_preview_with_unicode(self):
        """Test preview generation with unicode characters"""
        content = "Test with emoji 🎉 and unicode characters café, naïve, 日本語"
        doc = Document(doc_id="unicode", content=content, metadata={})

        generator = PreviewGenerator()
        preview = generator.generate_preview(doc)

        assert len(preview.preview_text) > 0
        assert "🎉" in preview.preview_text or len(preview.preview_text) > 0

    def test_preview_with_only_whitespace(self):
        """Test preview generation with whitespace-only content"""
        content = "   \n\n   \t\t   "
        doc = Document(doc_id="whitespace", content=content, metadata={})

        generator = PreviewGenerator()
        preview = generator.generate_preview(doc)

        # Should handle gracefully
        assert isinstance(preview, DocumentPreview)

    def test_preview_with_very_long_words(self):
        """Test preview generation with very long words"""
        content = "Thisisaveryverylongwordwithoutspaces " * 10
        doc = Document(doc_id="longwords", content=content, metadata={})

        generator = PreviewGenerator(max_preview_length=100)
        preview = generator.generate_preview(doc)

        # Should truncate to approximately max_preview_length
        assert len(preview.preview_text) <= 103  # Allow for "..." addition

    def test_preview_single_sentence(self):
        """Test preview with single sentence document"""
        content = "This is the only sentence in the document."
        doc = Document(doc_id="single", content=content, metadata={})

        generator = PreviewGenerator()
        preview = generator.generate_preview(doc)

        assert len(preview.key_sentences) >= 1
        assert len(preview.preview_text) > 0

    def test_preview_with_numbered_list(self):
        """Test preview with numbered list format"""
        content = "1. First item. 2. Second item. 3. Third item."
        doc = Document(doc_id="numbered", content=content, metadata={})

        generator = PreviewGenerator()
        preview = generator.generate_preview(doc)

        assert len(preview.preview_text) > 0

    def test_batch_with_mixed_document_types(self):
        """Test batch preview generation with mixed content"""
        documents = [
            Document(doc_id="d1", content="Short.", metadata={}),
            Document(doc_id="d2", content="Medium length document with multiple sentences.", metadata={}),
            Document(doc_id="d3", content="", metadata={}),
        ]

        generator = PreviewGenerator()
        previews = generator.generate_batch_previews(documents)

        assert len(previews) == 3
        assert all(isinstance(p, DocumentPreview) for p in previews)


class TestIntegration:
    """Integration tests for preview functionality"""

    def test_end_to_end_preview_workflow(self, sample_document):
        """Test complete preview generation workflow"""
        # Generate preview
        generator = PreviewGenerator(max_preview_length=200)
        preview = generator.generate_preview(sample_document)

        # Cache it
        cache = PreviewCache()
        cache.set(preview)

        # Retrieve from cache
        cached = cache.get(preview.doc_id)
        assert cached is not None
        assert cached.preview_text == preview.preview_text

    def test_multiple_documents_with_caching(self):
        """Test generating and caching previews for multiple documents"""
        documents = [
            Document(doc_id=f"doc-{i}", content=f"Content for document {i}.", metadata={})
            for i in range(10)
        ]

        cache = PreviewCache()
        generator = PreviewGenerator()

        for doc in documents:
            preview = generator.generate_preview(doc)
            cache.set(preview)

        # All should be cached
        for doc in documents:
            cached = cache.get(doc.doc_id)
            assert cached is not None
            assert cached.doc_id == doc.doc_id

    def test_preview_metadata_preservation(self):
        """Test that document metadata is preserved in preview"""
        metadata = {
            "source": "/path/to/file.pdf",
            "filename": "file.pdf",
            "file_type": "pdf",
            "page": 5,
            "total_pages": 10,
            "author": "Test Author"
        }

        doc = Document(
            doc_id="metadata-test",
            content="Test content for metadata preservation.",
            metadata=metadata
        )

        generator = PreviewGenerator()
        preview = generator.generate_preview(doc)

        # All metadata should be preserved
        for key, value in metadata.items():
            assert preview.metadata.get(key) == value
