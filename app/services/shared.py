"""Shared service-layer helpers and schema mappers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.db.models import Export, KeywordCandidate, KeywordCandidateStatus, KeywordMetrics, Opportunity, ResearchRun, TrendMetrics, User, UserStatus
from app.schemas.common import CandidateStatus, ExportFormat, ExportScope, ExportStatus, TrendDirection
from app.schemas.export import ExportResource
from app.schemas.keyword import KeywordDetails, KeywordListItem, KeywordMetrics as KeywordMetricsSchema
from app.schemas.opportunity import MarketSnapshot, OpportunityDetails, OpportunityListItem, OpportunityRationale, ScoreBreakdown
from app.schemas.research import (
    ResearchConfig,
    ResearchProgress,
    ResearchRun as ResearchRunSchema,
    ResearchRunDetails,
    ResearchRunListItem,
    ResearchRunStatus,
    ResearchRunSummary,
)

T = TypeVar("T")

ANONYMOUS_USER_ID = UUID("00000000-0000-0000-0000-000000000000")
ANONYMOUS_USER_EMAIL = "anonymous@ebook-niche-research.local"


@dataclass(slots=True)
class ListResult(Generic[T]):
    """Simple paginated list result returned by service methods."""

    items: list[T]
    total: int
    limit: int
    offset: int


def resolve_user_id(current_user: CurrentUser) -> UUID:
    """Resolve the current user identifier with an anonymous fallback."""
    return current_user.id or ANONYMOUS_USER_ID


def ensure_user(session: Session, current_user: CurrentUser) -> User:
    """Return the current user record, creating an anonymous/local fallback when needed."""
    user_id = resolve_user_id(current_user)
    user = session.get(User, user_id)
    if user is not None:
        return user

    email = current_user.email or ANONYMOUS_USER_EMAIL
    user = User(
        id=user_id,
        email=email,
        full_name="Anonymous User" if current_user.id is None else None,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    session.flush()
    return user


def build_summary(session: Session, run_id: UUID) -> ResearchRunSummary:
    """Build run-level summary counts from persisted records."""
    return build_summaries(session, [run_id]).get(run_id, ResearchRunSummary())


def build_summaries(session: Session, run_ids: list[UUID]) -> dict[UUID, ResearchRunSummary]:
    """Build run-level summary counts for many runs with aggregate queries."""
    if not run_ids:
        return {}

    keyword_rows = session.execute(
        select(
            KeywordCandidate.run_id,
            func.count(KeywordCandidate.id).label("keyword_count"),
            func.coalesce(
                func.sum(case((KeywordCandidate.status == KeywordCandidateStatus.ACCEPTED, 1), else_=0)),
                0,
            ).label("accepted_keyword_count"),
        )
        .where(KeywordCandidate.run_id.in_(run_ids))
        .group_by(KeywordCandidate.run_id)
    ).all()
    opportunity_rows = session.execute(
        select(
            Opportunity.run_id,
            func.count(Opportunity.id).label("opportunity_count"),
        )
        .where(Opportunity.run_id.in_(run_ids))
        .group_by(Opportunity.run_id)
    ).all()
    export_rows = session.execute(
        select(
            Export.run_id,
            func.count(Export.id).label("export_count"),
        )
        .where(Export.run_id.in_(run_ids))
        .group_by(Export.run_id)
    ).all()

    summaries = {run_id: ResearchRunSummary() for run_id in run_ids}
    for row in keyword_rows:
        summaries[row.run_id] = ResearchRunSummary(
            keyword_count=int(row.keyword_count or 0),
            accepted_keyword_count=int(row.accepted_keyword_count or 0),
            opportunity_count=summaries[row.run_id].opportunity_count,
            export_count=summaries[row.run_id].export_count,
        )
    for row in opportunity_rows:
        summary = summaries[row.run_id]
        summaries[row.run_id] = ResearchRunSummary(
            keyword_count=summary.keyword_count,
            accepted_keyword_count=summary.accepted_keyword_count,
            opportunity_count=int(row.opportunity_count or 0),
            export_count=summary.export_count,
        )
    for row in export_rows:
        summary = summaries[row.run_id]
        summaries[row.run_id] = ResearchRunSummary(
            keyword_count=summary.keyword_count,
            accepted_keyword_count=summary.accepted_keyword_count,
            opportunity_count=summary.opportunity_count,
            export_count=int(row.export_count or 0),
        )
    return summaries


def build_progress(run: ResearchRun, summary: ResearchRunSummary) -> ResearchProgress:
    """Derive progress payload from the research run state and stored counts."""
    total_steps = 5
    status = ResearchRunStatus(run.status.value)
    current_stage = {
        ResearchRunStatus.PENDING: "queued",
        ResearchRunStatus.RUNNING: "researching",
        ResearchRunStatus.COMPLETED: "completed",
        ResearchRunStatus.COMPLETED_NO_EVIDENCE: "completed_no_evidence",
        ResearchRunStatus.FAILED: "failed",
        ResearchRunStatus.CANCELLED: "cancelled",
    }[status]

    if status == ResearchRunStatus.COMPLETED:
        completed_steps = total_steps
        percent_complete = 100.0
        message = f"Research completed with {summary.keyword_count} keywords and {summary.opportunity_count} opportunities."
    elif status == ResearchRunStatus.COMPLETED_NO_EVIDENCE:
        completed_steps = total_steps
        percent_complete = 100.0
        detail = run.error_message or "No persisted evidence met the threshold for evidence-backed niche claims."
        message = f"Research completed without sufficient persisted evidence to support niche claims. {detail}"
    elif status == ResearchRunStatus.CANCELLED:
        completed_steps = min(total_steps, max(1, summary.keyword_count // 5))
        percent_complete = 0.0 if completed_steps == 0 else round(completed_steps / total_steps * 100, 1)
        message = "Research run cancelled."
    elif status == ResearchRunStatus.FAILED:
        completed_steps = min(total_steps - 1, max(1, summary.keyword_count // 5))
        percent_complete = round(completed_steps / total_steps * 100, 1)
        message = run.error_message or "Research run failed."
    elif status == ResearchRunStatus.RUNNING:
        completed_steps = max(1, min(total_steps - 1, summary.keyword_count // 3))
        percent_complete = round(completed_steps / total_steps * 100, 1)
        message = "Research run is collecting market signals."
    else:
        completed_steps = 0
        percent_complete = 0.0
        message = "Research run queued."

    return ResearchProgress(
        status=status,
        current_stage=current_stage,
        completed_steps=completed_steps,
        total_steps=total_steps,
        percent_complete=percent_complete,
        message=message,
        started_at=run.started_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
    )


def to_research_run(run: ResearchRun) -> ResearchRunSchema:
    """Map a research run ORM record to the base API schema."""
    return ResearchRunSchema(
        id=run.id,
        user_id=run.user_id,
        seed_niche=run.seed_niche,
        status=ResearchRunStatus(run.status.value),
        config=ResearchConfig.model_validate(run.config_json or {}),
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
    )


def to_research_run_list_item(session: Session, run: ResearchRun) -> ResearchRunListItem:
    """Map a research run ORM record to the list-item API schema."""
    return ResearchRunListItem(
        **to_research_run(run).model_dump(),
        summary=build_summary(session, run.id),
    )


def to_research_run_list_item_with_summary(run: ResearchRun, summary: ResearchRunSummary) -> ResearchRunListItem:
    """Map a research run ORM record to the list-item API schema with a precomputed summary."""
    return ResearchRunListItem(
        **to_research_run(run).model_dump(),
        summary=summary,
    )


def to_research_run_details(session: Session, run: ResearchRun) -> ResearchRunDetails:
    """Map a research run ORM record to the detailed API schema."""
    summary = build_summary(session, run.id)
    return ResearchRunDetails(
        **to_research_run(run).model_dump(),
        summary=summary,
        progress=build_progress(run, summary),
    )


def _latest_metric(rows: list[KeywordMetrics] | list[TrendMetrics]):
    """Return the most recent metrics row when present."""
    if not rows:
        return None
    return max(rows, key=lambda row: row.collected_at or row.updated_at or row.created_at)


def _trend_direction(change_30d: float | None) -> TrendDirection | None:
    """Map trend delta into a direction label."""
    if change_30d is None:
        return None
    if change_30d > 1:
        return TrendDirection.UP
    if change_30d < -1:
        return TrendDirection.DOWN
    return TrendDirection.FLAT


def to_keyword_metrics(keyword: KeywordCandidate) -> KeywordMetricsSchema:
    """Build the keyword metrics API payload from persisted related rows."""
    metrics = _latest_metric(list(keyword.keyword_metrics))
    trends = _latest_metric(list(keyword.trend_metrics))
    top_opportunity = max((opportunity.opportunity_score or 0.0 for opportunity in keyword.opportunities), default=0.0)
    search_volume = metrics.search_volume if metrics is not None else None
    demand_score = None if search_volume is None else round(min(100.0, 25.0 + search_volume / 120.0), 1)
    return KeywordMetricsSchema(
        provider_name=(metrics.provider_name if metrics is not None else None) or (trends.provider_name if trends is not None else None),
        search_volume=search_volume,
        cpc_usd=metrics.cpc_usd if metrics is not None else None,
        demand_score=demand_score,
        trend_score=trends.trend_score if trends is not None else None,
        competition_score=metrics.competition_score if metrics is not None else None,
        opportunity_score=round(top_opportunity, 1) if top_opportunity else 0.0,
        trend_change_30d=trends.trend_change_30d if trends is not None else None,
        trend_change_90d=trends.trend_change_90d if trends is not None else None,
        seasonality_score=trends.seasonality_score if trends is not None else None,
        trend_direction=_trend_direction(trends.trend_change_30d if trends is not None else None),
        collected_at=(metrics.collected_at if metrics is not None else None) or (trends.collected_at if trends is not None else None),
    )


def to_keyword_list_item(keyword: KeywordCandidate) -> KeywordListItem:
    """Map a keyword candidate ORM record to the list-item API schema."""
    return KeywordListItem(
        id=keyword.id,
        run_id=keyword.run_id,
        keyword_text=keyword.keyword_text,
        status=CandidateStatus(keyword.status.value),
        metrics=to_keyword_metrics(keyword),
        opportunity_count=len(keyword.opportunities),
        competitor_count=len(keyword.competitors),
        created_at=keyword.created_at,
        updated_at=keyword.updated_at,
    )


def to_keyword_details(keyword: KeywordCandidate) -> KeywordDetails:
    """Map a keyword candidate ORM record to the detailed API schema."""
    return KeywordDetails(
        **to_keyword_list_item(keyword).model_dump(),
        notes=keyword.notes,
    )


def _score_breakdown(opportunity: Opportunity) -> ScoreBreakdown:
    """Build the standardized opportunity score breakdown payload."""
    return ScoreBreakdown(
        demand_score=round(opportunity.demand_score or 0.0, 1),
        trend_score=round(opportunity.trend_score or 0.0, 1),
        intent_score=round(opportunity.intent_score or 0.0, 1),
        hook_score=round(opportunity.hook_score or 0.0, 1),
        monetization_score=round(opportunity.monetization_score or 0.0, 1),
        competition_score=round(opportunity.competition_score or 0.0, 1),
        opportunity_score=round(opportunity.opportunity_score or 0.0, 1),
    )


def _rationale_json(opportunity: Opportunity) -> dict[str, object]:
    """Return structured rationale data with safe defaults."""
    return dict(opportunity.rationale_json or {})


def to_opportunity_list_item(opportunity: Opportunity) -> OpportunityListItem:
    """Map an opportunity ORM record to the list-item API schema."""
    rationale = _rationale_json(opportunity)
    return OpportunityListItem(
        id=opportunity.id,
        run_id=opportunity.run_id,
        keyword_id=opportunity.keyword_candidate_id,
        keyword_text=opportunity.keyword_candidate.keyword_text,
        title=opportunity.title,
        summary=opportunity.summary,
        recommended=(opportunity.opportunity_score or 0.0) >= 70.0,
        score_breakdown=_score_breakdown(opportunity),
        rationale_summary=str(rationale.get("rationale_summary", opportunity.summary or "Promising market opportunity.")),
        positives=[str(item) for item in rationale.get("positives", [])],
        risks=[str(item) for item in rationale.get("risks", [])],
        landing_page_angles=[str(item) for item in rationale.get("landing_page_angles", [])],
        created_at=opportunity.created_at,
        updated_at=opportunity.updated_at,
    )


def to_opportunity_details(opportunity: Opportunity) -> OpportunityDetails:
    """Map an opportunity ORM record to the detailed API schema."""
    rationale = _rationale_json(opportunity)
    market_snapshot_raw = rationale.get("market_snapshot", {})
    market_snapshot = (
        MarketSnapshot.model_validate(market_snapshot_raw)
        if isinstance(market_snapshot_raw, dict) and market_snapshot_raw
        else None
    )
    return OpportunityDetails(
        **to_opportunity_list_item(opportunity).model_dump(),
        rationale=OpportunityRationale(
            rationale_summary=str(rationale.get("rationale_summary", opportunity.summary or "Promising market opportunity.")),
            positives=[str(item) for item in rationale.get("positives", [])],
            risks=[str(item) for item in rationale.get("risks", [])],
            landing_page_angles=[str(item) for item in rationale.get("landing_page_angles", [])],
        ),
        market_snapshot=market_snapshot,
    )


def to_export_resource(export: Export) -> ExportResource:
    """Map an export ORM record to the export API schema."""
    return ExportResource(
        id=export.id,
        run_id=export.run_id,
        format=ExportFormat(export.export_format),
        scope=ExportScope(export.scope),
        status=ExportStatus(export.status.value),
        file_name=export.file_name,
        storage_uri=export.storage_uri,
        download_url=export.download_url,
        created_at=export.created_at,
        updated_at=export.updated_at,
    )
