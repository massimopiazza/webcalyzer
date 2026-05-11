from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from pint import UnitRegistry

from webcalyzer.models import FieldKindParsing


@dataclass(frozen=True, slots=True)
class TelemetryUnit:
    name: str
    pint_name: str
    si_factor: float


class TelemetryUnitRegistry:
    """Pint-backed converter for one telemetry quantity kind."""

    def __init__(self, kind: str, units: tuple[TelemetryUnit, ...]) -> None:
        self.kind = kind
        self._ureg = UnitRegistry()
        self._base_unit = _base_unit_for_kind(kind)
        self._units = {unit.name: unit for unit in units}
        for unit in units:
            self._ureg.define(f"{unit.pint_name} = {unit.si_factor:.17g} * {self._base_unit}")

    def convert_to_si(self, value: float, unit_name: str) -> float | None:
        unit = self._units.get(unit_name.upper())
        if unit is None:
            return None
        try:
            quantity = float(value) * self._ureg.Unit(unit.pint_name)
            return float(quantity.to(self._base_unit).magnitude)
        except Exception:  # noqa: BLE001
            return None


def converter_for(kind: str, kind_parsing: FieldKindParsing) -> TelemetryUnitRegistry:
    key = tuple((unit.name.upper(), float(unit.si_factor)) for unit in kind_parsing.units)
    return _converter_for_key(kind, key)


@lru_cache(maxsize=64)
def _converter_for_key(
    kind: str,
    units_key: tuple[tuple[str, float], ...],
) -> TelemetryUnitRegistry:
    units = tuple(
        TelemetryUnit(
            name=name,
            pint_name=f"webcalyzer_{_safe_unit_name(kind)}_{_safe_unit_name(name)}",
            si_factor=si_factor,
        )
        for name, si_factor in units_key
    )
    return TelemetryUnitRegistry(kind=kind, units=units)


def _base_unit_for_kind(kind: str) -> str:
    if kind == "velocity":
        return "meter / second"
    if kind == "altitude":
        return "meter"
    return "dimensionless"


def _safe_unit_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip().lower())
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "unit"
