"""
Document Encryption Module

This module provides encryption and decryption functionality for sensitive document content.
It uses Fernet symmetric encryption (cryptography library) with proper key management.

Security Features:
- Fernet symmetric encryption (AES-128-CBC with HMAC)
- URL-safe base64 encoding for encrypted content
- Key rotation support
- Backward compatibility with non-encrypted documents

Usage:
    from app.core.encryption import EncryptionService

    # Initialize with default or custom key
    service = EncryptionService()

    # Encrypt content
    encrypted = service.encrypt("sensitive content")

    # Decrypt content
    decrypted = service.decrypt(encrypted)
"""

from typing import Optional, Dict, Any, List, Tuple
from cryptography.fernet import Fernet, InvalidToken
import logging
import os
import threading

logger = logging.getLogger(__name__)

# Fernet token prefix for detecting encrypted content
FERNET_TOKEN_PREFIX = 'gAAAAA'


class EncryptionError(Exception):
    """Base exception for encryption errors"""
    pass


class EncryptionKeyError(EncryptionError):
    """Exception raised for key-related errors"""
    pass


class EncryptionService:
    """
    Service for encrypting and decrypting document content.

    Uses Fernet symmetric encryption which provides:
    - AES-128-CBC for encryption
    - HMAC for authentication
    - Time-stamp support
    - URL-safe encoding

    Attributes:
        key: The encryption key (32 bytes, URL-safe base64 encoded)
        fernet: The Fernet instance for encryption/decryption
    """

    def __init__(self, key: Optional[str] = None):
        """
        Initialize the encryption service.

        Args:
            key: Optional encryption key. If not provided, will look for
                 ENCRYPTION_KEY environment variable or generate a new key.

        Raises:
            EncryptionKeyError: If key is provided but invalid
        """
        if key is None:
            # Try to get key from environment
            key = os.environ.get("ENCRYPTION_KEY")

            if key is None:
                # Generate a new key for development
                # In production, always set ENCRYPTION_KEY environment variable
                logger.warning(
                    "No ENCRYPTION_KEY found in environment. "
                    "Generating a temporary key. For production, set ENCRYPTION_KEY."
                )
                key = self.generate_key()

        # Validate and set the key
        try:
            self.key = key.encode() if isinstance(key, str) else key
            self.fernet = Fernet(self.key)
        except Exception as e:
            raise EncryptionKeyError(f"Invalid encryption key: {e}")

        logger.info("Encryption service initialized")

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet encryption key.

        Returns:
            URL-safe base64-encoded 32-byte key

        Example:
            >>> key = EncryptionService.generate_key()
            >>> # Save this key to your .env file:
            >>> # ENCRYPTION_KEY=your_generated_key_here
        """
        return Fernet.generate_key().decode()

    def encrypt(self, content: str) -> str:
        """
        Encrypt string content.

        Args:
            content: Plain text content to encrypt

        Returns:
            Encrypted content (URL-safe base64 encoded string)

        Raises:
            EncryptionError: If encryption fails

        Example:
            >>> service = EncryptionService()
            >>> encrypted = service.encrypt("sensitive data")
            >>> print(encrypted)  # 'gAAAAABh...'
        """
        if not content:
            logger.debug("Attempted to encrypt empty content, returning as-is")
            return content

        try:
            # Convert to bytes
            content_bytes = content.encode('utf-8')

            # Encrypt and decode to string
            encrypted_bytes = self.fernet.encrypt(content_bytes)
            encrypted_str = encrypted_bytes.decode('utf-8')

            logger.debug(f"Successfully encrypted {len(content)} bytes")
            return encrypted_str

        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt content: {e}")

    def decrypt(self, encrypted_content: str) -> str:
        """
        Decrypt encrypted string content.

        Args:
            encrypted_content: Encrypted content (URL-safe base64 encoded)

        Returns:
            Decrypted plain text string

        Raises:
            EncryptionError: If decryption fails (wrong key or corrupted data)
            InvalidToken: If the token is invalid (wrong key or tampered data)

        Example:
            >>> service = EncryptionService()
            >>> encrypted = service.encrypt("sensitive data")
            >>> decrypted = service.decrypt(encrypted)
            >>> assert decrypted == "sensitive data"
        """
        if not encrypted_content:
            logger.warning("Attempted to decrypt empty content")
            return encrypted_content

        # Check if content is actually encrypted
        # Fernet tokens start with 'gAAAAA' and are base64-like
        if not encrypted_content.startswith(FERNET_TOKEN_PREFIX):
            logger.debug("Content does not appear to be encrypted, returning as-is")
            return encrypted_content

        try:
            # Convert to bytes and decrypt
            encrypted_bytes = encrypted_content.encode('utf-8')
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            decrypted_str = decrypted_bytes.decode('utf-8')

            logger.debug(f"Successfully decrypted {len(encrypted_content)} bytes")
            return decrypted_str

        except InvalidToken as e:
            logger.error(f"Decryption failed: Invalid token (wrong key or corrupted data)")
            raise EncryptionError(
                "Failed to decrypt: Invalid token. "
                "This usually means the encryption key is wrong or the data was tampered with."
            )
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise EncryptionError(f"Failed to decrypt content: {e}")

    def encrypt_dict(self, data: Dict[str, Any], fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Encrypt specific fields in a dictionary.

        Useful for encrypting sensitive fields in document metadata.

        Args:
            data: Dictionary containing data to encrypt
            fields: List of field names to encrypt. If None, encrypts all string values

        Returns:
            Dictionary with specified fields encrypted

        Example:
            >>> service = EncryptionService()
            >>> metadata = {"title": "Public", "ssn": "123-45-6789"}
            >>> encrypted = service.encrypt_dict(metadata, fields=["ssn"])
            >>> print(encrypted)
            {'title': 'Public', 'ssn': 'gAAAAA...'}
        """
        if fields is None:
            # Encrypt all string values
            fields = [k for k, v in data.items() if isinstance(v, str)]

        result = data.copy()

        for field in fields:
            if field in result and isinstance(result[field], str):
                try:
                    result[field] = self.encrypt(result[field])
                except EncryptionError as e:
                    logger.warning(f"Failed to encrypt field '{field}': {e}")

        return result

    def decrypt_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt encrypted fields in a dictionary.

        Automatically detects and decrypts fields that appear to be encrypted
        (start with 'gAAAAA').

        Args:
            data: Dictionary potentially containing encrypted fields

        Returns:
            Dictionary with encrypted fields decrypted

        Example:
            >>> service = EncryptionService()
            >>> encrypted_data = {"title": "Public", "ssn": "gAAAAA..."}
            >>> decrypted = service.decrypt_dict(encrypted_data)
            >>> print(decrypted)
            {'title': 'Public', 'ssn': '123-45-6789'}
        """
        result = data.copy()

        for key, value in result.items():
            if isinstance(value, str) and value.startswith(FERNET_TOKEN_PREFIX):
                try:
                    result[key] = self.decrypt(value)
                except EncryptionError as e:
                    logger.warning(f"Failed to decrypt field '{key}': {e}")

        return result

    def rotate_key(self, old_key: str, encrypted_data: str) -> str:
        """
        Rotate encryption key by decrypting with old key and re-encrypting with new key.

        Args:
            old_key: The old encryption key
            encrypted_data: Data encrypted with the old key

        Returns:
            Data encrypted with the new key

        Raises:
            EncryptionError: If key rotation fails

        Example:
            >>> old_service = EncryptionService(key=old_key)
            >>> new_service = EncryptionService(key=new_key)
            >>> encrypted = old_service.encrypt("sensitive data")
            >>> rotated = new_service.rotate_key(old_key, encrypted)
        """
        try:
            # Create temporary service with old key
            temp_service = EncryptionService(key=old_key)

            # Decrypt with old key
            decrypted = temp_service.decrypt(encrypted_data)

            # Encrypt with new key
            re_encrypted = self.encrypt(decrypted)

            logger.info("Successfully rotated encryption key")
            return re_encrypted

        except Exception as e:
            logger.error(f"Key rotation failed: {e}")
            raise EncryptionError(f"Failed to rotate key: {e}")

    def is_encrypted(self, content: str) -> bool:
        """
        Check if content appears to be encrypted with Fernet.

        Args:
            content: Content to check

        Returns:
            True if content appears to be encrypted, False otherwise

        Example:
            >>> service = EncryptionService()
            >>> encrypted = service.encrypt("test")
            >>> service.is_encrypted(encrypted)
            True
            >>> service.is_encrypted("plain text")
            False
        """
        if not content or not isinstance(content, str):
            return False

        # Fernet tokens start with 'gAAAAA' and are base64-encoded
        # Minimum valid Fernet token length is ~40 characters
        return len(content) >= 40 and content.startswith(FERNET_TOKEN_PREFIX)


# Singleton instance for convenience
_default_service: Optional[EncryptionService] = None
_lock = threading.Lock()


def get_encryption_service() -> EncryptionService:
    """
    Get the default encryption service instance (thread-safe singleton).

    Thread Safety:
        This function is thread-safe. The returned EncryptionService
        uses Fernet which is thread-safe for encryption/decryption operations.
        However, EncryptionService initialization itself is not thread-safe,
        so this function should be called during application startup.

    Returns:
        The singleton EncryptionService instance

    Example:
        >>> service = get_encryption_service()
        >>> encrypted = service.encrypt("sensitive data")
    """
    global _default_service

    if _default_service is None:
        with _lock:
            # Double-checked locking pattern
            if _default_service is None:
                _default_service = EncryptionService()

    return _default_service
