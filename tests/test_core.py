import pytest

from pyopenutau import CoreError, OpenUtauCore, PitchCurve, PitchPoint, Project


def test_core_check_distinct_from_authoring_and_missing_install(tmp_path):
    project = Project()
    with pytest.raises(CoreError, match="Core.dll"):
        OpenUtauCore(tmp_path).check(project)
    # Authoring is usable without .NET/OpenUtau at all.
    assert project.save(tmp_path / "empty.ustx").is_file()


@pytest.mark.integration
def test_real_installed_openutau_deserializes_and_validates_notes():
    project = Project("Core compatibility", bpm=120)
    part = project.add_track().add_voice_part(beat=2)
    note = part.add_note("arbitrary lyric", "C4", beat=1)
    note.portamento = PitchCurve([PitchPoint(-30, -100), PitchPoint(50, 0)], snap_first=False)
    part.add_note("+", "D4")
    result = OpenUtauCore().check(project)
    assert result.notes == 2 and result.tracks == 1
    assert result.project_version == "0.7"
    assert result.isolated_state is True
    assert result.note_details[0]["position_ms"] == 1500  # part offset + local note offset
    assert result.note_details[0]["first_pitch_y"] == -10  # cents → native 0.1 semitones
    assert "no phonemization or rendering" in result.scope


def test_explicit_assembly_path_overrides_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENUTAU_ASSEMBLY_DIR", str(tmp_path / "configured"))
    assert OpenUtauCore().assembly_dir == (tmp_path / "configured").resolve()
    assert OpenUtauCore(tmp_path / "explicit").assembly_dir == (tmp_path / "explicit").resolve()
