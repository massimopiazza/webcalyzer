from __future__ import annotations

from pathlib import Path

import pytest

from webcalyzer import extract as extract_module
from webcalyzer.models import ProfileConfig
from webcalyzer.ocr_factory import OCRBackendOptions


class _Cancelled(RuntimeError):
    pass


class _NeverReadyResult:
    get_called = False

    def ready(self) -> bool:
        return False

    def get(self) -> object:
        self.get_called = True
        return []


class _FakePool:
    def __init__(self) -> None:
        self.results: list[_NeverReadyResult] = []
        self.closed = False
        self.terminated = False
        self.joined = False

    def apply_async(self, _func, _args):
        result = _NeverReadyResult()
        self.results.append(result)
        return result

    def close(self) -> None:
        self.closed = True

    def terminate(self) -> None:
        self.terminated = True

    def join(self) -> None:
        self.joined = True


class _FakeContext:
    def __init__(self, pool: _FakePool) -> None:
        self.pool = pool

    def Pool(self, processes: int) -> _FakePool:
        return self.pool


@pytest.mark.parametrize("workers", [1, 4])
def test_cancellable_phase_a_terminates_pool_without_waiting_for_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workers: int,
) -> None:
    pool = _FakePool()
    monkeypatch.setattr(extract_module.mp, "get_context", lambda _name: _FakeContext(pool))

    profile = ProfileConfig(
        profile_name="cancel_phase_a",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
    )

    def cancel_check() -> None:
        raise _Cancelled()

    with pytest.raises(_Cancelled):
        extract_module._run_phase_a(
            video_path=tmp_path / "video.mp4",
            profile=profile,
            metadata_fps=30.0,
            sample_indices=list(range(100)),
            backend_options=OCRBackendOptions(),
            workers=workers,
            skip_detection=False,
            cancel_check=cancel_check,
        )

    assert pool.terminated is True
    assert pool.closed is False
    assert pool.joined is True
    assert pool.results
    assert all(not result.get_called for result in pool.results)
