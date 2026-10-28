"""Synchronous, cancellable headless sessions backed by actual OpenUtau."""

from __future__ import annotations

from _thread import LockType
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from typing import Any, Iterator, Literal, TextIO

from .core import CoreError, OpenUtauCore
from .project import Project


class EngineCancelled(CoreError):
    """Cancelled before an output was published."""


class EngineTimeout(CoreError):
    """Build plus engine execution exceeded the operation deadline."""


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class EngineProgress:
    stage: Literal["building", "phonemizing", "rendering", "complete"]
    fraction: float | None = None


ProgressCallback = Callable[[EngineProgress], None]


@dataclass(frozen=True)
class SingerInfo:
    id: str
    name: str
    path: Path
    singer_type: str


@dataclass(frozen=True)
class OtoInfo:
    alias: str
    sample_path: Path
    offset_ms: float
    consonant_ms: float
    cutoff_ms: float
    preutter_ms: float
    overlap_ms: float


@dataclass(frozen=True)
class PhonemizerInfo:
    class_name: str
    name: str
    tag: str
    language: str | None


@dataclass(frozen=True)
class EngineCapabilities:
    core_version: str
    supported_version: str
    renderers: tuple[str, ...]
    phonemizers: tuple[PhonemizerInfo, ...]


@dataclass(frozen=True)
class EngineDiagnostic:
    code: str
    severity: Literal["error", "warning"]
    message: str
    track_index: int
    part_index: int
    note_index: int


@dataclass(frozen=True)
class PhonemeInfo:
    track_index: int
    part_index: int
    note_index: int
    phoneme_index: int
    phoneme: str
    mapped_alias: str | None
    position_ticks: int  # part-local, including negative consonant lead-ins
    duration_ticks: int
    position_ms: float  # project-absolute
    duration_ms: float
    preutter_ms: float
    overlap_ms: float
    sample_path: Path | None
    error: bool


@dataclass(frozen=True)
class PhonemizationResult:
    phonemes: tuple[PhonemeInfo, ...]
    diagnostics: tuple[EngineDiagnostic, ...]
    core_version: str

    @property
    def has_errors(self) -> bool:
        return any(d.severity == "error" for d in self.diagnostics)


@dataclass(frozen=True)
class RenderResult:
    output: Path
    sample_rate: int
    channels: int
    frames: int
    peak_abs: float
    core_version: str
    project_sha256: str
    diagnostics: tuple[EngineDiagnostic, ...]

    @property
    def duration_seconds(self) -> float:
        return self.frames / self.sample_rate


def _check_stop(deadline: float, cancel: CancellationToken | None) -> None:
    if cancel is not None and cancel.cancelled:
        raise EngineCancelled("OpenUtau operation cancelled; no output published")
    if time.monotonic() >= deadline:
        raise EngineTimeout("OpenUtau operation exceeded its build/execution deadline")


@contextmanager
def _locked(lock: LockType, deadline: float, cancel: CancellationToken | None) -> Iterator[None]:
    while not lock.acquire(timeout=.05):
        _check_stop(deadline, cancel)
    try:
        _check_stop(deadline, cancel)
        yield
    finally:
        lock.release()


def _process(command: list[str], environment: dict[str, str], deadline: float,
             cancel: CancellationToken | None, on_line: Callable[[str], None] | None = None) -> str:
    """Drain both pipes, checking cancellation even when the engine is silent."""
    _check_stop(deadline, cancel)
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace", env=environment,
                                   start_new_session=os.name != "nt")
    except OSError as error:
        raise CoreError(f"Cannot start OpenUtau host command: {error}") from error
    lines: queue.Queue[tuple[str, str | None]] = queue.Queue()

    def read(stream: TextIO, name: str) -> None:
        try:
            for line in stream:
                lines.put((name, line))
        finally:
            stream.close()
            lines.put((name, None))

    assert process.stdout is not None and process.stderr is not None
    readers = [threading.Thread(target=read, args=(stream, name), daemon=True)
               for stream, name in ((process.stdout, "out"), (process.stderr, "err"))]
    for reader in readers:
        reader.start()
    tails: dict[str, str] = {"out": "", "err": ""}
    ended = 0
    try:
        while ended < 2 or process.poll() is None:
            _check_stop(deadline, cancel)
            try:
                name, line = lines.get(timeout=.05)
            except queue.Empty:
                continue
            if line is None:
                ended += 1
            else:
                tails[name] = (tails[name] + line)[-16000:]
                if name == "out" and on_line is not None:
                    on_line(line)
        if process.returncode:
            raise CoreError(f"OpenUtau host failed ({process.returncode}): {tails['err'] or tails['out']}")
        return tails["out"]
    finally:
        if process.poll() is None:
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
        process.wait()
        for reader in readers:
            reader.join(timeout=1)


def _publish(source: Path, destination: Path, *, overwrite: bool) -> None:
    """Stage on the destination filesystem, publish atomically, refuse races."""
    staging: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".pyopenutau-", delete=False) as stream:
            staging = Path(stream.name)
            with source.open("rb") as incoming:
                shutil.copyfileobj(incoming, stream)
        if overwrite:
            os.replace(staging, destination)
        else:
            os.link(staging, destination)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)


class OpenUtauEngine:
    """A reusable host build with fresh, isolated OpenUtau state per operation.

    Use as a context manager. Sessions serialize calls; distinct sessions can
    run in parallel. Local singer bindings never change desktop registration.
    """

    def __init__(self, assembly_dir: str | Path | None = None, *, dotnet: str = "dotnet") -> None:
        self.core = OpenUtauCore(assembly_dir, dotnet=dotnet)
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._host_path: Path | None = None
        self._lock = threading.Lock()
        self._closed = False
        self._owner_thread: int | None = None

    def __enter__(self) -> OpenUtauEngine:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owner_thread == threading.get_ident():
            raise CoreError("Cannot close a session from its own progress callback; cancel the operation instead")
        with self._lock:
            if self._temporary is not None:
                self._temporary.cleanup()
                self._temporary = None
                self._host_path = None
            self._closed = True

    @contextmanager
    def _operation(self, deadline: float, cancel: CancellationToken | None) -> Iterator[None]:
        if self._owner_thread == threading.get_ident():
            raise CoreError("Cannot recursively call the same engine from its progress callback")
        with _locked(self._lock, deadline, cancel):
            self._owner_thread = threading.get_ident()
            try:
                yield
            finally:
                self._owner_thread = None

    def _request(self, spec: dict[str, Any], project: Project | None, *, timeout: float,
                 cancel: CancellationToken | None, progress: ProgressCallback | None,
                 output: Path | None = None, overwrite: bool = False) -> dict[str, Any]:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        deadline = time.monotonic() + timeout
        _check_stop(deadline, cancel)
        snapshot = (project or Project()).to_document()
        if spec["mode"] in ("phonemize", "render"):
            end_tick = max((part["position"] + note["position"] + note["duration"]
                            for part in snapshot["voice_parts"] for note in part["notes"]), default=0)
            if Project.from_document(snapshot).seconds_at(end_tick / 480) >= 3600:
                raise ValueError("Headless projects must be shorter than the one-hour safety limit")
        with self._operation(deadline, cancel):
            _check_stop(deadline, cancel)
            if self._closed:
                raise CoreError("OpenUtauEngine session is closed")
            if not (self.core.assembly_dir / "OpenUtau.Core.dll").is_file():
                raise CoreError(f"OpenUtau.Core.dll not found in {self.core.assembly_dir}")
            executable = shutil.which(self.core.dotnet)
            if executable is None:
                raise CoreError("Headless operations require a .NET 8 SDK")
            if self._temporary is None:
                self._temporary = tempfile.TemporaryDirectory(prefix="pyopenutau-engine-")
            root = Path(self._temporary.name)
            environment = {**os.environ, "DOTNET_CLI_HOME": str(root / "dotnet-home"),
                           "NUGET_PACKAGES": str(root / "nuget"), "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                           "DOTNET_NOLOGO": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1"}
            if self._host_path is None:
                # A cancelled build may leave a partial DLL/assets file. Never
                # treat file existence as successful compilation or reuse that
                # attempt's intermediate files on the next operation.
                build_root = Path(tempfile.mkdtemp(prefix="build-", dir=root))
                for source in (Path(__file__).parent / "bridge").iterdir():
                    if source.is_file():
                        shutil.copyfile(source, build_root / source.name)
                if progress is not None:
                    progress(EngineProgress("building"))
                _process([executable, "build", str(build_root / "CoreCheck.csproj"), "-o", str(build_root / "out"),
                          "--nologo", "-v", "quiet", "--disable-build-servers", "-p:UseSharedCompilation=false"], environment, deadline, cancel)
                host_path = build_root / "out/CoreCheck.dll"
                if not host_path.is_file():
                    raise CoreError("Host build completed without producing its assembly")
                self._host_path = host_path
            with tempfile.TemporaryDirectory(prefix="job-", dir=root) as job_directory:
                job = Path(job_directory)
                project_path = Project.from_document(snapshot).save(job / "project.ustx")
                if spec["mode"] == "render":
                    spec = {**spec, "output": str(job / "render.wav")}
                request_path = job / "request.json"
                request_path.write_text(json.dumps({**spec, "protocol_version": 1}), encoding="utf-8")
                def receive(line: str) -> None:
                    try:
                        message = json.loads(line)
                    except ValueError:
                        return  # Native libraries may log non-protocol lines.
                    if not isinstance(message, dict):
                        return
                    if message.get("protocol_version") == 1 and message.get("type") == "progress" and progress is not None:
                        progress(EngineProgress(message["stage"], message.get("fraction")))

                _process([executable, str(self._host_path), str(self.core.assembly_dir),
                          str(project_path), str(request_path)], environment, deadline, cancel, receive)
                _check_stop(deadline, cancel)
                try:
                    envelope = json.loads((job / "result.json").read_text(encoding="utf-8"))
                    if envelope.get("protocol_version") != 1 or envelope["type"] != "result" or not isinstance(envelope["data"], dict):
                        raise ValueError("invalid response envelope")
                    response: dict[str, Any] = envelope["data"]
                except (OSError, ValueError, KeyError, TypeError) as error:
                    raise CoreError("OpenUtau host returned no valid typed result") from error
                if progress is not None:
                    progress(EngineProgress("complete", 1))
                _check_stop(deadline, cancel)
                if output is not None:
                    _publish(job / "render.wav", output, overwrite=overwrite)
                    response["project_sha256"] = hashlib.sha256(project_path.read_bytes()).hexdigest()
                return response

    def capabilities(self, *, timeout: float = 60, cancel: CancellationToken | None = None) -> EngineCapabilities:
        data = self._request({"mode": "capabilities"}, None, timeout=timeout, cancel=cancel, progress=None)
        return EngineCapabilities(data["core_version"], data["supported_version"], tuple(data["renderers"]),
                                  tuple(PhonemizerInfo(**p) for p in data["phonemizers"]))

    def singers(self, search_paths: str | Path | Sequence[str | Path], *, timeout: float = 60,
                cancel: CancellationToken | None = None) -> tuple[SingerInfo, ...]:
        roots = [search_paths] if isinstance(search_paths, (str, Path)) else search_paths
        paths = [str(Path(path).expanduser().resolve(strict=True)) for path in roots]
        if any(not Path(path).is_dir() for path in paths):
            raise ValueError("Singer search paths must be directories")
        data = self._request({"mode": "singers", "search_paths": paths}, None,
                             timeout=timeout, cancel=cancel, progress=None)
        return tuple(SingerInfo(s["id"], s["name"], Path(s["path"]), s["singer_type"]) for s in data["singers"])

    def otos(self, bank_path: str | Path, *, timeout: float = 60,
             cancel: CancellationToken | None = None) -> tuple[OtoInfo, ...]:
        path = self._bindings({"bank": bank_path})["bank"]
        data = self._request({"mode": "otos", "path": path}, None, timeout=timeout, cancel=cancel, progress=None)
        return tuple(OtoInfo(**{**oto, "sample_path": Path(oto["sample_path"])}) for oto in data["otos"])

    @staticmethod
    def _bindings(singers: Mapping[str, str | Path]) -> dict[str, str]:
        result = {}
        for name, path in singers.items():
            if not isinstance(name, str) or not name:
                raise ValueError("Singer binding IDs must be nonempty strings")
            root = Path(path).expanduser().resolve(strict=True)
            if not (root / "character.txt").is_file():
                raise ValueError(f"Singer path needs character.txt: {root}")
            result[name] = str(root)
        return result

    def phonemize(self, project: Project, *, singers: Mapping[str, str | Path], timeout: float = 120,
                  cancel: CancellationToken | None = None, progress: ProgressCallback | None = None) -> PhonemizationResult:
        data = self._request({"mode": "phonemize", "singers": self._bindings(singers)}, project,
                             timeout=timeout, cancel=cancel, progress=progress)
        return PhonemizationResult(tuple(PhonemeInfo(**{**p, "sample_path": Path(p["sample_path"])
                                                        if p["sample_path"] is not None else None}) for p in data["phonemes"]),
                                   tuple(EngineDiagnostic(**d) for d in data["diagnostics"]), data["core_version"])

    def render(self, project: Project, output: str | Path, *, singers: Mapping[str, str | Path],
               timeout: float = 300, cancel: CancellationToken | None = None,
               progress: ProgressCallback | None = None, overwrite: bool = False) -> RenderResult:
        destination = Path(output).expanduser().absolute()
        if type(overwrite) is not bool:
            raise ValueError("overwrite must be bool")
        if not overwrite and destination.exists():
            raise FileExistsError(destination)
        if not destination.parent.is_dir():
            raise FileNotFoundError(f"Output directory does not exist: {destination.parent}")
        data = self._request({"mode": "render", "singers": self._bindings(singers)}, project,
                             timeout=timeout, cancel=cancel, progress=progress, output=destination, overwrite=overwrite)
        return RenderResult(destination, data["sample_rate"], data["channels"], data["frames"], data["peak_abs"],
                            data["core_version"], data["project_sha256"], tuple(EngineDiagnostic(**d) for d in data["diagnostics"]))
