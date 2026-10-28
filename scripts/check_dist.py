"""Audit built wheels/source distributions without extracting or importing them."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile


BRIDGE = {"Program.cs", "EngineHost.cs", "CoreCheck.csproj", "NuGet.Config"}
FORBIDDEN_SUFFIXES = {".wav", ".mp3", ".flac", ".dll", ".so", ".dylib", ".pyc", ".pyo"}
FORBIDDEN_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "artifacts", ".git"}
PRIVATE_PATH = re.compile(rb"/(?:Users|home)/[A-Za-z0-9_.-]+/")


def audit_files(files: dict[str, bytes], *, wheel: bool) -> None:
    for name, data in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe archive path: {name}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or FORBIDDEN_PARTS.intersection(path.parts):
            raise ValueError(f"Local/binary artifact in distribution: {name}")
        if PRIVATE_PATH.search(data):
            raise ValueError(f"Personal absolute path in distribution: {name}")
    root = "pyopenutau" if wheel else "src/pyopenutau"
    required = {f"{root}/py.typed", f"{root}/__init__.py", f"{root}/vocal.py"}
    required.update(f"{root}/bridge/{name}" for name in BRIDGE)
    if not wheel:
        required.update({"pyproject.toml", "README.md", "HEADLESS.md", "CONTRIBUTING.md",
                         "examples/synthetic.py", "tests/conftest.py", "LICENSE", "NOTICE"})
    missing = required.difference(files)
    if missing:
        raise ValueError(f"Required files missing: {sorted(missing)}")
    for notice in ("LICENSE", "NOTICE"):
        if not any(PurePosixPath(name).name == notice for name in files):
            raise ValueError(f"Missing license/attribution: {notice}")


def check(path: Path) -> None:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
        audit_files(files, wheel=True)
    else:
        with tarfile.open(path, "r:gz") as archive:
            files = {}
            for member in archive.getmembers():
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError(f"Nonregular archive member: {member.name}")
                parts = PurePosixPath(member.name).parts
                if len(parts) < 2 or ".." in parts or PurePosixPath(member.name).is_absolute():
                    raise ValueError(f"Unsafe source archive path: {member.name}")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError(f"Unreadable member: {member.name}")
                files[str(PurePosixPath(*parts[1:]))] = stream.read()
        audit_files(files, wheel=False)
    print(f"PASS {path.name}: {len(files)} files; bridge, typing and notices present; no local media/binaries/paths")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    wheels = sorted(args.directory.glob("*.whl"))
    sources = sorted(args.directory.glob("*.tar.gz"))
    if not wheels or not sources:
        parser.error("Expected both a wheel and a source tarball")
    for path in [*wheels, *sources]:
        check(path)


if __name__ == "__main__":
    main()
