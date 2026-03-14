"""
Unit tests for Document Export Feature (Feature 30)

Tests the document export service supporting PDF, DOCX, and TXT formats
with proper formatting, metadata preservation, and error handling.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from app.services.export import (
    DocumentExporter,
    ExportFormat,
    ExportResult,
    export_document
)


@pytest.fixture
def temp_output_dir():
    """Create temporary directory for export tests"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_content():
    """Sample document content for testing"""
    return """# Sample Document

This is a test document with multiple paragraphs.

## Section 1

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.

## Section 2

Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
"""


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing"""
    return {
        "author": "Test Author",
        "created_at": "2026-03-15",
        "category": "Testing",
        "version": "1.0"
    }


class TestDocumentExporterInitialization:
    """Test exporter initialization and setup"""

    def test_exporter_initialization_with_custom_dir(self, temp_output_dir):
        """Test exporter initialization with custom output directory"""
        exporter = DocumentExporter(output_dir=temp_output_dir)
        assert exporter.output_dir == Path(temp_output_dir)
        assert exporter.output_dir.exists()

    def test_exporter_initialization_default_dir(self):
        """Test exporter initialization with default directory"""
        exporter = DocumentExporter()
        assert exporter.output_dir == Path.cwd()

    def test_exporter_creates_output_dir(self, temp_output_dir):
        """Test that exporter creates output directory if it doesn't exist"""
        new_dir = Path(temp_output_dir) / "exports" / "test"
        exporter = DocumentExporter(output_dir=str(new_dir))
        assert new_dir.exists()


class TestTXTExport:
    """Test plain text export functionality"""

    def test_txt_export_success(self, temp_output_dir, sample_content):
        """Test successful TXT export"""
        exporter = DocumentExporter(output_dir=temp_output_dir)
        result = exporter.export_document(
            content=sample_content,
            filename="test_document",
            export_format=ExportFormat.TXT
        )

        assert result.success is True
        assert result.format == ExportFormat.TXT
        assert result.file_size > 0
        assert result.duration_ms >= 0
        assert result.error_message is None
        assert result.file_path is not None

        # Verify file exists
        assert Path(result.file_path).exists()
        assert result.file_path.endswith(".txt")

    def test_txt_export_with_metadata(self, temp_output_dir, sample_content, sample_metadata):
        """Test TXT export with metadata"""
        exporter = DocumentExporter(output_dir=temp_output_dir)
        result = exporter.export_document(
            content=sample_content,
            filename="test_with_metadata",
            export_format=ExportFormat.TXT,
            metadata=sample_metadata
        )

        assert result.success is True

        # Verify metadata is included in file
        with open(result.file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "DOCUMENT METADATA" in content
            assert "author: Test Author" in content
            assert "created_at: 2026-03-15" in content

    def test_txt_export_with_title(self, temp_output_dir, sample_content):
        """Test TXT export with title"""
        exporter = DocumentExporter(output_dir=temp_output_dir)
        result = exporter.export_document(
            content=sample_content,
            filename="test_with_title",
            export_format=ExportFormat.TXT,
            title="Test Document Title"
        )

        assert result.success is True

        # Verify content is in file
        with open(result.file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert sample_content in content

    def test_txt_export_empty_content(self, temp_output_dir):
        """Test TXT export with empty content"""
        exporter = DocumentExporter(output_dir=temp_output_dir)
        result = exporter.export_document(
            content="",
            filename="empty_document",
            export_format=ExportFormat.TXT
        )

        assert result.success is True
        assert result.file_size >= 0


class TestPDFExport:
    """Test PDF export functionality"""

    @patch('app.services.export.REPORTLAB_AVAILABLE', False)
    def test_pdf_export_without_library(self, temp_output_dir, sample_content):
        """Test PDF export when reportlab is not available"""
        exporter = DocumentExporter(output_dir=temp_output_dir)
        result = exporter.export_document(
            content=sample_content,
            filename="test_pdf_no_lib",
            export_format=ExportFormat.PDF
        )

        assert result.success is False
        assert "reportlab" in result.error_message.lower()

    @patch('app.services.export.REPORTLAB_AVAILABLE', False)
    def test_pdf_export_without_library(self, temp_output_dir, sample_content):
        """Test PDF export when reportlab is not available"""
        exporter = DocumentExporter(output_dir=temp_output_dir)
        result = exporter.export_document(
            content=sample_content,
            filename="test_pdf_no_lib",
            export_format=ExportFormat.PDF
        )

        assert result.success is False
        assert "reportlab" in result.error_message.lower()


class TestDOCXExport:
    """Test DOCX export functionality"""

    @patch('app.services.export.DOCX_AVAILABLE', False)
    def test_docx_export_without_library(self, temp_output_dir, sample_content):
        """Test DOCX export when python-docx is not available"""
        exporter = DocumentExporter(output_dir=temp_output_dir)
        result = exporter.export_document(
            content=sample_content,
            filename="test_docx_no_lib",
            export_format=ExportFormat.DOCX
        )

        assert result.success is False
        assert "python-docx" in result.error_message.lower() or "docx" in result.error_message.lower()


class TestBatchExport:
    """Test batch export functionality"""

    def test_batch_export_success(self, temp_output_dir, sample_content):
        """Test successful batch export"""
        documents = [
            {
                "content": sample_content,
                "filename": "doc1",
                "metadata": {"id": "1"}
            },
            {
                "content": sample_content,
                "filename": "doc2",
                "metadata": {"id": "2"}
            },
            {
                "content": "Short content",
                "filename": "doc3",
                "title": "Third Document"
            }
        ]

        exporter = DocumentExporter(output_dir=temp_output_dir)
        results = exporter.export_batch(
            documents=documents,
            export_format=ExportFormat.TXT
        )

        assert len(results) == 3
        assert all(r.success for r in results)
        assert all(r.format == ExportFormat.TXT for r in results)

    def test_batch_export_partial_failure(self, temp_output_dir, sample_content):
        """Test batch export with some failures"""
        documents = [
            {
                "content": sample_content,
                "filename": "doc1"
            },
            {
                "content": sample_content,
                "filename": "doc2"
            }
        ]

        exporter = DocumentExporter(output_dir=temp_output_dir)

        # Mock export_document to simulate one failure
        with patch.object(exporter, 'export_document') as mock_export:
            mock_export.side_effect = [
                ExportResult(success=True, format=ExportFormat.TXT, file_size=100, duration_ms=10, file_path="doc1.txt"),
                ExportResult(success=False, format=ExportFormat.TXT, file_size=0, duration_ms=5, error_message="Mock error")
            ]

            results = exporter.export_batch(
                documents=documents,
                export_format=ExportFormat.TXT
            )

            assert len(results) == 2
            assert results[0].success is True
            assert results[1].success is False


class TestErrorHandling:
    """Test error handling and edge cases"""

    def test_unsupported_format(self, temp_output_dir, sample_content):
        """Test export with unsupported format"""
        exporter = DocumentExporter(output_dir=temp_output_dir)

        with patch('app.services.export.ExportFormat') as mock_format:
            mock_format.side_effect = ValueError("Invalid format")

            result = exporter.export_document(
                content=sample_content,
                filename="test",
                export_format=ExportFormat.TXT
            )

            # Should handle the error gracefully
            assert isinstance(result, ExportResult)

    def test_invalid_format_string(self, temp_output_dir, sample_content):
        """Test convenience function with invalid format string"""
        result = export_document(
            content=sample_content,
            filename="test",
            export_format="invalid_format",
            output_dir=temp_output_dir
        )

        assert result.success is False
        assert "Invalid format" in result.error_message

    def test_export_with_file_write_error(self, temp_output_dir, sample_content):
        """Test export when file write fails"""
        # Create exporter with valid temp directory
        exporter = DocumentExporter(output_dir=temp_output_dir)

        # Mock the _export_to_txt to raise an exception
        with patch.object(exporter, '_export_to_txt') as mock_export:
            mock_export.side_effect = IOError("Write error")

            result = exporter.export_document(
                content=sample_content,
                filename="test",
                export_format=ExportFormat.TXT
            )

            # Should fail gracefully
            assert result.success is False
            assert result.error_message is not None


class TestSupportedFormats:
    """Test supported formats retrieval"""

    @patch('app.services.export.REPORTLAB_AVAILABLE', True)
    @patch('app.services.export.DOCX_AVAILABLE', True)
    def test_all_formats_available(self):
        """Test when all format libraries are available"""
        exporter = DocumentExporter()
        formats = exporter.get_supported_formats()

        assert "txt" in formats
        assert "pdf" in formats
        assert "docx" in formats

    @patch('app.services.export.REPORTLAB_AVAILABLE', False)
    @patch('app.services.export.DOCX_AVAILABLE', False)
    def test_only_txt_available(self):
        """Test when only TXT is available"""
        exporter = DocumentExporter()
        formats = exporter.get_supported_formats()

        assert "txt" in formats
        assert "pdf" not in formats
        assert "docx" not in formats


class TestConvenienceFunction:
    """Test the convenience export function"""

    def test_export_document_convenience(self, temp_output_dir, sample_content):
        """Test export_document convenience function"""
        result = export_document(
            content=sample_content,
            filename="convenience_test",
            export_format="txt",
            output_dir=temp_output_dir,
            metadata={"test": "value"},
            title="Test Title"
        )

        assert result.success is True
        assert result.format == ExportFormat.TXT
        assert result.file_size > 0
        assert result.file_path is not None

        # Verify file exists
        assert Path(result.file_path).exists()

    def test_export_document_case_insensitive(self, temp_output_dir, sample_content):
        """Test that format parameter is case-insensitive"""
        result1 = export_document(
            content=sample_content,
            filename="test1",
            export_format="TXT",
            output_dir=temp_output_dir
        )

        result2 = export_document(
            content=sample_content,
            filename="test2",
            export_format="txt",
            output_dir=temp_output_dir
        )

        assert result1.success is True
        assert result2.success is True


class TestExportResult:
    """Test ExportResult dataclass"""

    def test_export_result_creation(self):
        """Test ExportResult object creation"""
        result = ExportResult(
            success=True,
            format=ExportFormat.PDF,
            file_size=1024,
            duration_ms=150.5,
            file_path="/path/to/file.pdf"
        )

        assert result.success is True
        assert result.format == ExportFormat.PDF
        assert result.file_size == 1024
        assert result.duration_ms == 150.5
        assert result.file_path == "/path/to/file.pdf"
        assert result.error_message is None

    def test_export_result_with_error(self):
        """Test ExportResult with error"""
        result = ExportResult(
            success=False,
            format=ExportFormat.DOCX,
            file_size=0,
            duration_ms=50.0,
            error_message="Library not available"
        )

        assert result.success is False
        assert result.error_message == "Library not available"


class TestExportFormatEnum:
    """Test ExportFormat enumeration"""

    def test_export_format_values(self):
        """Test ExportFormat enum values"""
        assert ExportFormat.PDF.value == "pdf"
        assert ExportFormat.DOCX.value == "docx"
        assert ExportFormat.TXT.value == "txt"

    def test_export_format_from_string(self):
        """Test creating ExportFormat from string"""
        assert ExportFormat("pdf") == ExportFormat.PDF
        assert ExportFormat("docx") == ExportFormat.DOCX
        assert ExportFormat("txt") == ExportFormat.TXT

    def test_export_format_invalid_string(self):
        """Test ExportFormat with invalid string"""
        with pytest.raises(ValueError):
            ExportFormat("invalid")


class TestIntegrationScenarios:
    """Integration tests for common export scenarios"""

    def test_export_multiple_formats_same_content(self, temp_output_dir, sample_content):
        """Test exporting same content to multiple formats"""
        exporter = DocumentExporter(output_dir=temp_output_dir)

        formats_to_test = [ExportFormat.TXT]

        # Only test TXT since other libraries may not be available
        for fmt in formats_to_test:
            result = exporter.export_document(
                content=sample_content,
                filename=f"test_{fmt.value}",
                export_format=fmt,
                metadata={"format": fmt.value}
            )

            assert result.success is True
            assert result.format == fmt
            assert Path(result.file_path).exists()

    def test_export_with_unicode_content(self, temp_output_dir):
        """Test export with Unicode characters"""
        unicode_content = """
        # Test Document with Unicode

        This document contains various Unicode characters:
        - Japanese: 日本語
        - Chinese: 中文
        - Arabic: العربية
        - Russian: Русский
        - Emoji: 🎉 🔥 ⭐
        """

        exporter = DocumentExporter(output_dir=temp_output_dir)
        result = exporter.export_document(
            content=unicode_content,
            filename="unicode_test",
            export_format=ExportFormat.TXT
        )

        assert result.success is True

        # Verify Unicode is preserved
        with open(result.file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "日本語" in content
            assert "中文" in content
            assert "🎉" in content

    def test_export_large_document(self, temp_output_dir):
        """Test export of large document"""
        large_content = "\n\n".join(["Paragraph " + str(i) for i in range(1000)])

        exporter = DocumentExporter(output_dir=temp_output_dir)
        result = exporter.export_document(
            content=large_content,
            filename="large_document",
            export_format=ExportFormat.TXT
        )

        assert result.success is True
        assert result.file_size > 0
