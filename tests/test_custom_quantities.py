import numpy as np
import pandas as pd

from webcalyzer.config import load_profile, save_profile
from webcalyzer.dimensions import normalize_dimension_expression
from webcalyzer.models import (
    CalibrationSegmentConfig,
    FieldConfig,
    HardcodedRawDataPoint,
    ProfileConfig,
    TelemetryQuantityDefinition,
)
from webcalyzer.postprocess import apply_mahalanobis_outlier_rejection_with_rejected, rebuild_clean_from_raw
from webcalyzer.quantities import (
    delete_quantity,
    load_quantity_library,
    remove_quantity_from_templates,
    update_quantity_snapshots,
)
from webcalyzer.sanitize import parse_custom_measurement_options, resolve_custom_measurement_series
from webcalyzer.units import convert_value, typical_unit_for_dimension, validate_unit_compatible_with_dimension


def test_dimension_parser_normalizes_fractional_exponents() -> None:
    assert normalize_dimension_expression("L^(1/2)/T") == "L^(1/2)/T"
    assert normalize_dimension_expression("M/L/L/L") == "M/L^3"


def test_unit_validation_respects_angle_as_distinct_dimension() -> None:
    validate_unit_compatible_with_dimension("rad/s", "ANG/T")
    validate_unit_compatible_with_dimension("N/m^2", "M/(L*T^2)")
    assert typical_unit_for_dimension("M/(L*T^2)") == "N/m^2"


def test_quantity_to_dict_includes_optional_fields() -> None:
    quantity = TelemetryQuantityDefinition(
        id="q_pressure",
        name="Pressure",
        slug="pressure",
        dimensionality="M/(L*T^2)",
        display_unit="N/m^2",
    )

    assert quantity.to_dict()["description"] == ""
    assert quantity.to_dict()["unit_aliases"] == {}


def test_missing_quantity_library_is_seeded(tmp_path) -> None:
    quantities = load_quantity_library(tmp_path)

    assert [quantity.slug for quantity in quantities[:5]] == [
        "time",
        "stage1_velocity",
        "stage1_altitude",
        "stage2_velocity",
        "stage2_altitude",
    ]
    assert (tmp_path / "custom_quantities.yaml").exists()


def test_default_quantities_cannot_be_deleted(tmp_path) -> None:
    quantities = load_quantity_library(tmp_path)

    try:
        delete_quantity(quantities, "q_time")
    except ValueError as exc:
        assert "default quantities" in str(exc)
    else:
        raise AssertionError("Expected default quantity deletion to be rejected")


def test_custom_quantity_parser_normalizes_to_display_unit() -> None:
    quantity = TelemetryQuantityDefinition(
        id="q_accel",
        name="Acceleration",
        slug="acceleration",
        dimensionality="L/T^2",
        display_unit="m/s^2",
        unit_aliases={"gee": "standard_gravity"},
    )

    options = parse_custom_measurement_options("ACCEL 2 gee", quantity, "raw")

    assert options
    assert round(options[0].value_si, 3) == round(convert_value(2.0, "standard_gravity", "m/s^2"), 3)


def test_custom_series_uses_recent_unit_to_avoid_switch_jump() -> None:
    quantity = TelemetryQuantityDefinition(
        id="q_speed",
        name="Speed",
        slug="speed",
        dimensionality="L/T",
        display_unit="km/s",
    )

    results = resolve_custom_measurement_series(
        [[("SPEED 1200 m/s", "raw")], [("SPEED 1.3 km/s", "raw")], [("SPEED 1400", "raw")]],
        quantity=quantity,
        met_values=[1.0, 2.0, 3.0],
    )

    assert [round(result.chosen.value_si, 3) if result.chosen else None for result in results] == [1.2, 1.3, 1.4]


def test_rebuild_clean_includes_custom_anchor_points() -> None:
    quantity = TelemetryQuantityDefinition(
        id="q_density",
        name="Density",
        slug="density",
        dimensionality="M/L^3",
        display_unit="kg/m^3",
    )
    profile = ProfileConfig(
        profile_name="custom",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        custom_telemetry_quantities=[quantity],
        hardcoded_raw_data_points=[
            HardcodedRawDataPoint(
                mission_elapsed_time_s=2.0,
                custom_values={"custom_density": 1.225},
            )
        ],
        segments=[
            CalibrationSegmentConfig(
                id="segment_1",
                start_frame_index=0,
                start_time_s=0.0,
                end_frame_index=10,
                end_time_s=10.0,
                fields={
                    "custom_density": FieldConfig.custom("custom_density", "q_density"),
                },
            )
        ],
    )
    raw_df = pd.DataFrame(
        [{"frame_index": 0, "sample_time_s": 2.0, "mission_elapsed_time_s": 2.0}]
    )

    clean_df = rebuild_clean_from_raw(raw_df, profile=profile)

    assert clean_df.loc[0, "custom_density"] == 1.225


def test_outlier_rejection_handles_custom_columns_adaptively() -> None:
    times = np.arange(0, 42, 2, dtype=float)
    values = 0.5 * times
    values[10] = 250.0
    clean_df = pd.DataFrame(
        {
            "frame_index": np.arange(times.size),
            "sample_time_s": times,
            "mission_elapsed_time_s": times,
            "custom_acceleration": values,
        }
    )

    cleaned, rejected = apply_mahalanobis_outlier_rejection_with_rejected(clean_df, window_s=30.0)

    assert pd.isna(cleaned.at[10, "custom_acceleration"])
    assert rejected.at[10, "custom_acceleration"] == 250.0


def test_quantity_template_updates_rename_and_remove_fields(tmp_path) -> None:
    original = TelemetryQuantityDefinition(
        id="q_load",
        name="Load Factor",
        slug="load_factor",
        dimensionality="1",
        display_unit="1",
    )
    profile = ProfileConfig(
        profile_name="custom",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        custom_telemetry_quantities=[original],
        hardcoded_raw_data_points=[
            HardcodedRawDataPoint(
                mission_elapsed_time_s=1.0,
                custom_values={"custom_load_factor": 2.0},
            )
        ],
        segments=[
            CalibrationSegmentConfig(
                id="segment_1",
                start_frame_index=0,
                start_time_s=0.0,
                end_frame_index=10,
                end_time_s=10.0,
                fields={
                    "custom_load_factor": FieldConfig.custom("custom_load_factor", "q_load"),
                },
            )
        ],
    )
    template_path = tmp_path / "profile.yaml"
    save_profile(profile, template_path)

    updated = TelemetryQuantityDefinition(
        id="q_load",
        name="G Load",
        slug="g_load",
        dimensionality="1",
        display_unit="1",
    )
    assert update_quantity_snapshots(tmp_path, updated) == 1
    renamed_profile = load_profile(template_path)
    assert "custom_g_load" in renamed_profile.segments[0].fields
    assert renamed_profile.hardcoded_raw_data_points[0].custom_values == {"custom_g_load": 2.0}

    assert remove_quantity_from_templates(tmp_path, "q_load") == 1
    removed_profile = load_profile(template_path)
    assert removed_profile.custom_telemetry_quantities == []
    assert removed_profile.segments[0].fields == {}
    assert removed_profile.hardcoded_raw_data_points == []
