from __future__ import annotations

from app.services.extraction.canonicalization import SemanticSignalNormalizer
from app.services.extraction.types import SupportedSignalType


def test_semantic_normalizer_applies_basic_cleanup_and_alias_mapping() -> None:
    normalizer = SemanticSignalNormalizer()

    result = normalizer.canonicalize(
        signal_type=SupportedSignalType.TROPE,
        value="  Enemy-to-Lovers  ",
    )

    assert result.cleaned_value == "enemy to lovers"
    assert result.normalized_value == "enemies to lovers"
    assert "alias_map" in result.applied_transforms
    assert result.safety == "safe"


def test_semantic_normalizer_collapses_safe_plural_forms() -> None:
    normalizer = SemanticSignalNormalizer()

    result = normalizer.canonicalize(
        signal_type=SupportedSignalType.SOLUTION_ANGLE,
        value="Workbooks",
    )

    assert result.normalized_value == "workbook"
    assert "safe_plural_collapse" in result.applied_transforms
    assert result.duplicate_key == "solution_angle:workbook"


def test_semantic_normalizer_performs_conservative_typo_cleanup() -> None:
    normalizer = SemanticSignalNormalizer()

    result = normalizer.canonicalize(
        signal_type=SupportedSignalType.SUBGENRE,
        value="small town romnace",
    )

    assert result.normalized_value == "small town romance"
    assert "typo_cleanup" in result.applied_transforms
    assert result.safety == "safe"


def test_semantic_normalizer_does_not_force_unsafe_merge() -> None:
    normalizer = SemanticSignalNormalizer()

    result = normalizer.canonicalize(
        signal_type=SupportedSignalType.TONE,
        value="intense and moody",
    )

    assert result.normalized_value == "intense and moody"
    assert result.applied_transforms == ()
    assert result.safety == "safe"


def test_duplicate_suppression_uses_canonical_keys() -> None:
    normalizer = SemanticSignalNormalizer()

    keys = normalizer.suppress_duplicates(
        signal_type=SupportedSignalType.SUBGENRE,
        values=["Small-Town Romance", "small town romances", "small town romnace"],
    )

    assert keys == {"subgenre:small town romance"}
