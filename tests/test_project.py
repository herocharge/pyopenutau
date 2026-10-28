from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from pyopenutau import (
    AutomationCurve, CurvePoint, ExpressionDescriptor, ExpressionKind, Note,
    PhonemeOverride, Pitch, PitchCurve, PitchPoint, PitchShape, Project, Tempo,
    TimeSignature, ValidationError,
)


def composition():
    project = Project("From scratch", bpm=140)
    lead = project.add_track("Lead", singer="registered-id")
    part = lead.add_voice_part("Verse", beat=4)
    note = part.add_note("あ", "C#4", length=1.5)
    note.portamento = PitchCurve([PitchPoint(-50, -100, PitchShape.LINEAR), PitchPoint(100, 0)], False)
    note.vibrato.length_percent = 60
    note.set_expression("vel", 125).set_expression("vol", 90, phoneme_index=1)
    note.phoneme_overrides.append(PhonemeOverride(0, "- あ", 0, 12.5, -3))
    part.add_note("+", "D4", beat=2, length=1)
    part.curve("dyn").set(0, -60).set(1, 0).set(3, -30)
    harmony = project.add_track("Harmony")
    harmony.parts.append(part.clone(transpose=7, at_beat=8))
    project.set_tempo(8, 110)
    project.time_signatures.append(TimeSignature(4, 3, 4))
    return project


@pytest.mark.parametrize("name,midi", [("C4", 60), ("C#4", 61), ("Db4", 61), ("B#3", 60),
                                      ("C-1", 0), ("G9", 127), ("f♯3", 54), ("B♭3", 58)])
def test_pitch_names(name, midi):
    assert Pitch.parse(name).midi == midi
    assert Pitch.parse(str(Pitch(midi))) == Pitch(midi)


@pytest.mark.parametrize("bad", [True, 60.5, -1, 128, "H4", "C", "C10", "R", "C4 garbage"])
def test_invalid_pitch_rejected(bad):
    with pytest.raises(ValueError):
        Pitch.parse(bad)


def test_author_append_pause_and_explicit_tick_layer():
    project = Project()
    part = project.add_track().add_voice_part(beat=3)
    assert part.add_note("a", "C4").position_ticks == 0
    assert part.add_note("b", 62, length=.5).position_ticks == 480
    assert part.add_note("c", "E4", beat=2).position_ticks == 960
    assert part.position_ticks == 1440
    part.notes.append(Note("d", Pitch(65), position_ticks=1440, duration_ticks=120))
    project.validate()
    assert part.effective_duration_ticks == 1560
    with pytest.raises(ValueError, match="overlap"):
        part.add_note("x", beat=.5)
    with pytest.raises(ValueError, match="duration_ticks"):
        part.add_note("x", length=.001)


def test_roundtrip_and_native_unit_conversion(tmp_path):
    project = composition()
    path = project.save(tmp_path / "song.ustx")
    document = yaml.safe_load(path.read_text())
    assert document["ustx_version"] == "0.7"
    assert len(document["exp_selectors"]) == 10
    note = document["voice_parts"][0]["notes"][0]
    assert note["tone"] == 61
    assert note["pitch"]["data"][0] == {"x": -50, "y": -10, "shape": "l"}
    assert note["phoneme_overrides"][0]["offset"] == 0
    assert note["phoneme_overrides"][0]["preutter_delta"] == 12.5
    assert Project.load(path).to_document() == document
    assert project.to_document() == document  # exporting did not mutate the authoring objects


def test_unknown_fields_survive_at_every_modeled_level_and_track_reorder():
    doc = composition().to_document()
    doc["future_root"] = {"settings": [1, "x"]}
    doc["tracks"][0]["mix_fx"] = {"enabled": True, "future": 7}
    doc["tracks"][0]["renderer_settings"]["new_render_flag"] = 5
    part = doc["voice_parts"][0]
    part["new_part"] = True
    part["curves"][0]["new_curve"] = 9
    note = part["notes"][0]
    note["phonemizer"] = "Some future note override"
    note["pitch"]["future_pitch"] = True
    note["pitch"]["data"][0]["future_point"] = 1
    note["vibrato"]["future_vibrato"] = 2
    note["phoneme_overrides"][0]["future_override"] = 3
    note["phoneme_expressions"][0]["future_value"] = 4
    doc["expressions"]["vel"]["_custom_default_value"] = 115
    doc["tempos"][0]["future_tempo"] = 12
    doc["time_signatures"][0]["future_meter"] = 13
    doc["wave_parts"] = [{"track_no": 0, "position": 480, "file_path": "backing.wav", "future_wave": 6}]
    untouched = deepcopy(doc)
    project = Project.from_document(doc)
    assert project.to_document() == untouched
    assert doc == untouched
    project.tracks.reverse()
    result = project.to_document()
    assert result["tracks"][1]["mix_fx"]["future"] == 7
    assert result["wave_parts"][0]["track_no"] == 1
    assert next(p for p in result["voice_parts"] if p["name"] == "Verse" and p["position"] == 1920)["track_no"] == 1


def test_clones_are_independent_and_transpose_is_atomic():
    project = composition()
    original = project.tracks[0].parts[0]
    cloned = project.tracks[1].parts[0]
    cloned.notes[0].portamento.points[0].cents = -200
    cloned.notes[0].vibrato.depth_cents = 70
    assert original.notes[0].portamento.points[0].cents == -100
    assert original.notes[0].vibrato.depth_cents == 25
    assert cloned.notes[0].pitch.midi == original.notes[0].pitch.midi + 7
    before = project.to_document()
    with pytest.raises(ValueError):
        original.clone(transpose=100)
    assert project.to_document() == before


def test_tempo_map_positions_and_inverse():
    project = Project(bpm=120).set_tempo(4, 60).set_tempo(6, 180)
    assert project.seconds_at(4) == 2
    assert project.seconds_at(6) == 4
    assert project.seconds_at(9) == 5
    for beat in (0, 1, 3.5, 4, 5.5, 6, 9, 20):
        assert project.beat_at(project.seconds_at(beat)) == pytest.approx(beat)
    project.bpm = 100
    assert len(project.tempos) == 3
    assert project.tempos[0] == Tempo(0, 100)


def test_custom_expressions_and_track_descriptor_override():
    project = Project()
    track = project.add_track()
    note = track.add_voice_part().add_note("a")
    project.expressions["fx"] = ExpressionDescriptor("Effect", "fx", minimum=-5, maximum=5)
    note.set_expression("fx", 3)
    track.expressions.append(ExpressionDescriptor("Velocity", "vel", minimum=0, maximum=300, default=100))
    note.set_expression("vel", 250)
    project.validate()
    project.expressions["fxc"] = ExpressionDescriptor("Effect curve", "fxc", ExpressionKind.CURVE, -20, 20)
    track.parts[0].curve("fxc").set(0, 10).set(1, -10)
    assert Project.from_document(project.to_document()).to_document() == project.to_document()


def test_curve_set_replaces_and_sorts():
    curve = AutomationCurve("pitd").set(2, 100).set(0, 0).set(2, 200)
    assert curve.points == [CurvePoint(0, 0), CurvePoint(960, 200)]


@pytest.mark.parametrize("version", ["0.7", "0.8", "0.9"])
def test_version_is_explicit_and_preserved(version):
    project = composition()
    project.ustx_version = version
    assert Project.from_document(project.to_document()).ustx_version == version


@pytest.mark.parametrize("version", ["0.6", "0.10", "latest"])
def test_unsupported_versions_not_silently_rewritten(version):
    with pytest.raises(ValidationError, match="version"):
        Project(ustx_version=version).validate()


def test_save_does_not_overwrite_or_truncate_invalid_revision(tmp_path):
    project = composition()
    path = project.save(tmp_path / "song.ustx")
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        project.save(path)
    project.tracks[0].parts[0].notes[0].duration_ticks = 0
    with pytest.raises(ValidationError, match=r"tracks\[0\].*duration_ticks"):
        project.save(path, overwrite=True)
    assert path.read_bytes() == before
    project.tracks[0].parts[0].notes[0].duration_ticks = 480
    project.name = "Edited"
    project.save(path, overwrite=True)
    assert Project.load(path).name == "Edited"


@pytest.mark.parametrize("edit,match", [
    (lambda p: setattr(p.tracks[0].parts[0].notes[1], "position_ticks", 0), "overlap"),
    (lambda p: setattr(p.tracks[0].parts[0].notes[0].vibrato, "period_ms", float("nan")), "period_ms"),
    (lambda p: setattr(p.tracks[0].parts[0].notes[0].portamento, "points", []), "PitchPoints"),
    (lambda p: p.tracks[0].parts[0].notes[0].set_expression("vel", 999), "vel"),
    (lambda p: p.tracks[0].parts[0].curve("dyn").set(0, 999), "dyn"),
    (lambda p: setattr(p.tracks[0].parts[0], "duration_ticks", 10), "contain"),
    (lambda p: p.tempos.reverse(), "tempos"),
])
def test_advanced_edits_checked_with_paths(edit, match):
    project = composition()
    edit(project)
    with pytest.raises(ValidationError, match=match):
        project.validate()


def test_malformed_curves_and_track_indices_rejected():
    doc = composition().to_document()
    doc["voice_parts"][0]["curves"][0]["ys"].pop()
    with pytest.raises(ValueError, match="lengths"):
        Project.from_document(doc)
    doc = composition().to_document()
    doc["voice_parts"][0]["track_no"] = -1
    with pytest.raises(ValueError, match="track_no"):
        Project.from_document(doc)


def test_import_is_independent_of_previous_experiments():
    subprocess.run([sys.executable, "-c", "import pyopenutau,sys; assert not any(n.startswith(('voice2utau', 'numpy', 'tkinter')) for n in sys.modules)"],
                   check=True, env={**__import__('os').environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")})
