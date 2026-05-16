from webcalyzer.units import unit_suggestions, validate_unit_compatible_with_dimension


def test_unit_suggestions_search_pint_registry_case_insensitively() -> None:
    suggestions = unit_suggestions("Am")

    assert any(candidate.lower() == "ampere" for candidate in suggestions)
    assert unit_suggestions("not_a_real_unit_token") == []


def test_unit_suggestions_include_valid_prefixed_unit_symbols() -> None:
    for query, expected in (
        ("kg", "kg"),
        ("kw", "kW"),
        ("MW", "MW"),
        ("mW", "mW"),
        ("GW", "GW"),
        ("TW", "TW"),
        ("km", "km"),
        ("nm", "nm"),
        ("um", "um"),
        ("μm", "μm"),
    ):
        assert expected in unit_suggestions(query)


def test_prefixed_units_validate_against_dimensions() -> None:
    validate_unit_compatible_with_dimension("kg", "M")
    validate_unit_compatible_with_dimension("kW", "M*L^2/T^3")
    validate_unit_compatible_with_dimension("MW", "M*L^2/T^3")
    validate_unit_compatible_with_dimension("mW", "M*L^2/T^3")
    validate_unit_compatible_with_dimension("km", "L")
    validate_unit_compatible_with_dimension("μm", "L")
