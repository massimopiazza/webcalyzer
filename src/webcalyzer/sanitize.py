from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Callable

from rapidfuzz import fuzz, process

from webcalyzer.models import FieldKindParsing, MetParsing, ParsingProfile, TelemetryQuantityDefinition, UnitAlias
from webcalyzer.units import aliases_for_unit_expression, converter_for, converter_for_quantity, resolve_unit_alias


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

UNIT_TEXT_TRANSLATION = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "Х": "X",
        "Α": "A",
        "Β": "B",
        "Ε": "E",
        "Η": "H",
        "Κ": "K",
        "Μ": "M",
        "Ο": "O",
        "Ρ": "P",
        "Τ": "T",
        "Χ": "X",
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
    unit_source: str = "unknown"
    unit_match_text: str | None = None
    unit_match_score: float | None = None
    parse_confidence: float = 0.0
    numeric_source: str = "literal"


@dataclass(slots=True)
class MeasurementSeriesResult:
    chosen: MeasurementOption | None
    candidate_count: int
    reject_reason: str | None = None


@dataclass(slots=True)
class TimedValue:
    raw_text: str
    value: float
    variant: str


@dataclass(frozen=True, slots=True)
class UnitMatch:
    unit_name: str
    source: str
    match_text: str
    score: float


@dataclass(frozen=True, slots=True)
class NumericToken:
    token: str
    source_token: str
    source: str = "literal"


OptionFilter = Callable[[MeasurementOption, float | None], bool]


def normalize_text(text: str) -> str:
    return " ".join(text.upper().replace("§", "S").replace("\u2014", "-").replace("\u2013", "-").split())


def normalize_numeric_token(token: str) -> str:
    token = normalize_text(token)
    return token.translate(TEXT_TRANSLATION)


def _normalize_unit_text(text: str) -> str:
    return normalize_text(text).translate(UNIT_TEXT_TRANSLATION)


def _default_velocity_units() -> tuple[UnitAlias, ...]:
    return (
        UnitAlias(name="MPH", aliases=("MPH", "MPN", "MРН", "MPI", "M/H"), unit_expression="mile/hour"),
    )


_DEFAULT_MILE_ALTITUDE_ALIASES: tuple[str, ...] = (
    "MI",
    "ML",
    "M1",
    "MIL",
    "MII",
)


def _default_altitude_units() -> tuple[UnitAlias, ...]:
    return (
        UnitAlias(name="FT", aliases=("FT", "F7", "FI", "ET", "E7", "EI"), unit_expression="foot"),
        UnitAlias(
            name="MI",
            aliases=_DEFAULT_MILE_ALTITUDE_ALIASES,
            unit_expression="mile",
        ),
    )


def _default_kind_parsing(kind: str) -> FieldKindParsing:
    if kind == "velocity":
        return FieldKindParsing(units=_default_velocity_units(), default_unit="MPH", output_unit="meter/second")
    if kind == "altitude":
        return FieldKindParsing(
            units=_default_altitude_units(),
            default_unit="FT",
            ambiguous_default_unit="FT",
            inferred_units_with_separator=("FT", "MI"),
            inferred_units_without_separator=("FT",),
            output_unit="meter",
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

    match = _detect_unit_matches(text, kind=kind, parsing=parsing, include_fuzzy=False)
    return match[0].unit_name if match else None


def measurement_text_needs_unit_fallback(
    text: str,
    kind: str,
    parsing: ParsingProfile | None = None,
) -> bool:
    """Return true when OCR saw a numeric value plus an unrecognized unit token.

    This is deliberately narrower than unit alias expansion. It only flags
    measurement text that already contains a number, has no recognized unit,
    and includes a short non-ASCII unit-like token such as Cyrillic ``М``.
    """

    kind_parsing = _resolve_kind_parsing(kind, parsing)
    numeric_tokens = _extract_numeric_tokens(
        text,
        unit_suffix_tokens=_field_kind_unit_suffix_tokens(kind_parsing),
    )
    if not numeric_tokens:
        return False
    if _detect_unit_matches(text, kind=kind, parsing=parsing):
        return False
    return any(
        _is_unrecognized_unit_like_token(token)
        for token in _raw_unit_like_tokens(normalize_text(text))
    )


def _is_unrecognized_unit_like_token(token: str) -> bool:
    if len(token.replace("/", "")) > 4:
        return False
    return any(char.isalpha() and not ("A" <= char <= "Z") for char in token)


def _detect_unit_matches(
    text: str,
    kind: str,
    parsing: ParsingProfile | None = None,
    *,
    include_fuzzy: bool = True,
) -> list[UnitMatch]:
    raw_upper = normalize_text(text)
    upper = _normalize_unit_text(text)
    kind_parsing = _resolve_kind_parsing(kind, parsing)
    exact_matches = _exact_unit_matches(upper, raw_upper, kind_parsing)
    if exact_matches or not include_fuzzy:
        return exact_matches
    return _fuzzy_unit_matches(upper, kind_parsing)


def _exact_unit_matches(upper: str, raw_upper: str, kind_parsing: FieldKindParsing) -> list[UnitMatch]:
    matches: list[UnitMatch] = []
    seen: set[str] = set()
    alias_rows = sorted(
        (
            (unit.name, alias, _normalize_unit_text(alias), normalize_text(alias))
            for unit in kind_parsing.units
            for alias in unit.aliases
            if alias
        ),
        key=lambda item: len(item[2]),
        reverse=True,
    )
    for unit_name, alias, normalized_alias, raw_alias in alias_rows:
        if _unit_alias_is_single_symbol(normalized_alias):
            search_text = raw_upper
            search_alias = raw_alias
            boundary_class = r"A-ZА-Я0-9/"
        else:
            search_text = upper
            search_alias = normalized_alias
            boundary_class = r"A-Z0-9/"
        pattern = rf"(?<![{boundary_class}]){re.escape(search_alias)}(?![{boundary_class}])"
        if re.search(pattern, search_text) and unit_name not in seen:
            matches.append(
                UnitMatch(
                    unit_name=unit_name,
                    source="exact",
                    match_text=alias,
                    score=100.0,
                )
            )
            seen.add(unit_name)
    return matches


def _unit_alias_is_single_symbol(alias: str) -> bool:
    return len(re.sub(r"[^A-Z0-9]", "", alias)) <= 1


def _fuzzy_unit_matches(upper: str, kind_parsing: FieldKindParsing) -> list[UnitMatch]:
    tokens = _unit_like_tokens(upper)
    if not tokens:
        return []
    choices: dict[str, tuple[str, str]] = {}
    for unit in kind_parsing.units:
        for alias in unit.aliases:
            normalized_alias = _normalize_unit_text(alias)
            if len(normalized_alias.replace("/", "")) < 2:
                continue
            choices[normalized_alias] = (unit.name, alias)
    if not choices:
        return []

    matches: list[UnitMatch] = []
    seen: set[str] = set()
    for token in tokens:
        if len(token.replace("/", "")) < 2:
            continue
        match = process.extractOne(
            token,
            list(choices.keys()),
            scorer=fuzz.WRatio,
            score_cutoff=82,
        )
        if match is None:
            continue
        alias_text, score, _index = match
        unit_name, raw_alias = choices[alias_text]
        if unit_name in seen:
            continue
        matches.append(
            UnitMatch(
                unit_name=unit_name,
                source="fuzzy",
                match_text=token if token != alias_text else raw_alias,
                score=float(score),
            )
        )
        seen.add(unit_name)
    matches.sort(key=lambda item: item.score, reverse=True)
    return matches


def _unit_like_tokens(upper: str) -> list[str]:
    upper = _normalize_unit_text(upper)
    return _raw_unit_like_tokens(upper)


def _raw_unit_like_tokens(upper: str) -> list[str]:
    raw_tokens = re.findall(r"[A-ZА-Я]{1,8}(?:/[A-ZА-Я]{1,8})?", upper)
    stop_words = {
        "ALT",
        "ALTITUDE",
        "FORCE",
        "G",
        "GLENN",
        "NEW",
        "SPEED",
        "STAGE",
        "T",
        "VELOCITY",
    }
    return [token for token in raw_tokens if token not in stop_words]


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


def _extract_numeric_tokens(text: str, unit_suffix_tokens: tuple[str, ...] = ()) -> list[str]:
    return [token.token for token in _extract_numeric_token_options(text, unit_suffix_tokens=unit_suffix_tokens)]


def _extract_numeric_token_options(text: str, unit_suffix_tokens: tuple[str, ...] = ()) -> list[NumericToken]:
    upper = normalize_text(text)
    split_decimal_tokens = _extract_split_decimal_tokens(upper, unit_suffix_tokens=unit_suffix_tokens)
    raw_tokens = re.findall(
        r"[+-]?(?:[0-9OQDILSBG|]{1,3}(?:[,][0-9OQDILSBG|]{3})+(?:\.[0-9OQDILSBG|]+)?|[0-9OQDILSBG|]+(?:\.[0-9OQDILSBG|]+)?|\.[0-9OQDILSBG|]+)(?:[Ee][+-]?[0-9]+)?",
        upper,
    )
    tokens: list[NumericToken] = []
    seen: set[tuple[str, str]] = set()
    for candidate in split_decimal_tokens:
        key = (candidate.token, candidate.source_token)
        if key in seen:
            continue
        tokens.append(candidate)
        seen.add(key)
    for token in raw_tokens:
        digit_count = len(re.findall(r"[0-9]", token))
        has_separator = any(separator in token for separator in ",.:")
        has_ocr_letters = bool(re.search(r"[OQDILSBG|]", token))
        if digit_count == 0:
            continue
        if has_ocr_letters and not has_separator and digit_count < 3:
            continue
        normalized = normalize_numeric_token(token)
        for candidate in _numeric_token_candidates(normalized, source_token=token):
            key = (candidate.token, candidate.source_token)
            if key in seen:
                continue
            tokens.append(candidate)
            seen.add(key)
    return tokens


def _numeric_token_candidates(normalized: str, *, source_token: str) -> list[NumericToken]:
    candidates = [NumericToken(token=normalized, source_token=source_token)]
    if _plain_digits_can_have_missing_decimal(normalized):
        candidates.append(
            NumericToken(
                token=f"{normalized[:-1]}.{normalized[-1]}",
                source_token=source_token,
                source="inferred_decimal",
            )
        )
    return candidates


def _plain_digits_can_have_missing_decimal(token: str) -> bool:
    if not re.fullmatch(r"[+-]?[0-9]{2,3}", token):
        return False
    unsigned = token[1:] if token[0] in "+-" else token
    return not unsigned.startswith("0")


def _extract_split_decimal_tokens(upper: str, unit_suffix_tokens: tuple[str, ...]) -> list[NumericToken]:
    """Recover decimals when OCR inserts a word break around the point."""

    tokens: list[NumericToken] = []
    suffix_pattern = _unit_suffix_lookahead(unit_suffix_tokens)
    patterns: list[tuple[str, bool]] = [
        (
            r"(?<![A-Z0-9OQDILSBG|.])([+-]?[0-9OQDILSBG|]{1,3})\s+\.\s*([0-9OQDILSBG|]+)(?![A-Z0-9OQDILSBG|.])",
            False,
        ),
    ]
    if suffix_pattern:
        patterns.append(
            (
                r"(?<![A-Z0-9OQDILSBG|.])([+-]?[0-9OQDILSBG|]{1,3})\s+([0-9])\.?"
                + suffix_pattern,
                True,
            )
        )
    for pattern, allow_transposed in patterns:
        for match in re.finditer(pattern, upper):
            integer = normalize_numeric_token(match.group(1))
            fraction = normalize_numeric_token(match.group(2))
            if not integer or not fraction:
                continue
            if not re.search(r"[0-9]", integer) or not re.search(r"[0-9]", fraction):
                continue
            source_token = match.group(0).strip()
            tokens.append(NumericToken(token=f"{integer}.{fraction}", source_token=source_token))
            transposed = _transposed_split_decimal_token(integer=integer, fraction=fraction)
            if allow_transposed and transposed is not None:
                tokens.append(
                    NumericToken(
                        token=transposed,
                        source_token=source_token,
                        source="inferred_transposed_decimal",
                    )
                )
    return tokens


def _transposed_split_decimal_token(*, integer: str, fraction: str) -> str | None:
    sign = ""
    unsigned = integer
    if integer.startswith(("+", "-")):
        sign = integer[0]
        unsigned = integer[1:]
    if len(unsigned) != 1 or len(fraction) != 1:
        return None
    return f"{sign}{fraction}.{unsigned}"


def _unit_suffix_lookahead(unit_suffix_tokens: tuple[str, ...]) -> str:
    escaped = [
        re.escape(token)
        for token in sorted({_normalize_unit_text(token) for token in unit_suffix_tokens}, key=lambda item: (-len(item), item))
        if token
    ]
    if not escaped:
        return ""
    return rf"(?=\s*(?:(?:{'|'.join(escaped)})(?![A-Z0-9OQDILSBG|.])|$))"


def _field_kind_unit_suffix_tokens(kind_parsing: FieldKindParsing) -> tuple[str, ...]:
    tokens: list[str] = []
    for unit in kind_parsing.units:
        tokens.append(unit.name)
        tokens.extend(unit.aliases)
    return tuple(_normalize_unit_text(token) for token in tokens if _normalize_unit_text(token))


def _custom_unit_suffix_tokens(quantity: TelemetryQuantityDefinition) -> tuple[str, ...]:
    tokens = [
        quantity.display_unit,
        *quantity.unit_aliases.keys(),
        *aliases_for_unit_expression(quantity.display_unit, aliases=quantity.unit_aliases),
    ]
    return tuple(_normalize_unit_text(token) for token in tokens if _normalize_unit_text(token))


def parse_measurement_options(
    text: str,
    kind: str,
    variant: str,
    parsing: ParsingProfile | None = None,
    preferred_unit: str | None = None,
    dominant_unit: str | None = None,
) -> list[MeasurementOption]:
    kind_parsing = _resolve_kind_parsing(kind, parsing)
    tokens = _extract_numeric_token_options(text, unit_suffix_tokens=_field_kind_unit_suffix_tokens(kind_parsing))
    if not tokens:
        return []

    unit_matches = _detect_unit_matches(text, kind=kind, parsing=parsing)
    converter = converter_for(kind, kind_parsing)
    options: list[MeasurementOption] = []
    for numeric_token in tokens:
        unit_candidates = _unit_candidates_for_token(
            kind_parsing=kind_parsing,
            token=numeric_token.token,
            unit_matches=unit_matches,
            preferred_unit=preferred_unit,
            dominant_unit=dominant_unit,
        )
        for unit_name, unit_source, match_text, match_score in unit_candidates:
            unit = _lookup_unit(kind_parsing, unit_name)
            if unit is None:
                continue
            raw_value = _parse_token_to_number(token=numeric_token.token, unit=unit, kind=kind)
            if raw_value is None:
                continue
            value_si = converter.convert_to_output(float(raw_value), unit.name)
            if value_si is None:
                continue
            parse_confidence = _adjust_parse_confidence_for_numeric_source(
                _parse_confidence(unit_source, match_score),
                numeric_token.source,
            )
            options.append(
                MeasurementOption(
                    raw_text=text,
                    raw_token=numeric_token.token,
                    raw_value=raw_value,
                    unit=unit.name,
                    value_si=value_si,
                    explicit_unit=unit_source in {"exact", "fuzzy"},
                    variant=variant,
                    unit_source=unit_source,
                    unit_match_text=match_text,
                    unit_match_score=match_score,
                    parse_confidence=parse_confidence,
                    numeric_source=numeric_token.source,
                )
            )
    options.sort(key=lambda item: len(item.raw_token), reverse=True)
    return options


def _unit_candidates_for_token(
    *,
    kind_parsing: FieldKindParsing,
    token: str,
    unit_matches: list[UnitMatch],
    preferred_unit: str | None,
    dominant_unit: str | None,
) -> list[tuple[str, str, str | None, float | None]]:
    candidates: list[tuple[str, str, str | None, float | None]] = []
    seen: set[str] = set()

    def add(unit_name: str | None, source: str, match_text: str | None, match_score: float | None) -> None:
        if unit_name is None:
            return
        normalized = unit_name.upper()
        if normalized in seen:
            return
        if _lookup_unit(kind_parsing, normalized) is None:
            return
        candidates.append((normalized, source, match_text, match_score))
        seen.add(normalized)

    for match in unit_matches:
        add(match.unit_name, match.source, match.match_text, match.score)

    dominant = dominant_unit.upper() if dominant_unit else None
    preferred = preferred_unit.upper() if preferred_unit else None
    add(dominant, "inferred_dominant", None, None)
    add(preferred, "inferred_recent", None, None)

    if not unit_matches:
        for unit_name in _infer_unit_names(kind_parsing=kind_parsing, token=token):
            add(unit_name, "inferred_profile", None, None)

    return candidates


def _parse_confidence(unit_source: str, match_score: float | None) -> float:
    if unit_source == "exact":
        return 1.0
    if unit_source == "alias":
        return 1.0
    if unit_source == "fuzzy":
        return max(0.0, min(0.95, 0.55 + 0.40 * float(match_score or 0.0) / 100.0))
    if unit_source == "inferred_dominant":
        return 0.82
    if unit_source == "inferred_recent":
        return 0.78
    if unit_source == "inferred_profile":
        return 0.62
    return 0.0


def _adjust_parse_confidence_for_numeric_source(confidence: float, numeric_source: str) -> float:
    if numeric_source in {"inferred_decimal", "inferred_transposed_decimal"}:
        return max(0.0, confidence - 0.18)
    return confidence


def _lookup_unit(kind_parsing: FieldKindParsing, unit_name: str) -> UnitAlias | None:
    target = unit_name.upper()
    for unit in kind_parsing.units:
        if unit.name == target:
            return unit
    return None


def _infer_unit_names(
    kind_parsing: FieldKindParsing,
    token: str,
    preferred_unit: str | None = None,
) -> list[str]:
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
    preferred = preferred_unit.upper() if preferred_unit else None
    if preferred and preferred in available:
        candidates = [preferred] + [name for name in candidates if name != preferred]
    return candidates


def _parse_token_to_number(token: str, unit: UnitAlias, kind: str) -> float | None:
    cleaned = normalize_numeric_token(token).replace(",", "").replace(":", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_custom_measurement_options(
    text: str,
    quantity: TelemetryQuantityDefinition,
    variant: str,
    *,
    dominant_unit: str | None = None,
) -> list[MeasurementOption]:
    tokens = _extract_numeric_token_options(text, unit_suffix_tokens=_custom_unit_suffix_tokens(quantity))
    if not tokens:
        return []
    converter = converter_for_quantity(quantity)
    options: list[MeasurementOption] = []
    first_source_token: str | None = None
    for numeric_token in tokens:
        if first_source_token is None:
            first_source_token = numeric_token.source_token
        elif numeric_token.source_token != first_source_token:
            break
        raw_value = _parse_custom_token_to_number(numeric_token.token)
        if raw_value is None:
            continue
        unit_candidates = _custom_unit_candidates(
            text=text,
            source_token=numeric_token.source_token,
            quantity=quantity,
            dominant_unit=dominant_unit,
        )
        for unit_expression, unit_source, match_text in unit_candidates:
            normalized = converter.convert_expression_to_output(raw_value, unit_expression)
            if normalized is None:
                continue
            parse_confidence = _adjust_parse_confidence_for_numeric_source(
                _parse_confidence(unit_source, 100.0),
                numeric_token.source,
            )
            options.append(
                MeasurementOption(
                    raw_text=text,
                    raw_token=numeric_token.token,
                    raw_value=raw_value,
                    unit=unit_expression,
                    value_si=normalized,
                    explicit_unit=unit_source in {"exact", "alias"},
                    variant=variant,
                    unit_source=unit_source,
                    unit_match_text=match_text,
                    unit_match_score=100.0 if unit_source in {"exact", "alias"} else None,
                    parse_confidence=parse_confidence,
                    numeric_source=numeric_token.source,
                )
            )
    return _dedupe_options(options)


def resolve_custom_measurement_series(
    raw_candidates_by_sample: list[list[tuple[str, str]]],
    *,
    quantity: TelemetryQuantityDefinition,
    met_values: list[float | None],
) -> list[MeasurementSeriesResult]:
    dominant_unit = _dominant_custom_explicit_unit(raw_candidates_by_sample, quantity=quantity)
    parsed_options: list[list[MeasurementOption]] = []
    candidate_counts: list[int] = []
    for candidates in raw_candidates_by_sample:
        options: list[MeasurementOption] = []
        for text, variant in candidates:
            options.extend(
                parse_custom_measurement_options(
                    text,
                    quantity,
                    variant,
                    dominant_unit=dominant_unit,
                )
            )
        parsed_options.append(_dedupe_options(options))
        candidate_counts.append(len(options))
    chosen = _viterbi_resolve(parsed_options, kind="custom", met_values=met_values, dominant_unit=dominant_unit)
    return [
        MeasurementSeriesResult(
            chosen=option,
            candidate_count=candidate_counts[index],
            reject_reason=None if option is not None else ("no_candidates" if candidate_counts[index] == 0 else "low_confidence_or_jump"),
        )
        for index, option in enumerate(chosen)
    ]


def _parse_custom_token_to_number(token: str) -> float | None:
    cleaned = normalize_numeric_token(token).replace(",", "").replace(":", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _custom_unit_candidates(
    *,
    text: str,
    source_token: str,
    quantity: TelemetryQuantityDefinition,
    dominant_unit: str | None,
) -> list[tuple[str, str, str | None]]:
    explicit = _unit_suffix_after_token(text, source_token)
    candidates: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()

    def add(unit_expression: str | None, source: str, match_text: str | None) -> None:
        if not unit_expression:
            return
        key = unit_expression.strip()
        if not key or key.casefold() in seen:
            return
        candidates.append((key, source, match_text))
        seen.add(key.casefold())

    if explicit:
        alias = resolve_unit_alias(explicit, aliases=quantity.unit_aliases)
        add(alias or explicit, "alias" if alias else "exact", explicit)
    add(dominant_unit, "inferred_dominant", None)
    add(quantity.display_unit, "inferred_profile", None)
    return candidates


def _unit_suffix_after_token(text: str, token: str) -> str | None:
    normalized_text = _normalize_unit_text(text)
    normalized_token = normalize_numeric_token(token)
    index = normalized_text.find(normalized_token)
    if index < 0:
        return None
    suffix = normalized_text[index + len(normalized_token):].strip()
    match = re.match(r"([A-Z%/_^0-9.\-]+(?:\s*[*/]\s*[A-Z%/_^0-9.\-]+)*)", suffix)
    if match is None:
        return None
    unit_text = match.group(1).strip()
    return unit_text or None


def _dominant_custom_explicit_unit(
    raw_candidates_by_sample: list[list[tuple[str, str]]],
    *,
    quantity: TelemetryQuantityDefinition,
) -> str | None:
    counts: dict[str, int] = {}
    unit_suffix_tokens = _custom_unit_suffix_tokens(quantity)
    for candidates in raw_candidates_by_sample:
        seen_this_sample: set[str] = set()
        for text, _variant in candidates:
            tokens = _extract_numeric_token_options(text, unit_suffix_tokens=unit_suffix_tokens)
            if not tokens:
                continue
            suffix = _unit_suffix_after_token(text, tokens[0].source_token)
            if not suffix:
                continue
            seen_this_sample.add(resolve_unit_alias(suffix, aliases=quantity.unit_aliases) or suffix)
        for unit_expression in seen_this_sample:
            counts[unit_expression] = counts.get(unit_expression, 0) + 1
    if not counts:
        return None
    unit_expression, count = max(counts.items(), key=lambda item: item[1])
    return unit_expression


def choose_best_measurement(
    options: list[MeasurementOption],
    kind: str,
    previous_value_si: float | None,
    previous_met_s: float | None,
    current_met_s: float | None,
    preferred_unit: str | None = None,
) -> MeasurementOption | None:
    if not options:
        return None

    bounds = {
        "velocity": (0.0, 12000.0),
        "altitude": (-100.0, 2000000.0),
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
            score += 3.0 if option.unit_source == "exact" else 2.2
        elif preferred_unit and option.unit == preferred_unit.upper():
            score += 1.5
        score += option.parse_confidence
        if option.numeric_source in {"inferred_decimal", "inferred_transposed_decimal"}:
            score -= 0.35
        elif option.raw_token.count(",") or option.raw_token.count(".") or option.raw_token.count(":"):
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


def resolve_measurement_series(
    raw_candidates_by_sample: list[list[tuple[str, str]]],
    *,
    kind: str,
    parsing: ParsingProfile | None,
    met_values: list[float | None],
    option_filter: OptionFilter | None = None,
) -> list[MeasurementSeriesResult]:
    """Resolve OCR measurement candidates using local parses and time continuity."""

    dominant_unit = _dominant_explicit_unit(raw_candidates_by_sample, kind=kind, parsing=parsing)
    parsed_options: list[list[MeasurementOption]] = []
    candidate_counts: list[int] = []
    for candidates, met_s in zip(raw_candidates_by_sample, met_values):
        options: list[MeasurementOption] = []
        for text, variant in candidates:
            options.extend(
                parse_measurement_options(
                    text,
                    kind=kind,
                    variant=variant,
                    parsing=parsing,
                    dominant_unit=dominant_unit,
                )
            )
        if option_filter is not None:
            options = [option for option in options if option_filter(option, met_s)]
        options = _dedupe_options(options)
        parsed_options.append(options)
        candidate_counts.append(len(options))

    chosen = _viterbi_resolve(parsed_options, kind=kind, met_values=met_values, dominant_unit=dominant_unit)
    results: list[MeasurementSeriesResult] = []
    for index, option in enumerate(chosen):
        if option is None:
            reject_reason = "no_candidates" if candidate_counts[index] == 0 else "low_confidence_or_jump"
        else:
            reject_reason = None
        results.append(
            MeasurementSeriesResult(
                chosen=option,
                candidate_count=candidate_counts[index],
                reject_reason=reject_reason,
            )
        )
    return results


def _dominant_explicit_unit(
    raw_candidates_by_sample: list[list[tuple[str, str]]],
    *,
    kind: str,
    parsing: ParsingProfile | None,
) -> str | None:
    counts: dict[str, int] = {}
    for candidates in raw_candidates_by_sample:
        seen_this_sample: set[str] = set()
        for text, _variant in candidates:
            for match in _detect_unit_matches(text, kind=kind, parsing=parsing):
                if match.source == "fuzzy" and match.score < 90.0:
                    continue
                seen_this_sample.add(match.unit_name.upper())
        for unit_name in seen_this_sample:
            counts[unit_name] = counts.get(unit_name, 0) + 1
    if not counts:
        return None
    unit_name, count = max(counts.items(), key=lambda item: item[1])
    total = sum(counts.values())
    if count >= 2 and count / max(total, 1) >= 0.6:
        return unit_name
    if count >= 2 and len(counts) == 1:
        return unit_name
    return None


def _dedupe_options(options: list[MeasurementOption]) -> list[MeasurementOption]:
    best_by_key: dict[tuple[str, str], MeasurementOption] = {}
    for option in options:
        key = (option.raw_token, option.unit)
        current = best_by_key.get(key)
        if current is None or _local_option_cost(option, dominant_unit=None) < _local_option_cost(
            current,
            dominant_unit=None,
        ):
            best_by_key[key] = option
    return sorted(
        best_by_key.values(),
        key=lambda item: (
            _local_option_cost(item, dominant_unit=None),
            -len(item.raw_token),
            item.raw_token,
            item.unit,
        ),
    )


def _viterbi_resolve(
    options_by_sample: list[list[MeasurementOption]],
    *,
    kind: str,
    met_values: list[float | None],
    dominant_unit: str | None,
) -> list[MeasurementOption | None]:
    if not options_by_sample:
        return []

    effective_met_values = _effective_monotonic_met_values(met_values)
    states_by_sample: list[list[MeasurementOption | None]] = [
        [None] + options for options in options_by_sample
    ]
    costs: list[list[float]] = []
    backrefs: list[list[int | None]] = []

    first_costs = [
        _state_local_cost(state, dominant_unit=dominant_unit)
        for state in states_by_sample[0]
    ]
    costs.append(first_costs)
    backrefs.append([None for _state in states_by_sample[0]])

    for index in range(1, len(states_by_sample)):
        current_states = states_by_sample[index]
        previous_states = states_by_sample[index - 1]
        current_costs: list[float] = []
        current_backrefs: list[int | None] = []
        for state in current_states:
            best_cost = math.inf
            best_prev: int | None = None
            local_cost = _state_local_cost(state, dominant_unit=dominant_unit)
            for prev_index, prev_state in enumerate(previous_states):
                transition_cost = _transition_cost(
                    prev_state,
                    state,
                    kind=kind,
                    previous_met_s=effective_met_values[index - 1],
                    current_met_s=effective_met_values[index],
                )
                total_cost = costs[index - 1][prev_index] + local_cost + transition_cost
                if total_cost < best_cost:
                    best_cost = total_cost
                    best_prev = prev_index
            current_costs.append(best_cost)
            current_backrefs.append(best_prev)
        costs.append(current_costs)
        backrefs.append(current_backrefs)

    last_index = min(range(len(costs[-1])), key=lambda idx: costs[-1][idx])
    selected: list[MeasurementOption | None] = [None for _ in states_by_sample]
    for index in range(len(states_by_sample) - 1, -1, -1):
        selected[index] = states_by_sample[index][last_index]
        previous = backrefs[index][last_index]
        if previous is None:
            break
        last_index = previous
    return selected


def _effective_monotonic_met_values(met_values: list[float | None]) -> list[float | None]:
    finite_values = [
        float(value)
        for value in met_values
        if value is not None and math.isfinite(float(value))
    ]
    if len(finite_values) < 2:
        return met_values
    span_step = (
        (finite_values[-1] - finite_values[0]) / max(len(finite_values) - 1, 1)
        if finite_values[-1] > finite_values[0]
        else 0.0
    )
    positive_diffs = [
        right - left
        for left, right in zip(finite_values, finite_values[1:])
        if right > left
    ]
    positive_step = min(positive_diffs) if positive_diffs else 0.0
    step = min(value for value in (span_step, positive_step) if value > 0.0) if span_step > 0.0 or positive_step > 0.0 else 1.0

    effective: list[float | None] = []
    previous: float | None = None
    for value in met_values:
        if value is None or not math.isfinite(float(value)):
            next_value = None if previous is None else previous + step
        else:
            raw_value = float(value)
            next_value = raw_value if previous is None or raw_value > previous else previous + step
        effective.append(next_value)
        if next_value is not None:
            previous = next_value
    return effective


def _state_local_cost(option: MeasurementOption | None, *, dominant_unit: str | None) -> float:
    if option is None:
        return 2.8
    return _local_option_cost(option, dominant_unit=dominant_unit)


def _local_option_cost(option: MeasurementOption, *, dominant_unit: str | None) -> float:
    source_cost = {
        "exact": 0.15,
        "alias": 0.15,
        "fuzzy": 0.75 + (100.0 - float(option.unit_match_score or 0.0)) / 25.0,
        "inferred_dominant": 0.95,
        "inferred_recent": 1.15,
        "inferred_profile": 1.9,
    }.get(option.unit_source, 2.5)
    if dominant_unit and option.unit != dominant_unit.upper():
        source_cost += 0.45
    if option.numeric_source in {"inferred_decimal", "inferred_transposed_decimal"}:
        source_cost += 0.25
    return source_cost


def _transition_cost(
    previous: MeasurementOption | None,
    current: MeasurementOption | None,
    *,
    kind: str,
    previous_met_s: float | None,
    current_met_s: float | None,
) -> float:
    if previous is None and current is None:
        return 0.15
    if previous is None or current is None:
        return 0.75
    if previous_met_s is None or current_met_s is None or previous_met_s == current_met_s:
        return 0.5 if previous.unit == current.unit else 1.5

    max_rate = {
        "velocity": 250.0,
        "altitude": 6000.0,
    }.get(kind)
    dt = abs(float(current_met_s) - float(previous_met_s))
    if dt <= 0.0 or not math.isfinite(dt):
        return 0.0
    if max_rate is None:
        scale = max(abs(previous.value_si), abs(current.value_si), 1.0)
        relative_delta = abs(current.value_si - previous.value_si) / scale
        rate_cost = min(8.0, relative_delta * 2.0)
        unit_cost = 0.0 if previous.unit == current.unit else 0.65
        return rate_cost + unit_cost
    rate = abs(current.value_si - previous.value_si) / dt
    if rate > 3.0 * max_rate:
        return math.inf
    rate_cost = 0.0 if rate <= max_rate else 1.5 * (rate / max_rate - 1.0)
    unit_cost = 0.0 if previous.unit == current.unit else 1.25
    return rate_cost + unit_cost
