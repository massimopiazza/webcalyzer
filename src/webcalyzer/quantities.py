from __future__ import annotations

from pathlib import Path
import re
import uuid
from typing import Any

import yaml

from webcalyzer.dimensions import normalize_dimension_expression
from webcalyzer.models import ProfileConfig, TelemetryQuantityDefinition
from webcalyzer.units import validate_unit_compatible_with_dimension


QUANTITY_LIBRARY_FILENAME = "custom_quantities.yaml"
QUANTITY_LIBRARY_DIRNAME = "lib"
DEFAULT_QUANTITY_FIELD_NAMES: dict[str, str] = {
    "q_time": "met",
    "q_stage1_velocity": "stage1_velocity",
    "q_stage1_altitude": "stage1_altitude",
    "q_stage2_velocity": "stage2_velocity",
    "q_stage2_altitude": "stage2_altitude",
}


def default_quantity_library() -> list[TelemetryQuantityDefinition]:
    return [
        TelemetryQuantityDefinition(
            id="q_time",
            name="time",
            slug="time",
            dimensionality="T",
            display_unit="s",
            description="Mission elapsed time normalized to seconds.",
            unit_aliases={
                "H": "hour",
                "HR": "hour",
                "M": "minute",
                "MIN": "minute",
                "S": "second",
                "SEC": "second",
            },
        ),
        TelemetryQuantityDefinition(
            id="q_stage1_velocity",
            name="stage1_velocity",
            slug="stage1_velocity",
            dimensionality="L/T",
            display_unit="m/s",
            description="Stage 1 telemetry velocity normalized to meters per second.",
            unit_aliases={
                "MPH": "mile/hour",
                "KPH": "kilometer/hour",
                "KMH": "kilometer/hour",
                "KM/H": "kilometer/hour",
                "MPS": "meter/second",
                "M/S": "meter/second",
                "FPS": "foot/second",
                "FT/S": "foot/second",
            },
        ),
        TelemetryQuantityDefinition(
            id="q_stage1_altitude",
            name="stage1_altitude",
            slug="stage1_altitude",
            dimensionality="L",
            display_unit="m",
            description="Stage 1 telemetry altitude normalized to meters.",
            unit_aliases={
                "FT": "foot",
                "MI": "mile",
                "MIL": "mile",
                "MII": "mile",
                "KM": "kilometer",
                "M": "meter",
            },
        ),
        TelemetryQuantityDefinition(
            id="q_stage2_velocity",
            name="stage2_velocity",
            slug="stage2_velocity",
            dimensionality="L/T",
            display_unit="m/s",
            description="Stage 2 telemetry velocity normalized to meters per second.",
            unit_aliases={
                "MPH": "mile/hour",
                "KPH": "kilometer/hour",
                "KMH": "kilometer/hour",
                "KM/H": "kilometer/hour",
                "MPS": "meter/second",
                "M/S": "meter/second",
                "FPS": "foot/second",
                "FT/S": "foot/second",
            },
        ),
        TelemetryQuantityDefinition(
            id="q_stage2_altitude",
            name="stage2_altitude",
            slug="stage2_altitude",
            dimensionality="L",
            display_unit="m",
            description="Stage 2 telemetry altitude normalized to meters.",
            unit_aliases={
                "FT": "foot",
                "MI": "mile",
                "MIL": "mile",
                "MII": "mile",
                "KM": "kilometer",
                "M": "meter",
            },
        ),
    ]


def is_default_quantity_id(quantity_id: str) -> bool:
    return quantity_id in DEFAULT_QUANTITY_FIELD_NAMES


def quantity_field_name(quantity: TelemetryQuantityDefinition) -> str:
    return DEFAULT_QUANTITY_FIELD_NAMES.get(quantity.id, quantity.field_name())


def make_quantity_id() -> str:
    return f"q_{uuid.uuid4().hex[:12]}"


def make_quantity_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "quantity"


def default_quantity_library_dir(templates_dir: str | Path) -> Path:
    """Return the default library directory for a templates directory."""

    path = Path(templates_dir)
    if path.name == "configs":
        return path.parent / QUANTITY_LIBRARY_DIRNAME
    return path


def quantity_library_path(library_dir: str | Path) -> Path:
    return Path(library_dir) / QUANTITY_LIBRARY_FILENAME


def load_quantity_library(library_dir: str | Path) -> list[TelemetryQuantityDefinition]:
    path = quantity_library_path(library_dir)
    if not path.exists():
        quantities = default_quantity_library()
        save_quantity_library(library_dir, quantities)
        return quantities
    data = yaml.safe_load(path.read_text()) or {}
    if isinstance(data, list):
        raw_items = data
    else:
        raw_items = data.get("quantities", [])
    if not isinstance(raw_items, list):
        raise ValueError("custom quantity library must contain a quantities list")
    quantities = [_quantity_from_mapping(item) for item in raw_items]
    return _normalize_library_quantities(quantities)


def save_quantity_library(
    library_dir: str | Path,
    quantities: list[TelemetryQuantityDefinition],
) -> Path:
    quantities = _normalize_library_quantities(quantities)
    path = quantity_library_path(library_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"quantities": [quantity.to_dict() for quantity in quantities]},
            sort_keys=False,
            width=1000,
        )
    )
    return path


def normalize_quantity_mapping(
    data: dict[str, Any],
    *,
    existing_id: str | None = None,
) -> TelemetryQuantityDefinition:
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("quantity name is required")
    dimensionality = normalize_dimension_expression(str(data.get("dimensionality", "")).strip())
    display_unit = str(data.get("display_unit", "")).strip()
    if not display_unit:
        raise ValueError("display_unit is required")
    validate_unit_compatible_with_dimension(display_unit, dimensionality)
    aliases = data.get("unit_aliases", {}) or {}
    if not isinstance(aliases, dict):
        raise ValueError("unit_aliases must be a mapping")
    normalized_aliases: dict[str, str] = {}
    for alias, unit_expression in aliases.items():
        alias_text = str(alias).strip()
        unit_text = str(unit_expression).strip()
        if not alias_text or not unit_text:
            raise ValueError("unit_aliases entries must have non-empty alias and unit expression")
        validate_unit_compatible_with_dimension(unit_text, dimensionality)
        normalized_aliases[alias_text] = unit_text
    slug = make_quantity_slug(str(data.get("slug") or name))
    return TelemetryQuantityDefinition(
        id=str(data.get("id") or existing_id or make_quantity_id()),
        name=name,
        slug=slug,
        dimensionality=dimensionality,
        display_unit=display_unit,
        description=str(data.get("description", "") or ""),
        unit_aliases=normalized_aliases,
    )


def upsert_quantity(
    quantities: list[TelemetryQuantityDefinition],
    quantity: TelemetryQuantityDefinition,
) -> list[TelemetryQuantityDefinition]:
    replaced = False
    result: list[TelemetryQuantityDefinition] = []
    for current in quantities:
        if current.id == quantity.id:
            result.append(quantity)
            replaced = True
        else:
            result.append(current)
    if not replaced:
        result.append(quantity)
    _validate_quantity_collection(result)
    return result


def delete_quantity(
    quantities: list[TelemetryQuantityDefinition],
    quantity_id: str,
) -> list[TelemetryQuantityDefinition]:
    if is_default_quantity_id(quantity_id):
        raise ValueError("default quantities cannot be deleted")
    return [quantity for quantity in quantities if quantity.id != quantity_id]


def scan_quantity_usage(
    *,
    templates_dir: str | Path,
    quantity_id: str,
    current_profile: ProfileConfig | None = None,
) -> list[dict[str, Any]]:
    from webcalyzer.config import load_profile

    results: list[dict[str, Any]] = []
    if current_profile is not None:
        usage = _profile_usage(current_profile, quantity_id)
        if usage["categories"]:
            results.append({"template": "__current__", **usage})
    root = Path(templates_dir)
    if root.exists():
        for path in sorted(root.rglob("*.yaml")):
            if path.name == QUANTITY_LIBRARY_FILENAME:
                continue
            try:
                profile = load_profile(path)
            except Exception:  # noqa: BLE001
                continue
            usage = _profile_usage(profile, quantity_id)
            if usage["categories"]:
                results.append({"template": str(path.relative_to(root)), **usage})
    return results


def update_quantity_snapshots(
    templates_dir: str | Path,
    quantity: TelemetryQuantityDefinition,
) -> int:
    from webcalyzer.config import load_profile, save_profile

    changed_count = 0
    root = Path(templates_dir)
    for path in sorted(root.rglob("*.yaml")):
        if path.name == QUANTITY_LIBRARY_FILENAME:
            continue
        try:
            profile = load_profile(path)
        except Exception:  # noqa: BLE001
            continue
        changed = False
        for index, current in enumerate(profile.custom_telemetry_quantities):
            if current.id == quantity.id:
                old_field_name = current.field_name()
                new_field_name = quantity.field_name()
                profile.custom_telemetry_quantities[index] = quantity
                if old_field_name != new_field_name:
                    _rename_profile_custom_field(profile, old_field_name, new_field_name, quantity.id)
                changed = True
        if changed:
            save_profile(profile, path)
            changed_count += 1
    return changed_count


def remove_quantity_from_templates(templates_dir: str | Path, quantity_id: str) -> int:
    from webcalyzer.config import load_profile, save_profile

    changed_count = 0
    root = Path(templates_dir)
    for path in sorted(root.rglob("*.yaml")):
        if path.name == QUANTITY_LIBRARY_FILENAME:
            continue
        try:
            profile = load_profile(path)
        except Exception:  # noqa: BLE001
            continue
        removed_fields = {
            quantity.field_name()
            for quantity in profile.custom_telemetry_quantities
            if quantity.id == quantity_id
        }
        removed_fields.update(
            field_name
            for segment in profile.segments
            for field_name, field in segment.fields.items()
            if field.quantity_id == quantity_id
        )
        if not removed_fields and not any(
            quantity.id == quantity_id for quantity in profile.custom_telemetry_quantities
        ):
            continue
        profile.custom_telemetry_quantities = [
            quantity for quantity in profile.custom_telemetry_quantities if quantity.id != quantity_id
        ]
        for segment in profile.segments:
            for field_name in list(segment.fields):
                field = segment.fields[field_name]
                if field.quantity_id == quantity_id or field_name in removed_fields:
                    del segment.fields[field_name]
        for point in profile.hardcoded_raw_data_points:
            for field_name in removed_fields:
                point.custom_values.pop(field_name, None)
        profile.hardcoded_raw_data_points = [
            point for point in profile.hardcoded_raw_data_points if point.field_values()
        ]
        save_profile(profile, path)
        changed_count += 1
    return changed_count


def _profile_usage(profile: ProfileConfig, quantity_id: str) -> dict[str, Any]:
    categories: set[str] = set()
    if any(quantity.id == quantity_id for quantity in profile.custom_telemetry_quantities):
        categories.add("quantity definition")
    field_names = {
        quantity.field_name()
        for quantity in profile.custom_telemetry_quantities
        if quantity.id == quantity_id
    }
    if any(
        field_config.quantity_id == quantity_id
        for segment in profile.segments
        for field_config in segment.fields.values()
    ):
        categories.add("calibration fields")
    if any(
        field_name in point.custom_values
        for point in profile.hardcoded_raw_data_points
        for field_name in field_names
    ):
        categories.add("anchor points")
    return {"profile_name": profile.profile_name, "categories": sorted(categories)}


def _rename_profile_custom_field(
    profile: ProfileConfig,
    old_field_name: str,
    new_field_name: str,
    quantity_id: str,
) -> None:
    for segment in profile.segments:
        if old_field_name in segment.fields:
            field = segment.fields.pop(old_field_name)
            field.name = new_field_name
            field.quantity_id = quantity_id
            segment.fields[new_field_name] = field
    for point in profile.hardcoded_raw_data_points:
        if old_field_name in point.custom_values:
            point.custom_values[new_field_name] = point.custom_values.pop(old_field_name)


def _quantity_from_mapping(data: Any) -> TelemetryQuantityDefinition:
    if not isinstance(data, dict):
        raise ValueError("custom quantity entries must be mappings")
    return normalize_quantity_mapping(data)


def _normalize_library_quantities(
    quantities: list[TelemetryQuantityDefinition],
) -> list[TelemetryQuantityDefinition]:
    existing_by_id = {quantity.id: quantity for quantity in quantities}
    default_ids = set(DEFAULT_QUANTITY_FIELD_NAMES)
    result: list[TelemetryQuantityDefinition] = [
        existing_by_id.get(default_quantity.id, default_quantity)
        for default_quantity in default_quantity_library()
    ]
    for quantity in quantities:
        if quantity.id in default_ids:
            continue
        result.append(quantity)
    _validate_quantity_collection(result)
    return result


def _validate_quantity_collection(quantities: list[TelemetryQuantityDefinition]) -> None:
    names: set[str] = set()
    slugs: set[str] = set()
    ids: set[str] = set()
    for quantity in quantities:
        lowered = quantity.name.casefold()
        if lowered in names:
            raise ValueError(f"Duplicate custom quantity name {quantity.name!r}")
        if quantity.slug in slugs:
            raise ValueError(f"Duplicate custom quantity slug {quantity.slug!r}")
        if quantity.id in ids:
            raise ValueError(f"Duplicate custom quantity id {quantity.id!r}")
        names.add(lowered)
        slugs.add(quantity.slug)
        ids.add(quantity.id)
