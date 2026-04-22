from webcalyzer.sanitize import choose_best_measurement, parse_measurement_options, parse_met


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
