"""
Language Detection and Multi-Language Support Service

This module provides functionality for:
1. Detecting the language of text input (queries, documents)
2. Supporting multiple languages in RAG queries
3. Language-aware processing and translation
"""

import logging
import re
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from collections import Counter
from enum import Enum


logger = logging.getLogger(__name__)


class LanguageCode(Enum):
    """Supported language codes (ISO 639-1)"""
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    RUSSIAN = "ru"
    CHINESE = "zh"
    JAPANESE = "ja"
    KOREAN = "ko"
    ARABIC = "ar"
    HINDI = "hi"
    DUTCH = "nl"
    POLISH = "pl"
    TURKISH = "tr"


@dataclass
class LanguageDetectionResult:
    """Result of language detection"""
    text: str
    detected_language: LanguageCode
    confidence: float
    is_supported: bool
    alternative_languages: List[Tuple[LanguageCode, float]]


@dataclass
class LanguageTranslationRequest:
    """Request for translation"""
    text: str
    source_language: LanguageCode
    target_language: LanguageCode


@dataclass
class LanguageTranslationResult:
    """Result of translation"""
    original_text: str
    translated_text: str
    source_language: LanguageCode
    target_language: LanguageCode
    confidence: float


class LanguageDetector:
    """
    Language detection service using character n-grams and patterns.

    This is a lightweight, rule-based approach that doesn't require external ML models.
    For production use, consider integrating with libraries like langdetect or fasttext.
    """

    # Character patterns for different languages (simplified)
    LANGUAGE_PATTERNS: Dict[LanguageCode, Dict[str, Any]] = {
        LanguageCode.ENGLISH: {
            "common_words": {"the", "be", "to", "of", "and", "a", "in", "that", "have", "i"},
            "char_frequency": "etaoinshrdlcumwfgypbvkjxqz",
            "pattern": r"[a-zA-Z]"
        },
        LanguageCode.SPANISH: {
            "common_words": {"el", "la", "de", "que", "y", "a", "en", "un", "ser", "se"},
            "char_frequency": "eaosrnldctiumgpzvbhfyjñáéíóúü",
            "pattern": r"[a-zA-Záéíóúüñ]"
        },
        LanguageCode.FRENCH: {
            "common_words": {"le", "de", "et", "à", "un", "il", "avoir", "ne", "je", "son"},
            "char_frequency": "esaitnrulodcpmévqfbghjàâùîêôë",
            "pattern": r"[a-zA-Zàâäéèêëïîôùûüÿç]"
        },
        LanguageCode.GERMAN: {
            "common_words": {"der", "die", "und", "in", "den", "von", "zu", "das", "mit", "sich"},
            "char_frequency": "enisratdhulcgmobwfkzväöüßpjéyìxq",
            "pattern": r"[a-zA-Zäöüß]"
        },
        LanguageCode.ITALIAN: {
            "common_words": {"il", "di", "che", "e", "la", "un", "a", "per", "in", "è"},
            "char_frequency": "eaionlrtscdupmvqzgbfhóàìèéù",
            "pattern": r"[a-zA-Zàèéìòù]"
        },
        LanguageCode.PORTUGUESE: {
            "common_words": {"o", "de", "a", "e", "do", "da", "em", "um", "para", "é"},
            "char_frequency": "aeosidrnmtuclpvqgbhfzáâàãéêíóõú",
            "pattern": r"[a-zA-Záâãàéêíóõú]"
        },
        LanguageCode.RUSSIAN: {
            "common_words": {"и", "в", "не", "на", "я", "быть", "он", "с", "как", "что"},
            "pattern": r"[а-яА-Я]"
        },
        LanguageCode.CHINESE: {
            "common_words": {"的", "一", "是", "在", "不", "了", "有", "和", "人", "这"},
            "pattern": r"[\u4e00-\u9fff]"
        },
        LanguageCode.JAPANESE: {
            "common_words": {"の", "に", "は", "を", "た", "が", "で", "て", "だ", "する"},
            "pattern": r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]"
        },
        LanguageCode.KOREAN: {
            "common_words": {"의", "이", "가", "은", "는", "을", "를", "에", "와", "하고"},
            "pattern": r"[\uac00-\ud7af]"
        },
        LanguageCode.ARABIC: {
            "common_words": {"في", "من", "على", "أن", "إلى", "هذا", "كان", "أن", "لا", "التي"},
            "pattern": r"[\u0600-\u06ff]"
        },
        LanguageCode.HINDI: {
            "common_words": {"के", "में", "है", "की", "हैं", "से", "को", "पर", "और", "एक"},
            "pattern": r"[\u0900-\u097f]"
        },
        LanguageCode.DUTCH: {
            "common_words": {"de", "van", "het", "een", "en", "in", "is", "dat", "niet", "op"},
            "pattern": r"[a-zA-Zäëïöüé]"
        },
        LanguageCode.POLISH: {
            "common_words": {"w", "z", "i", "nie", "na", "do", "się", "o", "to", "co"},
            "pattern": r"[a-zA-Ząćęłńóśźż]"
        },
        LanguageCode.TURKISH: {
            "common_words": {"bir", "ve", "bu", "in", "da", "olarak", "için", "ama", "amaç", "yok"},
            "pattern": r"[a-zA-Zçğıöşü]"
        }
    }

    # Minimum text length for reliable detection
    MIN_TEXT_LENGTH = 10

    def __init__(self, default_language: LanguageCode = LanguageCode.ENGLISH):
        """
        Initialize language detector.

        Args:
            default_language: Default language to return when detection fails
        """
        self.default_language = default_language

    def detect(self, text: str) -> LanguageDetectionResult:
        """
        Detect the language of the given text.

        Args:
            text: Text to analyze

        Returns:
            LanguageDetectionResult with detected language and confidence
        """
        if not text or len(text.strip()) < self.MIN_TEXT_LENGTH:
            return LanguageDetectionResult(
                text=text,
                detected_language=self.default_language,
                confidence=0.0,
                is_supported=True,
                alternative_languages=[]
            )

        scores = self._calculate_language_scores(text)

        if not scores:
            return LanguageDetectionResult(
                text=text,
                detected_language=self.default_language,
                confidence=0.0,
                is_supported=True,
                alternative_languages=[]
            )

        # Sort by score
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_language, top_score = sorted_scores[0]

        # Calculate confidence (normalized 0-1)
        confidence = min(top_score / 100.0, 1.0)

        # Get alternatives (lower confidence)
        alternatives = [
            (lang, min(score / 100.0, 1.0))
            for lang, score in sorted_scores[1:4]
            if score > 10  # Only include alternatives with meaningful scores
        ]

        return LanguageDetectionResult(
            text=text,
            detected_language=top_language,
            confidence=confidence,
            is_supported=True,
            alternative_languages=alternatives
        )

    def _calculate_language_scores(self, text: str) -> Dict[LanguageCode, float]:
        """
        Calculate scores for each language based on text characteristics.

        Args:
            text: Text to analyze

        Returns:
            Dictionary mapping language codes to confidence scores
        """
        scores = {}
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)

        if not words:
            return {}

        for lang_code, patterns in self.LANGUAGE_PATTERNS.items():
            score = 0.0

            # Check for character presence
            char_pattern = patterns.get("pattern")
            if char_pattern:
                matching_chars = len(re.findall(char_pattern, text))
                total_chars = len(re.findall(r'\w', text))
                if total_chars > 0:
                    char_ratio = matching_chars / total_chars
                    score += char_ratio * 40

            # Check common words
            common_words = patterns.get("common_words", set())
            if common_words:
                word_matches = len(set(words) & common_words)
                word_ratio = word_matches / len(common_words)
                score += word_ratio * 60

            scores[lang_code] = score

        return scores

    def is_supported(self, language_code: LanguageCode) -> bool:
        """
        Check if a language is supported.

        Args:
            language_code: Language code to check

        Returns:
            True if supported, False otherwise
        """
        return language_code in self.LANGUAGE_PATTERNS


class LanguageService:
    """
    Service for handling multi-language support in the RAG system.

    Features:
    - Language detection for queries and documents
    - Language-aware query processing
    - Translation support (integration points)
    - Language-specific processing strategies
    """

    def __init__(self, detector: Optional[LanguageDetector] = None):
        """
        Initialize language service.

        Args:
            detector: Custom language detector (defaults to LanguageDetector)
        """
        self.detector = detector or LanguageDetector()
        self.logger = logging.getLogger(__name__)

    def detect_query_language(
        self,
        query: str
    ) -> LanguageDetectionResult:
        """
        Detect the language of a user query.

        Args:
            query: User query text

        Returns:
            LanguageDetectionResult with detected language
        """
        result = self.detector.detect(query)
        self.logger.info(
            f"Detected query language: {result.detected_language.value} "
            f"(confidence: {result.confidence:.2f})"
        )
        return result

    def detect_document_language(
        self,
        document_text: str
    ) -> LanguageDetectionResult:
        """
        Detect the language of a document.

        Args:
            document_text: Document text content

        Returns:
            LanguageDetectionResult with detected language
        """
        result = self.detector.detect(document_text)
        self.logger.info(
            f"Detected document language: {result.detected_language.value} "
            f"(confidence: {result.confidence:.2f})"
        )
        return result

    def should_translate(
        self,
        source_language: LanguageCode,
        target_language: LanguageCode
    ) -> bool:
        """
        Determine if translation is needed between two languages.

        Args:
            source_language: Source language code
            target_language: Target language code

        Returns:
            True if translation is needed, False otherwise
        """
        return source_language != target_language

    def process_multilingual_query(
        self,
        query: str,
        preferred_language: Optional[LanguageCode] = None
    ) -> Dict[str, Any]:
        """
        Process a multilingual query with language detection and normalization.

        Args:
            query: User query text
            preferred_language: Optional preferred language for results

        Returns:
            Dictionary with processed query and language information
        """
        detection_result = self.detect_query_language(query)

        result = {
            "original_query": query,
            "detected_language": detection_result.detected_language.value,
            "confidence": detection_result.confidence,
            "is_supported": detection_result.is_supported,
            "preferred_language": preferred_language.value if preferred_language else None,
            "needs_translation": False,
            "processed_query": query
        }

        # Check if translation is needed
        if preferred_language and detection_result.detected_language != preferred_language:
            result["needs_translation"] = True
            # In a real implementation, you would call a translation API here
            # For now, we keep the original query
            result["processed_query"] = query

        return result

    def get_supported_languages(self) -> List[Dict[str, str]]:
        """
        Get list of supported languages.

        Returns:
            List of dictionaries with language information
        """
        return [
            {
                "code": lang.value,
                "name": lang.name.replace("_", " ").title()
            }
            for lang in LanguageCode
        ]

    def get_language_name(self, language_code: LanguageCode) -> str:
        """
        Get human-readable name for a language code.

        Args:
            language_code: Language code

        Returns:
            Human-readable language name
        """
        return language_code.name.replace("_", " ").title()

    def validate_language_code(self, code: str) -> Optional[LanguageCode]:
        """
        Validate and convert string to LanguageCode.

        Args:
            code: String language code

        Returns:
            LanguageCode if valid, None otherwise
        """
        try:
            return LanguageCode(code)
        except ValueError:
            self.logger.warning(f"Invalid language code: {code}")
            return None
