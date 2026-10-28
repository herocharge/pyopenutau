"""Keep portable tests independent; opt into a provisioned engine explicitly."""

import os
from pathlib import Path
import shutil

import pytest


def pytest_addoption(parser):
    parser.addoption("--run-integration", action="store_true", default=False,
                     help="Require and test the local OpenUtau/.NET installation")


def pytest_collection_modifyitems(config, items):
    integration = [item for item in items if item.get_closest_marker("integration")]
    if not integration:
        return
    if not config.getoption("--run-integration"):
        skip = pytest.mark.skip(reason="Use --run-integration with OpenUtau and a .NET 8 SDK")
        for item in integration:
            item.add_marker(skip)
        return
    root = Path(os.environ.get("OPENUTAU_ASSEMBLY_DIR") or "/Applications/OpenUtau.app/Contents/MacOS").expanduser()
    if not shutil.which("dotnet") or not (root / "OpenUtau.Core.dll").is_file():
        raise pytest.UsageError(
            "--run-integration requires dotnet on PATH and OpenUtau.Core.dll; "
            "set OPENUTAU_ASSEMBLY_DIR to your OpenUtau assembly directory")
