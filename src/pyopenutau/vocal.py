"""A small, single-voice entry point over the ordinary authoring model."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import yaml

from .engine import (
    CancellationToken, OpenUtauEngine, PhonemizationResult, ProgressCallback, RenderResult,
)
from .project import Note, Project, Track, VoicePart
from .types import Pitch


def _preferred_phonemizer(bank: Path) -> str:
    metadata = bank / "character.yaml"
    if not metadata.is_file():
        return "OpenUtau.Core.DefaultPhonemizer"
    try:
        document = yaml.safe_load(metadata.read_text(encoding="utf-8-sig"))
    except (UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"Cannot read voicebank metadata: {metadata}") from error
    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise ValueError(f"Voicebank metadata must be a mapping: {metadata}")
    preferred = document.get("default_phonemizer")
    if preferred is None:
        return "OpenUtau.Core.DefaultPhonemizer"
    if not isinstance(preferred, str) or not preferred.strip():
        raise ValueError(f"default_phonemizer must be a nonempty class name: {metadata}")
    return preferred


class Vocal:
    """Compose and render one voice with minimal setup, without a GUI.

    Construction only reads the explicitly supplied bank's metadata; it does
    not start OpenUtau, discover singers, or register anything. Notes and the
    exposed project/track/part are the normal mutable SDK objects.
    """

    def __init__(self, bank: str | Path, *, name: str = "New vocal", bpm: float = 120,
                 phonemizer: str | None = None) -> None:
        self._bank = Path(bank).expanduser().resolve(strict=True)
        if not (self._bank / "character.txt").is_file():
            raise ValueError(f"Voicebank directory needs character.txt: {self._bank}")
        if phonemizer is not None and (not isinstance(phonemizer, str) or not phonemizer.strip()):
            raise ValueError("phonemizer must be a nonempty class name or None")
        selected = _preferred_phonemizer(self._bank) if phonemizer is None else phonemizer
        self._singer_id = self._bank.name
        self._project = Project(name, bpm=bpm)
        self._track = self._project.add_track("Voice", singer=self._singer_id, phonemizer=selected)
        self._part = self._track.add_voice_part()

    @property
    def bank(self) -> Path:
        return self._bank

    @property
    def project(self) -> Project:
        return self._project

    @property
    def track(self) -> Track:
        return self._track

    @property
    def part(self) -> VoicePart:
        return self._part

    def add_note(self, lyric: str, pitch: str | int | Pitch = "C4", *,
                 beat: float | None = None, length: float = 1) -> Note:
        """Append a note; beat/length are quarter-note beats, as in VoicePart."""
        return self._part.add_note(lyric, pitch, beat=beat, length=length)

    def save(self, path: str | Path, *, overwrite: bool = False) -> Path:
        """Save a USTX project only; this does not render audio."""
        return self._project.save(path, overwrite=overwrite)

    def phonemize(self, *, engine: OpenUtauEngine | None = None, timeout: float = 120,
                  cancel: CancellationToken | None = None,
                  progress: ProgressCallback | None = None) -> PhonemizationResult:
        """Optional inspection. Rendering already rejects phoneme errors."""
        with (nullcontext(engine) if engine is not None else OpenUtauEngine()) as session:
            return session.phonemize(
                self._project, singers={self._singer_id: self._bank},
                timeout=timeout, cancel=cancel, progress=progress,
            )

    def render(self, output: str | Path, *, engine: OpenUtauEngine | None = None,
               timeout: float = 300, cancel: CancellationToken | None = None,
               progress: ProgressCallback | None = None, overwrite: bool = False) -> RenderResult:
        """Render a WAV, automatically closing an engine unless one is supplied.

        Output parents must exist. Existing files require overwrite=True.
        A borrowed engine is never closed, including when rendering fails.
        """
        with (nullcontext(engine) if engine is not None else OpenUtauEngine()) as session:
            return session.render(
                self._project, output, singers={self._singer_id: self._bank},
                timeout=timeout, cancel=cancel, progress=progress, overwrite=overwrite,
            )
