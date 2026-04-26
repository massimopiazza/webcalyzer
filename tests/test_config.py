from pathlib import Path

from webcalyzer.config import load_profile, save_profile


def test_profile_uses_explicit_bbox_and_fixture_range_schema(tmp_path: Path) -> None:
    profile = load_profile("configs/blue_origin/new_glenn_ng3.yaml")

    assert profile.fixture_frame_count == 20
    assert profile.fixture_time_range_s == (0.0, 840.0)
    assert profile.fields["stage1_velocity"].box.normalized_tuple() == (
        0.065625,
        0.8722222222222222,
        0.2359375,
        0.9731481481481481,
    )
    assert profile.video_overlay.width_fraction == 0.5
    assert profile.video_overlay.height_fraction == 0.4

    saved_path = save_profile(profile, tmp_path / "profile.yaml")
    saved_text = saved_path.read_text()
    assert "fixture_time_range_s" in saved_text
    assert "fixture_reference_times_s" not in saved_text
    assert "bbox_x1y1x2y2" in saved_text
    assert "\n    box:" not in saved_text
