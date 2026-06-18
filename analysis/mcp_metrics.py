"""Attach Mathematics MCP-derived summary metrics to analysis reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from analysis.math_mcp import MathematicsMCPClient, MCPCallResult, batch_eval_with_fallback, statistics_with_fallback

if TYPE_CHECKING:
    from analysis.metrics import AnalysisReport


@dataclass
class MCPSummary:
    occupancy_pct: float | None
    occupancy_source: str
    avg_tariff: float | None
    avg_tariff_source: str
    tariff_stdev: float | None
    tariff_stdev_source: str
    verified_total_loss_usd: float | None
    verified_total_loss_source: str
    mcp_available: bool
    mcp_url: str
    expressions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "occupancy_pct": self.occupancy_pct,
            "occupancy_source": self.occupancy_source,
            "avg_tariff": self.avg_tariff,
            "avg_tariff_source": self.avg_tariff_source,
            "tariff_stdev": self.tariff_stdev,
            "tariff_stdev_source": self.tariff_stdev_source,
            "verified_total_loss_usd": self.verified_total_loss_usd,
            "verified_total_loss_source": self.verified_total_loss_source,
            "mcp_available": self.mcp_available,
            "mcp_url": self.mcp_url,
            "expressions": self.expressions,
        }


def enrich_report_with_mcp(
    report: "AnalysisReport",
    client: MathematicsMCPClient | None = None,
    use_mcp: bool = True,
) -> MCPSummary:
    mcp = client or MathematicsMCPClient()
    ping = mcp.ping() if use_mcp else MCPCallResult(success=False)
    active_client = mcp if use_mcp and ping.success else None

    occupancy_expr = None
    occupancy_pct, occupancy_source = None, "local"
    if report.total_available_nights > 0:
        occupancy_expr = f"{report.total_room_nights} / {report.total_available_nights} * 100"
        evaluated = batch_eval_with_fallback(active_client, [occupancy_expr])
        occupancy_pct, occupancy_source = evaluated[0]

    tariffs = report.reservations["tariff"].dropna().astype(float).tolist()
    avg_tariff, avg_tariff_source = statistics_with_fallback(active_client, tariffs, "mean")
    tariff_stdev, tariff_stdev_source = statistics_with_fallback(active_client, tariffs, "stdev")

    if report.include_availability_loss:
        loss_expr = f"{report.total_availability_loss_usd} + {report.total_pricing_loss_usd}"
    else:
        loss_expr = f"{report.total_pricing_loss_usd}"
    verified_loss, verified_loss_source = batch_eval_with_fallback(active_client, [loss_expr])[0]

    expressions = [expr for expr in [occupancy_expr, loss_expr] if expr]
    return MCPSummary(
        occupancy_pct=round(occupancy_pct, 2) if occupancy_pct is not None else None,
        occupancy_source=occupancy_source,
        avg_tariff=round(avg_tariff, 2) if avg_tariff is not None else None,
        avg_tariff_source=avg_tariff_source,
        tariff_stdev=round(tariff_stdev, 2) if tariff_stdev is not None else None,
        tariff_stdev_source=tariff_stdev_source,
        verified_total_loss_usd=round(verified_loss, 2) if verified_loss is not None else None,
        verified_total_loss_source=verified_loss_source,
        mcp_available=active_client is not None,
        mcp_url=mcp.url,
        expressions=expressions,
    )
