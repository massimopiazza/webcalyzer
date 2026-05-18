from webcalyzer.config import default_parsing_profile
from webcalyzer.models import FieldKindParsing, MetParsing, ParsingProfile, UnitAlias
from webcalyzer.sanitize import (
    choose_best_measurement,
    detect_unit,
    measurement_text_needs_unit_fallback,
    parse_measurement_options,
    parse_met,
    resolve_measurement_series,
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
    for both units, and MI happened to win via list ordering - yielding
    90 km altitude at MET=1. The conservative tie-breaker now prefers the
    smaller value, which is also the physically reasonable one."""

    options = parse_measurement_options("000,056 F NEW GLENN", kind="altitude", variant="vision")
    chosen = choose_best_measurement(
        options, kind="altitude", previous_value_si=None, previous_met_s=None, current_met_s=None
    )
    assert chosen is not None
    assert chosen.unit == "FT"


def test_unrecognized_non_ascii_unit_token_requests_ocr_fallback() -> None:
    profile = default_parsing_profile()

    assert measurement_text_needs_unit_fallback("000,063 М", kind="altitude", parsing=profile)
    assert measurement_text_needs_unit_fallback("000,064 МI", kind="altitude", parsing=profile)
    assert not measurement_text_needs_unit_fallback("000,064 MI", kind="altitude", parsing=profile)
    assert not measurement_text_needs_unit_fallback("ALTITUDE 000,064", kind="altitude", parsing=profile)


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


def test_altitude_parser_recovers_split_decimal_kilometer_text() -> None:
    profile = ParsingProfile(
        velocity=FieldKindParsing(
            units=(UnitAlias(name="KMH", aliases=("KM/H", "KMH"), si_factor=0.27777777777777778),),
            default_unit="KMH",
        ),
        altitude=FieldKindParsing(
            units=(UnitAlias(name="KM", aliases=("KM",), si_factor=1000.0),),
            default_unit="KM",
        ),
        met=MetParsing(timestamp_patterns=(r"T\s*([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?",)),
        custom_words=("KM/H", "KM"),
    )

    results = resolve_measurement_series(
        [
            [("ALTITUDE 7.1 KM", "raw")],
            [("ALTITUDE 7 .7 KM", "raw")],
            [("ALTITUDE 7 .9 KM", "raw")],
            [("ALTITUDE 8.3 KM", "raw")],
        ],
        kind="altitude",
        parsing=profile,
        met_values=[59.0, 61.0, 63.0, 65.0],
    )

    assert [result.chosen.value_si if result.chosen else None for result in results] == [
        7100.0,
        7700.0,
        7900.0,
        8300.0,
    ]


def test_altitude_parser_recovers_missing_decimal_point_before_unit() -> None:
    profile = ParsingProfile(
        velocity=FieldKindParsing(
            units=(UnitAlias(name="KMH", aliases=("KM/H", "KMH"), si_factor=0.27777777777777778),),
            default_unit="KMH",
        ),
        altitude=FieldKindParsing(
            units=(UnitAlias(name="KM", aliases=("KM",), si_factor=1000.0),),
            default_unit="KM",
        ),
        met=MetParsing(timestamp_patterns=(r"T\s*([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?",)),
        custom_words=("KM/H", "KM"),
    )

    options = parse_measurement_options("ALTITUDE 4 7 KM", kind="altitude", variant="raw", parsing=profile)

    assert options[0].raw_token == "4.7"
    assert options[0].value_si == 4700.0


def test_split_decimal_suffix_uses_profile_unit_aliases() -> None:
    profile = ParsingProfile(
        velocity=FieldKindParsing(
            units=(UnitAlias(name="V", aliases=("V",), unit_expression="meter/second"),),
            default_unit="V",
        ),
        altitude=FieldKindParsing(
            units=(UnitAlias(name="CUSTOMALT", aliases=("ALTU",), unit_expression="meter"),),
            default_unit="CUSTOMALT",
        ),
        met=MetParsing(timestamp_patterns=(r"T\s*([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?",)),
        custom_words=("ALTU",),
    )

    options = parse_measurement_options("ALTITUDE 4 7 ALTU", kind="altitude", variant="raw", parsing=profile)

    assert options[0].raw_token == "4.7"
    assert options[0].value_si == 4.7


def test_altitude_parser_keeps_recent_explicit_unit_for_unitless_text() -> None:
    profile = default_parsing_profile()
    options = parse_measurement_options(
        "ALTITUDE 166",
        kind="altitude",
        variant="raw",
        parsing=profile,
        preferred_unit="KM",
    )
    chosen = choose_best_measurement(
        options,
        kind="altitude",
        previous_value_si=166000.0,
        previous_met_s=1092.0,
        current_met_s=1106.0,
        preferred_unit="KM",
    )

    assert chosen is not None
    assert chosen.unit == "KM"
    assert chosen.value_si == 166000.0


def test_altitude_parser_accepts_high_stage2_kilometer_values() -> None:
    profile = default_parsing_profile()
    options = parse_measurement_options(
        "ALTITUDE 802 KM",
        kind="altitude",
        variant="raw",
        parsing=profile,
    )
    chosen = choose_best_measurement(
        options,
        kind="altitude",
        previous_value_si=799000.0,
        previous_met_s=2126.0,
        current_met_s=2128.0,
    )

    assert chosen is not None
    assert chosen.unit == "KM"
    assert chosen.value_si == 802000.0


def test_parser_recovers_fuzzy_unit_alias() -> None:
    profile = default_parsing_profile()

    options = parse_measurement_options(
        "ALTITUDE 166 KMN",
        kind="altitude",
        variant="raw",
        parsing=profile,
    )

    chosen = choose_best_measurement(
        options,
        kind="altitude",
        previous_value_si=165000.0,
        previous_met_s=1080.0,
        current_met_s=1082.0,
    )
    assert chosen is not None
    assert chosen.unit == "KM"
    assert chosen.value_si == 166000.0
    assert chosen.unit_source == "fuzzy"
    assert chosen.unit_match_score is not None
    assert chosen.unit_match_score >= 82.0


def test_series_resolver_recovers_missing_k_in_km_unit() -> None:
    profile = default_parsing_profile()

    results = resolve_measurement_series(
        [
            [("ALTITUDE 166 KM", "raw")],
            [("ALTITUDE 166 KM", "raw")],
            [("ALTITUDE 166 M", "raw")],
            [("ALTITUDE 167 KM", "raw")],
        ],
        kind="altitude",
        parsing=profile,
        met_values=[1080.0, 1082.0, 1084.0, 1086.0],
    )

    assert [result.chosen.value_si if result.chosen else None for result in results] == [
        166000.0,
        166000.0,
        166000.0,
        167000.0,
    ]
    assert results[2].chosen is not None
    assert results[2].chosen.unit_source == "inferred_dominant"


def test_series_resolver_prefers_gap_when_exact_and_context_units_both_jump() -> None:
    profile = default_parsing_profile()

    results = resolve_measurement_series(
        [
            [("ALTITUDE 166 KM", "raw")],
            [("ALTITUDE 166 KM", "raw")],
            [("ALTITUDE 500 M", "raw")],
            [("ALTITUDE 167 KM", "raw")],
        ],
        kind="altitude",
        parsing=profile,
        met_values=[1080.0, 1082.0, 1084.0, 1086.0],
    )

    assert results[2].chosen is None
    assert results[2].reject_reason == "low_confidence_or_jump"


def test_default_parsing_profile_has_baseline_custom_words() -> None:
    profile = default_parsing_profile()
    assert "MPH" in profile.custom_words
    assert "FT" in profile.custom_words
    assert "MI" in profile.custom_words
    assert "T+" in profile.custom_words
