"""Browser-first HTML report generation over persisted research data."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from html import escape
from pathlib import Path
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.db.models import Export, Opportunity, ResearchRun
from app.schemas.keyword import KeywordListItem
from app.schemas.opportunity import OpportunityListItem
from app.schemas.report import NicheOpportunitySummary, RunSummaryReport
from app.services.hypotheses import NicheHypothesisService
from app.services.shared import build_progress, build_summaries, to_keyword_list_item, to_opportunity_list_item
from app.services.summary_service import SummaryService


class HtmlReportService:
    """Generate a local HTML decision report for one research run."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        export_storage_path: str,
        summary_service: SummaryService | None = None,
        hypothesis_service: NicheHypothesisService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._summary_service = summary_service or SummaryService()
        self._hypothesis_service = hypothesis_service or NicheHypothesisService()
        export_root = Path(export_storage_path)
        self._report_storage_path = export_root.parent / "reports"
        self._report_storage_path.mkdir(parents=True, exist_ok=True)

    def generate_report(self, *, run_id: UUID) -> Path:
        """Generate one HTML report file and return its path."""
        with self._session_factory() as session:
            run = session.scalar(
                select(ResearchRun)
                .where(ResearchRun.id == run_id)
                .options(
                    selectinload(ResearchRun.keyword_candidates),
                    selectinload(ResearchRun.opportunities).selectinload(Opportunity.keyword_candidate),
                    selectinload(ResearchRun.exports),
                )
            )
            if run is None:
                raise ValueError(f"Research run {run_id} was not found.")

            summary = build_summaries(session, [run.id]).get(run.id)
            if summary is None:
                raise ValueError(f"Summary for run {run_id} was not found.")

            progress = build_progress(run, summary)
            report = self._summary_service.build_run_summary_report(session=session, run_id=run.id)
            diagnostics = self._hypothesis_service.diagnose_run(session=session, run_id=run.id)
            keywords = [to_keyword_list_item(item) for item in run.keyword_candidates]
            opportunities = [to_opportunity_list_item(item) for item in run.opportunities]
            exports = sorted(run.exports, key=lambda item: item.created_at, reverse=True)

        html = self._render_html(
            run=run,
            report=report,
            summary=summary,
            progress=progress,
            keywords=keywords,
            opportunities=opportunities,
            diagnostics=diagnostics,
            exports=exports,
        )

        file_path = self._report_path(run.seed_niche, run.id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(html, encoding="utf-8")
        return file_path

    def _report_path(self, seed_niche: str, run_id: UUID) -> Path:
        normalized_seed = re.sub(r"[^a-z0-9]+", "-", seed_niche.strip().lower()).strip("-") or "research-run"
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return self._report_storage_path / str(run_id) / f"{normalized_seed}-report-{timestamp}.html"

    def _render_html(
        self,
        *,
        run: ResearchRun,
        report: RunSummaryReport,
        summary,
        progress,
        keywords: list[KeywordListItem],
        opportunities: list[OpportunityListItem],
        diagnostics,
        exports: list[Export],
    ) -> str:
        best_balanced = report.top_niche_opportunities[0] if report.top_niche_opportunities else None
        highest_demand = self._highest_demand_but_crowded(opportunities)
        lower_comp = self._best_lower_comp_test_angle(opportunities)
        warnings = [item.message for item in report.warnings]
        missing_data = self._build_missing_data(report=report, run=run, opportunities=opportunities)
        confidence = self._confidence_label(report.depth_score.score)
        overlap_note = self._build_overlap_note(report.top_niche_opportunities)
        noisy_notes = self._build_noisy_signal_notes(report.top_niche_opportunities)
        diagnostics_summary = self._build_diagnostics_summary(diagnostics)
        anchor_summary = self._build_anchor_summary(diagnostics)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(run.seed_niche.title())} Report</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f4ee;
      --panel: #fffdf8;
      --ink: #1f2937;
      --muted: #6b7280;
      --line: #e5dccb;
      --accent: #215f48;
      --accent-soft: #dcefe6;
      --warn: #9a3412;
      --warn-soft: #ffedd5;
      --dim: #f3efe6;
      --badge: #ece7dc;
      --shadow: 0 10px 25px rgba(31, 41, 55, 0.08);
      --radius: 16px;
      --font: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--font);
      color: var(--ink);
      background: linear-gradient(180deg, #f3efe6 0%, var(--bg) 100%);
    }}
    .page {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 20px 64px;
    }}
    .hero, .card, .callout, .warning, .muted-card, .table-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }}
    .hero {{
      padding: 28px;
      margin-bottom: 20px;
    }}
    .hero h1 {{
      margin: 0 0 10px;
      font-size: 34px;
      line-height: 1.1;
    }}
    .meta-row, .stat-grid, .callout-grid, .summary-grid, .opportunity-grid, .anchor-grid {{
      display: grid;
      gap: 14px;
    }}
    .meta-row {{
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      margin-top: 14px;
    }}
    .badge {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      background: var(--badge);
      margin-right: 8px;
    }}
    .decision-banner {{
      padding: 22px;
      background: linear-gradient(135deg, var(--accent-soft), #f8fbf9);
      border: 1px solid #c7dfd3;
      border-radius: var(--radius);
      margin-bottom: 20px;
    }}
    .decision-banner h2, .section-title {{
      margin: 0 0 12px;
      font-size: 22px;
    }}
    .stat-grid {{
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    }}
    .stat {{
      padding: 16px;
      background: var(--dim);
      border-radius: 12px;
    }}
    .stat .label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 8px;
    }}
    .stat .value {{
      font-size: 24px;
      font-weight: 700;
    }}
    .callout-grid {{
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      margin: 18px 0 0;
    }}
    .callout {{
      padding: 18px;
    }}
    .callout h3 {{
      margin: 0 0 10px;
      font-size: 16px;
    }}
    .content-stack > * {{
      margin-bottom: 20px;
    }}
    .card, .table-card, .muted-card, .warning {{
      padding: 22px;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
    }}
    .opportunity-grid {{
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    }}
    .opportunity-card {{
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fff;
    }}
    .opportunity-card h3 {{
      margin: 0 0 8px;
      font-size: 18px;
    }}
    .muted {{
      color: var(--muted);
    }}
    .warning {{
      background: var(--warn-soft);
      border-color: #fdba74;
    }}
    .warning ul, .card ul, .muted-card ul, .callout ul {{
      margin: 10px 0 0 20px;
    }}
    .summary-grid {{
      grid-template-columns: 1.35fr 1fr;
    }}
    .muted-card {{
      background: #faf8f3;
      box-shadow: none;
    }}
    .anchor-grid {{
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    }}
    details {{
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px 16px;
      background: #fff;
      margin-top: 12px;
    }}
    summary {{
      cursor: pointer;
      font-weight: 700;
    }}
    code {{
      font-family: Consolas, 'Courier New', monospace;
      font-size: 12px;
      background: #f3efe6;
      padding: 2px 6px;
      border-radius: 6px;
    }}
    @media (max-width: 900px) {{
      .summary-grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <span class="badge">{escape(run.status.value)}</span>
      <span class="badge">Depth {report.depth_score.score}</span>
      <span class="badge">Confidence {escape(confidence)}</span>
      <h1>{escape(run.seed_niche.title())} Research Report</h1>
      <p class="muted">Decision-grade summary for run <code>{escape(str(run.id))}</code>.</p>
      <div class="meta-row">
        <div><strong>Generated</strong><br>{escape(report.generated_at.isoformat())}</div>
        <div><strong>Progress</strong><br>{escape(progress.current_stage or "unknown")}</div>
        <div><strong>Run Status</strong><br>{escape(run.status.value)}</div>
        <div><strong>Counts</strong><br>{summary.keyword_count} keywords / {summary.opportunity_count} opportunities</div>
        <div><strong>Exports</strong><br>{len(exports)}</div>
      </div>
    </section>

    <section class="decision-banner">
      <h2>Decision Summary</h2>
      <p>{escape(self._executive_summary(run=run, report=report, best_balanced=best_balanced, confidence=confidence))}</p>
      <div class="callout-grid">
        {self._callout_card('Best Balanced Opportunity', self._opportunity_label(best_balanced), self._opportunity_reason(best_balanced))}
        {self._callout_card('Highest Demand but Crowded', self._opportunity_label(highest_demand), self._crowded_reason(highest_demand))}
        {self._callout_card('Best Lower-Competition Test Angle', self._opportunity_label(lower_comp), self._lower_comp_reason(lower_comp))}
      </div>
    </section>

    <div class="content-stack">
      <section class="card">
        <h2 class="section-title">Run Health Snapshot</h2>
        <div class="stat-grid">
          {self._stat('Depth Score', report.depth_score.score)}
          {self._stat('Queries', f"{report.depth_score.successful_queries_count}/{report.depth_score.attempted_queries_count}")}
          {self._stat('Providers', report.depth_score.evidence_provider_count)}
          {self._stat('Items', report.depth_score.source_items_count)}
          {self._stat('Signals', report.depth_score.extracted_signals_count)}
          {self._stat('Clusters', report.depth_score.signal_clusters_count)}
          {self._stat('Hypotheses', report.depth_score.niche_hypotheses_count)}
          {self._stat('Failures', report.depth_score.provider_failures_count)}
        </div>
      </section>

      <div class="summary-grid">
        <section class="warning">
          <h2 class="section-title">Warnings</h2>
          {self._bullet_list(warnings, empty='No major warnings were surfaced for this run.')}
        </section>
        <section class="card">
          <h2 class="section-title">Confidence & Missing Data</h2>
          <p><strong>Confidence:</strong> {escape(confidence)}</p>
          {self._bullet_list(missing_data, empty='No major missing-data gaps were detected from the current persisted evidence.')}
          <p><strong>Overlap / Diversity:</strong> {escape(overlap_note)}</p>
          <p><strong>Noisy signal notes:</strong> {escape(noisy_notes)}</p>
        </section>
      </div>

      <section class="table-card">
        <h2 class="section-title">Keywords</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Keyword</th>
                <th>Status</th>
                <th>Demand</th>
                <th>Opportunity</th>
              </tr>
            </thead>
            <tbody>
              {self._keyword_rows(keywords)}
            </tbody>
          </table>
        </div>
      </section>

      <section class="card">
        <h2 class="section-title">Opportunities</h2>
        <div class="opportunity-grid">
          {''.join(self._opportunity_cards(opportunities))}
        </div>
      </section>

      <section class="card">
        <h2 class="section-title">Decision Notes</h2>
        <ul>
          <li><strong>Best balanced opportunity:</strong> {escape(self._opportunity_label(best_balanced))}</li>
          <li><strong>Highest demand but crowded:</strong> {escape(self._opportunity_label(highest_demand))}</li>
          <li><strong>Best lower-competition test angle:</strong> {escape(self._opportunity_label(lower_comp))}</li>
          <li><strong>Overlap risk:</strong> {escape(overlap_note)}</li>
          <li><strong>Noisy signal notes:</strong> {escape(noisy_notes)}</li>
        </ul>
      </section>

      <section class="muted-card">
        <h2 class="section-title">Diagnostics Summary</h2>
        <p>{escape(diagnostics_summary)}</p>
        <div class="anchor-grid">
          {''.join(self._anchor_cards(anchor_summary))}
        </div>
        <details>
          <summary>Appendix: Hypothesis Diagnostics</summary>
          {self._diagnostic_details(diagnostics)}
        </details>
      </section>

      <section class="muted-card">
        <h2 class="section-title">Export / Artifacts</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Export ID</th>
                <th>Format</th>
                <th>Scope</th>
                <th>Status</th>
                <th>File</th>
              </tr>
            </thead>
            <tbody>
              {self._export_rows(exports)}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</body>
</html>"""

    def _executive_summary(
        self,
        *,
        run: ResearchRun,
        report: RunSummaryReport,
        best_balanced: NicheOpportunitySummary | None,
        confidence: str,
    ) -> str:
        if run.status.value == "completed_no_evidence":
            return "The run completed honestly without evidence-backed niche output. Review the missing-data and warning sections before making any market decision."
        if best_balanced is None:
            return "The run completed, but no summarized opportunity rose high enough to support a confident recommendation."
        return (
            f"The strongest testable angle is {best_balanced.niche_label}. "
            f"The run finished with confidence rated {confidence.lower()} based on the persisted evidence available."
        )

    @staticmethod
    def _opportunity_label(item) -> str:
        if item is None:
            return "No clear candidate"
        if hasattr(item, "niche_label"):
            return str(item.niche_label)
        if hasattr(item, "title"):
            return str(item.title)
        return str(item)

    @staticmethod
    def _callout_card(title: str, label: str, body: str) -> str:
        return (
            f"<article class='callout'>"
            f"<h3>{escape(title)}</h3>"
            f"<p><strong>{escape(label)}</strong></p>"
            f"<p class='muted'>{escape(body)}</p>"
            f"</article>"
        )

    def _highest_demand_but_crowded(self, opportunities: list[OpportunityListItem]) -> OpportunityListItem | None:
        crowded = [item for item in opportunities if item.score_breakdown.competition_score >= 60.0]
        candidates = crowded or opportunities
        return max(candidates, key=lambda item: (item.score_breakdown.demand_score, item.score_breakdown.opportunity_score), default=None)

    def _best_lower_comp_test_angle(self, opportunities: list[OpportunityListItem]) -> OpportunityListItem | None:
        if not opportunities:
            return None
        candidates = [item for item in opportunities if item.score_breakdown.opportunity_score >= 50.0]
        ranked = candidates or opportunities
        return min(ranked, key=lambda item: (item.score_breakdown.competition_score, -item.score_breakdown.opportunity_score))

    def _opportunity_reason(self, item) -> str:
        if item is None:
            return "No strong opportunity was surfaced."
        if hasattr(item, "why_it_may_work") and item.why_it_may_work:
            return item.why_it_may_work[0]
        if hasattr(item, "summary") and item.summary:
            return str(item.summary)
        return "This is the strongest currently surfaced angle."

    def _crowded_reason(self, item) -> str:
        if item is None:
            return "No high-demand crowded angle was identified."
        if hasattr(item, "score_breakdown"):
            return f"Demand stays high, but competition is {item.score_breakdown.competition_score}."
        return "Demand looks strongest, but crowding is the key caution."

    def _lower_comp_reason(self, item) -> str:
        if item is None:
            return "No lower-competition test angle was identified."
        if hasattr(item, "score_breakdown"):
            return f"Competition is {item.score_breakdown.competition_score} with enough score strength to test."
        return "This surfaced as the most practical lower-competition test angle."

    def _build_missing_data(self, *, report: RunSummaryReport, run: ResearchRun, opportunities: list[OpportunityListItem]) -> list[str]:
        missing: list[str] = []
        if report.depth_score.evidence_provider_count == 0:
            missing.append("No provider-level evidence was captured.")
        elif report.depth_score.evidence_provider_count == 1:
            missing.append("Only one provider supplied evidence for this run.")
        if report.depth_score.breakdown.query_success_rate is None:
            missing.append("Query success rate could not be measured from the available run data.")
        if report.depth_score.provider_failures_count:
            missing.append("Some provider calls failed, so the observed market shape may be incomplete.")
        if not opportunities:
            missing.append("No final opportunities were materialized from the persisted evidence.")
        if report.depth_score.signal_clusters_count <= 3 and report.depth_score.source_items_count > 0:
            missing.append("Cluster diversity is limited, so breadth may still be understated.")
        return missing[:5]

    @staticmethod
    def _confidence_label(score: float) -> str:
        if score >= 75.0:
            return "High"
        if score >= 45.0:
            return "Medium"
        return "Low"

    def _build_overlap_note(self, summaries: list[NicheOpportunitySummary]) -> str:
        if len(summaries) <= 1:
            return "Output breadth is thin, so overlap cannot be assessed strongly."
        trope_counter: Counter[str] = Counter()
        labels: set[str] = set()
        for item in summaries:
            labels.add(item.niche_label)
            for signal in item.key_signals:
                if signal.signal_type == "trope":
                    trope_counter[signal.label] += 1
        if len(labels) != len(summaries):
            return "Some surfaced opportunities still collapse to the same visible label."
        if trope_counter:
            trope, count = trope_counter.most_common(1)[0]
            if count >= max(2, len(summaries) - 1):
                return f"Top results lean heavily on the same trope family: {trope}."
        return "Top results look materially differentiated."

    def _build_noisy_signal_notes(self, summaries: list[NicheOpportunitySummary]) -> str:
        risk_flags = {flag for item in summaries for flag in item.risk_flags}
        notes: list[str] = []
        if "generic_positioning" in risk_flags:
            notes.append("Some outputs still carry generic positioning risk.")
        if "weak_audience_definition" in risk_flags:
            notes.append("Audience clarity remains uneven across the surfaced opportunities.")
        if "public_evidence_sparse" in risk_flags:
            notes.append("Public-only evidence leaves some competition readings thin.")
        return " ".join(notes) if notes else "No major noisy-signal issue was surfaced in the top summarized opportunities."

    def _build_diagnostics_summary(self, diagnostics) -> str:
        fiction_anchor_count = len(diagnostics.fiction_anchors)
        raw_branch_count = sum(anchor.raw_branch_count for anchor in diagnostics.fiction_anchors)
        deduped_branch_count = sum(anchor.post_dedupe_branch_count for anchor in diagnostics.fiction_anchors)
        return (
            f"{fiction_anchor_count} fiction anchors were considered. "
            f"They produced {raw_branch_count} raw branches, {deduped_branch_count} post-dedupe branches, "
            f"and {diagnostics.persisted_hypothesis_count} persisted hypotheses."
        )

    def _build_anchor_summary(self, diagnostics) -> list[dict[str, str]]:
        cards: list[dict[str, str]] = []
        for anchor in diagnostics.fiction_anchors[:4]:
            cards.append(
                {
                    "title": anchor.anchor_label,
                    "body": f"{anchor.raw_branch_count} raw branches, {anchor.post_dedupe_branch_count} post-dedupe.",
                }
            )
        return cards

    @staticmethod
    def _stat(label: str, value) -> str:
        return (
            "<div class='stat'>"
            f"<span class='label'>{escape(label)}</span>"
            f"<span class='value'>{escape(str(value))}</span>"
            "</div>"
        )

    def _keyword_rows(self, keywords: list[KeywordListItem]) -> str:
        if not keywords:
            return "<tr><td colspan='4'>No final keywords were materialized.</td></tr>"
        rows = []
        for item in keywords:
            metrics = item.metrics
            rows.append(
                "<tr>"
                f"<td>{escape(item.keyword_text)}</td>"
                f"<td>{escape(str(item.status.value if hasattr(item.status, 'value') else item.status))}</td>"
                f"<td>{escape(str(metrics.demand_score if metrics.demand_score is not None else 'n/a'))}</td>"
                f"<td>{escape(str(metrics.opportunity_score if metrics.opportunity_score is not None else 'n/a'))}</td>"
                "</tr>"
            )
        return "".join(rows)

    def _opportunity_cards(self, opportunities: list[OpportunityListItem]) -> list[str]:
        if not opportunities:
            return ["<article class='opportunity-card'><h3>No opportunities</h3><p class='muted'>No final opportunities were materialized for this run.</p></article>"]
        cards: list[str] = []
        for item in opportunities[:6]:
            cards.append(
                "<article class='opportunity-card'>"
                f"<h3>{escape(item.title)}</h3>"
                f"<p>{escape(item.summary or 'No summary available.')}</p>"
                f"<p><strong>Final:</strong> {item.score_breakdown.opportunity_score} | <strong>Demand:</strong> {item.score_breakdown.demand_score} | <strong>Competition:</strong> {item.score_breakdown.competition_score}</p>"
                f"<p class='muted'>{escape(item.rationale_summary)}</p>"
                "</article>"
            )
        return cards

    def _anchor_cards(self, cards: list[dict[str, str]]) -> list[str]:
        if not cards:
            return ["<article class='callout'><h3>No anchor diagnostics</h3><p class='muted'>No anchor data was available for this run.</p></article>"]
        return [
            f"<article class='callout'><h3>{escape(card['title'])}</h3><p class='muted'>{escape(card['body'])}</p></article>"
            for card in cards
        ]

    def _diagnostic_details(self, diagnostics) -> str:
        blocks: list[str] = []
        if not diagnostics.fiction_anchors:
            return "<p class='muted'>No fiction anchor diagnostics were available.</p>"
        for anchor in diagnostics.fiction_anchors:
            candidate_lines = []
            for signal_type, candidates in anchor.candidate_components_by_type.items():
                rendered = ", ".join(
                    f"{candidate['label']} (ratio={candidate['cooccurrence_ratio']}, score={candidate['selection_score']})"
                    for candidate in candidates
                )
                candidate_lines.append(f"<li><strong>{escape(signal_type)}</strong>: {escape(rendered)}</li>")
            final_lines = []
            for branch in anchor.post_dedupe_branches:
                selected = ", ".join(f"{key}={value}" for key, value in branch.selected_components.items()) or "(none)"
                final_lines.append(
                    f"<li><strong>{escape(branch.label)}</strong> — score {branch.branch_score} — {escape(selected)}</li>"
                )
            blocks.append(
                "<div style='margin-top:14px'>"
                f"<h3 style='margin:0 0 8px'>{escape(anchor.anchor_label)}</h3>"
                f"<p class='muted'>Raw branches: {anchor.raw_branch_count} | Post-dedupe: {anchor.post_dedupe_branch_count}</p>"
                f"<ul>{''.join(candidate_lines) if candidate_lines else '<li>No candidates</li>'}</ul>"
                f"<ul>{''.join(final_lines) if final_lines else '<li>No final branches</li>'}</ul>"
                "</div>"
            )
        return "".join(blocks)

    def _export_rows(self, exports: list[Export]) -> str:
        if not exports:
            return "<tr><td colspan='5'>No exports were created for this run.</td></tr>"
        rows = []
        for export in exports[:10]:
            rows.append(
                "<tr>"
                f"<td><code>{escape(str(export.id))}</code></td>"
                f"<td>{escape(export.export_format)}</td>"
                f"<td>{escape(export.scope)}</td>"
                f"<td>{escape(export.status.value)}</td>"
                f"<td>{escape(export.file_name or export.storage_uri or '')}</td>"
                "</tr>"
            )
        return "".join(rows)

    @staticmethod
    def _bullet_list(items: list[str], *, empty: str) -> str:
        if not items:
            return f"<p class='muted'>{escape(empty)}</p>"
        return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"
