from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mpg", ".mpeg", ".ts"}


@dataclass(frozen=True)
class BrowseRoot:
    """A user-visible root the file browser is allowed to expose."""

    label: str
    path: Path


def _resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def normalize_roots(raw_roots: Iterable[Path | str]) -> list[BrowseRoot]:
    seen: set[Path] = set()
    roots: list[BrowseRoot] = []
    for raw in raw_roots:
        candidate = _resolve(raw)
        if not candidate.exists() or candidate in seen:
            continue
        seen.add(candidate)
        roots.append(BrowseRoot(label=candidate.name or str(candidate), path=candidate))
    return roots


def is_within_roots(path: Path, roots: list[BrowseRoot]) -> bool:
    target = _resolve(path)
    for root in roots:
        try:
            target.relative_to(root.path)
            return True
        except ValueError:
            continue
    return False


def safe_resolve(path: str | None, roots: list[BrowseRoot]) -> Path:
    if not path:
        if roots:
            return roots[0].path
        raise PermissionError("No browsable roots configured")
    target = _resolve(path)
    if not is_within_roots(target, roots):
        raise PermissionError(f"Path is outside the allowed roots: {target}")
    return target


def listing(target: Path, *, kinds: set[str] | None = None) -> dict:
    if not target.exists():
        raise FileNotFoundError(target)
    if target.is_file():
        target = target.parent

    entries: list[dict] = []
    try:
        children = sorted(
            target.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        )
    except PermissionError as exc:  # pragma: no cover - defensive
        raise PermissionError(str(exc)) from exc

    for child in children:
        if child.name.startswith("."):
            continue
        try:
            stat = child.stat()
        except OSError:
            continue
        is_dir = child.is_dir()
        is_video = (not is_dir) and child.suffix.lower() in VIDEO_EXTENSIONS
        kind = "dir" if is_dir else ("video" if is_video else "file")
        if kinds and kind not in kinds and "any" not in kinds:
            continue
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "type": kind,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        )
    return {
        "path": str(target),
        "parent": str(target.parent) if target.parent != target else None,
        "entries": entries,
    }
