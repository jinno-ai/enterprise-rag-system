"""
Document Loading and Processing

This module handles loading documents from various sources and formats.

For advanced chunking strategies (fixed, sentence-based, recursive),
see app/services/chunking.py which provides a more comprehensive
chunking framework with multiple strategies.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
import hashlib
import logging

logger = logging.getLogger(__name__)

from app.core.logging_config import get_logger


logger = get_logger(__name__)


# Try to import transcription service
try:
    from app.services.transcription import AudioTranscriptionService, TranscriptionError
    TRANSCRIPTION_AVAILABLE = True
except ImportError:
    TRANSCRIPTION_AVAILABLE = False

# Try to import encryption service
try:
    from app.core.encryption import EncryptionService, EncryptionError, get_encryption_service
    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False
    # Define stubs for type checking
    EncryptionService = None  # type: ignore
    EncryptionError = None  # type: ignore
    get_encryption_service = None  # type: ignore


@dataclass
class Document:
    """Document representation"""
    content: str
    metadata: Dict[str, Any]
    doc_id: Optional[str] = None
    encrypted: bool = False

    def __post_init__(self):
        """Generate document ID if not provided"""
        if not self.doc_id:
            self.doc_id = self._generate_id()

    def _generate_id(self) -> str:
        """Generate unique document ID based on content"""
        content_hash = hashlib.sha256(self.content.encode()).hexdigest()
        source = self.metadata.get('source', 'unknown')
        return f"{source}_{content_hash[:16]}"

    def encrypt_content(self, encryption_service: Optional[EncryptionService] = None) -> 'Document':
        """
        Encrypt the document content.

        Args:
            encryption_service: Optional EncryptionService instance.
                               If not provided, uses singleton instance.

        Returns:
            Document with encrypted content

        Raises:
            ImportError: If encryption is not available
            EncryptionError: If encryption fails
        """
        if not ENCRYPTION_AVAILABLE:
            raise ImportError(
                "Encryption requires cryptography library. "
                "Ensure app.core.encryption is available."
            )

        if encryption_service is None:
            encryption_service = get_encryption_service()

        try:
            encrypted_content = encryption_service.encrypt(self.content)
        except EncryptionError as e:
            logger.error(f"Failed to encrypt document {self.doc_id}: {e}")
            raise

        # Return new Document with encrypted content
        return Document(
            content=encrypted_content,
            metadata=self.metadata.copy(),
            doc_id=self.doc_id,
            encrypted=True
        )

    def decrypt_content(self, encryption_service: Optional[EncryptionService] = None) -> 'Document':
        """
        Decrypt the document content.

        Args:
            encryption_service: Optional EncryptionService instance.
                               If not provided, uses singleton instance.

        Returns:
            Document with decrypted content

        Raises:
            ImportError: If encryption is not available
            EncryptionError: If decryption fails
        """
        if not ENCRYPTION_AVAILABLE:
            raise ImportError(
                "Decryption requires cryptography library. "
                "Ensure app.core.encryption is available."
            )

        if encryption_service is None:
            encryption_service = get_encryption_service()

        try:
            decrypted_content = encryption_service.decrypt(self.content)
        except EncryptionError as e:
            logger.error(f"Failed to decrypt document {self.doc_id}: {e}")
            raise

        # Return new Document with decrypted content
        return Document(
            content=decrypted_content,
            metadata=self.metadata.copy(),
            doc_id=self.doc_id,
            encrypted=False
        )


class DocumentLoader:
    """Base class for document loaders"""

    @staticmethod
    def load_text_file(
        file_path: str,
        encrypt: bool = False,
        encryption_service: Optional[EncryptionService] = None
    ) -> Document:
        """
        Load a plain text file

        Args:
            file_path: Path to the text file
            encrypt: Whether to encrypt the content after loading
            encryption_service: Optional EncryptionService instance

        Returns:
            Document with (optionally encrypted) content
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        metadata = {
            'source': str(path),
            'filename': path.name,
            'file_type': 'txt',
            'size_bytes': path.stat().st_size
        }

        doc = Document(content=content, metadata=metadata)

        # Encrypt if requested
        if encrypt and ENCRYPTION_AVAILABLE:
            if encryption_service is None:
                encryption_service = EncryptionService()
            doc = doc.encrypt_content(encryption_service)
            logger.info(f"Loaded and encrypted: {path.name}")
        elif encrypt and not ENCRYPTION_AVAILABLE:
            logger.warning("Encryption requested but not available, loading without encryption")

        return doc
    
    @staticmethod
    def load_pdf(file_path: str) -> List[Document]:
        """Load a PDF file"""
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("pypdf not installed. Run: pip install pypdf")
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        reader = PdfReader(str(path))
        documents = []
        
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            
            if text.strip():  # Only include non-empty pages
                metadata = {
                    'source': str(path),
                    'filename': path.name,
                    'file_type': 'pdf',
                    'page': page_num + 1,
                    'total_pages': len(reader.pages)
                }
                
                documents.append(Document(content=text, metadata=metadata))
        
        return documents
    
    @staticmethod
    def load_markdown(file_path: str) -> Document:
        """Load a Markdown file"""
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        metadata = {
            'source': str(path),
            'filename': path.name,
            'file_type': 'markdown',
            'size_bytes': path.stat().st_size
        }
        
        return Document(content=content, metadata=metadata)
    
    @staticmethod
    def load_audio(
        file_path: str,
        model_size: str = "base",
        language: Optional[str] = None
    ) -> Document:
        """
        Load and transcribe an audio file

        Args:
            file_path: Path to the audio file
            model_size: Whisper model size (tiny, base, small, medium, large)
            language: Language code for transcription or None for auto-detect

        Returns:
            Document with transcribed text as content

        Raises:
            FileNotFoundError: If audio file doesn't exist
            ImportError: If transcription service is not available
            TranscriptionError: If transcription fails
        """
        if not TRANSCRIPTION_AVAILABLE:
            raise ImportError(
                "Audio transcription requires openai-whisper. "
                "Install it with: pip install openai-whisper"
            )

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        logger.info(f"Transcribing audio file: {path.name}")

        try:
            from app.services.transcription import (
                TranscriptionConfig,
                AudioTranscriptionService
            )

            config = TranscriptionConfig(model_size=model_size, language=language)
            service = AudioTranscriptionService(config)
            result = service.transcribe_file(file_path)

            metadata = {
                'source': str(path),
                'filename': path.name,
                'file_type': 'audio',
                'audio_format': path.suffix[1:],
                'language': result.get('language', 'unknown'),
                'transcription_model': model_size,
                'duration_seconds': result.get('duration', 0)
            }

            logger.info(f"Successfully transcribed: {path.name}")
            return Document(content=result['text'], metadata=metadata)

        except TranscriptionError as e:
            logger.error(f"Transcription failed for {path.name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to process audio file {path.name}: {e}")
            raise

    @staticmethod
    def load_directory(
        directory_path: str,
        file_extensions: Optional[List[str]] = None,
        recursive: bool = True,
        transcribe_audio: bool = False,
        audio_model_size: str = "base",
        encrypt: bool = False,
        encryption_service: Optional[EncryptionService] = None
    ) -> List[Document]:
        """
        Load all documents from a directory

        Args:
            directory_path: Path to the directory
            file_extensions: List of file extensions to load
            recursive: Whether to search recursively
            transcribe_audio: Whether to transcribe audio files
            audio_model_size: Whisper model size for transcription
            encrypt: Whether to encrypt document contents
            encryption_service: Optional EncryptionService instance

        Returns:
            List of Documents with (optionally encrypted) content
        """
        if file_extensions is None:
            file_extensions = ['.txt', '.md', '.pdf']
            if transcribe_audio:
                file_extensions.extend(['.mp3', '.wav', '.mp4', '.m4a', '.webm'])

        directory = Path(directory_path)
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        documents = []

        # Get all files
        if recursive:
            files = [f for f in directory.rglob('*') if f.is_file()]
        else:
            files = [f for f in directory.glob('*') if f.is_file()]

        # Filter by extension
        files = [f for f in files if f.suffix.lower() in file_extensions]

        logger.info(f"Found {len(files)} files to process")

        # Audio format extensions
        audio_extensions = {'.mp3', '.wav', '.mp4', '.m4a', '.webm', '.mpga', '.mpeg'}

        # Initialize encryption service if needed
        if encrypt and ENCRYPTION_AVAILABLE and encryption_service is None:
            encryption_service = EncryptionService()

        # Load each file
        for file_path in files:
            try:
                ext = file_path.suffix.lower()

                if ext in audio_extensions:
                    if transcribe_audio and TRANSCRIPTION_AVAILABLE:
                        doc = DocumentLoader.load_audio(
                            str(file_path),
                            model_size=audio_model_size
                        )
                        if encrypt and ENCRYPTION_AVAILABLE:
                            doc = doc.encrypt_content(encryption_service)
                        documents.append(doc)
                    else:
                        logger.warning(
                            f"Skipping audio file {file_path.name}. "
                            "Enable transcribe_audio=True to process audio files."
                        )
                elif ext == '.pdf':
                    docs = DocumentLoader.load_pdf(str(file_path))
                    if encrypt and ENCRYPTION_AVAILABLE:
                        docs = [doc.encrypt_content(encryption_service) for doc in docs]
                    documents.extend(docs)
                elif ext == '.md':
                    doc = DocumentLoader.load_markdown(str(file_path))
                    if encrypt and ENCRYPTION_AVAILABLE:
                        doc = doc.encrypt_content(encryption_service)
                    documents.append(doc)
                elif ext == '.txt':
                    doc = DocumentLoader.load_text_file(
                        str(file_path),
                        encrypt=encrypt,
                        encryption_service=encryption_service
                    )
                    documents.append(doc)

                logger.debug(f"Loaded: {file_path.name}")

            except Exception as e:
                logger.error(f"Failed to load {file_path.name}: {e}")

        logger.info(f"Successfully loaded {len(documents)} documents")
        return documents


class TextSplitter:
    """
    Split documents into smaller chunks for embedding.

    This is a backward-compatible wrapper around the new chunking module.
    For new code, use app.services.chunking.DocumentChunker directly.

    Deprecated: Use app.services.chunking.DocumentChunker for new code.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Optional[List[str]] = None
    ):
        # Import here to avoid circular dependency
        from app.services.chunking import RecursiveCharacterChunkingStrategy

        self._strategy = RecursiveCharacterChunkingStrategy(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators
        )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def split_text(self, text: str) -> List[str]:
        """
        Split text into chunks.

        Returns:
            List of chunk strings (for backward compatibility)
        """
        chunks = self._strategy.chunk(text)
        return [chunk.content for chunk in chunks]

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        Split documents into smaller chunks.

        Returns:
            List of chunked Documents (for backward compatibility)
        """
        chunked_documents = []

        for doc in documents:
            chunks = self._strategy.chunk(doc.content, metadata=doc.metadata)

            for chunk in chunks:
                chunk_metadata = chunk.metadata.copy()
                chunk_metadata['original_doc_id'] = doc.doc_id

                chunked_doc = Document(
                    content=chunk.content,
                    metadata=chunk_metadata
                )
                chunked_documents.append(chunked_doc)

        return chunked_documents
