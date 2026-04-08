"""Explainable similarity heuristics for signal clustering."""

from __future__ import annotations

from collections import Counter

from app.services.clustering.types import ClusterAssignmentReason, SimilarityDecision, SimilarityHook


def compare_labels(
    *,
    left: str,
    right: str,
    future_hook: SimilarityHook | None = None,
    signal_type: str | None = None,
) -> SimilarityDecision:
    """Return a deterministic similarity decision for two normalized labels."""
    if left == right:
        return SimilarityDecision(True, 1.0, ClusterAssignmentReason.EXACT_NORMALIZED_MATCH)

    left_tokens = left.split()
    right_tokens = right.split()
    if left_tokens and right_tokens and Counter(left_tokens) == Counter(right_tokens):
        return SimilarityDecision(True, 0.96, ClusterAssignmentReason.TOKEN_REORDER_MATCH)

    jaccard = _token_jaccard(left_tokens, right_tokens)
    if jaccard >= 0.84 and abs(len(left_tokens) - len(right_tokens)) <= 1:
        return SimilarityDecision(True, round(jaccard, 2), ClusterAssignmentReason.HIGH_TOKEN_SIMILARITY)

    if len(left_tokens) == len(right_tokens):
        distance = _levenshtein_distance(left, right)
        if distance <= 2:
            score = max(0.86, 1.0 - distance / max(len(left), len(right), 1))
            return SimilarityDecision(True, round(score, 2), ClusterAssignmentReason.SMALL_TYPO_VARIANT)

    if future_hook is not None and signal_type is not None:
        hook_score = future_hook.score(signal_type=signal_type, left=left, right=right)
        if hook_score is not None and hook_score >= 0.90:
            return SimilarityDecision(True, round(hook_score, 2), ClusterAssignmentReason.FUTURE_SIMILARITY_HOOK)

    return SimilarityDecision(False, 0.0, ClusterAssignmentReason.NEW_CLUSTER)


def _token_jaccard(left_tokens: list[str], right_tokens: list[str]) -> float:
    left_set = set(left_tokens)
    right_set = set(right_tokens)
    if not left_set or not right_set:
        return 0.0
    intersection = len(left_set & right_set)
    union = len(left_set | right_set)
    return intersection / union if union else 0.0


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            substitute_cost = previous[right_index - 1] + (left_char != right_char)
            current.append(min(insert_cost, delete_cost, substitute_cost))
        previous = current
    return previous[-1]
