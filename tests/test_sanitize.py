from webcalyzer.config import default_parsing_profile
from webcalyzer.models import FieldKindParsing, MetParsing, ParsingProfile, UnitAlias
from webcalyzer.sanitize import (
    choose_best_measurement,
    detect_unit,
    parse_measurement_options,
    parse_met,
)


def test_parse_met_with_countdown_and_launch_time() -> None:
    assert parse_met("T-00:05") == -5.0
    assert parse_met("T+00:03:49") == 229.0
    assert parse_met("T+00:13: 12") == 792.0


def test_parse_velocity_uses_mph_units() -> None:
    options = parse_measurement_options("STAGE 2 VELOCITY 004,679 MPH", kind="velocity", variant="raw")
    assert options
    best = choose_best_measurement(options, kind="velocity", previous_value_si=None, previous_met_s=None, current_met_s=None)
    assert best is not None
    assert round(best.raw_value) == 4679
    assert best.unit == "MPH"


def test_parse_altitude_handles_miles_decimal_format() -> None:
    options = parse_measurement_options("STAGE 2 ALTITUDE 000,071 MI", kind="altitude", variant="raw")
    best = choose_best_measurement(options, kind="altitude", previous_value_si=None, previous_met_s=None, current_met_s=None)
    assert best is not None
    assert best.raw_value == 71.0
    assert best.unit == "MI"


def test_parse_altitude_handles_feet_format() -> None:
    options = parse_measurement_options("NEW GLENN ALTITUDE 031,108 FT", kind="altitude", variant="raw")
    best = choose_best_measurement(options, kind="altitude", previous_value_si=None, previous_met_s=None, current_met_s=None)
    assert best is not None
    assert best.raw_value == 31108.0
    assert best.unit == "FT"


def test_non_numeric_words_do_not_turn_into_measurements() -> None:
    assert parse_measurement_options("BOOSTER LANDING BURN O", kind="velocity", variant="raw") == []
    assert parse_measurement_options("SO08", kind="velocity", variant="raw") == []


def test_ambiguous_altitude_with_no_explicit_unit_prefers_feet() -> None:
    """Without an explicit FT/MI label, "000,056" used to score equally
    for both units, and MI happened to win via list ordering — yielding
    90 km altitude at MET=1. The conservative tie-breaker now prefers the
    smaller value, which is also the physically reasonable one."""

    options = parse_measurement_options("000,056 F NEW GLENN", kind="altitude", variant="vision")
    chosen = choose_best_measurement(
        options, kind="altitude", previous_value_si=None, previous_met_s=None, current_met_s=None
    )
    assert chosen is not None
    assert chosen.unit == "FT"


def test_parsing_profile_enables_custom_unit_aliases() -> None:
    """A YAML-driven profile can introduce new unit aliases (e.g. KM/H or
    KM) without touching the Python source."""

    profile = ParsingProfile(
        velocity=FieldKindParsing(
            units=(
                UnitAlias(name="KMH", aliases=("KM/H", "KMH"), si_factor=0.27777777777777778),
            ),
            default_unit="KMH",
        ),
        altitude=FieldKindParsing(
            units=(UnitAlias(name="KM", aliases=("KM",), si_factor=1000.0),),
            default_unit="KM",
        ),
        met=MetParsing(timestamp_patterns=(r"T\s*([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?",)),
        custom_words=("KM/H", "KM"),
    )
    assert detect_unit("ALT 002,500 KM", kind="altitude", parsing=profile) == "KM"

    options = parse_measurement_options(
        "VEL 000,360 KM/H", kind="velocity", variant="raw", parsing=profile
    )
    chosen = choose_best_measurement(
        options, kind="velocity", previous_value_si=None, previous_met_s=None, current_met_s=None
    )
    assert chosen is not None
    assert chosen.unit == "KMH"
    assert round(chosen.value_si, 3) == 100.0


def test_default_parsing_profile_has_baseline_custom_words() -> None:
    profile = default_parsing_profile()
    assert "MPH" in profile.custom_words
    assert "FT" in profile.custom_words
    assert "MI" in profile.custom_words
    assert "T+" in profile.custom_words
