"""
Query Autocorrect Service

Provides spell correction and query suggestion functionality for user queries.
This improves query quality by detecting and correcting typos before processing.
"""

import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher, get_close_matches
import re


logger = logging.getLogger(__name__)


@dataclass
class AutocorrectResult:
    """Result of autocorrection"""
    original: str
    corrected: str
    was_corrected: bool
    corrections: List[Dict[str, Any]]


class AutocorrectService:
    """
    Service for correcting spelling mistakes in user queries.

    Uses multiple strategies:
    1. Dictionary-based correction using common English words
    2. Fuzzy matching for detecting typos
    3. Domain-specific term preservation
    4. Pattern-based corrections (common misspellings)
    """

    # Common misspellings and their corrections
    COMMON_MISPELLINGS: Dict[str, str] = {
        "helo": "hello",
        "remoot": "remote",
        "remot": "remote",
        "compnay": "company",
        "comany": "company",
        "pollicy": "policy",
        "plicy": "policy",
        "emploee": "employee",
        "benfit": "benefit",
        "benifit": "benefit",
        "vacation": "vacation",
        "vaction": "vacation",
        "helath": "health",
        "insurace": "insurance",
        "insuranc": "insurance",
        "recurit": "recruit",
        "recruit": "recruit",
        "wrold": "world",
        "onboard": "onboard",
        "onbard": "onboard",
        "perfomance": "performance",
        "performace": "performance",
        "mangement": "management",
        "managment": "management",
        "documnet": "document",
        "docuent": "document",
        "procedur": "procedure",
        "procedue": "procedure",
        "guidlines": "guidelines",
        "guidline": "guideline",
        "resorces": "resources",
        "resorce": "resource",
        "trainig": "training",
        "trainin": "training",
        "developmet": "development",
        "developmnt": "development",
        "sucess": "success",
        "succes": "success",
        "communicaton": "communication",
        "comunication": "communication",
        "collaborate": "collaborate",
        "colaborate": "collaborate",
        "projec": "project",
        "projct": "project",
        "deadlin": "deadline",
        "deadine": "deadline",
        "priorit": "priority",
        "prioriy": "priority",
        "responsibilty": "responsibility",
        "responsiblity": "responsibility",
        "requirment": "requirement",
        "requirment": "requirement",
        "specification": "specification",
        "specifiction": "specification",
        "implement": "implement",
        "implemnt": "implement",
        "deploy": "deploy",
        "depoy": "deploy",
        "maintain": "maintain",
        "maintan": "maintain",
        "monotor": "monitor",
        "monior": "monitor",
        "optimze": "optimize",
        "optimise": "optimize",
        "scalabilty": "scalability",
        "scalablity": "scalability",
        "securty": "security",
        "secuity": "security",
        "authentiction": "authentication",
        "authentiction": "authentication",
        "authorzation": "authorization",
        "authorisation": "authorization",
        "database": "database",
        "databse": "database",
        "backend": "backend",
        "backnd": "backend",
        "fronend": "frontend",
        "frontnd": "frontend",
        "interface": "interface",
        "interace": "interface",
        "integraton": "integration",
        "intergration": "integration",
        "configurtion": "configuration",
        "configration": "configuration",
        "envirnment": "environment",
        "enviroment": "environment",
        "plattform": "platform",
        "platorm": "platform",
        "framewor": "framework",
        "framwork": "framework",
        "librarry": "library",
        "libray": "library",
        "dependncy": "dependency",
        "dependance": "dependency",
        "versio": "version",
        "verison": "version",
        "releas": "release",
        "relase": "release",
        "updat": "update",
        "upate": "update",
        "upgrad": "upgrade",
        "upgrde": "upgrade",
        "bugfix": "bugfix",
        "bugfi": "bugfix",
        "patch": "patch",
        "patc": "patch",
        "featur": "feature",
        "featue": "feature",
        "functon": "function",
        "functin": "function",
        "methd": "method",
        "metho": "method",
        "class": "class",
        "clas": "class",
        "objec": "object",
        "objet": "object",
        "variabl": "variable",
        "variale": "variable",
        "parametr": "parameter",
        "paramter": "parameter",
        "argumnt": "argument",
        "argment": "argument",
        "excepton": "exception",
        "excetion": "exception",
        "error": "error",
        "eror": "error",
        "warnig": "warning",
        "warnng": "warning",
        "log": "log",
        "infomation": "information",
        "informtion": "information",
        "debug": "debug",
        "debgu": "debug",
        "trace": "trace",
        "trce": "trace",
        "asert": "assert",
        "asert": "assert",
        "test": "test",
        "tst": "test",
        "mock": "mock",
        "moc": "mock",
        "stub": "stub",
        "stb": "stub",
        "fixtur": "fixture",
        "fixtue": "fixture",
        "covrage": "coverage",
        "coverag": "coverage",
        "qualty": "quality",
        "qualiy": "quality",
        "metric": "metric",
        "metrc": "metric",
        "performace": "performance",
        "performnce": "performance",
        "latenc": "latency",
        "lattency": "latency",
        "throughpu": "throughput",
        "througput": "throughput",
        "capacty": "capacity",
        "capaity": "capacity",
        "availablity": "availability",
        "availablty": "availability",
        "reliabilty": "reliability",
        "reliablty": "reliability",
        "scalabilty": "scalability",
        "scalablity": "scalability",
        "maintanabilty": "maintainability",
        "maintainabilty": "maintainability",
        "usabilty": "usability",
        "usablty": "usability",
        "accessibilty": "accessibility",
        "accessabilty": "accessibility",
    }

    # Basic English word list for correction
    BASIC_WORDS: Set[str] = {
        "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
        "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
        "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
        "or", "an", "will", "my", "one", "all", "would", "there", "their",
        "what", "so", "up", "out", "if", "about", "who", "get", "which", "go",
        "me", "when", "make", "can", "like", "time", "no", "just", "him", "know",
        "take", "people", "into", "year", "your", "good", "some", "could", "them",
        "see", "other", "than", "then", "now", "look", "only", "come", "its", "over",
        "think", "also", "back", "after", "use", "two", "how", "our", "work", "first",
        "well", "way", "even", "new", "want", "because", "any", "these", "give", "day",
        "most", "us", "is", "are", "was", "were", "been", "has", "had", "does", "did",
        "hello", "world", "what", "where", "when", "why", "how", "who", "which", "that",
        "this", "company", "policy", "remote", "work", "employee", "benefit", "health",
        "insurance", "vacation", "sick", "leave", "pay", "salary", "hour", "day", "week",
        "month", "year", "manager", "team", "department", "office", "home", "job",
        "position", "role", "responsibility", "task", "project", "deadline", "goal",
        "objective", "target", "kpi", "performance", "review", "feedback", "meeting",
        "document", "file", "report", "data", "information", "system", "process",
        "procedure", "guideline", "rule", "regulation", "compliance", "legal", "contract",
        "agreement", "terms", "condition", "requirement", "specification", "standard",
        "best", "practice", "method", "technique", "approach", "strategy", "plan",
        "schedule", "timeline", "milestone", "deliverable", "output", "result", "outcome",
    }

    def __init__(
        self,
        min_confidence: float = 0.6,
        max_corrections: int = 10,
        enable_fuzzy_matching: bool = True
    ):
        """
        Initialize autocorrect service.

        Args:
            min_confidence: Minimum confidence threshold for corrections (0.0-1.0)
            max_corrections: Maximum number of corrections to make per query
            enable_fuzzy_matching: Enable fuzzy matching for corrections
        """
        self.min_confidence = min_confidence
        self.max_corrections = max_corrections
        self.enable_fuzzy_matching = enable_fuzzy_matching
        self.domain_terms: Set[str] = set()

        # Add common technical terms
        self._initialize_domain_terms()

    def _initialize_domain_terms(self):
        """Initialize domain-specific terms that should not be corrected"""
        domain_terms = [
            "api", "aws", "azure", "gcp", "docker", "kubernetes", "python", "javascript",
            "typescript", "java", "go", "rust", "sql", "nosql", "mongodb", "postgresql",
            "mysql", "redis", "elasticsearch", "kibana", "grafana", "prometheus",
            "jenkins", "gitlab", "github", "bitbucket", "jira", "confluence", "notion",
            "slack", "teams", "zoom", "webex", "skype", "email", "calendar", "drive",
            "dropbox", "box", "sharepoint", "onedrive", "gdrive", "sheets", "docs",
            "slides", "forms", "excel", "word", "powerpoint", "outlook", "powerpoint",
            "visio", "trello", "asana", "monday", "clickup", "notion", "airtable",
            "smartsheet", "basecamp", "podio", "zoho", "salesforce", "hubspot", "zendesk",
            "intercom", "drift", "qualtrics", "surveygizmo", "typeform", "google",
            "microsoft", "amazon", "apple", "meta", "twitter", "facebook", "instagram",
            "linkedin", "youtube", "tiktok", "snapchat", "whatsapp", "telegram",
            "slack", "discord", "reddit", "quora", "medium", "wordpress", "shopify",
            "squarespace", "wix", "godaddy", "bluehost", "hostgator", "heroku",
            "vercel", "netlify", "digitalocean", "linode", "aws", "azure", "gcp",
            "pinecone", "weaviate", "faiss", "chroma", "langchain", "openai", "anthropic",
            "cohere", "huggingface", "pytorch", "tensorflow", "scikit", "numpy", "pandas",
        ]
        self.domain_terms.update(term.lower() for term in domain_terms)

    def add_domain_term(self, term: str):
        """
        Add a domain-specific term that should not be corrected.

        Args:
            term: The term to add to the domain dictionary
        """
        self.domain_terms.add(term.lower())

    def correct(self, query: str) -> AutocorrectResult:
        """
        Correct spelling mistakes in the query.

        Args:
            query: The original query string

        Returns:
            AutocorrectResult with corrections applied
        """
        try:
            logger.debug(f"Autocorrect request for query: '{query[:100]}...'")

            if not query or not query.strip():
                logger.debug("Empty query received, skipping correction")
                return AutocorrectResult(
                    original=query,
                    corrected=query,
                    was_corrected=False,
                    corrections=[]
                )

            original_query = query
            corrections = []
            words = self._tokenize(query)
            corrected_words = []

            for word in words:
                corrected_word, correction = self._correct_word(word)
                corrected_words.append(corrected_word)
                if correction:
                    corrections.append(correction)

            corrected_query = self._reconstruct_query(corrected_words, words, original_query)
            was_corrected = len(corrections) > 0

            if was_corrected:
                logger.info(
                    f"Applied {len(corrections)} corrections: '{original_query[:50]}...' -> '{corrected_query[:50]}...'",
                    extra={
                        "original_query": original_query,
                        "corrected_query": corrected_query,
                        "corrections_count": len(corrections),
                        "corrections": corrections
                    }
                )
            else:
                logger.debug(f"No corrections needed for query: '{query[:100]}...'")

            return AutocorrectResult(
                original=original_query,
                corrected=corrected_query,
                was_corrected=was_corrected,
                corrections=corrections
            )

        except Exception as e:
            logger.error(f"Autocorrect failed for query '{query[:100]}...': {e}", exc_info=True)
            # Return original query on error (graceful degradation)
            return AutocorrectResult(
                original=query,
                corrected=query,
                was_corrected=False,
                corrections=[]
            )

    def _tokenize(self, query: str) -> List[str]:
        """
        Tokenize query into words and non-word tokens.

        Preserves punctuation, numbers, and special characters.
        """
        # Split on word boundaries but keep delimiters
        tokens = []
        pattern = r'(\w+|\s+|[^\w\s])'
        matches = re.finditer(pattern, query)

        for match in matches:
            tokens.append(match.group())

        return tokens

    def _correct_word(self, word: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Correct a single word.

        Returns:
            Tuple of (corrected_word, correction_dict_or_None)
        """
        # Skip non-word tokens (spaces, punctuation, numbers-only)
        if not word.isalpha():
            return word, None

        lower_word = word.lower()

        # Check if it's a domain term (including variations)
        if self._is_domain_term(lower_word):
            return word, None

        # Check common misspellings first (highest confidence)
        if lower_word in self.COMMON_MISPELLINGS:
            corrected = self.COMMON_MISPELLINGS[lower_word]
            return self._preserve_case(word, corrected), {
                "original": word,
                "corrected": self._preserve_case(word, corrected),
                "confidence": 0.95,
                "method": "dictionary"
            }

        # Check if word is in basic dictionary
        if lower_word in self.BASIC_WORDS:
            return word, None

        # Try fuzzy matching if enabled
        if self.enable_fuzzy_matching:
            # Search in domain terms first (with fuzzy matching)
            domain_corrections = get_close_matches(
                lower_word,
                self.domain_terms,
                n=1,
                cutoff=max(0.7, self.min_confidence)  # Higher threshold for domain terms
            )

            if domain_corrections:
                corrected = domain_corrections[0]
                confidence = SequenceMatcher(None, lower_word, corrected).ratio()
                return self._preserve_case(word, corrected), {
                    "original": word,
                    "corrected": self._preserve_case(word, corrected),
                    "confidence": round(confidence, 2),
                    "method": "domain_fuzzy"
                }

            # Search in common misspellings values
            corrections = get_close_matches(
                lower_word,
                self.COMMON_MISPELLINGS.values(),
                n=1,
                cutoff=self.min_confidence
            )

            if corrections:
                corrected = corrections[0]
                confidence = SequenceMatcher(None, lower_word, corrected).ratio()
                return self._preserve_case(word, corrected), {
                    "original": word,
                    "corrected": self._preserve_case(word, corrected),
                    "confidence": round(confidence, 2),
                    "method": "fuzzy"
                }

            # Search in basic words
            corrections = get_close_matches(
                lower_word,
                self.BASIC_WORDS,
                n=1,
                cutoff=self.min_confidence
            )

            if corrections:
                corrected = corrections[0]
                confidence = SequenceMatcher(None, lower_word, corrected).ratio()
                return self._preserve_case(word, corrected), {
                    "original": word,
                    "corrected": self._preserve_case(word, corrected),
                    "confidence": round(confidence, 2),
                    "method": "fuzzy"
                }

        # No correction found
        return word, None

    def _is_domain_term(self, word: str) -> bool:
        """
        Check if word is a domain term or close variation.

        Args:
            word: The word to check (lowercase)

        Returns:
            True if word is a domain term or close variation
        """
        if word in self.domain_terms:
            return True

        # Check for close variations (only for very close matches)
        # This prevents correcting slight misspellings of domain terms
        for term in self.domain_terms:
            if len(word) > 4 and abs(len(word) - len(term)) <= 1:
                ratio = SequenceMatcher(None, word, term).ratio()
                # Only treat as domain term if very similar (90%+)
                if ratio >= 0.90:
                    return True

        return False

    def _preserve_case(self, original: str, corrected: str) -> str:
        """
        Preserve the case pattern of the original word in the correction.

        Args:
            original: The original word
            corrected: The corrected word (lowercase)

        Returns:
            Corrected word with case pattern preserved
        """
        if original.isupper():
            return corrected.upper()
        elif original[0].isupper():
            return corrected.capitalize()
        else:
            return corrected

    def _reconstruct_query(
        self,
        corrected_words: List[str],
        original_words: List[str],
        original_query: str
    ) -> str:
        """
        Reconstruct the query with corrected words.

        Preserves original spacing, punctuation, and special characters.
        """
        return ''.join(corrected_words)

    def suggest(self, query: str, max_suggestions: int = 5) -> List[str]:
        """
        Generate query suggestions based on corrections.

        Args:
            query: The original query
            max_suggestions: Maximum number of suggestions to return

        Returns:
            List of suggested query variations
        """
        result = self.correct(query)
        suggestions = []

        if result.was_corrected:
            suggestions.append(result.corrected)

        # Generate additional suggestions by trying different corrections
        words = [w for w in self._tokenize(query) if w.isalpha()]

        for word in words[:3]:  # Only check first 3 words for performance
            lower_word = word.lower()

            if lower_word in self.COMMON_MISPELLINGS:
                suggestion = query.replace(word, self.COMMON_MISPELLINGS[lower_word], 1)
                if suggestion not in suggestions:
                    suggestions.append(suggestion)

        return suggestions[:max_suggestions]
