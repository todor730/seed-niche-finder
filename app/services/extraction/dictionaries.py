"""Curated normalization dictionaries for semantic signal cleanup."""

from __future__ import annotations

from app.services.extraction.types import SupportedSignalType

# These maps are intentionally conservative. They can later move to YAML/JSON
# without changing the normalization code path.
SIGNAL_ALIAS_MAP: dict[SupportedSignalType, dict[str, str]] = {
    SupportedSignalType.TROPE: {
        "enemy to lover": "enemies to lovers",
        "enemy to lovers": "enemies to lovers",
        "enemies to lover": "enemies to lovers",
        "friends to lover": "friends to lovers",
        "friend to lovers": "friends to lovers",
        "grumpy sunshine": "grumpy sunshine",
        "grumpy/sunshine": "grumpy sunshine",
        "grumpy x sunshine": "grumpy sunshine",
        "marriage convenience": "marriage of convenience",
    },
    SupportedSignalType.SUBGENRE: {
        "dark romances": "dark romance",
        "small town romances": "small town romance",
        "small towns romance": "small town romance",
        "small-town romance": "small town romance",
        "sports romances": "sports romance",
        "paranormal romances": "paranormal romance",
        "historical romances": "historical romance",
        "fantasy romances": "fantasy romance",
        "contemporary romances": "contemporary romance",
        "mafia romances": "mafia romance",
        "billionaire romances": "billionaire romance",
        "christian romances": "christian romance",
        "clean romances": "clean romance",
        "rom suspense": "romantic suspense",
        "self-help": "self help",
        "self help books": "self help",
    },
    SupportedSignalType.AUDIENCE: {
        "young adult": "young adults",
        "ya": "young adults",
        "ya readers": "young adults",
        "newbies": "beginners",
        "starter readers": "beginners",
    },
    SupportedSignalType.PROMISE: {},
    SupportedSignalType.TONE: {
        "feel good": "uplifting",
        "feel-good": "uplifting",
        "warm hearted": "heartfelt",
        "warm-hearted": "heartfelt",
    },
    SupportedSignalType.SETTING: {
        "small-town": "small town",
        "small towns": "small town",
        "beach-town": "beach town",
        "college-campus": "college campus",
    },
    SupportedSignalType.PROBLEM_ANGLE: {
        "burned out": "burnout",
        "burnt out": "burnout",
        "anxious": "anxiety",
        "procrastinating": "procrastination",
        "heart broken": "heartbreak",
    },
    SupportedSignalType.SOLUTION_ANGLE: {
        "workbooks": "workbook",
        "guides": "guide",
        "methods": "method",
        "frameworks": "framework",
        "systems": "system",
        "plans": "plan",
        "journals": "journal",
        "roadmaps": "roadmap",
        "check lists": "checklist",
        "check-list": "checklist",
        "step by step guide": "guide",
        "step-by-step guide": "guide",
    },
}


SAFE_SINGULAR_SUFFIXES: dict[SupportedSignalType, frozenset[str]] = {
    SupportedSignalType.TROPE: frozenset(),
    SupportedSignalType.SUBGENRE: frozenset({"romances"}),
    SupportedSignalType.AUDIENCE: frozenset(),
    SupportedSignalType.PROMISE: frozenset(),
    SupportedSignalType.TONE: frozenset(),
    SupportedSignalType.SETTING: frozenset({"towns"}),
    SupportedSignalType.PROBLEM_ANGLE: frozenset(),
    SupportedSignalType.SOLUTION_ANGLE: frozenset(
        {"workbooks", "guides", "methods", "frameworks", "systems", "plans", "journals", "roadmaps", "checklists"}
    ),
}


GENRE_SPECIFIC_SYNONYM_GROUPS: dict[str, dict[SupportedSignalType, dict[str, tuple[str, ...]]]] = {
    "romance": {
        SupportedSignalType.TROPE: {
            "enemies to lovers": ("enemy to lover", "enemy to lovers", "enemies to lover"),
            "friends to lovers": ("friends to lover", "friend to lovers"),
            "grumpy sunshine": ("grumpy/sunshine", "grumpy x sunshine"),
        },
        SupportedSignalType.SUBGENRE: {
            "small town romance": ("small-town romance", "small town romances"),
            "dark romance": ("dark romances",),
            "romantic suspense": ("rom suspense",),
        },
    },
    "nonfiction": {
        SupportedSignalType.SOLUTION_ANGLE: {
            "workbook": ("workbooks",),
            "guide": ("guides", "step-by-step guide"),
            "method": ("methods",),
            "system": ("systems",),
            "plan": ("plans",),
        },
        SupportedSignalType.PROBLEM_ANGLE: {
            "burnout": ("burned out", "burnt out"),
            "anxiety": ("anxious",),
            "procrastination": ("procrastinating",),
        },
    },
}
