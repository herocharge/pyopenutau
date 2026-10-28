"""Copy only public source/docs/tests into a new standalone repository directory.

Does not initialize Git, download dependencies, or include generated outputs.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil


ROOT_FILES = (
    ".gitignore", ".gitattributes", ".editorconfig", "pyproject.toml", "MANIFEST.in",
    "LICENSE", "NOTICE", "README.md", "HEADLESS.md", "CONTRIBUTING.md", "CHANGELOG.md",
    "SECURITY.md", "AI_DISCLOSURE.md", "requirements-dev.txt",
)
SOURCE_TREES = {"src": {".py", ".typed", ".cs", ".csproj", ".Config"},
                "tests": {".py"}, "examples": {".py"}, "scripts": {".py"},
                "docs": {".md", ".json"}, ".github": {".yml"}}


def export(source: Path, destination: Path) -> int:
    source = source.resolve(strict=True)
    destination = destination.absolute()
    # Reject nested destinations, which could recursively enter an input tree.
    if source == destination.resolve() or source in destination.resolve().parents:
        raise ValueError("Export outside the source repository")
    files = [source / name for name in ROOT_FILES]
    for tree, suffixes in SOURCE_TREES.items():
        for path in (source / tree).rglob("*"):
            if "__pycache__" in path.parts or any(part.endswith(".egg-info") for part in path.parts):
                continue
            if path.is_symlink():
                raise ValueError(f"Refusing source symlink: {path}")
            if path.is_file() and path.suffix in suffixes:
                files.append(path)
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing/unsafe public file: {path}")
    destination.mkdir(parents=True, exist_ok=False)
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New directory outside this repository")
    args = parser.parse_args()
    count = export(Path(__file__).resolve().parents[1], args.destination)
    print(f"Exported {count} public files to {args.destination}; no Git repository/remote created")


if __name__ == "__main__":
    main()
