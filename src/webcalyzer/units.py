from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
import re

from pint import UnitRegistry

from webcalyzer.dimensions import (
    DIMENSION_PRESET_DISPLAY_UNITS,
    DIMENSION_PRESETS,
    DimensionExpression,
    normalize_dimension_expression,
    parse_dimension_expression,
)
from webcalyzer.models import FieldKindParsing, TelemetryQuantityDefinition


_DIMENSION_MAP = {
    "[length]": "L",
    "[mass]": "M",
    "[time]": "T",
    "[current]": "I",
    "[temperature]": "TEMP",
    "[substance]": "AMOUNT",
    "[luminosity]": "LUM",
}

_ANGLE_UNITS = {
    "rad",
    "radian",
    "radians",
    "degree",
    "degrees",
    "deg",
    "revolution",
    "revolutions",
    "rev",
    "turn",
    "turns",
}

_SOLID_ANGLE_UNITS = {"sr", "steradian", "steradians"}
_BIT_UNITS = {"bit", "bits", "byte", "bytes", "B"}
_COUNT_UNITS = {"count", "counts", "ct"}
_UNIT_IDENTIFIER_RE = re.compile(r"^[A-Za-z_%µμ]+$")

_TELEMETRY_ALIASES: dict[str, str] = {
    "KPH": "kilometer/hour",
    "KMH": "kilometer/hour",
    "KM/H": "kilometer/hour",
    "KMPH": "kilometer/hour",
    "KPS": "kilometer/second",
    "KM/S": "kilometer/second",
    "MPS": "meter/second",
    "M/S": "meter/second",
    "FPS": "foot/second",
    "FT/S": "foot/second",
    "MPH": "mile/hour",
    "M/H": "mile/hour",
    "MPN": "mile/hour",
    "MРН": "mile/hour",
    "MPI": "mile/hour",
    "G": "standard_gravity",
    "GEE": "standard_gravity",
    "GEES": "standard_gravity",
    "G'S": "standard_gravity",
    "PCT": "percent",
    "%": "percent",
}


@dataclass(frozen=True, slots=True)
class TelemetryUnit:
    name: str
    unit_expression: str


class TelemetryUnitRegistry:
    """Pint-backed converter for one telemetry quantity kind."""

    def __init__(
        self,
        *,
        units: tuple[TelemetryUnit, ...],
        output_unit: str,
        unit_aliases: dict[str, str] | None = None,
    ) -> None:
        self._ureg = _unit_registry()
        self.output_unit = _normalize_unit_expression(output_unit)
        self._units = {unit.name.upper(): unit for unit in units}
        self._aliases = _normalized_aliases(unit_aliases or {})

    def convert_to_output(self, value: float, unit_name: str) -> float | None:
        unit = self._units.get(unit_name.upper())
        if unit is None:
            return None
        return convert_value(value, unit.unit_expression, self.output_unit, aliases=self._aliases)

    def convert_expression_to_output(self, value: float, unit_expression: str) -> float | None:
        return convert_value(value, unit_expression, self.output_unit, aliases=self._aliases)

    def resolve_alias(self, text: str) -> str | None:
        return resolve_unit_alias(text, self._aliases)


def converter_for(kind: str, kind_parsing: FieldKindParsing) -> TelemetryUnitRegistry:
    output_unit = kind_parsing.output_unit or _base_unit_for_kind(kind)
    key = (
        output_unit,
        tuple((unit.name.upper(), unit.unit_expression) for unit in kind_parsing.units),
    )
    return _converter_for_key(key)


def converter_for_quantity(quantity: TelemetryQuantityDefinition) -> TelemetryUnitRegistry:
    aliases = {
        alias: target
        for alias, target in quantity.unit_aliases.items()
    }
    units = (TelemetryUnit(name="DISPLAY", unit_expression=quantity.display_unit),)
    return TelemetryUnitRegistry(
        units=units,
        output_unit=quantity.display_unit,
        unit_aliases=aliases,
    )


@lru_cache(maxsize=64)
def _converter_for_key(
    key: tuple[str, tuple[tuple[str, str], ...]],
) -> TelemetryUnitRegistry:
    output_unit, units_key = key
    return TelemetryUnitRegistry(
        units=tuple(TelemetryUnit(name=name, unit_expression=unit) for name, unit in units_key),
        output_unit=output_unit,
    )


def convert_value(
    value: float,
    from_unit: str,
    to_unit: str,
    *,
    aliases: dict[str, str] | None = None,
) -> float | None:
    try:
        ureg = _unit_registry()
        source = _unit_expression_for_pint(from_unit, aliases=aliases)
        target = _unit_expression_for_pint(to_unit, aliases=aliases)
        quantity = float(value) * ureg.parse_expression(source)
        return float(quantity.to(ureg.parse_expression(target)).magnitude)
    except Exception:  # noqa: BLE001
        return None


def validate_unit_compatible_with_dimension(unit_expression: str, dimension_expression: str) -> None:
    unit_dimension = unit_dimension_expression(unit_expression)
    expected = parse_dimension_expression(dimension_expression)
    if unit_dimension.exponents != expected.exponents:
        raise ValueError(
            f"unit {unit_expression!r} has dimension {unit_dimension.normalized()}, "
            f"expected {expected.normalized()}"
        )


def unit_dimension_expression(unit_expression: str) -> DimensionExpression:
    ureg = _unit_registry()
    pint_expression = _unit_expression_for_pint(unit_expression)
    try:
        dimensionality = (1 * ureg.parse_expression(pint_expression)).dimensionality
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid unit expression {unit_expression!r}: {exc}") from exc

    exponents: dict[str, Fraction] = {}
    for raw_key, raw_power in dimensionality.items():
        base = _DIMENSION_MAP.get(str(raw_key))
        if base is None:
            continue
        exponents[base] = exponents.get(base, Fraction(0)) + Fraction(str(raw_power))

    for base, units in (
        ("ANG", _ANGLE_UNITS),
        ("SR", _SOLID_ANGLE_UNITS),
        ("BIT", _BIT_UNITS),
        ("COUNT", _COUNT_UNITS),
    ):
        exponent = _special_unit_exponent(unit_expression, units)
        if exponent:
            exponents[base] = exponents.get(base, Fraction(0)) + exponent
            if exponents[base] == 0:
                del exponents[base]
    return DimensionExpression(exponents)


def resolve_unit_alias(text: str, aliases: dict[str, str] | None = None) -> str | None:
    normalized = _normalize_unit_text(text)
    if not normalized:
        return None
    all_aliases = {**_TELEMETRY_ALIASES, **_normalized_aliases(aliases or {})}
    return all_aliases.get(normalized)


def aliases_for_unit_expression(unit_expression: str, aliases: dict[str, str] | None = None) -> tuple[str, ...]:
    target = _normalize_unit_expression(unit_expression).casefold()
    all_aliases = {**_TELEMETRY_ALIASES, **_normalized_aliases(aliases or {})}
    return tuple(
        sorted(
            alias
            for alias, expression in all_aliases.items()
            if _normalize_unit_expression(expression).casefold() == target
        )
    )


@lru_cache(maxsize=1)
def known_unit_identifiers() -> tuple[str, ...]:
    identifiers = {
        str(name)
        for name in getattr(_unit_registry(), "_units", {}).keys()
        if str(name) and not str(name).startswith("_")
    }
    identifiers.add("dimensionless")
    return tuple(sorted(identifiers, key=lambda item: (item.lower(), item)))


def unit_suggestions(prefix: str, limit: int = 20) -> list[str]:
    prefix_clean = prefix.strip()
    prefix_norm = prefix_clean.lower()
    candidates = known_unit_identifiers()
    if not prefix_norm:
        return list(candidates[:limit])

    exact = sorted(
        [candidate for candidate in candidates if candidate.lower() == prefix_norm],
        key=lambda candidate: _unit_suggestion_sort_key(candidate, prefix_clean),
    )
    prefixed_exact, prefixed_startswith = _prefixed_unit_suggestions(
        prefix_clean,
        prefix_norm,
        limit=limit,
    )
    exact_matches = sorted(
        _unique_units([*exact, *prefixed_exact]),
        key=lambda candidate: _unit_suggestion_sort_key(candidate, prefix_clean),
    )
    startswith = [
        candidate
        for candidate in candidates
        if candidate.lower().startswith(prefix_norm) and candidate.lower() != prefix_norm
    ]
    contains = [
        candidate
        for candidate in candidates
        if prefix_norm in candidate.lower() and not candidate.lower().startswith(prefix_norm)
    ]
    return _unique_units([*exact_matches, *startswith, *prefixed_startswith, *contains])[:limit]


def typical_unit_for_dimension(dimension_expression: str) -> str:
    normalized = normalize_dimension_expression(dimension_expression)
    preset_units_by_dimension = {
        normalize_dimension_expression(expression): DIMENSION_PRESET_DISPLAY_UNITS[name]
        for name, expression in DIMENSION_PRESETS.items()
        if name in DIMENSION_PRESET_DISPLAY_UNITS
    }
    if normalized in preset_units_by_dimension:
        return preset_units_by_dimension[normalized]
    return _decomposed_si_unit(parse_dimension_expression(normalized))


@lru_cache(maxsize=1)
def _unit_registry() -> UnitRegistry:
    registry = UnitRegistry()
    try:
        registry.define("count = []")
    except Exception:  # noqa: BLE001
        pass
    return registry


@lru_cache(maxsize=1)
def _unit_prefixes() -> tuple[str, ...]:
    prefixes = {
        str(prefix)
        for prefix in getattr(_unit_registry(), "_prefixes", {}).keys()
        if str(prefix) and not str(prefix).startswith("_") and _UNIT_IDENTIFIER_RE.fullmatch(str(prefix))
    }
    return tuple(sorted(prefixes, key=lambda item: (item.lower(), item)))


@lru_cache(maxsize=1)
def _prefixable_unit_identifiers() -> tuple[str, ...]:
    return tuple(
        identifier
        for identifier in known_unit_identifiers()
        if _UNIT_IDENTIFIER_RE.fullmatch(identifier)
    )


@lru_cache(maxsize=8192)
def _is_valid_unit_identifier(identifier: str) -> bool:
    try:
        _unit_registry().parse_expression(identifier)
    except Exception:  # noqa: BLE001
        return False
    return True


def _prefixed_unit_suggestions(
    prefix_clean: str,
    prefix_norm: str,
    *,
    limit: int,
) -> tuple[list[str], list[str]]:
    exact: list[str] = []
    startswith: list[str] = []
    seen: set[str] = set()
    if not prefix_norm:
        return exact, startswith

    def add(candidate: str) -> None:
        if candidate in seen or not _is_valid_unit_identifier(candidate):
            return
        seen.add(candidate)
        if candidate.lower() == prefix_norm:
            exact.append(candidate)
        elif candidate.lower().startswith(prefix_norm):
            startswith.append(candidate)

    for unit_prefix in _unit_prefixes():
        prefix_lower = unit_prefix.lower()
        if prefix_norm.startswith(prefix_lower):
            base_query = prefix_norm[len(prefix_lower):]
        elif prefix_lower.startswith(prefix_norm):
            base_query = ""
        else:
            continue
        for unit in _prefixable_unit_identifiers():
            if base_query and not unit.lower().startswith(base_query):
                continue
            add(f"{unit_prefix}{unit}")
            if len(exact) + len(startswith) >= limit * 3:
                break

    exact.sort(key=lambda item: _unit_suggestion_sort_key(item, prefix_clean))
    startswith.sort(key=lambda item: _unit_suggestion_sort_key(item, prefix_clean))
    return exact, startswith


def _unit_suggestion_sort_key(candidate: str, query: str) -> tuple[int, int, str, str]:
    query_lower = query.lower()
    candidate_lower = candidate.lower()
    if candidate == query:
        rank = 0
    elif candidate_lower == query_lower:
        rank = 1
    elif candidate.startswith(query):
        rank = 2
    elif candidate_lower.startswith(query_lower):
        rank = 3
    else:
        rank = 4
    return rank, len(candidate), candidate_lower, candidate


def _unique_units(units: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for unit in units:
        if unit in seen:
            continue
        seen.add(unit)
        unique.append(unit)
    return unique


def _base_unit_for_kind(kind: str) -> str:
    if kind == "velocity":
        return "meter / second"
    if kind == "altitude":
        return "meter"
    return "dimensionless"


def _decomposed_si_unit(dimension: DimensionExpression) -> str:
    base_units = {
        "L": "m",
        "M": "kg",
        "T": "s",
        "I": "A",
        "TEMP": "K",
        "AMOUNT": "mol",
        "LUM": "cd",
        "ANG": "rad",
        "SR": "sr",
        "BIT": "bit",
        "COUNT": "count",
    }
    positive: list[str] = []
    negative: list[str] = []
    for base, unit in base_units.items():
        exponent = dimension.exponents.get(base, Fraction(0))
        if exponent > 0:
            positive.append(_format_unit_power(unit, exponent))
        elif exponent < 0:
            negative.append(_format_unit_power(unit, -exponent))
    numerator = "*".join(positive) if positive else "dimensionless"
    if not negative:
        return numerator
    denominator = "*".join(negative)
    if len(negative) > 1:
        denominator = f"({denominator})"
    return f"{numerator}/{denominator}" if positive else f"1/{denominator}"


def _format_unit_power(unit: str, exponent: Fraction) -> str:
    if exponent == 1:
        return unit
    if exponent.denominator == 1:
        return f"{unit}^{exponent.numerator}"
    return f"{unit}^({exponent.numerator}/{exponent.denominator})"


def _normalized_aliases(aliases: dict[str, str]) -> dict[str, str]:
    return {
        _normalize_unit_text(alias): target
        for alias, target in aliases.items()
        if _normalize_unit_text(alias)
    }


def _normalize_unit_text(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().upper())


def _normalize_unit_expression(expression: str) -> str:
    expression = expression.strip()
    if expression == "%":
        return "percent"
    return expression


def _unit_expression_for_pint(
    expression: str,
    *,
    aliases: dict[str, str] | None = None,
) -> str:
    direct = resolve_unit_alias(expression, aliases=aliases)
    if direct is not None:
        return _normalize_unit_expression(direct)
    expression = _normalize_unit_expression(expression)
    replacements = {
        "%": "percent",
        "bits": "bit",
        "bytes": "byte",
        "counts": "count",
        "ct": "count",
    }
    for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        expression = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(source)}(?![A-Za-z0-9_])", target, expression)
    return expression


def _special_unit_exponent(expression: str, units: set[str]) -> Fraction:
    normalized = expression.replace("**", "^")
    tokens = re.findall(r"([*/]?)\s*([A-Za-z%]+)\s*(?:\^\s*(\(?[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:/\d+(?:\.\d+)?)?\)?))?", normalized)
    exponent = Fraction(0)
    for operator, token, raw_power in tokens:
        token_norm = token.strip()
        if token_norm not in units:
            continue
        power = Fraction(1)
        if raw_power:
            cleaned = raw_power.strip()
            if cleaned.startswith("(") and cleaned.endswith(")"):
                cleaned = cleaned[1:-1]
            if "/" in cleaned:
                left, right = cleaned.split("/", 1)
                power = Fraction(left) / Fraction(right)
            else:
                power = Fraction(cleaned)
        if operator == "/":
            power *= -1
        exponent += power
    return exponent
