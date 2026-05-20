from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List

from trading_bot.analytics.performance import calculate_metrics, mistake_tag_counts
from trading_bot.models import Recommendation


class RecommendationEngine:
    """Suggests rule changes without applying them."""

    minimum_sample_size = 3

    def generate(self, trades: Iterable[Dict], alerts: Iterable[Dict]) -> List[Recommendation]:
        trade_rows = list(trades)
        alert_rows = list(alerts)
        recommendations: List[Recommendation] = []
        recommendations.extend(self._setup_recommendations(trade_rows))
        recommendations.extend(self._confidence_recommendations(trade_rows))
        recommendations.extend(self._mistake_recommendations(trade_rows))
        if alert_rows and not trade_rows:
            recommendations.append(
                Recommendation(
                    title="Collect outcome data before changing rules",
                    rationale="Alerts exist, but no manual trade outcomes have been logged yet.",
                    proposed_change="Keep rules unchanged and journal whether each alert was taken, ignored, won, or failed.",
                    metric="sample_size",
                    before_value=0,
                    after_value=None,
                    sample_size=0,
                    evidence_quality="insufficient",
                    overfitting_risk="high",
                )
            )
        return recommendations

    @staticmethod
    def _setup_recommendations(rows: List[Dict]) -> List[Recommendation]:
        grouped: Dict[str, List[Dict]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get("setup_type") or "unknown")].append(row)
        recs = []
        for setup_type, group in grouped.items():
            if len(group) < RecommendationEngine.minimum_sample_size:
                continue
            metrics = calculate_metrics(group)
            if metrics["expectancy"] < 0:
                recs.append(
                    Recommendation(
                        title=f"Review {setup_type} filter quality",
                        rationale=f"{setup_type} has negative expectancy across logged trades.",
                        proposed_change=(
                            f"Simulate requiring stronger confirmation or reducing score weight for {setup_type}."
                        ),
                        metric="expectancy",
                        before_value=metrics["expectancy"],
                        after_value=None,
                        sample_size=len(group),
                        evidence_quality=_evidence_quality(len(group)),
                        overfitting_risk=_overfitting_risk(len(group)),
                    )
                )
        return recs

    @staticmethod
    def _confidence_recommendations(rows: List[Dict]) -> List[Recommendation]:
        high_conf = [row for row in rows if row.get("confidence") and int(row["confidence"]) >= 90]
        if len(high_conf) < RecommendationEngine.minimum_sample_size:
            return []
        metrics = calculate_metrics(high_conf)
        if metrics["win_rate"] < 45:
            return [
                Recommendation(
                    title="Recalibrate high-confidence scores",
                    rationale="Logged 90+ confidence trades are not yet behaving like A+ setups.",
                    proposed_change="Simulate reducing confidence for weak-volume or mixed-market 90+ alerts.",
                    metric="win_rate",
                    before_value=metrics["win_rate"],
                    after_value=None,
                    sample_size=len(high_conf),
                    evidence_quality=_evidence_quality(len(high_conf)),
                    overfitting_risk=_overfitting_risk(len(high_conf)),
                )
            ]
        return []

    @staticmethod
    def _mistake_recommendations(rows: List[Dict]) -> List[Recommendation]:
        counts = mistake_tag_counts(rows)
        recs = []
        if counts.get("FOMO", 0) >= 2:
            recs.append(
                Recommendation(
                    title="Add stronger chase warning",
                    rationale="FOMO tags appear repeatedly in the journal.",
                    proposed_change="Require alert text and dashboard to flag entries taken outside the planned zone.",
                    metric="mistake_tags",
                    before_value=float(counts["FOMO"]),
                    after_value=None,
                    sample_size=counts["FOMO"],
                    evidence_quality=_evidence_quality(counts["FOMO"]),
                    overfitting_risk=_overfitting_risk(counts["FOMO"]),
                )
            )
        if counts.get("ignored stop", 0) >= 2:
            recs.append(
                Recommendation(
                    title="Tighten stop-discipline review",
                    rationale="Ignored-stop mistakes are recurring.",
                    proposed_change="Add a post-trade review prompt whenever exit is worse than invalidation.",
                    metric="mistake_tags",
                    before_value=float(counts["ignored stop"]),
                    after_value=None,
                    sample_size=counts["ignored stop"],
                    evidence_quality=_evidence_quality(counts["ignored stop"]),
                    overfitting_risk=_overfitting_risk(counts["ignored stop"]),
                )
            )
        return recs

    @staticmethod
    def simulate_score_adjustment(rows: Iterable[Dict], setup_type: str, score_delta: int) -> Dict:
        affected = [row for row in rows if row.get("setup_type") == setup_type]
        current = calculate_metrics(affected)
        simulated_taken = [
            row
            for row in affected
            if row.get("confidence") is not None and int(row["confidence"]) + score_delta >= 85
        ]
        simulated = calculate_metrics(simulated_taken)
        return {
            "current": current,
            "simulated": simulated,
            "score_delta": score_delta,
            "sample_size": len(affected),
            "evidence_quality": _evidence_quality(len(affected)),
            "overfitting_risk": _overfitting_risk(len(affected)),
        }


def _evidence_quality(sample_size: int) -> str:
    if sample_size >= 30:
        return "strong"
    if sample_size >= 10:
        return "moderate"
    if sample_size >= RecommendationEngine.minimum_sample_size:
        return "low"
    return "insufficient"


def _overfitting_risk(sample_size: int) -> str:
    if sample_size >= 30:
        return "low"
    if sample_size >= 10:
        return "medium"
    return "high"
