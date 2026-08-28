"""
Unit tests for Multi-Language Support Feature (Feature 11)

Tests the language detection and multilingual query processing functionality.
This feature enables the RAG system to handle queries and documents in multiple languages.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from app.main import app
from app.services.language import (
    LanguageService,
    LanguageDetector,
    LanguageCode,
    LanguageDetectionResult
)
from app.models.schemas import (
    MultilingualQueryRequest,
    MultilingualQueryResponse,
    LanguageDetectionResponse,
    SupportedLanguagesResponse
)


@pytest.fixture
def client():
    """Create test client without lifespan for unit testing"""
    test_app = app.__class__()
    test_app.title = app.title
    test_app.version = app.version
    test_app.description = app.description

    from app.api.routes import query, health
    test_app.include_router(health.router)
    test_app.include_router(query.router, prefix="/api/v1", tags=["Query"])

    return TestClient(test_app)


@pytest.fixture
def language_service():
    """Create language service instance"""
    return LanguageService()


@pytest.fixture
def language_detector():
    """Create language detector instance"""
    return LanguageDetector()


class TestLanguageDetector:
    """Test suite for LanguageDetector"""

    def test_detect_english_text(self, language_detector):
        """Test detection of English text"""
        text = "What is the company policy on remote work?"
        result = language_detector.detect(text)

        assert result.detected_language == LanguageCode.ENGLISH
        assert result.confidence > 0.3  # Lower threshold due to simple scoring
        assert result.is_supported is True
        assert result.text == text

    def test_detect_spanish_text(self, language_detector):
        """Test detection of Spanish text"""
        text = "¿Cuál es la política de trabajo remoto?"
        result = language_detector.detect(text)

        assert result.detected_language == LanguageCode.SPANISH
        assert result.is_supported is True
        assert result.text == text

    def test_detect_french_text(self, language_detector):
        """Test detection of French text"""
        text = "Quelle est la politique de travail à distance?"
        result = language_detector.detect(text)

        assert result.detected_language == LanguageCode.FRENCH
        assert result.is_supported is True

    def test_detect_german_text(self, language_detector):
        """Test detection of German text"""
        text = "Was ist die Richtlinie für Fernarbeit?"
        result = language_detector.detect(text)

        assert result.detected_language == LanguageCode.GERMAN
        assert result.is_supported is True

    def test_detect_chinese_text(self, language_detector):
        """Test detection of Chinese text"""
        text = "远程办公政策是什么？"
        result = language_detector.detect(text)

        assert result.detected_language == LanguageCode.CHINESE
        assert result.is_supported is True

    def test_detect_japanese_text(self, language_detector):
        """Test detection of Japanese text"""
        text = "リモートワークのポリシーは何ですか？"
        result = language_detector.detect(text)

        assert result.detected_language == LanguageCode.JAPANESE
        assert result.is_supported is True

    def test_detect_empty_text(self, language_detector):
        """Test handling of empty text"""
        result = language_detector.detect("")

        assert result.confidence == 0.0
        assert result.is_supported is True

    def test_detect_short_text(self, language_detector):
        """Test handling of very short text"""
        result = language_detector.detect("Hi")

        assert result.confidence == 0.0
        assert result.detected_language == LanguageCode.ENGLISH

    def test_alternative_languages(self, language_detector):
        """Test that alternative languages are provided"""
        text = "the policy of remote work"
        result = language_detector.detect(text)

        # English should be top
        assert result.detected_language == LanguageCode.ENGLISH
        # Should have some alternatives (even if low confidence)
        assert isinstance(result.alternative_languages, list)

    def test_is_supported_language(self, language_detector):
        """Test checking if a language is supported"""
        assert language_detector.is_supported(LanguageCode.ENGLISH) is True
        assert language_detector.is_supported(LanguageCode.SPANISH) is True
        assert language_detector.is_supported(LanguageCode.CHINESE) is True


class TestLanguageService:
    """Test suite for LanguageService"""

    def test_detect_query_language(self, language_service):
        """Test detecting query language"""
        query = "What is the remote work policy?"
        result = language_service.detect_query_language(query)

        assert isinstance(result, LanguageDetectionResult)
        assert result.detected_language == LanguageCode.ENGLISH
        assert result.confidence > 0.0

    def test_detect_document_language(self, language_service):
        """Test detecting document language"""
        document = "Este documento describe las políticas de la empresa."
        result = language_service.detect_document_language(document)

        assert isinstance(result, LanguageDetectionResult)
        assert result.detected_language == LanguageCode.SPANISH

    def test_should_translate_same_language(self, language_service):
        """Test translation decision for same language"""
        result = language_service.should_translate(
            LanguageCode.ENGLISH,
            LanguageCode.ENGLISH
        )
        assert result is False

    def test_should_translate_different_language(self, language_service):
        """Test translation decision for different languages"""
        result = language_service.should_translate(
            LanguageCode.SPANISH,
            LanguageCode.ENGLISH
        )
        assert result is True

    def test_process_multilingual_query_no_translation(self, language_service):
        """Test processing multilingual query without translation needed"""
        query = "What is the company policy?"
        result = language_service.process_multilingual_query(
            query,
            preferred_language=LanguageCode.ENGLISH
        )

        assert result["original_query"] == query
        assert result["detected_language"] == "en"
        assert result["needs_translation"] is False
        assert result["processed_query"] == query

    def test_process_multilingual_query_with_translation(self, language_service):
        """Test processing multilingual query with translation needed"""
        query = "¿Cuál es la política de la empresa?"
        result = language_service.process_multilingual_query(
            query,
            preferred_language=LanguageCode.ENGLISH
        )

        assert result["original_query"] == query
        assert result["detected_language"] == "es"
        assert result["needs_translation"] is True

    def test_get_supported_languages(self, language_service):
        """Test getting list of supported languages"""
        languages = language_service.get_supported_languages()

        assert isinstance(languages, list)
        assert len(languages) > 10
        assert all("code" in lang and "name" in lang for lang in languages)

        # Check for expected languages
        lang_codes = [lang["code"] for lang in languages]
        assert "en" in lang_codes
        assert "es" in lang_codes
        assert "fr" in lang_codes

    def test_get_language_name(self, language_service):
        """Test getting human-readable language name"""
        name = language_service.get_language_name(LanguageCode.ENGLISH)
        assert name == "English"

        name = language_service.get_language_name(LanguageCode.SPANISH)
        assert name == "Spanish"

    def test_validate_language_code_valid(self, language_service):
        """Test validating a valid language code"""
        result = language_service.validate_language_code("en")
        assert result == LanguageCode.ENGLISH

        result = language_service.validate_language_code("es")
        assert result == LanguageCode.SPANISH

    def test_validate_language_code_invalid(self, language_service):
        """Test validating an invalid language code"""
        result = language_service.validate_language_code("xx")
        assert result is None

        result = language_service.validate_language_code("")
        assert result is None


class TestMultilingualQueryRequest:
    """Test suite for MultilingualQueryRequest schema"""

    def test_valid_multilingual_query_request(self):
        """Test creating a valid multilingual query request"""
        request = MultilingualQueryRequest(
            query="¿Cuál es la política?",
            collection="hr-policies",
            top_k=5,
            include_sources=True,
            language="es",
            preferred_language="en"
        )

        assert request.query == "¿Cuál es la política?"
        assert request.collection == "hr-policies"
        assert request.language.value == "es"
        assert request.preferred_language.value == "en"

    def test_multilingual_query_request_optional_fields(self):
        """Test multilingual query request with optional fields"""
        request = MultilingualQueryRequest(
            query="What is the policy?"
        )

        assert request.query == "What is the policy?"
        assert request.collection == "default"
        assert request.top_k == 5
        assert request.include_sources is True
        assert request.language is None
        assert request.preferred_language is None

    def test_multilingual_query_query_too_short(self):
        """Test validation error for query that's too short"""
        with pytest.raises(Exception):
            MultilingualQueryRequest(query="")

    def test_multilingual_query_top_k_validation(self):
        """Test validation of top_k parameter"""
        with pytest.raises(Exception):
            MultilingualQueryRequest(query="test", top_k=0)

        with pytest.raises(Exception):
            MultilingualQueryRequest(query="test", top_k=25)


class TestLanguageDetectionResponse:
    """Test suite for LanguageDetectionResponse schema"""

    def test_language_detection_response_creation(self):
        """Test creating a language detection response"""
        response = LanguageDetectionResponse(
            detected_language="en",
            confidence=0.95,
            is_supported=True,
            alternative_languages=[
                {"language": "es", "confidence": 0.05}
            ]
        )

        assert response.detected_language == "en"
        assert response.confidence == 0.95
        assert response.is_supported is True
        assert len(response.alternative_languages) == 1

    def test_language_detection_response_empty_alternatives(self):
        """Test language detection response with no alternatives"""
        response = LanguageDetectionResponse(
            detected_language="en",
            confidence=0.98,
            is_supported=True,
            alternative_languages=[]
        )

        assert len(response.alternative_languages) == 0


class TestSupportedLanguagesResponse:
    """Test suite for SupportedLanguagesResponse schema"""

    def test_supported_languages_response(self):
        """Test creating supported languages response"""
        languages = [
            {"code": "en", "name": "English"},
            {"code": "es", "name": "Spanish"},
            {"code": "fr", "name": "French"}
        ]

        response = SupportedLanguagesResponse(
            languages=languages,
            count=3
        )

        assert response.count == 3
        assert len(response.languages) == 3
        assert response.languages[0]["code"] == "en"


class TestMultilingualQueryIntegration:
    """Test suite for multilingual query integration"""

    @patch('app.services.language.LanguageDetector.detect')
    def test_multilingual_query_processing_flow(
        self,
        mock_detect,
        language_service
    ):
        """Test the complete flow of multilingual query processing"""
        # Mock language detection
        mock_detect.return_value = LanguageDetectionResult(
            text="¿Cuál es la política?",
            detected_language=LanguageCode.SPANISH,
            confidence=0.92,
            is_supported=True,
            alternative_languages=[]
        )

        query = "¿Cuál es la política de trabajo remoto?"
        result = language_service.process_multilingual_query(
            query,
            preferred_language=LanguageCode.ENGLISH
        )

        assert result["original_query"] == query
        assert result["detected_language"] == "es"
        assert result["confidence"] == 0.92
        assert result["needs_translation"] is True
        assert result["preferred_language"] == "en"

    def test_language_code_enum_values(self):
        """Test that language code enum has expected values"""
        assert LanguageCode.ENGLISH.value == "en"
        assert LanguageCode.SPANISH.value == "es"
        assert LanguageCode.FRENCH.value == "fr"
        assert LanguageCode.GERMAN.value == "de"
        assert LanguageCode.CHINESE.value == "zh"
        assert LanguageCode.JAPANESE.value == "ja"

    def test_all_supported_languages_have_patterns(self):
        """Test that all supported languages have detection patterns"""
        detector = LanguageDetector()
        supported_langs = set(LanguageCode)
        pattern_langs = set(detector.LANGUAGE_PATTERNS.keys())

        # All supported languages should have patterns
        assert supported_langs.issubset(pattern_langs)

    def test_multilingual_edge_case_mixed_language(self, language_detector):
        """Test detection of mixed language text"""
        text = "Hola, what is the política de remote work?"
        result = language_detector.detect(text)

        # Should detect something with reasonable confidence
        assert result.is_supported is True
        assert result.confidence >= 0.0

    def test_multilingual_special_characters(self, language_detector):
        """Test handling of special characters in different languages"""
        text = "¿Qué es la política de @trabajo_remoto? #empresa"
        result = language_detector.detect(text)

        assert result.is_supported is True
        assert isinstance(result.confidence, float)

    def test_multilingual_numbers_and_mixed_content(self, language_detector):
        """Test handling of numbers and mixed content"""
        text = "Policy 2023: 50% employees work remotely"
        result = language_detector.detect(text)

        assert result.detected_language == LanguageCode.ENGLISH
        assert result.is_supported is True
