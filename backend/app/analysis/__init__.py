"""Rule-based analysis: risk scoring, clustering, trends, and briefing."""

from app.analysis.clustering import detect_hotspots
from app.analysis.risk_score import compute_global_risk_score
from app.analysis.rule_briefing import generate_rule_briefing
from app.analysis.trends import detect_trend_anomalies

__all__ = [
    "compute_global_risk_score",
    "detect_hotspots",
    "detect_trend_anomalies",
    "generate_rule_briefing",
]
