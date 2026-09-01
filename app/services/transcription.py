"""
Audio Transcription Service

This module handles audio file transcription using OpenAI's Whisper model.
It provides functionality to transcribe audio files and convert them to text format
for further processing in the RAG pipeline.
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
import logging
import tempfile

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Custom exception for transcription errors"""
    pass


class TranscriptionConfig:
    """Configuration for audio transcription"""

    def __init__(
        self,
        model_size: str = "base",
        language: Optional[str] = None,
        task: str = "transcribe",
        temperature: float = 0.0,
    ):
        """
        Initialize transcription configuration

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            language: Language code (e.g., 'en', 'ja', 'zh'). None for auto-detect
            task: Either 'transcribe' or 'translate'
            temperature: Sampling temperature for decoding
        """
        valid_models = ["tiny", "base", "small", "medium", "large"]
        if model_size not in valid_models:
            raise ValueError(
                f"Invalid model_size: {model_size}. Must be one of {valid_models}"
            )

        if task not in ["transcribe", "translate"]:
            raise ValueError(
                f"Invalid task: {task}. Must be 'transcribe' or 'translate'"
            )

        if not 0.0 <= temperature <= 1.0:
            raise ValueError("Temperature must be between 0.0 and 1.0")

        self.model_size = model_size
        self.language = language
        self.task = task
        self.temperature = temperature


class AudioTranscriptionService:
    """
    Service for transcribing audio files using OpenAI's Whisper model
    """

    def __init__(self, config: Optional[TranscriptionConfig] = None):
        """
        Initialize the transcription service

        Args:
            config: Transcription configuration. Uses defaults if not provided
        """
        if not WHISPER_AVAILABLE:
            raise ImportError(
                "Whisper is not installed. "
                "Install it with: pip install openai-whisper"
            )

        self.config = config or TranscriptionConfig()
        self._model = None

    def _load_model(self):
        """Lazy load the Whisper model"""
        if self._model is None:
            logger.info(f"Loading Whisper model: {self.config.model_size}")
            self._model = whisper.load_model(self.config.model_size)
            logger.info("Whisper model loaded successfully")

    def transcribe_file(
        self,
        audio_path: str,
        output_format: str = "text"
    ) -> Dict[str, Any]:
        """
        Transcribe an audio file

        Args:
            audio_path: Path to the audio file
            output_format: Format for output ('text', 'json', 'verbose_json')

        Returns:
            Dictionary containing transcription results with keys:
                - text: Transcribed text
                - language: Detected/specified language
                - duration: Audio duration in seconds (if verbose)
                - segments: List of segments with timestamps (if verbose)

        Raises:
            FileNotFoundError: If audio file doesn't exist
            TranscriptionError: If transcription fails
        """
        audio_file = Path(audio_path)

        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if not self._is_supported_audio_format(audio_file):
            raise TranscriptionError(
                f"Unsupported audio format: {audio_file.suffix}. "
                f"Supported formats: .mp3, .mp4, .mpeg, .mpga, .m4a, .wav, .webm"
            )

        try:
            self._load_model()

            logger.info(f"Transcribing audio file: {audio_file.name}")

            # Prepare transcription options
            options = {
                "task": self.config.task,
                "temperature": self.config.temperature,
            }

            if self.config.language:
                options["language"] = self.config.language

            if output_format == "verbose_json":
                options["verbose"] = True

            # Perform transcription
            result = self._model.transcribe(str(audio_file), **options)

            # Build response
            response = {
                "text": result["text"],
                "language": result.get("language", "unknown"),
                "source": str(audio_file),
                "filename": audio_file.name,
                "file_type": audio_file.suffix[1:],
            }

            if output_format == "verbose_json":
                response["duration"] = result.get("duration", 0)
                response["segments"] = result.get("segments", [])

            logger.info(
                f"Transcription completed. "
                f"Language: {response['language']}, "
                f"Length: {len(response['text'])} chars"
            )

            return response

        except Exception as e:
            logger.error(f"Transcription failed for {audio_file.name}: {e}")
            raise TranscriptionError(f"Failed to transcribe audio: {str(e)}")

    def transcribe_audio_data(
        self,
        audio_data: bytes,
        file_format: str = "wav",
        output_format: str = "text"
    ) -> Dict[str, Any]:
        """
        Transcribe audio data from bytes

        Args:
            audio_data: Audio file data as bytes
            file_format: Format of the audio data (wav, mp3, etc.)
            output_format: Format for output ('text', 'json', 'verbose_json')

        Returns:
            Dictionary containing transcription results
        """
        with tempfile.NamedTemporaryFile(
            suffix=f".{file_format}",
            delete=False
        ) as temp_file:
            temp_file.write(audio_data)
            temp_path = temp_file.name

        try:
            result = self.transcribe_file(temp_path, output_format=output_format)
            # Remove the temporary source path
            result.pop("source", None)
            result.pop("filename", None)
            result["file_type"] = file_format
            return result
        finally:
            # Clean up temporary file
            Path(temp_path).unlink(missing_ok=True)

    @staticmethod
    def _is_supported_audio_format(audio_file: Path) -> bool:
        """Check if the audio format is supported"""
        supported_extensions = {
            ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"
        }
        return audio_file.suffix.lower() in supported_extensions

    def get_supported_formats(self) -> List[str]:
        """Get list of supported audio formats"""
        return [ext[1:] for ext in {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}]


def transcribe_audio_file(
    audio_path: str,
    model_size: str = "base",
    language: Optional[str] = None,
) -> str:
    """
    Convenience function to transcribe an audio file and return text

    Args:
        audio_path: Path to the audio file
        model_size: Whisper model size
        language: Language code or None for auto-detect

    Returns:
        Transcribed text

    Raises:
        FileNotFoundError: If audio file doesn't exist
        TranscriptionError: If transcription fails
    """
    config = TranscriptionConfig(model_size=model_size, language=language)
    service = AudioTranscriptionService(config)
    result = service.transcribe_file(audio_path)
    return result["text"]
