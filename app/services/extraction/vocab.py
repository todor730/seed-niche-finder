"""Controlled vocabularies and regex patterns for rule-based extraction."""

from __future__ import annotations

import re

from app.services.extraction.normalization import clean_capture
from app.services.extraction.types import KeywordRule, PatternRule, SupportedSignalType

GENERIC_AUDIENCE_VALUES = {
    "everyone",
    "anyone",
    "readers",
    "book lovers",
}

_AUDIENCE_ANCHOR_TOKENS = {
    "adults",
    "beginners",
    "caregivers",
    "couples",
    "creatives",
    "entrepreneurs",
    "leaders",
    "men",
    "moms",
    "mothers",
    "parents",
    "professionals",
    "students",
    "teens",
    "women",
    "workers",
    "ya",
}
_GENERIC_PROMISE_VALUES = {
    "creating momentum",
    "easy navigation",
    "inner peace",
    "positive change",
}
_PROMISE_ACTION_TOKENS = {
    "build",
    "create",
    "find",
    "heal",
    "improve",
    "manage",
    "overcome",
    "reduce",
    "reset",
    "stop",
    "strengthen",
}


def _clean_audience_capture(value: str) -> str | None:
    cleaned = clean_capture(value, max_words=8)
    if not cleaned:
        return None
    normalized = cleaned.lower()
    if normalized in GENERIC_AUDIENCE_VALUES:
        return None
    if not set(normalized.split()).intersection(_AUDIENCE_ANCHOR_TOKENS):
        return None
    return cleaned


def _clean_promise_capture(value: str) -> str | None:
    cleaned = clean_capture(value, max_words=10)
    if not cleaned or len(cleaned.split()) < 2:
        return None
    normalized = cleaned.lower()
    if normalized in _GENERIC_PROMISE_VALUES:
        return None
    if not set(normalized.split()).intersection(_PROMISE_ACTION_TOKENS):
        return None
    return cleaned


def _clean_solution_capture(value: str) -> str | None:
    cleaned = clean_capture(value, max_words=8)
    if not cleaned:
        return None
    tokens = cleaned.split()
    if len(tokens) >= 2:
        suffix = " ".join(tokens[-2:]).lower()
        if suffix in {"habit system", "weekly plan", "meal plan"}:
            return " ".join(tokens[-2:])
    if tokens:
        tail = tokens[-1].lower()
        if tail in {"system", "framework", "method", "plan", "workbook", "guide", "journal", "roadmap", "checklist"}:
            return " ".join(tokens[-2:]) if len(tokens) >= 2 else tokens[-1]
    return cleaned


KEYWORD_SIGNAL_RULES: dict[SupportedSignalType, tuple[KeywordRule, ...]] = {
    SupportedSignalType.TROPE: (
        KeywordRule("enemies to lovers", aliases=("enemy-to-lover", "enemy to lovers")),
        KeywordRule("friends to lovers"),
        KeywordRule("fake dating"),
        KeywordRule("second chance"),
        KeywordRule("forbidden love"),
        KeywordRule("forced proximity"),
        KeywordRule("grumpy sunshine", aliases=("grumpy/sunshine",)),
        KeywordRule("arranged marriage"),
        KeywordRule("marriage of convenience"),
        KeywordRule("opposites attract"),
    ),
    SupportedSignalType.SUBGENRE: (
        KeywordRule("dark romance"),
        KeywordRule("small town romance", aliases=("small-town romance",)),
        KeywordRule("sports romance"),
        KeywordRule("paranormal romance"),
        KeywordRule("romantic suspense"),
        KeywordRule("fantasy romance"),
        KeywordRule("historical romance"),
        KeywordRule("contemporary romance"),
        KeywordRule("mafia romance"),
        KeywordRule("billionaire romance"),
        KeywordRule("clean romance"),
        KeywordRule("christian romance"),
        KeywordRule("self help", aliases=("self-help",)),
        KeywordRule("productivity"),
        KeywordRule("personal finance"),
    ),
    SupportedSignalType.AUDIENCE: (
        KeywordRule("beginners", allowed_fields=("subtitle", "description", "category")),
        KeywordRule("busy professionals", allowed_fields=("subtitle", "description")),
        KeywordRule("women over 40", allowed_fields=("subtitle", "description", "category")),
        KeywordRule("women", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("men", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("entrepreneurs", allowed_fields=("subtitle", "description", "category")),
        KeywordRule("moms", allowed_fields=("subtitle", "description", "category")),
        KeywordRule("couples", allowed_fields=("subtitle", "description", "category")),
        KeywordRule("teens", allowed_fields=("subtitle", "description", "category")),
        KeywordRule("young adults", aliases=("young adult",), allowed_fields=("subtitle", "description", "category")),
    ),
    SupportedSignalType.TONE: (
        KeywordRule("dark"),
        KeywordRule("cozy"),
        KeywordRule("uplifting"),
        KeywordRule("heartfelt", aliases=("warm hearted", "warm-hearted")),
        KeywordRule("humorous"),
        KeywordRule("emotional"),
        KeywordRule("gritty"),
        KeywordRule("wholesome"),
        KeywordRule("suspenseful"),
        KeywordRule("steamy"),
        KeywordRule("spicy"),
        KeywordRule("sweet"),
        KeywordRule("clean"),
    ),
    SupportedSignalType.SETTING: (
        KeywordRule("small town", aliases=("small-town",)),
        KeywordRule("beach town"),
        KeywordRule("college campus"),
        KeywordRule("high school"),
        KeywordRule("workplace"),
        KeywordRule("office"),
        KeywordRule("ranch"),
        KeywordRule("mountain town"),
        KeywordRule("fae kingdom"),
        KeywordRule("royal court"),
        KeywordRule("boarding school"),
    ),
    SupportedSignalType.PROBLEM_ANGLE: (
        KeywordRule("burnout", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("anxiety", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("codependency", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("confidence", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("self confidence", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("self esteem", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("depression", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("procrastination", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("heartbreak", allowed_fields=("title", "subtitle", "description")),
        KeywordRule("grief", allowed_fields=("title", "subtitle", "description")),
        KeywordRule("insomnia", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("debt", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("stress", allowed_fields=("title", "subtitle", "description")),
        KeywordRule("clutter", allowed_fields=("title", "subtitle", "description")),
    ),
    SupportedSignalType.SOLUTION_ANGLE: (
        KeywordRule("workbook", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("journal", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("framework", allowed_fields=("subtitle", "description")),
        KeywordRule("method", allowed_fields=("subtitle", "description")),
        KeywordRule("system", allowed_fields=("subtitle", "description")),
        KeywordRule("plan", allowed_fields=("subtitle", "description")),
        KeywordRule("guide", allowed_fields=("title", "subtitle", "description", "category")),
        KeywordRule("roadmap", allowed_fields=("subtitle", "description")),
        KeywordRule("checklist", allowed_fields=("subtitle", "description")),
        KeywordRule("meal plan", allowed_fields=("title", "subtitle", "description")),
    ),
    SupportedSignalType.PROMISE: (),
}


PATTERN_SIGNAL_RULES: dict[SupportedSignalType, tuple[PatternRule, ...]] = {
    SupportedSignalType.AUDIENCE: (
        PatternRule(
            name="for_audience",
            pattern=re.compile(r"\b(?:for|perfect for|ideal for)\s+(?P<value>[A-Za-z][^.;:]{2,80})", re.IGNORECASE),
            allowed_fields=("subtitle", "description"),
            post_process=_clean_audience_capture,
        ),
    ),
    SupportedSignalType.PROMISE: (
        PatternRule(
            name="guide_to",
            pattern=re.compile(r"\b(?:guide|roadmap|playbook)\s+to\s+(?P<value>[A-Za-z][^.;:]{3,90})", re.IGNORECASE),
            allowed_fields=("title", "subtitle", "description"),
            post_process=_clean_promise_capture,
        ),
        PatternRule(
            name="how_to",
            pattern=re.compile(r"\b(?:learn|discover)\s+how\s+to\s+(?P<value>[A-Za-z][^.;:]{3,90})", re.IGNORECASE),
            allowed_fields=("subtitle", "description"),
            post_process=_clean_promise_capture,
        ),
        PatternRule(
            name="helps_you",
            pattern=re.compile(r"\bhelps?\s+(?:you|readers)\s+(?P<value>[A-Za-z][^.;:]{3,90})", re.IGNORECASE),
            allowed_fields=("description",),
            post_process=_clean_promise_capture,
        ),
        PatternRule(
            name="to_help_you",
            pattern=re.compile(r"\bto\s+help\s+(?:you|readers)\s+(?P<value>[A-Za-z][^.;:]{3,90})", re.IGNORECASE),
            allowed_fields=("description",),
            post_process=_clean_promise_capture,
        ),
    ),
    SupportedSignalType.PROBLEM_ANGLE: (
        PatternRule(
            name="problem_state",
            pattern=re.compile(
                r"\b(?:overcome|beat|coping with|dealing with|struggling with|healing from)\s+(?P<value>[A-Za-z][^.;:]{3,90})",
                re.IGNORECASE,
            ),
            allowed_fields=("title", "subtitle", "description"),
            post_process=lambda value: clean_capture(value, max_words=8),
        ),
    ),
    SupportedSignalType.SOLUTION_ANGLE: (
        PatternRule(
            name="using_method",
            pattern=re.compile(
                r"\busing\s+(?P<value>(?:a|an|the)\s+[^.;:]{1,70}?(?:system|framework|method|plan|workbook|guide|journal|roadmap))",
                re.IGNORECASE,
            ),
            allowed_fields=("description",),
            post_process=_clean_solution_capture,
        ),
        PatternRule(
            name="structured_program",
            pattern=re.compile(
                r"\b(?P<value>(?:step-by-step|30-day|7-day)\s+[^.;:]{1,70}?(?:plan|program|system|guide))",
                re.IGNORECASE,
            ),
            allowed_fields=("subtitle", "description"),
            post_process=_clean_solution_capture,
        ),
    ),
    SupportedSignalType.TROPE: (),
    SupportedSignalType.SUBGENRE: (),
    SupportedSignalType.TONE: (),
    SupportedSignalType.SETTING: (),
}
