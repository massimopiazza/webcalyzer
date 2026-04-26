from types import SimpleNamespace

from webcalyzer.overlay_ffmpeg import (
    _build_ffmpeg_command,
    _ffmpeg_out_time_s,
    _ffmpeg_progress_percent,
    _format_ffmpeg_progress,
)


def test_ffmpeg_command_enables_machine_readable_progress(tmp_path) -> None:
    plan = SimpleNamespace(
        metadata=SimpleNamespace(fps=60.0),
        display_overlay_width=960,
        display_overlay_height=432,
        left_margin_px=16,
        top_margin_px=16,
    )

    command = _build_ffmpeg_command(
        ffmpeg="ffmpeg",
        source_path=tmp_path / "source.mp4",
        concat_path=tmp_path / "concat.txt",
        output_path=tmp_path / "output.mp4",
        plan=plan,
        include_audio=True,
        encoder="libx264",
    )

    assert "-progress" in command
    assert command[command.index("-progress") + 1] == "pipe:1"
    assert "-nostats" in command


def test_ffmpeg_progress_helpers_parse_progress_output() -> None:
    progress = {
        "frame": "900",
        "out_time_us": "15000000",
        "out_time": "00:00:15.000000",
    }

    assert _ffmpeg_out_time_s(progress) == 15.0
    assert _ffmpeg_progress_percent(progress, total_duration_s=60.0) == 25.0
    message = _format_ffmpeg_progress(progress, 25.0, final=False)
    assert "25.0%" in message
    assert "speed" not in message
