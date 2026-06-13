"""
Unit tests for PII detection and redaction (app/core/pii.py).
"""

import pytest

from app.core.pii import PIIDetector, PIIMatch, _luhn_valid


# ---------------------------------------------------------------------------
# Luhn checksum
# ---------------------------------------------------------------------------

def test_luhn_valid_known_test_card():
    # Visa test number with a valid Luhn checksum.
    assert _luhn_valid("4111111111111111") is True


def test_luhn_invalid_number():
    assert _luhn_valid("4111111111111112") is False


def test_luhn_non_digits():
    assert _luhn_valid("abcd") is False


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def test_detect_email():
    matches = PIIDetector.detect("contact me at john.doe@example.com please")
    assert len(matches) == 1
    assert matches[0].type == "email"
    assert matches[0].value == "john.doe@example.com"


def test_detect_multiple_emails():
    summary = PIIDetector.summary("a@x.com and b@y.org")
    assert summary == {"email": 2}


# ---------------------------------------------------------------------------
# Credit card (Luhn-gated)
# ---------------------------------------------------------------------------

def test_detect_credit_card_valid():
    matches = PIIDetector.detect("card: 4111 1111 1111 1111")
    types = [m.type for m in matches]
    assert "credit_card" in types


def test_invalid_card_number_not_detected_as_card():
    # Fails Luhn -> must not be reported as a credit card.
    matches = PIIDetector.detect("number 1234 5678 9012 3456")
    assert all(m.type != "credit_card" for m in matches)


# ---------------------------------------------------------------------------
# SSN
# ---------------------------------------------------------------------------

def test_detect_ssn():
    matches = PIIDetector.detect("SSN 123-45-6789 on file")
    assert any(m.type == "ssn" and m.value == "123-45-6789" for m in matches)


# ---------------------------------------------------------------------------
# Phone
# ---------------------------------------------------------------------------

def test_detect_phone_international():
    matches = PIIDetector.detect("call +1 415-555-2671 today")
    assert any(m.type == "phone" for m in matches)


# ---------------------------------------------------------------------------
# IP address
# ---------------------------------------------------------------------------

def test_detect_ipv4():
    matches = PIIDetector.detect("server at 192.168.1.100 down")
    assert any(m.type == "ip_address" and m.value == "192.168.1.100" for m in matches)


def test_invalid_ipv4_not_detected():
    matches = PIIDetector.detect("value 999.999.999.999 here")
    assert all(m.type != "ip_address" for m in matches)


# ---------------------------------------------------------------------------
# has_pii / clean text
# ---------------------------------------------------------------------------

def test_has_pii_true():
    assert PIIDetector.has_pii("reach me: a@b.com") is True


def test_has_pii_false_on_clean_text():
    assert PIIDetector.has_pii("the quick brown fox jumps over the lazy dog") is False


def test_detect_empty_and_non_string():
    assert PIIDetector.detect("") == []
    assert PIIDetector.detect(None) == []


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_redact_default_type_tokens():
    redacted = PIIDetector.redact("email a@b.com or call +1 415-555-2671")
    assert "a@b.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted


def test_redact_custom_mask():
    redacted = PIIDetector.redact("ssn 123-45-6789", mask="***")
    assert "123-45-6789" not in redacted
    assert "***" in redacted


def test_redact_no_pii_returns_original():
    text = "nothing sensitive here"
    assert PIIDetector.redact(text) == text


def test_redact_preserves_surrounding_text():
    redacted = PIIDetector.redact("start a@b.com end")
    assert redacted.startswith("start ")
    assert redacted.endswith(" end")


def test_matches_are_sorted_and_non_overlapping():
    matches = PIIDetector.detect("a@b.com 192.168.0.1 c@d.com")
    starts = [m.start for m in matches]
    assert starts == sorted(starts)
    # non-overlapping
    for earlier, later in zip(matches, matches[1:]):
        assert earlier.end <= later.start
