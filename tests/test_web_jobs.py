from pathlib import Path

from webcalyzer.web.jobs import _collect_output_paths


def test_collect_output_paths_omits_review_files(tmp_path: Path) -> None:
    (tmp_path / "plot.pdf").write_text("", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "telemetry.csv").write_text("", encoding="utf-8")
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / "frame_00.jpg").write_bytes(b"jpeg")

    assert set(_collect_output_paths(tmp_path)) == {"plot.pdf", "data/telemetry.csv"}
