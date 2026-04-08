"""Normalization helpers for the rule-based extraction layer."""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")
_SEPARATOR_RE = re.compile(r"[-_/]+")
_NON_WORD_RE = re.compile(r"[^a-z0-9\s]+")
_TRAILING_FILLER_RE = re.compile(
    r"\b(?:that|who|with|using|through|without|and|or|in|on|for)\b.*$",
    re.IGNORECASE,
)


def clean_text(value: str | None) -> str:
    """Return compact whitespace-cleaned text."""
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip()


def normalize_signal_value(value: str | None) -> str:
    """Return a stable lowercase canonical label for matching and persistence."""
    cleaned = clean_text(value).lower()
    if not cleaned:
        return ""
    cleaned = _SEPARATOR_RE.sub(" ", cleaned)
    cleaned = _NON_WORD_RE.sub(" ", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def clean_capture(value: str | None, *, max_words: int = 8) -> str | None:
    """Trim regex capture groups to a stable, practical label."""
    normalized = clean_text(value)
    if not normalized:
        return None
    normalized = normalized.strip(" ,.;:()[]{}")
    normalized = _TRAILING_FILLER_RE.sub("", normalized).strip(" ,.;:()[]{}")
    if not normalized:
        return None
    tokens = normalized.split()
    if len(tokens) > max_words:
        normalized = " ".join(tokens[:max_words])
    return normalized


def build_evidence_span(
    *,
    field_name: str,
    source_text: str,
    start: int | None = None,
    end: int | None = None,
    max_length: int = 180,
) -> str | None:
    """Build a short source-text span reference for debugging and audits."""
    text = clean_text(source_text)
    if not text:
        return None

    if start is None or end is None:
        snippet = text[:max_length]
    else:
        left = max(0, start - 48)
        right = min(len(source_text), end + 48)
        snippet = clean_text(source_text[left:right])[:max_length]

    if not snippet:
        return None
    return f"{field_name}: {snippet}"


def compile_phrase_regex(phrase: str) -> re.Pattern[str]:
    """Compile a case-insensitive whole-phrase regex for one alias."""
    escaped = re.escape(clean_text(phrase))
    escaped = escaped.replace(r"\ ", r"[\s\-_\/]+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)
