"""Authoring objects, mirroring UProject → UTrack → UVoicePart → UNote."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import defaults
from .types import (
    RESOLUTION, AutomationCurve, ExpressionDescriptor, ExpressionValue, PhonemeOverride,
    Pitch, PitchCurve, RenderSettings, Tempo, TimeSignature, Vibrato, integer, number, ticks,
)


@dataclass
class Note:
    lyric: str
    pitch: Pitch = field(default_factory=lambda: Pitch(60))
    position_ticks: int = 0  # relative to its voice part
    duration_ticks: int = RESOLUTION
    tuning_cents: int = 0
    portamento: PitchCurve = field(default_factory=PitchCurve)
    vibrato: Vibrato = field(default_factory=Vibrato)
    expressions: list[ExpressionValue] = field(default_factory=list)
    phoneme_overrides: list[PhonemeOverride] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def end_ticks(self) -> int:
        return self.position_ticks + self.duration_ticks

    @property
    def beat(self) -> float:
        return self.position_ticks / RESOLUTION

    @property
    def length(self) -> float:
        return self.duration_ticks / RESOLUTION

    def set_expression(self, abbreviation: str, value: float, *, phoneme_index: int = 0) -> Note:
        """Set a phoneme expression in its native units; checked against the project on save."""
        number(value, abbreviation)
        integer(phoneme_index, "phoneme_index")
        self.expressions[:] = [e for e in self.expressions
                               if (e.abbreviation, e.phoneme_index) != (abbreviation, phoneme_index)]
        self.expressions.append(ExpressionValue(abbreviation, value, phoneme_index))
        return self


@dataclass
class VoicePart:
    name: str = "Voice"
    position_ticks: int = 0  # relative to project start
    notes: list[Note] = field(default_factory=list)
    curves: list[AutomationCurve] = field(default_factory=list)
    duration_ticks: int | None = None  # None auto-sizes to the final note
    comment: str = ""
    extras: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def end_ticks(self) -> int:
        return self.position_ticks + self.effective_duration_ticks

    @property
    def effective_duration_ticks(self) -> int:
        return self.duration_ticks if self.duration_ticks is not None else max(
            (note.end_ticks for note in self.notes), default=0)

    def add_note(self, lyric: str, pitch: str | int | Pitch = "C4", *,
                 beat: float | None = None, length: float = 1) -> Note:
        """Add a note in quarter-note beats, part-local. Omit beat to append.

        For exact tick control, construct Note and append it to ``notes``.
        A gap is a rest; '+' lyrics are OpenUtau's native melisma convention.
        """
        if not isinstance(lyric, str) or not lyric.strip():
            raise ValueError("lyric must be a nonempty string")
        position = ticks(beat) if beat is not None else max((n.end_ticks for n in self.notes), default=0)
        duration = ticks(length)
        integer(duration, "note duration_ticks", 10)
        note = Note(lyric, Pitch.parse(pitch), position, duration)
        if any(position < n.end_ticks and note.end_ticks > n.position_ticks for n in self.notes):
            raise ValueError("Notes overlap inside a voice part; put harmony on a separate track")
        if self.duration_ticks is not None and note.end_ticks > self.duration_ticks:
            raise ValueError("Note extends past the explicit part duration_ticks")
        self.notes.append(note)
        return note

    def curve(self, abbreviation: str) -> AutomationCurve:
        """Get/create a part-local expression curve (e.g. pitd in cents, dyn in 0.1 dB)."""
        for curve in self.curves:
            if curve.abbreviation == abbreviation:
                return curve
        curve = AutomationCurve(abbreviation)
        self.curves.append(curve)
        return curve

    def clone(self, *, transpose: int = 0, at_beat: float | None = None) -> VoicePart:
        """Independent deep copy for repetitions/harmonies; never aliases mutable note controls."""
        integer(transpose, "transpose", -127, 127)
        result = deepcopy(self)
        for note in result.notes:
            note.pitch = note.pitch.transpose(transpose)
        if at_beat is not None:
            result.position_ticks = ticks(at_beat)
        return result


@dataclass
class Track:
    name: str = "Track"
    singer: str | None = None  # desktop ID or headless session binding, NOT a filesystem path
    phonemizer: str = "OpenUtau.Core.DefaultPhonemizer"
    render_settings: RenderSettings = field(default_factory=RenderSettings)
    parts: list[VoicePart] = field(default_factory=list)
    volume_db: float = 0
    pan: float = 0  # OpenUtau native range: -100..100
    mute: bool = False
    solo: bool = False
    color: str = "Blue"
    expressions: list[ExpressionDescriptor] = field(default_factory=list)
    voice_color_names: list[str] = field(default_factory=lambda: [""])
    # Wave parts are retained as opaque USTX mappings, owned by their track so
    # track insertion/reordering cannot silently reassign the backing audio.
    wave_parts: list[dict[str, Any]] = field(default_factory=list, repr=False)
    extras: dict[str, Any] = field(default_factory=dict, repr=False)

    def add_voice_part(self, name: str = "Voice", *, beat: float = 0) -> VoicePart:
        part = VoicePart(name=name, position_ticks=ticks(beat))
        self.parts.append(part)
        return part


class Project:
    """Mutable OpenUtau project with explicit, validated persistence boundaries.

    Convenient methods reject mistakes immediately. Direct dataclass/list edits
    are allowed for advanced work and are checked by validate()/save().
    """

    def __init__(self, name: str = "New Project", *, bpm: float = 120,
                 ustx_version: str = "0.7") -> None:
        self.name = name
        self.comment = ""
        self.ustx_version = ustx_version
        self.tempos: list[Tempo] = [Tempo(0, number(bpm, "bpm", 1, 1000))]
        self.time_signatures: list[TimeSignature] = [TimeSignature()]
        self.tracks: list[Track] = []
        self.expressions: dict[str, ExpressionDescriptor] = defaults.expressions()
        self.extras: dict[str, Any] = {}

    @property
    def bpm(self) -> float:
        return self.tempos[0].bpm

    @bpm.setter
    def bpm(self, value: float) -> None:
        self.set_tempo(0, value)

    def add_track(self, name: str = "Track", *, singer: str | None = None,
                  phonemizer: str = "OpenUtau.Core.DefaultPhonemizer") -> Track:
        track = Track(name=name, singer=singer, phonemizer=phonemizer)
        self.tracks.append(track)
        return track

    def set_tempo(self, beat: float, bpm: float) -> Project:
        position = ticks(beat)
        tempo = Tempo(position, number(bpm, "bpm", 1, 1000))
        self.tempos[:] = sorted([t for t in self.tempos if t.position_ticks != position] + [tempo],
                                key=lambda t: t.position_ticks)
        return self

    def seconds_at(self, beat: float) -> float:
        """Project-absolute quarter-note beat → seconds, integrating tempo changes."""
        self._validate_tempos()
        end = ticks(beat)
        seconds = 0.0
        for index, tempo in enumerate(self.tempos):
            if tempo.position_ticks >= end:
                break
            stop = min(end, self.tempos[index + 1].position_ticks) if index + 1 < len(self.tempos) else end
            seconds += (stop - tempo.position_ticks) / RESOLUTION * 60 / tempo.bpm
        return seconds

    def beat_at(self, seconds: float) -> float:
        """Project-absolute seconds → fractional quarter-note beat (no tick rounding)."""
        self._validate_tempos()
        remaining = number(seconds, "seconds", 0)
        for index, tempo in enumerate(self.tempos):
            if index + 1 == len(self.tempos):
                return tempo.position_ticks / RESOLUTION + remaining * tempo.bpm / 60
            span = (self.tempos[index + 1].position_ticks - tempo.position_ticks) / RESOLUTION
            duration = span * 60 / tempo.bpm
            if remaining <= duration:
                return tempo.position_ticks / RESOLUTION + remaining * tempo.bpm / 60
            remaining -= duration
        raise ValueError("Project has no initial tempo")

    def _validate_tempos(self) -> None:
        if not self.tempos or self.tempos[0].position_ticks != 0:
            raise ValueError("tempos must start at tick zero")
        previous = -1
        for tempo in self.tempos:
            integer(tempo.position_ticks, "tempo.position_ticks")
            number(tempo.bpm, "tempo.bpm", 1, 1000)
            if tempo.position_ticks <= previous:
                raise ValueError("tempos must be strictly increasing")
            previous = tempo.position_ticks

    def validate(self) -> None:
        """Check structure and native units, not installed singers or audible renderability."""
        from .validation import validate
        validate(self)

    def to_document(self) -> dict[str, Any]:
        """Return an independent USTX mapping for advanced/unsupported fields."""
        from .codec import encode
        self.validate()
        return encode(self)

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> Project:
        from .codec import decode
        project = decode(deepcopy(document))
        project.validate()
        return project

    @classmethod
    def load(cls, path: str | Path) -> Project:
        """Load supported USTX 0.7–0.9, retaining unknown mapping fields."""
        import yaml
        with Path(path).expanduser().open(encoding="utf-8-sig") as stream:
            data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            raise ValueError("Expected a USTX project mapping")
        return cls.from_document(data)

    def save(self, path: str | Path, *, overwrite: bool = False) -> Path:
        """Save USTX only. Never launches OpenUtau or claims audio was rendered."""
        import yaml
        # Finish serialization before opening the destination, so invalid edits
        # cannot truncate an existing project even with overwrite=True.
        text = yaml.safe_dump(self.to_document(), sort_keys=False, allow_unicode=True)
        target = Path(path).expanduser().resolve()
        with target.open("w" if overwrite else "x", encoding="utf-8") as stream:
            stream.write(text)
        return target
