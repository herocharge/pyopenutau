from pathlib import Path
import runpy

import pytest


ROOT = Path(__file__).parents[1]
AUDIT = runpy.run_path(str(ROOT / "scripts/check_dist.py"))
EXPORT = runpy.run_path(str(ROOT / "scripts/export_repo.py"))


def wheel_files():
    files = {f"pyopenutau/bridge/{name}": b"test" for name in AUDIT["BRIDGE"]}
    files.update({name: b"test" for name in (
        "pyopenutau/py.typed", "pyopenutau/__init__.py", "pyopenutau/vocal.py",
        "pyopenutau-0.3.0.dist-info/licenses/LICENSE", "pyopenutau-0.3.0.dist-info/licenses/NOTICE")})
    return files


def test_distribution_audit_requires_bridge_typing_and_attribution():
    files = wheel_files()
    AUDIT["audit_files"](files, wheel=True)
    for name in list(files):
        if name.endswith("vocal.py"):
            continue
        incomplete = {k: v for k, v in files.items() if k != name}
        with pytest.raises(ValueError):
            AUDIT["audit_files"](incomplete, wheel=True)


@pytest.mark.parametrize("name,data", [
    ("pyopenutau/sample.wav", b"audio"),
    ("pyopenutau/OpenUtau.Core.dll", b"engine"),
    ("pyopenutau/__pycache__/thing.pyc", b"cache"),
    ("../escape.py", b"unsafe"),
    ("pyopenutau/leak.json", b"/" + b"Users/" + b"someone/private.wav"),
])
def test_distribution_audit_rejects_private_or_generated_content(name, data):
    with pytest.raises(ValueError):
        AUDIT["audit_files"]({**wheel_files(), name: data}, wheel=True)


def test_public_export_is_standalone_and_refuses_existing_destination(tmp_path):
    destination = tmp_path / "public"
    count = EXPORT["export"](ROOT, destination)
    assert count > 30
    assert (destination / ".github/workflows/ci.yml").is_file()
    assert (destination / "src/pyopenutau/bridge/NuGet.Config").is_file()
    assert (destination / "LICENSE").is_file()
    for path in destination.rglob("*"):
        assert not path.is_symlink()
        assert path.suffix not in {".wav", ".whl", ".pyc", ".dll", ".dylib"}
        assert not {"__pycache__", "artifacts", "build", "dist"}.intersection(path.parts)
    with pytest.raises(FileExistsError):
        EXPORT["export"](ROOT, destination)
    with pytest.raises(ValueError, match="outside"):
        EXPORT["export"](ROOT, ROOT / "nested-export")
