from pathlib import Path

import pytest

from pyopenutau import CancellationToken, CoreError, Note, Pitch, Project, Vocal


@pytest.fixture
def bank(tmp_path):
    root = tmp_path / "voice"
    root.mkdir()
    (root / "character.txt").write_text("name=Test voice\n")
    return root


def test_setup_is_lazy_and_notes_are_normal_editable_objects(bank, monkeypatch):
    def unexpected():
        pytest.fail("Authoring must not construct an engine")
    monkeypatch.setattr("pyopenutau.vocal.OpenUtauEngine", unexpected)
    vocal = Vocal(bank, name="My vocal", bpm=140)
    assert vocal.bank == bank.resolve()
    assert vocal.track is vocal.project.tracks[0]
    assert vocal.part is vocal.track.parts[0]
    assert vocal.track.singer == bank.name
    assert vocal.track.phonemizer == "OpenUtau.Core.DefaultPhonemizer"
    note = vocal.add_note("a", "C4", length=0.5)
    assert isinstance(note, Note) and note is vocal.part.notes[0]
    note.vibrato.length_percent = 60
    vocal.add_note("i", Pitch.parse("E4"))
    vocal.add_note("u", 67, beat=3, length=2)
    assert [n.beat for n in vocal.part.notes] == [0, 0.5, 3]
    assert vocal.project.seconds_at(1) == pytest.approx(60 / 140)
    with pytest.raises(ValueError, match="overlap"):
        vocal.add_note("a", beat=0)


def test_bank_metadata_default_and_explicit_override(bank):
    (bank / "character.yaml").write_text(
        "\ufeffdefault_phonemizer: OpenUtau.Plugin.Builtin.JapaneseVCVPhonemizer\n",
        encoding="utf-8",
    )
    assert Vocal(bank).track.phonemizer == "OpenUtau.Plugin.Builtin.JapaneseVCVPhonemizer"
    assert Vocal(bank, phonemizer="Custom.Class").track.phonemizer == "Custom.Class"


@pytest.mark.parametrize("metadata", ["", "null", "name: Test\n", "default_phonemizer: null"])
def test_absent_preference_means_direct_aliases(bank, metadata):
    (bank / "character.yaml").write_text(metadata)
    assert Vocal(bank).track.phonemizer == "OpenUtau.Core.DefaultPhonemizer"


@pytest.mark.parametrize("metadata", ["[bad", "[]", "default_phonemizer: 42", "default_phonemizer: ''"])
def test_invalid_metadata_is_not_silently_guessed(bank, metadata):
    (bank / "character.yaml").write_text(metadata)
    with pytest.raises(ValueError):
        Vocal(bank)
    # Explicit choice bypasses bad preference metadata, not engine validation.
    assert Vocal(bank, phonemizer="Explicit.Class").track.phonemizer == "Explicit.Class"


def test_paths_and_explicit_phonemizer_are_validated(bank, monkeypatch):
    monkeypatch.setenv("HOME", str(bank.parent))
    monkeypatch.setenv("USERPROFILE", str(bank.parent))  # Path.home() on Windows
    assert Vocal("~/voice").bank == bank.resolve()
    with pytest.raises(FileNotFoundError):
        Vocal(bank / "missing")
    with pytest.raises(ValueError, match="character.txt"):
        Vocal(bank.parent)
    for invalid in ("", " ", 4):
        with pytest.raises(ValueError, match="phonemizer"):
            Vocal(bank, phonemizer=invalid)


def test_save_uses_normal_project_safety_and_preserves_controls(bank, tmp_path):
    vocal = Vocal(bank)
    vocal.add_note("a").set_expression("vel", 125)
    vocal.track.pan = -20
    vocal.part.curve("dyn").set(0, -30)
    path = vocal.save(tmp_path / "song.ustx")
    assert Project.load(path).to_document() == vocal.project.to_document()
    with pytest.raises(FileExistsError):
        vocal.save(path)
    vocal.save(path, overwrite=True)


@pytest.mark.parametrize("operation", ["render", "phonemize"])
@pytest.mark.parametrize("failure", [False, True])
def test_engine_ownership_options_and_failure_cleanup(bank, monkeypatch, operation, failure):
    instances = []
    calls = []
    sentinel = object()

    class Engine:
        closed = False
        def __init__(self):
            instances.append(self)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.closed = True
        def invoke(self, project, *args, **kwargs):
            calls.append((project, args, kwargs))
            if failure:
                raise CoreError("Expected engine failure")
            return sentinel
        render = invoke
        phonemize = invoke

    monkeypatch.setattr("pyopenutau.vocal.OpenUtauEngine", Engine)
    vocal = Vocal(bank)
    vocal.add_note("a")
    token = CancellationToken()
    progress = lambda event: None
    options = dict(timeout=27, cancel=token, progress=progress)
    if operation == "render":
        options["overwrite"] = True
    args = ("sample.wav",) if operation == "render" else ()
    method = getattr(vocal, operation)
    borrowed = Engine()
    for engine_options in ({}, {"engine": borrowed}):
        if failure:
            with pytest.raises(CoreError, match="Expected engine failure"):
                method(*args, **options, **engine_options)
        else:
            assert method(*args, **options, **engine_options) is sentinel
    assert len(instances) == 2
    assert instances[1].closed and not borrowed.closed
    assert len(calls) == 2
    for project, actual_args, actual_options in calls:
        assert project is vocal.project and actual_args == args
        assert actual_options == dict(singers={bank.name: bank.resolve()}, **options)
