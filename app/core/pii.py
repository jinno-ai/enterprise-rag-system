"""
PII (Personally Identifiable Information) detection and redaction.

This module provides detection and masking of common PII so that sensitive
data can be redacted before it is logged, cached, or sent to an LLM provider.

Supported PII types:
- ``email``       email addresses
- ``credit_card`` credit/debit card numbers (Luhn-validated to limit false positives)
- ``ssn``         US Social Security Numbers (``###-##-####``)
- ``phone``       phone numbers (international ``+`` prefix or US-style)
- ``ip_address``  IPv4 addresses

Detection is regex-based and intentionally conservative. It is a safety net,
not a guarantee that every possible PII representation is caught.
"""

import re
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class PIIMatch:
    """A single detected piece of PII."""
    type: str
    value: str
    start: int
    end: int


def _luhn_valid(digits: str) -> bool:
    """Return True if ``digits`` (a string of 0-9) passes the Luhn checksum."""
    if not digits.isdigit():
        return False
    total = 0
    # Process digits from right to left, doubling every second digit.
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


class PIIDetector:
    """Detect and redact common PII in free text."""

    # Order matters: more specific / structured patterns are listed first so
    # that, e.g., a credit card is not also partially matched as a phone number.
    # Each entry is (type, compiled_pattern).
    _PATTERNS = [
        ("email", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
        # Card-like sequences of 13-19 digits, optionally grouped by spaces/hyphens.
        ("credit_card", re.compile(r"(?<![\d-])(?:\d[ -]?){13,19}(?<=\d)")),
        ("ssn", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
        # International (+CC ...) or US style; requires separators or a + prefix
        # to avoid matching arbitrary long digit runs.
        (
            "phone",
            re.compile(
                r"(?<![\w.])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)|\d{2,4})(?:[\s.-]\d{2,4}){1,4}(?![\w])"
            ),
        ),
        (
            "ip_address",
            re.compile(
                r"(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)"
            ),
        ),
    ]

    @classmethod
    def detect(cls, text: str) -> List[PIIMatch]:
        """
        Detect all PII in ``text``.

        Returns a list of :class:`PIIMatch` sorted by start offset. Overlapping
        matches are resolved in favor of the earlier (and, on a tie, longer)
        match so each character belongs to at most one PII span.
        """
        if not isinstance(text, str) or not text:
            return []

        candidates: List[PIIMatch] = []
        for pii_type, pattern in cls._PATTERNS:
            for m in pattern.finditer(text):
                value = m.group()
                if pii_type == "credit_card":
                    digits = re.sub(r"\D", "", value)
                    # Require a plausible card length AND a valid Luhn checksum.
                    if not (13 <= len(digits) <= 19 and _luhn_valid(digits)):
                        continue
                candidates.append(PIIMatch(pii_type, value, m.start(), m.end()))

        # Resolve overlaps: prefer earlier start, then longer span.
        candidates.sort(key=lambda x: (x.start, -(x.end - x.start)))
        resolved: List[PIIMatch] = []
        last_end = -1
        for match in candidates:
            if match.start >= last_end:
                resolved.append(match)
                last_end = match.end
        return resolved

    @classmethod
    def has_pii(cls, text: str) -> bool:
        """Return True if any PII is detected in ``text``."""
        return len(cls.detect(text)) > 0

    @classmethod
    def summary(cls, text: str) -> Dict[str, int]:
        """Return a count of detected PII per type, e.g. ``{"email": 2}``."""
        counts: Dict[str, int] = {}
        for match in cls.detect(text):
            counts[match.type] = counts.get(match.type, 0) + 1
        return counts

    @classmethod
    def redact(cls, text: str, mask: str = None) -> str:
        """
        Return ``text`` with detected PII replaced.

        Args:
            text: input text.
            mask: replacement string. If ``None`` (default), each match is
                replaced with a type-specific token such as ``[REDACTED_EMAIL]``.
                If provided, every match is replaced with that single token.
        """
        if not isinstance(text, str) or not text:
            return text

        matches = cls.detect(text)
        if not matches:
            return text

        # Rebuild the string left-to-right, replacing each span.
        result = []
        cursor = 0
        for match in matches:
            result.append(text[cursor:match.start])
            token = mask if mask is not None else f"[REDACTED_{match.type.upper()}]"
            result.append(token)
            cursor = match.end
        result.append(text[cursor:])
        return "".join(result)
