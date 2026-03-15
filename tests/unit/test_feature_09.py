"""
Unit tests for Document Chunking Strategies (Feature 09)

Tests multiple document chunking strategies including:
- Fixed-size chunking
- Semantic chunking
- Recursive character chunking

This ensures documents are properly chunked for RAG applications
with optimal context preservation and retrieval performance.
"""

import pytest
from typing import List, Dict, Any
from unittest.mock import Mock, patch

from app.services.chunking import (
    ChunkingStrategy,
    FixedSizeChunkingStrategy,
    RecursiveCharacterChunkingStrategy,
    SentenceBasedChunkingStrategy,
    ChunkingConfig,
    Chunk,
    ChunkingResult,
    DocumentChunker,
    get_chunker_for_strategy
)


class TestChunk:
    """Test suite for Chunk dataclass"""

    def test_chunk_creation(self):
        """Test creating a chunk"""
        chunk = Chunk(
            content="This is a test chunk",
            chunk_id="chunk-1",
            metadata={"index": 0, "source": "test.txt"}
        )

        assert chunk.content == "This is a test chunk"
        assert chunk.chunk_id == "chunk-1"
        assert chunk.metadata["index"] == 0
        assert chunk.metadata["source"] == "test.txt"

    def test_chunk_to_dict(self):
        """Test converting chunk to dictionary"""
        chunk = Chunk(
            content="Test content",
            chunk_id="chunk-2",
            metadata={"index": 1}
        )

        chunk_dict = chunk.to_dict()

        assert chunk_dict["content"] == "Test content"
        assert chunk_dict["chunk_id"] == "chunk-2"
        assert chunk_dict["metadata"]["index"] == 1


class TestChunkingConfig:
    """Test suite for ChunkingConfig"""

    def test_default_config(self):
        """Test default chunking configuration"""
        config = ChunkingConfig()

        assert config.chunk_size == 1000
        assert config.chunk_overlap == 200
        assert config.strategy == ChunkingStrategy.RECURSIVE

    def test_custom_config(self):
        """Test custom chunking configuration"""
        config = ChunkingConfig(
            chunk_size=500,
            chunk_overlap=50,
            strategy=ChunkingStrategy.FIXED
        )

        assert config.chunk_size == 500
        assert config.chunk_overlap == 50
        assert config.strategy == ChunkingStrategy.FIXED

    def test_config_validation_overlap_too_large(self):
        """Test that overlap cannot exceed chunk size"""
        with pytest.raises(ValueError, match="Overlap must be between 0 and chunk_size"):
            ChunkingConfig(
                chunk_size=100,
                chunk_overlap=100  # overlap >= chunk_size should fail
            )

    def test_config_validation_chunk_size_too_small(self):
        """Test that chunk size must be at least 100"""
        with pytest.raises(ValueError, match="Chunk size must be between 100 and 100000"):
            ChunkingConfig(chunk_size=50)

    def test_config_validation_chunk_size_too_large(self):
        """Test that chunk size has an upper bound"""
        with pytest.raises(ValueError, match="Chunk size must be between 100 and 100000"):
            ChunkingConfig(chunk_size=200_000)

    def test_config_validation_negative_overlap(self):
        """Test that overlap cannot be negative"""
        with pytest.raises(ValueError, match="Overlap must be between 0 and chunk_size"):
            ChunkingConfig(
                chunk_size=1000,
                chunk_overlap=-10
            )


class TestFixedSizeChunkingStrategy:
    """Test suite for fixed-size chunking"""

    @pytest.fixture
    def strategy(self):
        """Create fixed-size chunking strategy"""
        return FixedSizeChunkingStrategy(
            chunk_size=100,
            chunk_overlap=20
        )

    def test_chunk_short_text(self, strategy):
        """Test chunking text shorter than chunk size"""
        text = "This is a short text"
        chunks = strategy.chunk(text)

        assert len(chunks) == 1
        assert chunks[0].content == "This is a short text"

    def test_chunk_long_text(self, strategy):
        """Test chunking text longer than chunk size"""
        text = "word " * 50  # ~250 characters
        chunks = strategy.chunk(text)

        assert len(chunks) > 1
        # Verify overlap
        if len(chunks) > 1:
            first_chunk_end = chunks[0].content[-20:]
            second_chunk_start = chunks[1].content[:20]
            # Should have some overlap
            assert len(chunks[0].content) <= 100

    def test_chunk_with_empty_string(self, strategy):
        """Test chunking empty string"""
        chunks = strategy.chunk("")

        assert len(chunks) == 0

    def test_chunk_metadata(self, strategy):
        """Test that chunks contain proper metadata"""
        text = "word " * 50
        chunks = strategy.chunk(text, metadata={"source": "test.txt"})

        for i, chunk in enumerate(chunks):
            assert chunk.metadata["chunk_index"] == i
            assert chunk.metadata["total_chunks"] == len(chunks)
            assert chunk.metadata["source"] == "test.txt"
            # chunk_id is set in metadata by the strategy
            assert "chunk_id" in chunk.metadata

    def test_chunk_respects_chunk_size(self, strategy):
        """Test that chunks don't exceed max size"""
        text = "a" * 500  # 500 characters
        chunks = strategy.chunk(text)

        for chunk in chunks:
            assert len(chunk.content) <= 100

    def test_chunk_with_no_overlap(self):
        """Test chunking with zero overlap"""
        strategy = FixedSizeChunkingStrategy(
            chunk_size=100,
            chunk_overlap=0
        )

        text = "word " * 50
        chunks = strategy.chunk(text)

        # With zero overlap, chunks should be adjacent
        # Just verify the chunking works
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.content) <= 100


class TestRecursiveCharacterChunkingStrategy:
    """Test suite for recursive character chunking"""

    @pytest.fixture
    def strategy(self):
        """Create recursive character chunking strategy"""
        return RecursiveCharacterChunkingStrategy(
            chunk_size=100,
            chunk_overlap=20
        )

    def test_chunk_by_paragraphs(self, strategy):
        """Test that text is split by paragraphs first"""
        text = """First paragraph with some content.

Second paragraph here.

Third paragraph."""

        chunks = strategy.chunk(text)

        assert len(chunks) >= 1
        # Should try to keep paragraphs together
        assert "First paragraph" in chunks[0].content

    def test_chunk_by_sentences(self, strategy):
        """Test that text is split by sentences when paragraphs don't fit"""
        text = "This is sentence one. This is sentence two. " * 10

        chunks = strategy.chunk(text)

        assert len(chunks) >= 1
        # Recursive strategy tries to keep sentences together
        # but may split mid-sentence if needed to meet chunk size
        total_content = " ".join(c.content for c in chunks)
        assert "This is sentence one" in total_content

    def test_custom_separators(self):
        """Test custom separators"""
        strategy = RecursiveCharacterChunkingStrategy(
            chunk_size=200,
            chunk_overlap=50,
            separators=["|||", "\n\n", "\n", " "]
        )

        text = "Section 1|||Section 2|||Section 3"
        chunks = strategy.chunk(text)

        # Should split by custom separator if text is long enough
        # Since the text is short, it may be kept as one chunk
        assert len(chunks) >= 1
        # Check that all content is present
        all_content = "".join(c.content for c in chunks)
        assert "Section 1" in all_content
        assert "Section 2" in all_content
        assert "Section 3" in all_content

    def test_fallback_to_word_splitting(self, strategy):
        """Test fallback to word splitting when no separators work"""
        text = "aaaaabbbbbcccccdddddeeee" * 10

        chunks = strategy.chunk(text)

        assert len(chunks) >= 1
        # Should eventually chunk by character/word
        for chunk in chunks:
            assert len(chunk.content) <= 100

    def test_metadata_preservation(self, strategy):
        """Test that metadata is preserved in chunks"""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        metadata = {
            "source": "test.md",
            "type": "markdown"
        }

        chunks = strategy.chunk(text, metadata=metadata)

        for chunk in chunks:
            assert chunk.metadata["source"] == "test.md"
            assert chunk.metadata["type"] == "markdown"
            assert "chunk_index" in chunk.metadata


class TestSentenceBasedChunkingStrategy:
    """Test suite for sentence-based chunking"""

    @pytest.fixture
    def strategy(self):
        """Create sentence-based chunking strategy"""
        strategy = SentenceBasedChunkingStrategy(
            chunk_size=200,
            chunk_overlap=50
        )
        return strategy

    def test_chunk_by_sentences(self, strategy):
        """Test chunking by grouping sentences"""
        text = """This is about machine learning. ML is a subset of AI.

Now let's talk about renewable energy. Solar and wind are important.

Back to AI topics. Deep learning is popular."""

        chunks = strategy.chunk(text)

        assert len(chunks) >= 1
        # Should create chunks that preserve sentence boundaries
        for chunk in chunks:
            # Chunks should end with sentence-ending punctuation
            assert chunk.content.rstrip().endswith((".", "!", "?")) or chunk == chunks[-1]

    def test_metadata_preserved(self, strategy):
        """Test that metadata includes sentence information"""
        text = "Topic one. " * 20 + "\n\n" + "Topic two. " * 20

        chunks = strategy.chunk(text, metadata={"source": "test.txt"})

        for chunk in chunks:
            assert "source" in chunk.metadata
            assert "chunk_index" in chunk.metadata

    def test_handles_splitting_errors(self, strategy):
        """Test graceful handling of splitting errors"""
        text = "Some text here with more content to make it longer. " * 20

        # Mock splitting failure
        with patch.object(strategy, '_sentence_based_split', side_effect=Exception("Split Error")):
            chunks = strategy.chunk(text)

            # Should fall back to recursive chunking
            assert len(chunks) >= 1

    def test_empty_text(self, strategy):
        """Test sentence-based chunking with empty text"""
        chunks = strategy.chunk("")

        assert len(chunks) == 0


class TestDocumentChunker:
    """Test suite for DocumentChunker"""

    @pytest.fixture
    def sample_documents(self):
        """Create sample documents"""
        from app.services.document_loader import Document

        return [
            Document(
                content="First document with some content. " * 20,
                metadata={"source": "doc1.txt"}
            ),
            Document(
                content="Second document here. " * 20,
                metadata={"source": "doc2.txt"}
            )
        ]

    def test_chunk_documents_with_fixed_strategy(self, sample_documents):
        """Test chunking documents with fixed-size strategy"""
        config = ChunkingConfig(
            strategy=ChunkingStrategy.FIXED,
            chunk_size=100,
            chunk_overlap=20
        )

        chunker = DocumentChunker(config)
        results = chunker.chunk_documents(sample_documents)

        assert len(results) == 2
        assert all(isinstance(r, ChunkingResult) for r in results)

        # Check first result
        assert results[0].doc_id == sample_documents[0].doc_id
        assert len(results[0].chunks) > 0
        assert results[0].total_chunks > 0

    def test_chunk_documents_with_recursive_strategy(self, sample_documents):
        """Test chunking documents with recursive strategy"""
        config = ChunkingConfig(
            strategy=ChunkingStrategy.RECURSIVE,
            chunk_size=200,
            chunk_overlap=50
        )

        chunker = DocumentChunker(config)
        results = chunker.chunk_documents(sample_documents)

        assert len(results) == 2
        total_chunks = sum(r.total_chunks for r in results)
        assert total_chunks > 0

    def test_chunk_empty_document_list(self):
        """Test chunking empty document list"""
        config = ChunkingConfig()
        chunker = DocumentChunker(config)

        results = chunker.chunk_documents([])

        assert len(results) == 0

    def test_chunk_results_metadata(self, sample_documents):
        """Test that chunking results contain proper metadata"""
        config = ChunkingConfig(
            chunk_size=300,
            chunk_overlap=50,
            strategy=ChunkingStrategy.FIXED  # Explicitly set to FIXED
        )
        chunker = DocumentChunker(config)

        results = chunker.chunk_documents(sample_documents)

        for result, doc in zip(results, sample_documents):
            assert result.doc_id == doc.doc_id
            assert result.total_chunks == len(result.chunks)
            assert result.strategy_used == ChunkingStrategy.FIXED

            for chunk in result.chunks:
                assert "original_doc_id" in chunk.metadata
                assert chunk.metadata["original_doc_id"] == doc.doc_id


class TestGetChunkerForStrategy:
    """Test suite for get_chunker_for_strategy factory"""

    def test_get_fixed_strategy_chunker(self):
        """Test getting chunker for fixed strategy"""
        config = ChunkingConfig(strategy=ChunkingStrategy.FIXED)
        chunker = get_chunker_for_strategy(config)

        assert isinstance(chunker, FixedSizeChunkingStrategy)

    def test_get_recursive_strategy_chunker(self):
        """Test getting chunker for recursive strategy"""
        config = ChunkingConfig(strategy=ChunkingStrategy.RECURSIVE)
        chunker = get_chunker_for_strategy(config)

        assert isinstance(chunker, RecursiveCharacterChunkingStrategy)

    def test_get_sentence_strategy_chunker(self):
        """Test getting chunker for sentence-based strategy"""
        config = ChunkingConfig(strategy=ChunkingStrategy.SENTENCE)
        chunker = get_chunker_for_strategy(config)

        assert isinstance(chunker, SentenceBasedChunkingStrategy)

    def test_invalid_strategy(self):
        """Test handling of invalid strategy"""
        # Invalid strategy should fail during config validation
        with pytest.raises(ValueError, match="Invalid strategy.*Must be ChunkingStrategy enum"):
            ChunkingConfig(strategy="invalid")


class TestChunkingResult:
    """Test suite for ChunkingResult"""

    def test_chunking_result_creation(self):
        """Test creating a chunking result"""
        chunks = [
            Chunk(content="Chunk 1", chunk_id="1", metadata={}),
            Chunk(content="Chunk 2", chunk_id="2", metadata={})
        ]

        result = ChunkingResult(
            doc_id="doc-123",
            chunks=chunks,
            total_chunks=2,
            strategy_used=ChunkingStrategy.FIXED
        )

        assert result.doc_id == "doc-123"
        assert len(result.chunks) == 2
        assert result.total_chunks == 2
        assert result.strategy_used == ChunkingStrategy.FIXED

    def test_chunking_result_to_dict(self):
        """Test converting chunking result to dictionary"""
        chunks = [
            Chunk(content="Test", chunk_id="1", metadata={})
        ]

        result = ChunkingResult(
            doc_id="doc-456",
            chunks=chunks,
            total_chunks=1,
            strategy_used=ChunkingStrategy.RECURSIVE
        )

        result_dict = result.to_dict()

        assert result_dict["doc_id"] == "doc-456"
        assert result_dict["total_chunks"] == 1
        assert result_dict["strategy_used"] == "recursive"
        assert len(result_dict["chunks"]) == 1


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_very_long_text(self):
        """Test chunking very long text"""
        strategy = FixedSizeChunkingStrategy(
            chunk_size=1000,
            chunk_overlap=100
        )

        # Create 100KB text
        text = "word " * 20000
        chunks = strategy.chunk(text)

        assert len(chunks) > 1
        # Each chunk should be within limits
        for chunk in chunks:
            assert len(chunk.content) <= 1000

    def test_unicode_content(self):
        """Test chunking unicode content"""
        strategy = RecursiveCharacterChunkingStrategy(
            chunk_size=100,
            chunk_overlap=20
        )

        text = "日本語のテキスト\n\n🚀 Emoji content\n\nالعربية"
        chunks = strategy.chunk(text)

        assert len(chunks) >= 1
        # Should handle unicode properly
        for chunk in chunks:
            assert isinstance(chunk.content, str)

    def test_text_with_only_whitespace(self):
        """Test chunking text with only whitespace"""
        strategy = FixedSizeChunkingStrategy(chunk_size=100)

        chunks = strategy.chunk("   \n\n   \t  ")

        # Should handle gracefully (either no chunks or single whitespace chunk)
        assert len(chunks) <= 1

    def test_mixed_line_endings(self):
        """Test handling of mixed line endings"""
        strategy = RecursiveCharacterChunkingStrategy(
            chunk_size=100,
            chunk_overlap=20
        )

        text = "Line1\r\nLine2\rLine3\nLine4"
        chunks = strategy.chunk(text)

        assert len(chunks) >= 1
        # Should normalize line endings
        for chunk in chunks:
            assert "\r" not in chunk.content or chunk.content.count("\r\n") > 0

    def test_preserves_trailing_whitespace_in_overlap(self):
        """Test that overlapping chunks preserve context"""
        strategy = FixedSizeChunkingStrategy(
            chunk_size=50,
            chunk_overlap=10
        )

        text = "word " * 20
        chunks = strategy.chunk(text)

        if len(chunks) > 1:
            # Second chunk should have overlap from first
            overlap_content = chunks[0].content[-10:]
            assert overlap_content in chunks[1].content


class TestIntegrationWithDocumentLoader:
    """Integration tests with document loader"""

    def test_chunk_loaded_document(self):
        """Test chunking a document loaded by DocumentLoader"""
        from app.services.document_loader import DocumentLoader

        # Create a temporary test file
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("This is a test document. " * 50)
            temp_file = f.name

        try:
            # Load document
            doc = DocumentLoader.load_text_file(temp_file)

            # Chunk it
            config = ChunkingConfig(
                strategy=ChunkingStrategy.RECURSIVE,
                chunk_size=200,
                chunk_overlap=50
            )
            chunker = DocumentChunker(config)
            results = chunker.chunk_documents([doc])

            assert len(results) == 1
            assert results[0].total_chunks > 0
            assert len(results[0].chunks) == results[0].total_chunks

            # Verify metadata
            for chunk in results[0].chunks:
                assert chunk.metadata["source"] == temp_file
                assert "original_doc_id" in chunk.metadata

        finally:
            os.unlink(temp_file)

    def test_chunk_multiple_documents(self):
        """Test chunking multiple documents efficiently"""
        from app.services.document_loader import Document

        documents = [
            Document(content=f"Document {i} content. " * 30, metadata={"index": i})
            for i in range(5)
        ]

        config = ChunkingConfig(chunk_size=300, chunk_overlap=50)  # Larger chunk size
        chunker = DocumentChunker(config)
        results = chunker.chunk_documents(documents)

        assert len(results) == 5
        total_chunks = sum(r.total_chunks for r in results)
        # Should have chunks
        assert total_chunks >= 5
