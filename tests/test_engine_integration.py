"""Real OpenUtau execution against generated signals, never the old cover files."""

import hashlib
from pathlib import Path
import wave

import pytest

from pyopenutau import (CancellationToken, CoreError, EngineCancelled, OpenUtauEngine,
                       PhonemeOverride, PitchCurve, PitchPoint, Project, Vocal)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def np():
    return pytest.importorskip("numpy")


@pytest.fixture(scope="module")
def bank(tmp_path_factory, np):
    root = tmp_path_factory.mktemp("headless-bank") / "synth"
    root.mkdir()
    (root / "character.txt").write_text("name=Known synthetic singer\n", encoding="utf-8")
    (root / "oto.ini").write_text("\n".join(f"a.wav={alias},0,40,-800,20,10" for alias in ("a", "- a", "a a")), encoding="utf-8")
    t = np.arange(44100) / 44100
    # A broadband periodic source retains usable spectral-envelope energy at
    # higher target pitches; a near-pure 220 Hz sine has none around 880 Hz.
    samples = sum(.12 / h * np.sin(2 * np.pi * 220 * h * t) for h in range(1, 13))
    with wave.open(str(root / "a.wav"), "wb") as writer:
        writer.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
        writer.writeframes((samples * 32767).astype("<i2").tobytes())
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    yield root
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    assert after == before, "Host modified the input voicebank or wrote analysis files into it"


@pytest.fixture(scope="module")
def engine():
    with OpenUtauEngine() as instance:
        yield instance


def song():
    project = Project("Synthetic authoring test", bpm=120)
    part = project.add_track("Lead", singer="local").add_voice_part(beat=1)
    part.add_note("a", "A4", length=1)
    return project


def read_float_wav(path, np):
    import struct
    data = path.read_bytes()
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    assert struct.unpack_from("<H", data, 20)[0] == 3
    return np.frombuffer(data[44:], dtype="<f4").reshape(-1, 2)


def dominant_hz(samples, np):
    x = samples - samples.mean()
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.fft.rfftfreq(len(x), 1 / 44100)[np.argmax(spec)]


def test_discovery_and_capabilities_use_real_core(engine, bank):
    cap = engine.capabilities()
    assert "WORLDLINE-R" in cap.renderers
    assert any(p.class_name == "OpenUtau.Core.DefaultPhonemizer" for p in cap.phonemizers)
    singers = engine.singers([bank.parent, bank])  # overlapping search roots do not duplicate a bank
    assert len(singers) == 1
    assert singers[0].name == "Known synthetic singer"
    assert singers[0].path.resolve() == bank.resolve()
    otos = engine.otos(bank)
    assert {o.alias for o in otos} == {"a", "- a", "a a"}
    assert otos[0].sample_path.resolve() == (bank / "a.wav").resolve()
    assert otos[0].consonant_ms == 40


def test_builtin_phonemizer_uses_real_context_instead_of_default_aliases(engine, bank):
    project = song()
    project.tracks[0].phonemizer = "OpenUtau.Plugin.Builtin.JapaneseVCVPhonemizer"
    project.tracks[0].parts[0].add_note("a", "B4")
    result = engine.phonemize(project, singers={"local": bank})
    assert not result.diagnostics
    assert [p.mapped_alias for p in result.phonemes] == ["- a", "a a"]


def test_vocal_shortcut_renders_with_owned_and_borrowed_sessions(engine, bank, tmp_path, np):
    vocal = Vocal(bank)
    vocal.add_note("a", "A4", beat=1)
    vocal.track.pan = -100
    result = vocal.render(tmp_path / "vocal.wav")
    audio = read_float_wav(result.output, np)
    assert np.isfinite(audio).all()
    assert abs(dominant_hz(audio[28000:38000, 0], np) - 440) < 8
    assert result.duration_seconds >= 1
    with pytest.raises(FileExistsError):
        vocal.render(result.output)
    with pytest.raises(FileNotFoundError):
        vocal.render(tmp_path / "missing-parent" / "vocal.wav")
    assert vocal.phonemize(engine=engine).phonemes[0].mapped_alias == "a"
    vocal.render(tmp_path / "borrowed.wav", engine=engine)
    assert engine.capabilities().renderers  # the borrowed session was not closed


def test_phonemization_absolute_timing_and_native_override(engine, bank):
    project = song()
    project.set_tempo(1, 60)
    part = project.tracks[0].parts[0]
    part.notes[0].phoneme_overrides.append(PhonemeOverride(index=0, offset_ticks=48, preutter_delta_ms=5))
    before = project.to_document()
    result = engine.phonemize(project, singers={"local": bank})
    assert not result.diagnostics and len(result.phonemes) == 1
    phoneme = result.phonemes[0]
    assert phoneme.mapped_alias == "a" and not phoneme.error
    assert phoneme.position_ticks == 48
    assert phoneme.position_ms == pytest.approx(600)  # 500 ms part offset + 100 ms at 60 BPM
    assert phoneme.preutter_ms == pytest.approx(25)
    assert Path(phoneme.sample_path).resolve() == (bank / "a.wav").resolve()
    assert project.to_document() == before


def test_missing_alias_returns_structured_diagnostics_and_render_refuses(engine, bank, tmp_path):
    project = song()
    project.tracks[0].parts[0].notes[0].lyric = "not-an-alias"
    result = engine.phonemize(project, singers={"local": bank})
    assert any(d.code == "phoneme_error" and d.severity == "error" for d in result.diagnostics)
    output = tmp_path / "not-created.wav"
    with pytest.raises(CoreError, match="Phonemization errors"):
        engine.render(project, output, singers={"local": bank})
    assert not output.exists()


def test_real_engine_render_respects_pitch_timeline_and_pan(engine, bank, tmp_path, np):
    project = song()
    project.tracks[0].pan = -100
    progress = []
    output = tmp_path / "tone.wav"
    result = engine.render(project, output, singers={"local": bank}, progress=progress.append)
    audio = read_float_wav(output, np)
    assert result.sample_rate == 44100 and result.channels == 2
    assert result.frames == len(audio)
    assert 1 <= result.duration_seconds <= 1.1
    assert np.isfinite(audio).all() and np.max(np.abs(audio)) > .02
    assert np.max(np.abs(audio[:18000])) < 1e-7  # real lead-in, not shifted to time zero
    assert np.max(np.abs(audio[:, 1])) < 1e-7  # hard-left pan through OpenUtau fader
    assert abs(dominant_hz(audio[28000:38000, 0], np) - 440) < 8
    assert result.project_sha256
    assert [p.stage for p in progress] == ["phonemizing", "rendering", "complete"]


def test_pitch_bend_is_executed_by_the_full_engine(engine, bank, tmp_path, np):
    project = song()
    note = project.tracks[0].parts[0].notes[0]
    note.portamento = PitchCurve([PitchPoint(-5, 1200), PitchPoint(5, 1200)], snap_first=False)
    output = tmp_path / "bent.wav"
    engine.render(project, output, singers={"local": bank})
    audio = read_float_wav(output, np)
    assert abs(dominant_hz(audio[28000:38000, 0], np) - 880) < 10


def test_solo_is_applied_without_gui_state_initialization(engine, bank, tmp_path, np):
    project = song()
    project.tracks[0].pan = -100
    second = project.add_track("Solo", singer="local")
    second.solo = True
    second.pan = 100
    second.add_voice_part(beat=1).add_note("a", "A5")
    output = tmp_path / "solo.wav"
    engine.render(project, output, singers={"local": bank})
    audio = read_float_wav(output, np)
    assert np.max(np.abs(audio[:, 0])) < 1e-7
    assert abs(dominant_hz(audio[28000:38000, 1], np) - 880) < 10


def test_muting_all_tracks_is_an_intentional_silent_render(engine, bank, tmp_path, np):
    project = song()
    project.tracks[0].mute = True
    result = engine.render(project, tmp_path / "muted.wav", singers={"local": bank})
    audio = read_float_wav(result.output, np)
    assert result.frames in (44100, 44101)  # Native export may retain one tail sample.
    assert not audio.any()


def test_part_automation_and_track_volume_reach_the_engine(engine, bank, tmp_path, np):
    project = song()
    project.tracks[0].parts[0].curve("pitd").set(0, 200).set(1, 200)
    loud = engine.render(project, tmp_path / "loud.wav", singers={"local": bank})
    loud_audio = read_float_wav(loud.output, np)[28000:38000, 0]
    assert abs(dominant_hz(loud_audio, np) - 440 * 2 ** (2 / 12)) < 8
    project.tracks[0].volume_db = -6
    quiet = engine.render(project, tmp_path / "quiet.wav", singers={"local": bank})
    quiet_audio = read_float_wav(quiet.output, np)[28000:38000, 0]
    ratio = np.sqrt(np.mean(quiet_audio ** 2) / np.mean(loud_audio ** 2))
    assert .43 < ratio < .57


def test_track_local_part_indices_are_not_global_part_indices(engine, bank):
    project = song()
    project.tracks[0].add_voice_part(beat=3).add_note("a")
    project.add_track(singer="local").add_voice_part(beat=1).add_note("a")
    project.add_track("Empty unassigned track")
    result = engine.phonemize(project, singers={"local": bank})
    assert {(p.track_index, p.part_index) for p in result.phonemes} == {(0, 0), (0, 1), (1, 0)}


def test_cancellation_during_engine_operation_never_publishes(engine, bank, tmp_path):
    token = CancellationToken()
    output = tmp_path / "cancelled.wav"

    def cancel_on_event(event):
        if event.stage == "phonemizing":
            token.cancel()

    with pytest.raises(EngineCancelled):
        engine.render(song(), output, singers={"local": bank}, cancel=token, progress=cancel_on_event)
    assert not output.exists()
    assert engine.phonemize(song(), singers={"local": bank}).phonemes  # session remains usable


def test_unsupported_configuration_and_missing_binding_are_explicit(engine, bank, tmp_path):
    with pytest.raises(CoreError, match="No singer binding"):
        engine.phonemize(song(), singers={})
    project = song()
    project.tracks[0].render_settings.renderer = "not-supported"
    with pytest.raises(CoreError, match="Unsupported headless renderer"):
        engine.render(project, tmp_path / "missing.wav", singers={"local": bank})
    project.tracks[0].render_settings.renderer = None
    project.tracks[0].render_settings.resampler = "external.exe"
    with pytest.raises(CoreError, match="Unsupported headless resampler"):
        engine.render(project, tmp_path / "missing.wav", singers={"local": bank})
    assert not (tmp_path / "missing.wav").exists()


def test_float_mix_retains_over_scale_peaks_and_warns(engine, bank, tmp_path, np):
    project = song()
    project.tracks[0].volume_db = 40
    result = engine.render(project, tmp_path / "over-scale.wav", singers={"local": bank})
    audio = read_float_wav(result.output, np)
    assert result.peak_abs > 1 and np.max(np.abs(audio)) == pytest.approx(result.peak_abs)
    assert any(d.code == "peak_above_full_scale" and d.severity == "warning" for d in result.diagnostics)
