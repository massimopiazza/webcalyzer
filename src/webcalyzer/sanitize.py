from __future__ import annotations

from dataclasses import dataclass
import math
import re


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
    return " ".join(text.upper().replace("§", "S").replace("—", "-").replace("–", "-").split())


def normalize_numeric_token(token: str) -> str:
    token = normalize_text(token)
    return token.translate(TEXT_TRANSLATION)


def detect_unit(text: str, kind: str) -> str | None:
    upper = normalize_text(text)
    if kind == "velocity":
        if re.search(r"M[PFR][HNR]", upper) or "MPH" in upper:
            return "MPH"
        return None
    if kind == "altitude":
        if re.search(r"\b[FE][T7I]\b", upper):
            return "FT"
        if re.search(r"\bM[IL1]\b", upper):
            return "MI"
        return None
    return None


def parse_met_candidates(candidates: list[tuple[str, str]]) -> TimedValue | None:
    best: TimedValue | None = None
    best_score = -math.inf
    for raw_text, variant in candidates:
        parsed = parse_met(raw_text)
        if parsed is None:
            continue
        score = 2 if "T" in normalize_text(raw_text) else 1
        if score > best_score:
            best_score = score
            best = TimedValue(raw_text=raw_text, value=parsed, variant=variant)
    return best


def parse_met(text: str) -> float | None:
    upper = normalize_text(text)
    upper = upper.replace(";", ":").replace(".", ":")
    upper = re.sub(r"\s*:\s*", ":", upper)
    upper = upper.replace("T ", "T")
    match = re.search(r"T\s*([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?", upper)
    if not match:
        match = re.search(r"([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?", upper)
    if not match:
        return None
    sign_token = match.group(1) or "+"
    first = int(match.group(2))
    second = int(match.group(3))
    third = match.group(4)
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


def parse_measurement_options(text: str, kind: str, variant: str) -> list[MeasurementOption]:
    tokens = _extract_numeric_tokens(text)
    if not tokens:
        return []

    explicit_unit = detect_unit(text, kind=kind)
    options: list[MeasurementOption] = []
    for token in tokens:
        inferred_units = [explicit_unit] if explicit_unit else _infer_units(kind=kind, token=token)
        for unit in inferred_units:
            raw_value = _parse_token(token=token, unit=unit, kind=kind)
            if raw_value is None:
                continue
            value_si = _to_si(raw_value=raw_value, unit=unit, kind=kind)
            options.append(
                MeasurementOption(
                    raw_text=text,
                    raw_token=token,
                    raw_value=raw_value,
                    unit=unit,
                    value_si=value_si,
                    explicit_unit=explicit_unit is not None,
                    variant=variant,
                )
            )
    options.sort(key=lambda item: len(item.raw_token), reverse=True)
    return options


def _infer_units(kind: str, token: str) -> list[str]:
    if kind == "velocity":
        return ["MPH"]
    if kind == "altitude":
        if "," in token or "." in token or ":" in token:
            return ["MI", "FT"]
        return ["FT"]
    raise ValueError(f"Unsupported measurement kind: {kind}")


def _parse_token(token: str, unit: str, kind: str) -> float | None:
    token = normalize_numeric_token(token)
    if kind == "velocity":
        return float(token.replace(",", "").replace(".", "").replace(":", ""))
    if kind == "altitude":
        if unit == "MI":
            cleaned = token.replace(",", "").replace(".", "").replace(":", "")
            try:
                return float(cleaned)
            except ValueError:
                return None
        cleaned = token.replace(",", "").replace(".", "").replace(":", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _to_si(raw_value: float, unit: str, kind: str) -> float:
    if kind == "velocity":
        return raw_value * MPH_TO_MPS
    if kind == "altitude":
        if unit == "FT":
            return raw_value * FT_TO_M
        if unit == "MI":
            return raw_value * MI_TO_M
    raise ValueError(f"Unsupported conversion: kind={kind}, unit={unit}")


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

        if best is None or score > best_score:
            best = option
            best_score = score
    return best
