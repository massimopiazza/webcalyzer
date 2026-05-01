from __future__ import annotations

from dataclasses import dataclass
import math
import re

from webcalyzer.models import FieldKindParsing, MetParsing, ParsingProfile, UnitAlias


# Legacy hard-coded conversions; kept for backward compatibility with call
# sites that don't pass an explicit ParsingProfile.
MPH_TO_MPS = 0.44704
FT_TO_M = 0.3048
MI_TO_M = 1609.344

TEXT_TRANSLATION = str.maketrans(
    {
        "O": "0",
        "Q": "0",
        "D": "0",
        "I": "1",
        "L": "1",
        "|": "1",
        "S": "5",
        "B": "8",
        "G": "6",
    }
)


@dataclass(slots=True)
class MeasurementOption:
    raw_text: str
    raw_token: str
    raw_value: float
    unit: str
    value_si: float
    explicit_unit: bool
    variant: str


@dataclass(slots=True)
class TimedValue:
    raw_text: str
    value: float
    variant: str


def normalize_text(text: str) -> str:
    return " ".join(text.upper().replace("§", "S").replace("\u2014", "-").replace("–", "-").split())


def normalize_numeric_token(token: str) -> str:
    token = normalize_text(token)
    return token.translate(TEXT_TRANSLATION)


def _default_velocity_units() -> tuple[UnitAlias, ...]:
    return (
        UnitAlias(name="MPH", aliases=("MPH", "MPN", "MРН", "MPI", "M/H"), si_factor=MPH_TO_MPS),
    )


def _default_altitude_units() -> tuple[UnitAlias, ...]:
    return (
        UnitAlias(name="FT", aliases=("FT", "F7", "FI", "ET", "E7", "EI"), si_factor=FT_TO_M),
        UnitAlias(name="MI", aliases=("MI", "ML", "M1"), si_factor=MI_TO_M),
    )


def _default_kind_parsing(kind: str) -> FieldKindParsing:
    if kind == "velocity":
        return FieldKindParsing(units=_default_velocity_units(), default_unit="MPH")
    if kind == "altitude":
        return FieldKindParsing(
            units=_default_altitude_units(),
            default_unit="FT",
            ambiguous_default_unit="FT",
            inferred_units_with_separator=("FT", "MI"),
            inferred_units_without_separator=("FT",),
        )
    raise ValueError(f"Unsupported measurement kind: {kind}")


def _default_met_parsing() -> MetParsing:
    return MetParsing(
        timestamp_patterns=(
            r"T\s*([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?",
            r"([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?",
        )
    )


def _resolve_kind_parsing(kind: str, parsing: ParsingProfile | None) -> FieldKindParsing:
    if parsing is None:
        return _default_kind_parsing(kind)
    return parsing.kind(kind)


def _resolve_met_parsing(parsing: ParsingProfile | None) -> MetParsing:
    if parsing is None:
        return _default_met_parsing()
    return parsing.met


def detect_unit(text: str, kind: str, parsing: ParsingProfile | None = None) -> str | None:
    """Look for an explicit unit token in ``text`` for the given kind.

    The match is alias-driven: each alias is checked as a whole-word token
    (``\\b``-bounded) to avoid bleeding "M" from "MPH" into altitude
    detection or "FT" from "GIFT" into something larger. Aliases are
    tested in declaration order so a profile can encode a preferred match
    order (e.g. specific multi-letter aliases before single-letter ones).
    """

    upper = normalize_text(text)
    kind_parsing = _resolve_kind_parsing(kind, parsing)
    for unit in kind_parsing.units:
        for alias in unit.aliases:
            if not alias:
                continue
            pattern = rf"(?<![A-Z0-9]){re.escape(alias)}(?![A-Z0-9])"
            if re.search(pattern, upper):
                return unit.name
    return None


def parse_met_candidates(
    candidates: list[tuple[str, str]],
    parsing: ParsingProfile | None = None,
) -> TimedValue | None:
    best: TimedValue | None = None
    best_score = -math.inf
    for raw_text, variant in candidates:
        parsed = parse_met(raw_text, parsing=parsing)
        if parsed is None:
            continue
        score = 2 if "T" in normalize_text(raw_text) else 1
        if score > best_score:
            best_score = score
            best = TimedValue(raw_text=raw_text, value=parsed, variant=variant)
    return best


def parse_met(text: str, parsing: ParsingProfile | None = None) -> float | None:
    upper = normalize_text(text)
    upper = upper.replace(";", ":").replace(".", ":")
    upper = re.sub(r"\s*:\s*", ":", upper)
    upper = upper.replace("T ", "T")
    met_parsing = _resolve_met_parsing(parsing)
    match = None
    for pattern in met_parsing.timestamp_patterns:
        match = re.search(pattern, upper)
        if match is not None:
            break
    if match is None:
        return None
    sign_token = match.group(1) or "+"
    first = int(match.group(2))
    second = int(match.group(3))
    third = match.group(4) if match.lastindex and match.lastindex >= 4 else None
    if third is None:
        total_seconds = first * 60 + second
    else:
        total_seconds = first * 3600 + second * 60 + int(third)
    if sign_token == "-":
        total_seconds *= -1
    return float(total_seconds)


def _extract_numeric_tokens(text: str) -> list[str]:
    upper = normalize_text(text)
    raw_tokens = re.findall(r"[0-9OQDILSBG|]{1,3}(?:[,.:][0-9OQDILSBG|]{2,3})+|[0-9OQDILSBG|]{3,}", upper)
    tokens: list[str] = []
    for token in raw_tokens:
        digit_count = len(re.findall(r"[0-9]", token))
        has_separator = any(separator in token for separator in ",.:")
        if digit_count == 0:
            continue
        if not has_separator and digit_count < 3:
            continue
        tokens.append(normalize_numeric_token(token))
    return tokens


def parse_measurement_options(
    text: str,
    kind: str,
    variant: str,
    parsing: ParsingProfile | None = None,
) -> list[MeasurementOption]:
    tokens = _extract_numeric_tokens(text)
    if not tokens:
        return []

    kind_parsing = _resolve_kind_parsing(kind, parsing)
    explicit_unit = detect_unit(text, kind=kind, parsing=parsing)
    options: list[MeasurementOption] = []
    for token in tokens:
        inferred_unit_names = (
            [explicit_unit] if explicit_unit else _infer_unit_names(kind_parsing=kind_parsing, token=token)
        )
        for unit_name in inferred_unit_names:
            unit = _lookup_unit(kind_parsing, unit_name)
            if unit is None:
                continue
            raw_value = _parse_token_to_number(token=token, unit=unit, kind=kind)
            if raw_value is None:
                continue
            value_si = float(raw_value) * unit.si_factor
            options.append(
                MeasurementOption(
                    raw_text=text,
                    raw_token=token,
                    raw_value=raw_value,
                    unit=unit.name,
                    value_si=value_si,
                    explicit_unit=explicit_unit is not None,
                    variant=variant,
                )
            )
    options.sort(key=lambda item: len(item.raw_token), reverse=True)
    return options


def _lookup_unit(kind_parsing: FieldKindParsing, unit_name: str) -> UnitAlias | None:
    target = unit_name.upper()
    for unit in kind_parsing.units:
        if unit.name == target:
            return unit
    return None


def _infer_unit_names(kind_parsing: FieldKindParsing, token: str) -> list[str]:
    """Pick which unit candidates to try when the OCR text has no explicit unit.

    The candidate set is profile-driven: a feed where velocity is only ever
    MPH stays a single-option case (no false alternatives), while altitude
    keeps multiple candidates so a "000,056" reading whose unit label was
    lost in OCR noise can still be disambiguated. The
    ``ambiguous_default_unit`` is moved to the front so it wins on ties.
    """

    has_separator = any(separator in token for separator in ",.:")
    available = {unit.name for unit in kind_parsing.units}
    candidates = (
        kind_parsing.inferred_units_with_separator
        if has_separator
        else kind_parsing.inferred_units_without_separator
    )
    candidates = [name.upper() for name in candidates if name.upper() in available]
    primary = kind_parsing.ambiguous_default_unit
    if primary and primary in candidates:
        candidates = [primary] + [name for name in candidates if name != primary]
    return candidates


def _parse_token_to_number(token: str, unit: UnitAlias, kind: str) -> float | None:
    cleaned = normalize_numeric_token(token).replace(",", "").replace(".", "").replace(":", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def choose_best_measurement(
    options: list[MeasurementOption],
    kind: str,
    previous_value_si: float | None,
    previous_met_s: float | None,
    current_met_s: float | None,
) -> MeasurementOption | None:
    if not options:
        return None

    bounds = {
        "velocity": (0.0, 12000.0),
        "altitude": (-100.0, 500000.0),
    }
    max_rate = {
        "velocity": 250.0,
        "altitude": 6000.0,
    }

    lower, upper = bounds[kind]
    best: MeasurementOption | None = None
    best_score = -math.inf
    best_value: float = math.inf
    for option in options:
        if not (lower <= option.value_si <= upper):
            continue

        score = 0.0
        if option.explicit_unit:
            score += 3.0
        if option.raw_token.count(",") or option.raw_token.count(".") or option.raw_token.count(":"):
            score += 0.5

        if previous_value_si is not None and previous_met_s is not None and current_met_s is not None and current_met_s != previous_met_s:
            dt = abs(current_met_s - previous_met_s)
            rate = abs(option.value_si - previous_value_si) / dt
            if rate > 2 * max_rate[kind]:
                continue
            if rate <= max_rate[kind]:
                score += 2.0
            else:
                score -= min(5.0, rate / max_rate[kind])

        # Tie-breaker: prefer the smaller |value_si|. With no previous value,
        # ambiguous unit pairs (e.g. FT vs MI) score equally; the smaller
        # interpretation is the safer one to commit to.
        if best is None or score > best_score or (score == best_score and option.value_si < best_value):
            best = option
            best_score = score
            best_value = option.value_si
    return best
