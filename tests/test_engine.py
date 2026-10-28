from pathlib import Path
import os
import sys
import threading
import time

import pytest

from pyopenutau import CancellationToken, CoreError, EngineCancelled, EngineTimeout, OpenUtauEngine, Pitch, Project
from pyopenutau.engine import _locked, _process, _publish


def test_cancelled_before_start_needs_no_installation(tmp_path):
    token = CancellationToken()
    token.cancel()
    with OpenUtauEngine(tmp_path) as engine, pytest.raises(EngineCancelled):
        engine.capabilities(cancel=token)


def test_closed_session_and_missing_installation(tmp_path):
    engine = OpenUtauEngine(tmp_path)
    with pytest.raises(CoreError, match="Core.dll"):
        engine.capabilities()
    engine.close()
    with pytest.raises(CoreError, match="closed"):
        engine.capabilities()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_deadlines_rejected_without_starting_host(timeout):
    with OpenUtauEngine() as engine, pytest.raises(ValueError, match="timeout"):
        engine.capabilities(timeout=timeout)


def test_running_silent_process_can_be_cancelled():
    token = CancellationToken()
    timer = threading.Timer(.15, token.cancel)
    timer.start()
    began = time.monotonic()
    try:
        with pytest.raises(EngineCancelled):
            _process([sys.executable, "-c", "import time; time.sleep(30)"], dict(os.environ), began + 5, token)
    finally:
        timer.cancel()
    assert time.monotonic() - began < 3


def test_running_silent_process_has_deadline():
    began = time.monotonic()
    with pytest.raises(EngineTimeout):
        _process([sys.executable, "-c", "import time; time.sleep(30)"], dict(os.environ), began + .15, None)
    assert time.monotonic() - began < 3


def test_process_drains_both_pipes_and_propagates_callback_errors():
    seen = []
    _process([sys.executable, "-c", "import sys; print('event'); sys.stderr.write('x' * 100000)"],
             dict(os.environ), time.monotonic() + 5, None, seen.append)
    assert seen == ["event\n"]

    def broken(line):
        raise RuntimeError("callback failed")

    with pytest.raises(RuntimeError, match="callback failed"):
        _process([sys.executable, "-u", "-c", "import time; print('event'); time.sleep(30)"],
                 dict(os.environ), time.monotonic() + 5, None, broken)


def test_waiting_for_session_lock_remains_cancellable():
    lock = threading.Lock()
    lock.acquire()
    token = CancellationToken()
    timer = threading.Timer(.1, token.cancel)
    timer.start()
    try:
        with pytest.raises(EngineCancelled), _locked(lock, time.monotonic() + 5, token):
            pytest.fail("should not acquire occupied lock")
    finally:
        timer.cancel()
        lock.release()


def test_atomic_publish_preserves_existing_destination_and_refuses_races(tmp_path):
    source = tmp_path / "source.wav"
    destination = tmp_path / "out.wav"
    source.write_bytes(b"new data")
    destination.write_bytes(b"existing recording")
    with pytest.raises(FileExistsError):
        _publish(source, destination, overwrite=False)
    assert destination.read_bytes() == b"existing recording"
    assert not list(tmp_path.glob(".pyopenutau-*"))
    _publish(source, destination, overwrite=True)
    assert destination.read_bytes() == b"new data"
    assert source.read_bytes() == b"new data"


def test_render_existing_file_fails_before_any_host_or_bank_access(tmp_path):
    output = tmp_path / "original.wav"
    output.write_bytes(b"keep")
    with OpenUtauEngine(tmp_path) as engine, pytest.raises(FileExistsError):
        engine.render(Project(), output, singers={"singer": "missing-bank"})
    assert output.read_bytes() == b"keep"


def test_invalid_project_fails_before_build(tmp_path):
    project = Project()
    project.add_track().add_voice_part().add_note("a").duration_ticks = 0
    with OpenUtauEngine(tmp_path) as engine, pytest.raises(ValueError, match="duration_ticks"):
        engine.phonemize(project, singers={})


def test_oversized_project_fails_before_host_curve_allocation(tmp_path):
    project = Project(bpm=60)
    project.add_track().add_voice_part().add_note("a", length=7200)
    with OpenUtauEngine(tmp_path) as engine, pytest.raises(ValueError, match="one-hour"):
        engine.phonemize(project, singers={})


def test_native_non_utf8_logs_do_not_break_pipe_draining():
    seen = []
    _process([sys.executable, "-c", "import sys; sys.stdout.buffer.write(bytes([255,10]))"],
             dict(os.environ), time.monotonic() + 5, None, seen.append)
    assert seen == ["\ufffd\n"]


def test_missing_output_parent_and_non_bool_overwrite_fail_fast(tmp_path):
    with OpenUtauEngine(tmp_path) as engine:
        with pytest.raises(FileNotFoundError, match="Output directory"):
            engine.render(Project(), tmp_path / "missing" / "out.wav", singers={})
        with pytest.raises(ValueError, match="overwrite"):
            engine.render(Project(), tmp_path / "out.wav", singers={}, overwrite="yes")


def test_callback_reentrancy_and_close_are_rejected_instead_of_deadlocking(tmp_path):
    with OpenUtauEngine(tmp_path) as engine:
        with engine._operation(time.monotonic() + 5, None):
            with pytest.raises(CoreError, match="recursively"):
                engine.capabilities()
            with pytest.raises(CoreError, match="Cannot close"):
                engine.close()
        assert engine._owner_thread is None


def test_request_uses_snapshot_taken_before_callbacks(tmp_path, monkeypatch):
    import json
    import pyopenutau.engine as implementation
    (tmp_path / "OpenUtau.Core.dll").touch()
    monkeypatch.setattr(implementation.shutil, "which", lambda _: sys.executable)
    project = Project()
    note = project.add_track().add_voice_part().add_note("a", "C4")
    captured = []

    def fake_process(command, environment, deadline, cancel, on_line=None):
        if "build" in command:
            output = Path(command[command.index("-o") + 1])
            output.mkdir()
            (output / "CoreCheck.dll").touch()
        else:
            loaded = Project.load(command[-2])
            captured.append(loaded.tracks[0].parts[0].notes[0].pitch.midi)
            Path(command[-1]).with_name("result.json").write_text(json.dumps({"protocol_version": 1, "type": "result", "data": {
                "phonemes": [], "diagnostics": [], "core_version": "test protocol only"}}))
        return ""

    def edit_in_callback(event):
        note.pitch = Pitch(72)

    monkeypatch.setattr(implementation, "_process", fake_process)
    with OpenUtauEngine(tmp_path) as engine:
        engine.phonemize(project, singers={}, progress=edit_in_callback)
    assert note.pitch.midi == 72
    assert captured == [60]


def test_cancelled_partial_build_is_not_cached_as_a_working_host(tmp_path, monkeypatch):
    import json
    import pyopenutau.engine as implementation
    (tmp_path / "OpenUtau.Core.dll").touch()
    monkeypatch.setattr(implementation.shutil, "which", lambda _: sys.executable)
    attempts = []

    def interrupted_then_successful(command, environment, deadline, cancel, on_line=None):
        if "build" in command:
            output = Path(command[command.index("-o") + 1])
            attempts.append(output)
            output.mkdir()
            (output / "CoreCheck.dll").write_bytes(b"partial or completed build fixture")
            if len(attempts) == 1:
                raise EngineCancelled("simulated cancellation during compilation")
        else:
            Path(command[-1]).with_name("result.json").write_text(json.dumps({"protocol_version": 1,
                "type": "result", "data": {"singers": []}}))
        return ""

    monkeypatch.setattr(implementation, "_process", interrupted_then_successful)
    with OpenUtauEngine(tmp_path) as engine:
        with pytest.raises(EngineCancelled):
            engine.singers([])
        assert engine.singers([]) == ()
    assert len(attempts) == 2 and attempts[0] != attempts[1]
