from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import re


DIMENSION_BASES: tuple[str, ...] = (
    "L",
    "M",
    "T",
    "I",
    "TEMP",
    "AMOUNT",
    "LUM",
    "ANG",
    "SR",
    "BIT",
    "COUNT",
)

DIMENSION_LABELS: dict[str, str] = {
    "L": "length",
    "M": "mass",
    "T": "time",
    "I": "electric current",
    "TEMP": "thermodynamic temperature",
    "AMOUNT": "amount of substance",
    "LUM": "luminous intensity",
    "ANG": "plane angle",
    "SR": "solid angle",
    "BIT": "information",
    "COUNT": "count",
}

DIMENSION_PRESETS: dict[str, str] = {
    "nondimensional": "1",
    "length": "L",
    "mass": "M",
    "time": "T",
    "velocity": "L/T",
    "acceleration": "L/T^2",
    "density": "M/L^3",
    "force": "M*L/T^2",
    "pressure": "M/(L*T^2)",
    "energy": "M*L^2/T^2",
    "power": "M*L^2/T^3",
    "angle": "ANG",
    "angular velocity": "ANG/T",
    "angular acceleration": "ANG/T^2",
    "frequency": "1/T",
    "count": "COUNT",
    "count rate": "COUNT/T",
    "information": "BIT",
    "bitrate": "BIT/T",
}

DIMENSION_PRESET_DISPLAY_UNITS: dict[str, str] = {
    "nondimensional": "dimensionless",
    "length": "m",
    "mass": "kg",
    "time": "s",
    "velocity": "m/s",
    "acceleration": "m/s^2",
    "density": "kg/m^3",
    "force": "N",
    "pressure": "N/m^2",
    "energy": "J",
    "power": "W",
    "angle": "rad",
    "angular velocity": "rad/s",
    "angular acceleration": "rad/s^2",
    "frequency": "Hz",
    "count": "count",
    "count rate": "count/s",
    "information": "bit",
    "bitrate": "bit/s",
}


@dataclass(frozen=True, slots=True)
class DimensionExpression:
    exponents: dict[str, Fraction]

    def normalized(self) -> str:
        positive: list[str] = []
        negative: list[str] = []
        for base in DIMENSION_BASES:
            exponent = self.exponents.get(base, Fraction(0))
            if exponent > 0:
                positive.append(_format_power(base, exponent))
            elif exponent < 0:
                negative.append(_format_power(base, -exponent))
        numerator = "*".join(positive) if positive else "1"
        if not negative:
            return numerator
        denominator = "*".join(negative)
        if len(negative) > 1:
            denominator = f"({denominator})"
        return f"{numerator}/{denominator}" if positive else f"1/{denominator}"

    def as_json(self) -> dict[str, str]:
        return {
            base: _fraction_to_string(exponent)
            for base, exponent in self.exponents.items()
            if exponent != 0
        }


class DimensionSyntaxError(ValueError):
    pass


def parse_dimension_expression(expression: str) -> DimensionExpression:
    parser = _DimensionParser(expression)
    exponents = parser.parse()
    return DimensionExpression(
        {
            base: exponent
            for base, exponent in exponents.items()
            if exponent != 0
        }
    )


def normalize_dimension_expression(expression: str) -> str:
    return parse_dimension_expression(expression).normalized()


def dimension_json(expression: str) -> dict[str, str]:
    return parse_dimension_expression(expression).as_json()


def _format_power(base: str, exponent: Fraction) -> str:
    if exponent == 1:
        return base
    return f"{base}^{_format_exponent(exponent)}"


def _format_exponent(exponent: Fraction) -> str:
    if exponent.denominator == 1:
        return str(exponent.numerator)
    return f"({exponent.numerator}/{exponent.denominator})"


def _fraction_to_string(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


class _DimensionParser:
    def __init__(self, expression: str) -> None:
        self.expression = expression.strip()
        self.index = 0

    def parse(self) -> dict[str, Fraction]:
        if not self.expression:
            raise DimensionSyntaxError("dimension expression is required")
        value = self._parse_product()
        self._skip_ws()
        if self.index != len(self.expression):
            raise DimensionSyntaxError(f"unexpected token at position {self.index + 1}")
        return value

    def _parse_product(self) -> dict[str, Fraction]:
        value = self._parse_factor()
        while True:
            self._skip_ws()
            if self._peek("*"):
                self.index += 1
                value = _combine(value, self._parse_factor(), Fraction(1))
            elif self._peek("/"):
                self.index += 1
                value = _combine(value, self._parse_factor(), Fraction(-1))
            else:
                return value

    def _parse_factor(self) -> dict[str, Fraction]:
        self._skip_ws()
        if self._peek("("):
            self.index += 1
            value = self._parse_product()
            self._skip_ws()
            if not self._peek(")"):
                raise DimensionSyntaxError("missing closing parenthesis")
            self.index += 1
        elif self._peek("1"):
            self.index += 1
            value = {}
        else:
            token = self._read_base()
            value = {token: Fraction(1)}

        self._skip_ws()
        if self._peek("^"):
            self.index += 1
            exponent = self._read_exponent()
            value = {base: power * exponent for base, power in value.items()}
        return value

    def _read_base(self) -> str:
        self._skip_ws()
        match = re.match(r"[A-Za-z]+", self.expression[self.index :])
        if match is None:
            raise DimensionSyntaxError(f"expected dimension token at position {self.index + 1}")
        token = match.group(0).upper()
        self.index += len(match.group(0))
        if token not in DIMENSION_BASES:
            raise DimensionSyntaxError(f"unknown dimension token {token!r}")
        return token

    def _read_exponent(self) -> Fraction:
        self._skip_ws()
        if self._peek("("):
            self.index += 1
            start = self.index
            depth = 1
            while self.index < len(self.expression) and depth:
                if self.expression[self.index] == "(":
                    depth += 1
                elif self.expression[self.index] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                self.index += 1
            if depth:
                raise DimensionSyntaxError("missing closing parenthesis in exponent")
            raw = self.expression[start : self.index].strip()
            self.index += 1
        else:
            match = re.match(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:/\d+(?:\.\d+)?)?", self.expression[self.index :])
            if match is None:
                raise DimensionSyntaxError(f"expected exponent at position {self.index + 1}")
            raw = match.group(0)
            self.index += len(raw)
        try:
            if "/" in raw:
                left, right = raw.split("/", 1)
                denominator = Fraction(right)
                if denominator == 0:
                    raise DimensionSyntaxError("exponent denominator must not be zero")
                return Fraction(left) / denominator
            return Fraction(raw)
        except ValueError as exc:
            raise DimensionSyntaxError(f"invalid exponent {raw!r}") from exc

    def _skip_ws(self) -> None:
        while self.index < len(self.expression) and self.expression[self.index].isspace():
            self.index += 1

    def _peek(self, token: str) -> bool:
        return self.expression.startswith(token, self.index)


def _combine(
    left: dict[str, Fraction],
    right: dict[str, Fraction],
    right_sign: Fraction,
) -> dict[str, Fraction]:
    result = dict(left)
    for base, exponent in right.items():
        result[base] = result.get(base, Fraction(0)) + right_sign * exponent
        if result[base] == 0:
            del result[base]
    return result
