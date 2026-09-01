"""
Unit tests for Audio Transcription Service (Feature 35)

Tests the audio transcription implementation using OpenAI's Whisper model.
Test coverage includes:
- Configuration validation
- Audio file transcription
- Audio data transcription from bytes
- Error handling for missing files
- Error handling for unsupported formats
- Language detection and specification
- Model loading and caching
- Integration with document loader
- Edge cases and boundary conditions
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
from pathlib import Path
import tempfile

from app.services.transcription import (
    AudioTranscriptionService,
    TranscriptionConfig,
    TranscriptionError,
    transcribe_audio_file,
    WHISPER_AVAILABLE,
)


class TestTranscriptionConfig:
    """Test TranscriptionConfig validation and initialization"""

    def test_valid_config_default_values(self):
        """Test creating a valid configuration with defaults"""
        config = TranscriptionConfig()

        assert config.model_size == "base"
        assert config.language is None
        assert config.task == "transcribe"
        assert config.temperature == 0.0

    def test_valid_config_with_custom_values(self):
        """Test creating a valid configuration with custom values"""
        config = TranscriptionConfig(
            model_size="small",
            language="en",
            task="translate",
            temperature=0.5
        )

        assert config.model_size == "small"
        assert config.language == "en"
        assert config.task == "translate"
        assert config.temperature == 0.5

    def test_invalid_model_size(self):
        """Test that invalid model_size raises ValueError"""
        with pytest.raises(ValueError, match="Invalid model_size"):
            TranscriptionConfig(model_size="invalid")

    def test_invalid_task(self):
        """Test that invalid task raises ValueError"""
        with pytest.raises(ValueError, match="Invalid task"):
            TranscriptionConfig(task="invalid")

    def test_invalid_temperature_too_high(self):
        """Test that temperature > 1.0 raises ValueError"""
        with pytest.raises(ValueError, match="Temperature must be between"):
            TranscriptionConfig(temperature=1.5)

    def test_invalid_temperature_too_low(self):
        """Test that temperature < 0.0 raises ValueError"""
        with pytest.raises(ValueError, match="Temperature must be between"):
            TranscriptionConfig(temperature=-0.1)

    def test_valid_temperature_boundary(self):
        """Test that boundary values for temperature are accepted"""
        config_low = TranscriptionConfig(temperature=0.0)
        config_high = TranscriptionConfig(temperature=1.0)

        assert config_low.temperature == 0.0
        assert config_high.temperature == 1.0


class TestAudioTranscriptionServiceInitialization:
    """Test AudioTranscriptionService initialization"""

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    def test_initialization_with_default_config(self):
        """Test service initialization with default configuration"""
        service = AudioTranscriptionService()

        assert service.config.model_size == "base"
        assert service.config.language is None
        assert service.config.task == "transcribe"
        assert service._model is None  # Model should be lazy loaded

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    def test_initialization_with_custom_config(self):
        """Test service initialization with custom configuration"""
        config = TranscriptionConfig(
            model_size="small",
            language="en"
        )
        service = AudioTranscriptionService(config)

        assert service.config.model_size == "small"
        assert service.config.language == "en"

    @pytest.mark.skipif(WHISPER_AVAILABLE, reason="Whisper is installed")
    def test_initialization_without_whisper(self):
        """Test that initialization fails when Whisper is not installed"""
        with patch('app.services.transcription.WHISPER_AVAILABLE', False):
            with pytest.raises(ImportError, match="Whisper is not installed"):
                AudioTranscriptionService()


class TestAudioTranscriptionServiceTranscribeFile:
    """Test AudioTranscriptionService.transcribe_file method"""

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    def test_transcribe_file_not_found(self):
        """Test transcription with non-existent file"""
        service = AudioTranscriptionService()

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            service.transcribe_file("/nonexistent/audio.mp3")

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    def test_transcribe_unsupported_format(self):
        """Test transcription with unsupported audio format"""
        service = AudioTranscriptionService()

        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            temp_path = f.name

        try:
            with pytest.raises(TranscriptionError, match="Unsupported audio format"):
                service.transcribe_file(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_success_text_format(self, mock_load_model):
        """Test successful transcription with text output format"""
        # Mock the model
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Hello, world!",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        # Create a temporary audio file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path, output_format="text")

            assert result["text"] == "Hello, world!"
            assert result["language"] == "en"
            assert result["file_type"] == "wav"
            assert "source" in result
            assert "filename" in result
            assert "segments" not in result
            assert "duration" not in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_success_verbose_json_format(self, mock_load_model):
        """Test successful transcription with verbose_json output format"""
        # Mock the model
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Hello, world!",
            "language": "en",
            "duration": 5.2,
            "segments": [
                {"start": 0.0, "end": 5.2, "text": "Hello, world!"}
            ]
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        # Create a temporary audio file
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path, output_format="verbose_json")

            assert result["text"] == "Hello, world!"
            assert result["language"] == "en"
            assert result["duration"] == 5.2
            assert len(result["segments"]) == 1
            assert result["segments"][0]["text"] == "Hello, world!"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_with_language_specified(self, mock_load_model):
        """Test transcription with language pre-specified"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Hola mundo",
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
            # Verify that language was passed to transcribe
            mock_model.transcribe.assert_called_once()
            call_kwargs = mock_model.transcribe.call_args[1]
            assert call_kwargs["language"] == "es"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_model_cached(self, mock_load_model):
        """Test that model is loaded only once and cached"""
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
            # First call should load the model
            service.transcribe_file(temp_path)
            assert mock_load_model.call_count == 1

            # Second call should use cached model
            service.transcribe_file(temp_path)
            assert mock_load_model.call_count == 1  # Still 1, not 2
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestAudioTranscriptionServiceTranscribeAudioData:
    """Test AudioTranscriptionService.transcribe_audio_data method"""

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_audio_data_success(self, mock_load_model):
        """Test transcribing audio data from bytes"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Audio from bytes",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()

        # Simulate audio data as bytes
        audio_data = b"fake_audio_data"

        result = service.transcribe_audio_data(audio_data, file_format="wav")

        assert result["text"] == "Audio from bytes"
        assert result["language"] == "en"
        assert result["file_type"] == "wav"
        assert "source" not in result
        assert "filename" not in result

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    @patch('app.services.transcription.whisper.load_model')
    def test_transcribe_audio_data_cleanup(self, mock_load_model):
        """Test that temporary files are cleaned up after transcription"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Test",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        service = AudioTranscriptionService()
        audio_data = b"fake_audio_data"

        with patch('pathlib.Path.unlink') as mock_unlink:
            service.transcribe_audio_data(audio_data, file_format="wav")
            # Verify that unlink was called to clean up temp file
            mock_unlink.assert_called_once()


class TestGetSupportedFormats:
    """Test AudioTranscriptionService.get_supported_formats method"""

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    def test_get_supported_formats(self):
        """Test getting list of supported audio formats"""
        service = AudioTranscriptionService()
        formats = service.get_supported_formats()

        assert isinstance(formats, list)
        assert "mp3" in formats
        assert "wav" in formats
        assert "mp4" in formats
        assert "m4a" in formats
        assert "webm" in formats


class TestTranscribeAudioFileConvenienceFunction:
    """Test the convenience function transcribe_audio_file"""

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    @patch('app.services.transcription.whisper.load_model')
    def test_convenience_function_success(self, mock_load_model):
        """Test the convenience function returns text directly"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Convenience test",
            "language": "en"
        }
        mock_load_model.return_value = mock_model

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = transcribe_audio_file(temp_path, model_size="base")
            assert result == "Convenience test"
            assert isinstance(result, str)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    def test_convenience_function_file_not_found(self):
        """Test convenience function with non-existent file"""
        with pytest.raises(FileNotFoundError):
            transcribe_audio_file("/nonexistent/file.wav")


class TestIntegrationWithDocumentLoader:
    """Test integration with document_loader.py"""

    def test_document_loader_imports_transcription(self):
        """Test that document_loader can import transcription service"""
        try:
            from app.services.document_loader import DocumentLoader, TRANSCRIPTION_AVAILABLE
            # Check that the import works
            assert DocumentLoader is not None
            # TRANSCRIPTION_AVAILABLE depends on whether Whisper is installed
            assert isinstance(TRANSCRIPTION_AVAILABLE, bool)
        except ImportError as e:
            pytest.fail(f"Failed to import document_loader: {e}")

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    @patch('app.services.transcription.whisper.load_model')
    def test_document_loader_load_audio_method(self, mock_load_model):
        """Test DocumentLoader.load_audio method"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Loaded via DocumentLoader",
            "language": "en",
            "duration": 3.5
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
            assert doc.metadata["language"] == "en"
            assert doc.metadata["duration_seconds"] == 3.5
            assert "transcription_model" in doc.metadata
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_document_loader_load_audio_without_whisper(self):
        """Test DocumentLoader.load_audio raises ImportError when Whisper unavailable"""
        from app.services.document_loader import DocumentLoader

        with patch('app.services.document_loader.TRANSCRIPTION_AVAILABLE', False):
            with pytest.raises(ImportError, match="openai-whisper"):
                DocumentLoader.load_audio("test.wav")


class TestErrorHandling:
    """Test error handling in transcription service"""

    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
    @patch('app.services.transcription.whisper.load_model')
    def test_transcription_error_propagation(self, mock_load_model):
        """Test that transcription errors are properly wrapped"""
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = Exception("Whisper internal error")
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
    @patch('app.services.transcription.whisper.load_model')
    def test_language_detection_when_language_none(self, mock_load_model):
        """Test that language detection works when language not specified"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Detected language",
            "language": "fr"
        }
        mock_load_model.return_value = mock_model

        config = TranscriptionConfig(language=None)
        service = AudioTranscriptionService(config)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            result = service.transcribe_file(temp_path)
            # Language should be detected by Whisper
            assert result["language"] == "fr"
        finally:
            Path(temp_path).unlink(missing_ok=True)
