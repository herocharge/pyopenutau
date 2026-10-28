from pathlib import Path
import runpy

import pytest

from pyopenutau import Project, ValidationError, Vocal


def test_complete_composition_example_roundtrips(tmp_path):
    compose = runpy.run_path(str(Path(__file__).parents[1] / "examples/compose.py"))["compose"]
    project = compose()
    path = project.save(tmp_path / "example.ustx")
    loaded = Project.load(path)
    assert loaded.to_document() == project.to_document()
    assert len(loaded.tracks) == 2
    assert len(loaded.tracks[0].parts) == 2
    assert len(loaded.tracks[1].parts) == 1
    assert sum(len(p.notes) for t in loaded.tracks for p in t.parts) == 12


def test_removing_stock_selector_descriptor_is_reported_before_save():
    project = Project()
    project.expressions.pop("bre")
    with pytest.raises(ValidationError, match="exp_selectors"):
        project.validate()


def test_simplified_teto_composition_keeps_low_level_controls(tmp_path):
    bank = tmp_path / "bank"
    bank.mkdir()
    (bank / "character.txt").write_text("name=Example\n")
    compose = runpy.run_path(str(Path(__file__).parents[1] / "examples/teto_sample.py"))["compose"]
    vocal = compose(bank)
    assert isinstance(vocal, Vocal)
    assert len(vocal.part.notes) == 12
    assert vocal.part.notes[0].beat == 0.5
    assert vocal.part.notes[-1].beat + vocal.part.notes[-1].length == 16.5
    assert vocal.part.notes[-1].vibrato.length_percent == 55
    vocal.project.validate()


def test_synthetic_demo_is_reproducible_without_any_engine(tmp_path):
    import hashlib
    import wave
    create = runpy.run_path(str(Path(__file__).parents[1] / "examples/synthetic.py"))["create_demo"]
    first = create(tmp_path / "first")
    second = create(tmp_path / "second")
    assert first.project.to_document() == second.project.to_document()
    samples = first.bank / "a.wav"
    assert hashlib.sha256(samples.read_bytes()).digest() == hashlib.sha256((second.bank / "a.wav").read_bytes()).digest()
    with wave.open(str(samples), "rb") as reader:
        assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate(), reader.getnframes()) == (1, 2, 44100, 44100)
    assert first.part.notes[0].beat == 1
    with pytest.raises(FileExistsError):
        create(tmp_path / "first")
