"""
Unit tests for Document Encryption Feature (Feature 49)

Comprehensive test suite for document encryption and decryption functionality.
This feature enables the enterprise-rag-system to encrypt sensitive document content
using Fernet symmetric encryption with proper key management.

Test Coverage:
- Encryption and decryption of document content
- Key generation and validation
- Dictionary field encryption/decryption
- Key rotation functionality
- Integration with document loader
- Error handling for invalid keys and corrupted data
- Edge cases (empty content, non-encrypted content)
- Backward compatibility with non-encrypted documents
- Performance and resource cleanup
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import os

from app.core.encryption import (
    EncryptionService,
    EncryptionError,
    EncryptionKeyError,
    get_encryption_service,
)
from app.services.document_loader import Document, DocumentLoader


class TestFeature49EncryptionBasics:
    """Basic encryption and decryption functionality tests"""

    def test_encrypt_and_decrypt_simple_content(self):
        """Test encrypting and decrypting simple text content"""
        service = EncryptionService()

        original_content = "This is sensitive information"
        encrypted = service.encrypt(original_content)

        # Verify encryption changed the content
        assert encrypted != original_content
        assert encrypted.startswith('gAAAAA')  # Fernet tokens start with this

        # Verify decryption restores original
        decrypted = service.decrypt(encrypted)
        assert decrypted == original_content

    def test_encrypt_empty_content(self):
        """Test encrypting empty content"""
        service = EncryptionService()

        # Empty content should be returned as-is
        result = service.encrypt("")
        assert result == ""

    def test_decrypt_non_encrypted_content(self):
        """Test decrypting content that wasn't encrypted"""
        service = EncryptionService()

        plain_text = "This is not encrypted"

        # Should return as-is with a warning
        result = service.decrypt(plain_text)
        assert result == plain_text

    def test_decrypt_with_wrong_key(self):
        """Test decryption with wrong encryption key"""
        service1 = EncryptionService()
        service2 = EncryptionService()  # Different key

        content = "Sensitive data"
        encrypted = service1.encrypt(content)

        # Should raise error when decrypting with different key
        with pytest.raises(EncryptionError) as exc_info:
            service2.decrypt(encrypted)

        assert "Invalid token" in str(exc_info.value)

    def test_encrypt_unicode_content(self):
        """Test encrypting content with Unicode characters"""
        service = EncryptionService()

        content = "Hello 世界 🌍 Привет"
        encrypted = service.encrypt(content)
        decrypted = service.decrypt(encrypted)

        assert decrypted == content

    def test_encrypt_large_content(self):
        """Test encrypting large content"""
        service = EncryptionService()

        # Create 1MB of content
        content = "A" * (1024 * 1024)
        encrypted = service.encrypt(content)
        decrypted = service.decrypt(encrypted)

        assert len(decrypted) == len(content)
        assert decrypted == content


class TestFeature49KeyManagement:
    """Tests for encryption key generation and management"""

    def test_generate_new_key(self):
        """Test generating a new encryption key"""
        key1 = EncryptionService.generate_key()
        key2 = EncryptionService.generate_key()

        # Keys should be different
        assert key1 != key2

        # Keys should be valid Fernet keys
        assert len(key1) == 44  # Fernet keys are 44 characters (base64)
        assert len(key2) == 44

    def test_service_initialization_with_custom_key(self):
        """Test initializing service with a custom key"""
        custom_key = EncryptionService.generate_key()
        service = EncryptionService(key=custom_key)

        content = "Test content"
        encrypted = service.encrypt(content)
        decrypted = service.decrypt(encrypted)

        assert decrypted == content

    def test_service_initialization_with_invalid_key(self):
        """Test initialization with invalid key raises error"""
        with pytest.raises(EncryptionKeyError):
            EncryptionService(key="invalid_key")

    def test_service_initialization_from_environment(self):
        """Test initialization using environment variable"""
        test_key = EncryptionService.generate_key()

        with patch.dict(os.environ, {'ENCRYPTION_KEY': test_key}):
            service = EncryptionService()
            assert service.key == test_key.encode()

    def test_service_auto_generates_key_when_missing(self):
        """Test that service generates key when ENCRYPTION_KEY not set"""
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise error, should generate key
            service = EncryptionService()
            assert service.fernet is not None
            assert service.key is not None


class TestFeature49DictionaryEncryption:
    """Tests for encrypting/decrypting dictionary fields"""

    def test_encrypt_specific_fields(self):
        """Test encrypting specific fields in a dictionary"""
        service = EncryptionService()

        data = {
            "title": "Public Document",
            "ssn": "123-45-6789",
            "credit_card": "4111-1111-1111-1111"
        }

        encrypted = service.encrypt_dict(data, fields=["ssn", "credit_card"])

        # Public fields should remain unchanged
        assert encrypted["title"] == "Public Document"

        # Sensitive fields should be encrypted
        assert encrypted["ssn"] != "123-45-6789"
        assert encrypted["ssn"].startswith('gAAAAA')
        assert encrypted["credit_card"] != "4111-1111-1111-1111"
        assert encrypted["credit_card"].startswith('gAAAAA')

    def test_decrypt_dictionary_fields(self):
        """Test decrypting encrypted fields in a dictionary"""
        service = EncryptionService()

        data = {
            "public": "Public info",
            "secret": "Secret info"
        }

        # Encrypt specific fields
        encrypted = service.encrypt_dict(data, fields=["secret"])

        # Decrypt all fields
        decrypted = service.decrypt_dict(encrypted)

        assert decrypted["public"] == "Public info"
        assert decrypted["secret"] == "Secret info"

    def test_encrypt_dict_with_all_string_fields(self):
        """Test encrypting all string fields when fields=None"""
        service = EncryptionService()

        data = {
            "field1": "value1",
            "field2": "value2",
            "number": 123  # Should not encrypt
        }

        encrypted = service.encrypt_dict(data)

        assert encrypted["field1"].startswith('gAAAAA')
        assert encrypted["field2"].startswith('gAAAAA')
        assert encrypted["number"] == 123  # Numbers unchanged


class TestFeature49KeyRotation:
    """Tests for encryption key rotation"""

    def test_rotate_encryption_key(self):
        """Test rotating encryption keys"""
        old_key = EncryptionService.generate_key()
        new_key = EncryptionService.generate_key()

        old_service = EncryptionService(key=old_key)
        new_service = EncryptionService(key=new_key)

        content = "Sensitive data that needs key rotation"
        encrypted_with_old = old_service.encrypt(content)

        # Rotate key
        encrypted_with_new = new_service.rotate_key(old_key, encrypted_with_old)

        # Should be decryptable with new key
        decrypted = new_service.decrypt(encrypted_with_new)
        assert decrypted == content

    def test_rotate_key_with_invalid_old_key(self):
        """Test key rotation fails with invalid old key"""
        service = EncryptionService()

        fake_key = EncryptionService.generate_key()
        encrypted_data = "gAAAAAinvalid_token"

        with pytest.raises(EncryptionError):
            service.rotate_key(fake_key, encrypted_data)


class TestFeature49DocumentIntegration:
    """Tests for integration with Document class"""

    def test_document_encrypt_content(self):
        """Test encrypting document content"""
        from app.core.encryption import EncryptionService

        doc = Document(
            content="Sensitive document content",
            metadata={"source": "test.txt"}
        )

        encrypted_doc = doc.encrypt_content()

        assert encrypted_doc.encrypted is True
        assert encrypted_doc.content != "Sensitive document content"
        assert encrypted_doc.content.startswith('gAAAAA')
        assert encrypted_doc.doc_id == doc.doc_id

    def test_document_decrypt_content(self):
        """Test decrypting document content"""
        from app.core.encryption import EncryptionService, get_encryption_service

        encryption_service = get_encryption_service()

        doc = Document(
            content="Sensitive document content",
            metadata={"source": "test.txt"}
        )

        encrypted_doc = doc.encrypt_content(encryption_service)
        decrypted_doc = encrypted_doc.decrypt_content(encryption_service)

        assert decrypted_doc.encrypted is False
        assert decrypted_doc.content == "Sensitive document content"
        assert decrypted_doc.doc_id == doc.doc_id

    def test_document_loader_with_encryption(self):
        """Test loading documents with encryption enabled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Sensitive content to encrypt")

            # Load with encryption
            from app.core.encryption import EncryptionService
            encryption_service = EncryptionService()

            doc = DocumentLoader.load_text_file(
                str(test_file),
                encrypt=True,
                encryption_service=encryption_service
            )

            assert doc.encrypted is True
            assert doc.content.startswith('gAAAAA')

    def test_document_loader_without_encryption(self):
        """Test loading documents without encryption (default)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Public content")

            doc = DocumentLoader.load_text_file(str(test_file))

            assert doc.encrypted is False
            assert doc.content == "Public content"

    def test_load_directory_with_encryption(self):
        """Test loading directory with encryption enabled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple test files
            (Path(tmpdir) / "file1.txt").write_text("Content 1")
            (Path(tmpdir) / "file2.txt").write_text("Content 2")

            from app.core.encryption import EncryptionService
            encryption_service = EncryptionService()

            docs = DocumentLoader.load_directory(
                tmpdir,
                encrypt=True,
                encryption_service=encryption_service
            )

            assert len(docs) == 2
            assert all(doc.encrypted for doc in docs)
            assert all(doc.content.startswith('gAAAAA') for doc in docs)


class TestFeature49UtilityFunctions:
    """Tests for utility functions"""

    def test_is_encrypted_with_encrypted_content(self):
        """Test is_encrypted returns True for encrypted content"""
        service = EncryptionService()
        content = "Test content"
        encrypted = service.encrypt(content)

        assert service.is_encrypted(encrypted) is True

    def test_is_encrypted_with_plain_content(self):
        """Test is_encrypted returns False for plain content"""
        service = EncryptionService()

        assert service.is_encrypted("plain text") is False
        assert service.is_encrypted("") is False
        assert service.is_encrypted("gAAAA") is False  # Too short

    def test_get_encryption_service_singleton(self):
        """Test that get_encryption_service returns singleton"""
        service1 = get_encryption_service()
        service2 = get_encryption_service()

        # Should return the same instance
        assert service1 is service2


class TestFeature49ErrorHandling:
    """Tests for error handling and edge cases"""

    def test_decrypt_corrupted_data(self):
        """Test decrypting corrupted/invalid data"""
        service = EncryptionService()

        corrupted = "gAAAAAcorrupted_invalid_token_data"

        with pytest.raises(EncryptionError) as exc_info:
            service.decrypt(corrupted)

        assert "Invalid token" in str(exc_info.value)

    def test_encrypt_with_service_initialization_error(self):
        """Test encryption fails when service can't be initialized"""
        with pytest.raises(EncryptionKeyError):
            EncryptionService(key=b"invalid_key_length")

    def test_document_encrypt_without_encryption_available(self):
        """Test document encryption fails when library unavailable"""
        doc = Document(
            content="Test",
            metadata={}
        )

        # Patch ENCRYPTION_AVAILABLE to False
        with patch('app.services.document_loader.ENCRYPTION_AVAILABLE', False):
            with pytest.raises(ImportError):
                doc.encrypt_content()

    def test_backward_compatibility_mixed_documents(self):
        """Test handling mix of encrypted and non-encrypted documents"""
        service = EncryptionService()

        docs = [
            Document(content="Public", metadata={}),
            Document(
                content=service.encrypt("Secret"),
                metadata={},
                encrypted=True
            ),
            Document(content="Another public", metadata={})
        ]

        # Should be able to process mixed documents
        encrypted_count = sum(1 for doc in docs if doc.encrypted)
        assert encrypted_count == 1


class TestFeature49Performance:
    """Tests for performance and resource management"""

    def test_encrypt_decrypt_multiple_documents(self):
        """Test encrypting/decrypting multiple documents efficiently"""
        service = EncryptionService()

        documents = [f"Document content {i}" for i in range(100)]

        # Encrypt all
        encrypted = [service.encrypt(doc) for doc in documents]

        # Decrypt all
        decrypted = [service.decrypt(enc) for enc in encrypted]

        assert decrypted == documents

    def test_repeated_encryption_produces_different_results(self):
        """Test that encrypting same content twice produces different ciphertext"""
        service = EncryptionService()

        content = "Same content"

        encrypted1 = service.encrypt(content)
        encrypted2 = service.encrypt(content)

        # Fernet includes a timestamp, so ciphertexts should differ
        assert encrypted1 != encrypted2

        # But both should decrypt to the same content
        assert service.decrypt(encrypted1) == content
        assert service.decrypt(encrypted2) == content
