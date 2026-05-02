from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def _hash_file(root: Path, path: Path, digest: "hashlib._Hash") -> None:
    relative = path.relative_to(root).as_posix()
    digest.update(relative.encode("utf-8"))
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")


def _iter_existing_files(root: Path, paths: list[str]):
    for item in paths:
        path = root / item
        if path.is_file():
            yield path


def _iter_tree(root: Path, directory: str, suffixes: tuple[str, ...]):
    base = root / directory
    if not base.exists():
        return
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.suffix in suffixes:
            yield path


def build_file_list(root: Path, target: str) -> list[Path]:
    if target == "python":
        return sorted(_iter_existing_files(root, ["pyproject.toml"]))

    if target == "frontend-deps":
        return sorted(_iter_existing_files(root, ["web/package.json", "web/package-lock.json"]))

    if target == "frontend-build":
        files = list(
            _iter_existing_files(
                root,
                [
                    "web/index.html",
                    "web/package.json",
                    "web/package-lock.json",
                    "web/postcss.config.js",
                    "web/tailwind.config.ts",
                    "web/tsconfig.json",
                    "web/vite.config.ts",
                    "web/scripts/with-modern-node.sh",
                ],
            )
        )
        files.extend(_iter_tree(root, "web/src", (".css", ".ts", ".tsx")))
        files.extend(_iter_tree(root, "docs/user", (".md",)))
        files.extend(_iter_tree(root, "docs/internal", (".md",)))
        return sorted(set(files))

    raise ValueError(f"Unknown fingerprint target: {target}")


def fingerprint(root: Path, target: str) -> str:
    digest = hashlib.sha256()
    for path in build_file_list(root, target):
        _hash_file(root, path, digest)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute webcalyzer launcher rebuild fingerprints.")
    parser.add_argument("target", choices=["python", "frontend-deps", "frontend-build"])
    parser.add_argument("root", nargs="?", default=".", help="Repository root.")
    args = parser.parse_args()
    print(fingerprint(Path(args.root).resolve(), args.target))


if __name__ == "__main__":
    main()
