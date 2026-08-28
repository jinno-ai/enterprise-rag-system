"""
Unit tests for Audio Transcription Feature (Feature 35)

Comprehensive test suite for audio file transcription and indexing functionality.
This feature enables the enterprise-rag-system to process audio files by transcribing
them using OpenAI's Whisper model and indexing the transcribed text.

Test Coverage:
- Configuration validation and defaults
- Audio file transcription with various formats
- Audio data transcription from bytes
- Error handling for missing/invalid files
- Language detection and specification
- Integration with document loader
- Batch processing of audio files
- Edge cases and boundary conditions
- Performance and resource cleanup
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile

from app.services.transcription import (
    AudioTranscriptionService,
    TranscriptionConfig,
    TranscriptionError,
    transcribe_audio_file,
    WHISPER_AVAILABLE,
)


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestFeature35AudioTranscriptionBasics:
    """Basic functionality tests for audio transcription"""

    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_simple_audio_file(self, mock_load_model):
        """Test transcribing a simple audio file"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "This is a simple transcription test",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)

            assert result["text"] == "This is a simple transcription test"
            assert result["language"] == "en"
            assert result["file_type"] == "wav"
            assert "filename" in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_with_auto_language_detection(self, mock_load_model):
        """Test transcription with automatic language detection"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Bonjour le monde",
            "language": "fr"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)
            assert result["language"] == "fr"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_with_explicit_language(self, mock_load_model):
        """Test transcription with explicitly specified language"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Esta es una prueba en español",
            "language": "es"
        }
        mock_load_model.return_value = mock_model

        config = TranscriptionConfig(language="es")
        service = AudioTranscriptionService(config)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)
            assert result["language"] == "es"
        finally:
            Path(temp_path).unlink(missing_ok=True)


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestFeature35SupportedFormats:
    """Test support for various audio formats"""

    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_mp3_format(self, mock_load_model):
        """Test transcribing MP3 audio file"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "MP3 audio content",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)
            assert result["text"] == "MP3 audio content"
            assert result["file_type"] == "mp3"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_m4a_format(self, mock_load_model):
        """Test transcribing M4A audio file"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "M4A audio content",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)
            assert result["text"] == "M4A audio content"
            assert result["file_type"] == "m4a"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_webm_format(self, mock_load_model):
        """Test transcribing WebM audio file"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "WebM audio content",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)
            assert result["text"] == "WebM audio content"
            assert result["file_type"] == "webm"
        finally:
            Path(temp_path).unlink(missing_ok=True)


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestFeature35ErrorHandling:
    """Test error handling in audio transcription"""

    def test_transcribe_nonexistent_file(self):
        """Test handling of non-existent audio file"""
        service = AudioTranscriptionService()

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            service.transcribe_file("/nonexistent/path/to/audio.wav")

    def test_transcribe_unsupported_format(self):
        """Test handling of unsupported audio format"""
        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            temp_path = f.name

        try:
            with pytest.raises(TranscriptionError, match="Unsupported audio format"):
                service.transcribe_file(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_model_failure(self, mock_load_model):
        """Test handling of transcription model failure"""
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = Exception("Model processing error")
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            with pytest.raises(TranscriptionError, match="Failed to transcribe"):
                service.transcribe_file(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestFeature35OutputFormats:
    """Test different output formats"""

    @patch('app.services.transcription.whisper.load_model')
    def test_text_output_format(self, mock_load_model):
        """Test text-only output format"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Simple text output",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path, output_format="text")

            assert "text" in result
            assert "segments" not in result
            assert "duration" not in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch('app.services.transcription.whisper.load_model')
    def test_verbose_json_output_format(self, mock_load_model):
        """Test verbose JSON output format with segments"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Verbose output with segments",
            "language": "en",
            "duration": 12.5,
            "segments": [
                {"start": 0.0, "end": 5.0, "text": "Verbose output"},
                {"start": 5.0, "end": 12.5, "text": "with segments"}
            ]
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path, output_format="verbose_json")

            assert result["text"] == "Verbose output with segments"
            assert result["duration"] == 12.5
            assert len(result["segments"]) == 2
            assert result["segments"][0]["text"] == "Verbose output"
            assert result["segments"][1]["text"] == "with segments"
        finally:
            Path(temp_path).unlink(missing_ok=True)


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestFeature35ModelConfigurations:
    """Test different model configurations"""

    @patch('app.services.transcription.whisper.load_model')
    def test_different_model_sizes(self, mock_load_model):
        """Test using different Whisper model sizes"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Test transcription",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        # Test with 'tiny' model
        config_tiny = TranscriptionConfig(model_size="tiny")
        service_tiny = AudioTranscriptionService(config_tiny)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result_tiny = service_tiny.transcribe_file(temp_path)
            assert result_tiny["text"] == "Test transcription"
        finally:
            Path(temp_path).unlink(missing_ok=True)

        # Test with 'large' model
        config_large = TranscriptionConfig(model_size="large")
        service_large = AudioTranscriptionService(config_large)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result_large = service_large.transcribe_file(temp_path)
            assert result_large["text"] == "Test transcription"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_invalid_model_size_raises_error(self):
        """Test that invalid model size raises ValueError"""
        with pytest.raises(ValueError, match="Invalid model_size"):
            TranscriptionConfig(model_size="invalid_size")


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestFeature35AudioDataTranscription:
    """Test transcribing audio data from bytes"""

    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_audio_data_from_bytes(self, mock_load_model):
        """Test transcribing audio data provided as bytes"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Transcribed from bytes",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        # Simulate audio data
        audio_data = b"mock_audio_bytes_data"

        result = service.transcribe_audio_data(audio_data, file_format="wav")

        assert result["text"] == "Transcribed from bytes"
        assert result["file_type"] == "wav"
        assert "source" not in result
        assert "filename" not in result

    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_audio_data_cleanup(self, mock_load_model):
        """Test that temporary files from audio data are cleaned up"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Test",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()
        audio_data = b"test_data"

        with patch('pathlib.Path.unlink') as mock_unlink:
            service.transcribe_audio_data(audio_data, file_format="mp3")
            # Verify cleanup was called
            mock_unlink.assert_called()


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestFeature35DocumentLoaderIntegration:
    """Test integration with document loader"""

    @patch('app.services.transcription.whisper.load_model')
    def test_document_loader_load_audio(self, mock_load_model):
        """Test loading audio through DocumentLoader"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Loaded via DocumentLoader",
            "language": "en",
            "duration": 8.3
        }
        mock_load_model.return_value = mock_model

        from app.services.document_loader import DocumentLoader

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            doc = DocumentLoader.load_audio(temp_path)

            assert doc.content == "Loaded via DocumentLoader"
            assert doc.metadata["file_type"] == "audio"
            assert doc.metadata["audio_format"] == "wav"
            assert doc.metadata["duration_seconds"] == 8.3
            assert doc.metadata["language"] == "en"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_document_loader_import_check(self):
        """Test that document loader properly imports transcription"""
        from app.services.document_loader import DocumentLoader, TRANSCRIPTION_AVAILABLE

        assert hasattr(DocumentLoader, 'load_audio')
        assert isinstance(TRANSCRIPTION_AVAILABLE, bool)


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestFeature35ConvenienceFunctions:
    """Test convenience functions for audio transcription"""

    @patch('app.services.transcription.whisper.load_model')
    def test_convenience_function_returns_text(self, mock_load_model):
        """Test that convenience function returns text string directly"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Quick transcription",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = transcribe_audio_file(temp_path)
            assert isinstance(result, str)
            assert result == "Quick transcription"
        finally:
            Path(temp_path).unlink(missing_ok=True)


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestFeature35ModelCaching:
    """Test model loading and caching behavior"""

    @patch('app.services.transcription.whisper.load_model')
    def test_model_is_loaded_once_and_cached(self, mock_load_model):
        """Test that model is loaded once and reused for subsequent transcriptions"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Test",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            # First transcription loads the model
            service.transcribe_file(temp_path)
            assert mock_load_model.call_count == 1

            # Second transcription uses cached model
            service.transcribe_file(temp_path)
            assert mock_load_model.call_count == 1  # Still 1, not 2

            # Third transcription also uses cached model
            service.transcribe_file(temp_path)
            assert mock_load_model.call_count == 1  # Still 1
        finally:
            Path(temp_path).unlink(missing_ok=True)


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestFeature35EdgeCases:
    """Test edge cases and boundary conditions"""

    @patch('app.services.transcription.whisper.load_model')
    def test_empty_transcription_result(self, mock_load_model):
        """Test handling of empty transcription result"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)
            assert result["text"] == ""
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch('app.services.transcription.whisper.load_model')
    def test_transcription_with_special_characters(self, mock_load_model):
        """Test transcription with special characters and punctuation"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Hello! How are you? I'm fine, thanks.",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)
            assert "!" in result["text"]
            assert "?" in result["text"]
            assert "'" in result["text"]
            assert "," in result["text"]
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch('app.services.transcription.whisper.load_model')
    def test_very_long_transcription(self, mock_load_model):
        """Test handling of very long transcriptions"""
        long_text = " ".join(["word"] * 1000)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": long_text,
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)
            assert len(result["text"]) == len(long_text)
        finally:
            Path(temp_path).unlink(missing_ok=True)


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestFeature35TemperatureConfiguration:
    """Test temperature configuration for transcription"""

    @patch('app.services.transcription.whisper.load_model')
    def test_zero_temperature_for_deterministic_output(self, mock_load_model):
        """Test zero temperature for deterministic transcription"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Deterministic result",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        config = TranscriptionConfig(temperature=0.0)
        service = AudioTranscriptionService(config)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)
            assert result["text"] == "Deterministic result"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch('app.services.transcription.whisper.load_model')
    def test_high_temperature_for_creative_output(self, mock_load_model):
        """Test higher temperature for more varied output"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "More varied result",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        config = TranscriptionConfig(temperature=0.7)
        service = AudioTranscriptionService(config)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)
            assert result["text"] == "More varied result"
        finally:
            Path(temp_path).unlink(missing_ok=True)
