"""Suggest a heating curve coefficient from what SAT learned about the house and the floor.

The house loses H (kW/K) times the indoor-outdoor difference. The floor passes heat to the room
at about K (kW/K) times the difference between the mean water temperature and the room, learned
from settled heating burns. Together they give the flow temperature the house needs at each
outside temperature, and the coefficient whose curve comes closest to it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .heating_curve import HeatingCurve

WATER_HEAT_KJ_PER_LITRE_K = 4.186
DEFAULT_SPREAD = 5.0
# A spread this small between the water and the room is mostly sensor error
MINIMUM_DRIVE = 2.0
SMOOTHING = 0.05
MINIMUM_SAMPLES = 20
DESIGN_OUTDOOR = (-15.0, -5.0, 5.0)
COEFFICIENT_BOUNDS = (0.1, 5.0)


class CurveAdvisor:
    """Learn the floor's heat transfer and derive a heating curve coefficient."""

    def __init__(self) -> None:
        self._transfer: float | None = None
        self._samples = 0

    @property
    def transfer_kw_per_k(self) -> float | None:
        return None if self._samples < MINIMUM_SAMPLES else self._transfer

    def update(
        self, *, heat_kw: float, flow: float, return_temperature: float, indoor: float
    ) -> None:
        """Feed one sample from a settled space heating burn."""
        drive = (flow + return_temperature) / 2 - indoor
        if drive < MINIMUM_DRIVE or heat_kw <= 0:
            return

        transfer = heat_kw / drive
        self._transfer = (
            transfer
            if self._transfer is None
            else self._transfer + (transfer - self._transfer) * SMOOTHING
        )
        self._samples += 1

    def suggest(
        self,
        curve: HeatingCurve,
        *,
        heat_loss_kw_per_k: float,
        target: float,
        water_flow_lpm: float | None,
    ) -> float | None:
        transfer = self.transfer_kw_per_k
        if transfer is None or heat_loss_kw_per_k <= 0:
            return None

        coefficients: list[float] = []
        for outdoor in DESIGN_OUTDOOR:
            if curve.calculate(target, outdoor) <= 0:
                continue
            need = heat_loss_kw_per_k * (target - outdoor)
            spread = (
                need * 60 / (WATER_HEAT_KJ_PER_LITRE_K * water_flow_lpm)
                if water_flow_lpm
                else DEFAULT_SPREAD
            )
            flow = target + need / transfer + spread / 2
            coefficients.append(curve.calculate_coefficient(flow, target, outdoor))

        if not coefficients:
            return None
        low, high = COEFFICIENT_BOUNDS
        return round(min(max(sum(coefficients) / len(coefficients), low), high), 1)
