from __future__ import annotations

import sys
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import create_engine_from_url
from app.services.hypotheses import NicheHypothesisService


def _print_anchor(anchor) -> None:
    print(f"- Anchor: {anchor.anchor_label} [{anchor.anchor_signal_type}]")
    print(f"  raw_branches={anchor.raw_branch_count} | post_dedupe={anchor.post_dedupe_branch_count}")
    if anchor.candidate_components_by_type:
        for signal_type, candidates in anchor.candidate_components_by_type.items():
            rendered = ", ".join(
                f"{candidate['label']} (ratio={candidate['cooccurrence_ratio']}, score={candidate['selection_score']})"
                for candidate in candidates
            )
            print(f"  candidates[{signal_type}]: {rendered}")
    else:
        print("  candidates: (none)")

    if anchor.raw_branches:
        print("  raw:")
        for branch in anchor.raw_branches:
            selected = ", ".join(f"{key}={value}" for key, value in branch.selected_components.items()) or "(none)"
            reason = branch.reject_reason_code or "accepted"
            print(f"    - {branch.label or '(no label)'} | reason={reason} | score={branch.branch_score} | {selected}")

    if anchor.post_dedupe_branches:
        print("  final:")
        for branch in anchor.post_dedupe_branches:
            selected = ", ".join(f"{key}={value}" for key, value in branch.selected_components.items()) or "(none)"
            reason = branch.reject_reason_code or "accepted"
            print(f"    - {branch.label} | reason={reason} | score={branch.branch_score} | {selected}")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python inspect_hypotheses_run.py <run_id>")
        return 1

    run_id = UUID(sys.argv[1])
    settings = get_settings()
    engine = create_engine_from_url(settings.database_url)
    service = NicheHypothesisService()

    with Session(engine) as session:
        diagnostics = service.diagnose_run(session=session, run_id=run_id)

    print(f"Run: {diagnostics.run_id}")
    print(f"Persisted hypotheses: {diagnostics.persisted_hypothesis_count}")
    if diagnostics.persisted_hypothesis_labels:
        print("Persisted labels:")
        for label in diagnostics.persisted_hypothesis_labels:
            print(f"  - {label}")

    print("")
    print("Fiction anchors:")
    if diagnostics.fiction_anchors:
        for anchor in diagnostics.fiction_anchors:
            _print_anchor(anchor)
    else:
        print("  (none)")

    if diagnostics.nonfiction_anchors:
        print("")
        print("Nonfiction anchors:")
        for anchor in diagnostics.nonfiction_anchors:
            _print_anchor(anchor)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
