"""Optional .NET compatibility checks using actual, separately installed OpenUtau.

This checker does not render; OpenUtauEngine provides the separate engine API.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from .project import Project


class CoreError(RuntimeError):
    """OpenUtau checking/engine execution was unavailable or rejected an operation."""


@dataclass(frozen=True)
class CoreCheckResult:
    core_version: str
    project_version: str
    supported_version: str
    tracks: int
    notes: int
    isolated_state: bool
    note_details: tuple[dict[str, Any], ...]
    scope: str


class OpenUtauCore:
    """Read-only bridge to OpenUtau's C# model, isolated from the Python process.

    Requires a .NET 8 SDK and OpenUtau's assembly directory. The desktop app's
    standard macOS location is detected; other installations pass assembly_dir.
    No command is silently downloaded or run at import/Project.save() time.
    """

    def __init__(self, assembly_dir: str | Path | None = None, *, dotnet: str = "dotnet") -> None:
        selected = assembly_dir if assembly_dir is not None else (
            os.environ.get("OPENUTAU_ASSEMBLY_DIR") or "/Applications/OpenUtau.app/Contents/MacOS")
        self.assembly_dir = Path(selected).expanduser().resolve()
        self.dotnet = dotnet

    def check(self, project: Project, *, timeout: float = 60) -> CoreCheckResult:
        """Deserialize and validate notes with real OpenUtau. Does NOT render audio."""
        if not (self.assembly_dir / "OpenUtau.Core.dll").is_file():
            raise CoreError(f"OpenUtau.Core.dll not found in {self.assembly_dir}")
        executable = shutil.which(self.dotnet)
        if executable is None:
            raise CoreError("Core checking requires the .NET 8 SDK; ordinary authoring does not")
        project.validate()
        with tempfile.TemporaryDirectory(prefix="pyopenutau-core-") as directory:
            root = Path(directory)
            for source in (Path(__file__).parent / "bridge").iterdir():
                if source.is_file():
                    shutil.copyfile(source, root / source.name)
            path = project.save(root / "project.ustx")
            environment = {**os.environ, "DOTNET_CLI_HOME": str(root / "dotnet-home"),
                           "NUGET_PACKAGES": str(root / "nuget"), "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
                           "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
            try:
                build = subprocess.run([executable, "build", str(root / "CoreCheck.csproj"),
                                        "-o", str(root / "out"), "--nologo", "-v", "quiet"],
                                       capture_output=True, text=True, env=environment, timeout=timeout)
                if build.returncode:
                    raise CoreError(f"Cannot build OpenUtau probe: {build.stdout[-2000:]} {build.stderr[-2000:]}")
                result = subprocess.run([executable, str(root / "out/CoreCheck.dll"), str(self.assembly_dir), str(path)],
                                        capture_output=True, text=True, env=environment, timeout=timeout)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise CoreError(f"OpenUtau probe did not complete: {error}") from error
            if result.returncode:
                raise CoreError(f"OpenUtau core rejected the project: {result.stderr[-4000:]}")
            try:
                data = json.loads(result.stdout.strip().splitlines()[-1])
                data["note_details"] = tuple(data["note_details"])
                return CoreCheckResult(**data)
            except (ValueError, TypeError, IndexError, KeyError) as error:
                raise CoreError("OpenUtau probe returned an invalid response") from error
