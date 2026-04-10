"""Application service layer."""

from app.services.clustering import ClusteringService
from app.services.depth_score import DepthScoreService, calculate_depth_score
from app.services.extraction import RuleBasedExtractionService
from app.services.export_service import ExportService
from app.services.html_report_service import HtmlReportService
from app.services.hypotheses import NicheHypothesisService
from app.services.keyword_service import KeywordService
from app.services.marketplaces import BasePlaywrightMarketplaceAdapter, MarketplaceAdapterRegistry
from app.services.opportunity_service import OpportunityService
from app.services.research_service import ResearchService
from app.services.scoring import HypothesisRankingService, RankingCalibration
from app.services.summary_service import SummaryService

__all__ = [
    "BasePlaywrightMarketplaceAdapter",
    "ClusteringService",
    "DepthScoreService",
    "ExportService",
    "HtmlReportService",
    "HypothesisRankingService",
    "KeywordService",
    "MarketplaceAdapterRegistry",
    "NicheHypothesisService",
    "OpportunityService",
    "RankingCalibration",
    "ResearchService",
    "RuleBasedExtractionService",
    "SummaryService",
    "calculate_depth_score",
]
