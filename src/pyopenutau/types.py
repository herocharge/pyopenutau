"""Small domain types. Unit suffixes are part of the public API contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from typing import Any

RESOLUTION = 480  # OpenUtau fixes this; it is not a project preference.


def number(value: float, name: str, minimum: float = -math.inf,
           maximum: float = math.inf) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not minimum <= value <= maximum):
        raise ValueError(f"{name} must be finite and in [{minimum}, {maximum}], got {value!r}")
    return float(value)


def integer(value: int, name: str, minimum: int = 0, maximum: int = 2**31 - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}], got {value!r}")
    return value


def ticks(beats: float) -> int:
    """Round quarter-note beats to the nearest OpenUtau tick (1/480 beat)."""
    return round(number(beats, "beats", 0, (2**31 - 1) / RESOLUTION) * RESOLUTION)


@dataclass(frozen=True)
class Pitch:
    """An integral MIDI key. Microtuning belongs in Note.tuning_cents."""

    midi: int

    def __post_init__(self) -> None:
        integer(self.midi, "MIDI pitch", 0, 127)

    @classmethod
    def parse(cls, value: str | int | Pitch) -> Pitch:
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            return cls(value)
        if not isinstance(value, str):
            raise ValueError("pitch must be a MIDI integer, Pitch, or a name such as C#4")
        match = re.fullmatch(r"([A-Ga-g])([#b♯♭]?)(-?\d+)", value)
        if match is None:
            raise ValueError(f"Invalid pitch {value!r}; use C4, F#3, Bb5, or a MIDI integer")
        name, accidental, octave = match.groups()
        semitone = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[name.upper()]
        semitone += 1 if accidental in ("#", "♯") else -1 if accidental in ("b", "♭") else 0
        return cls((int(octave) + 1) * 12 + semitone)

    @property
    def hz(self) -> float:
        return 440 * 2 ** ((self.midi - 69) / 12)

    def transpose(self, semitones: int) -> Pitch:
        integer(semitones, "semitones", -127, 127)
        return Pitch(self.midi + semitones)

    def __str__(self) -> str:
        return f"{('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')[self.midi % 12]}{self.midi // 12 - 1}"


class PitchShape(str, Enum):
    SINE_IN_OUT = "io"
    LINEAR = "l"
    SINE_IN = "i"
    SINE_OUT = "o"
    SPLINE = "sp"


@dataclass
class PitchPoint:
    """Time in ms relative to note onset; pitch deviation in cents."""

    time_ms: float
    cents: float = 0
    shape: PitchShape = PitchShape.SINE_IN_OUT
    extras: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class PitchCurve:
    """OpenUtau's note-local portamento points, not its part-level pitd curve."""

    points: list[PitchPoint] = field(default_factory=lambda: [PitchPoint(-5), PitchPoint(5)])
    snap_first: bool = True
    extras: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class Vibrato:
    length_percent: float = 0
    period_ms: float = 175
    depth_cents: float = 25
    fade_in_percent: float = 10
    fade_out_percent: float = 10
    phase_percent: float = 0
    drift_percent: float = 0
    volume_link_percent: float = 0
    extras: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class PhonemeOverride:
    """Override one generated phoneme. None means unchanged; zero is meaningful."""

    index: int = 0
    phoneme: str | None = None
    offset_ticks: int | None = None
    preutter_delta_ms: float | None = None
    overlap_delta_ms: float | None = None
    attack_time_delta_ms: float | None = None
    release_time_delta_ms: float | None = None
    extras: dict[str, Any] = field(default_factory=dict, repr=False)


class ExpressionKind(str, Enum):
    NUMERICAL = "Numerical"
    OPTIONS = "Options"
    CURVE = "Curve"


@dataclass
class ExpressionDescriptor:
    name: str
    abbreviation: str
    kind: ExpressionKind = ExpressionKind.NUMERICAL
    minimum: float = 0
    maximum: float = 100
    default: float = 0
    options: list[str] | None = None
    flag: str = ""
    is_flag: bool = False
    extras: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class ExpressionValue:
    abbreviation: str
    value: float
    phoneme_index: int | None = 0
    extras: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class CurvePoint:
    position_ticks: int
    value: int


@dataclass
class AutomationCurve:
    """A part-local UCurve; values use its expression descriptor's native units."""

    abbreviation: str
    points: list[CurvePoint] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict, repr=False)

    def set(self, beat: float, value: int) -> AutomationCurve:
        position = ticks(beat)
        integer(value, "curve value", -(2**31), 2**31 - 1)
        self.points[:] = sorted([p for p in self.points if p.position_ticks != position]
                                + [CurvePoint(position, value)], key=lambda p: p.position_ticks)
        return self


@dataclass
class Tempo:
    position_ticks: int = 0
    bpm: float = 120
    extras: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class TimeSignature:
    bar_position: int = 0
    beats_per_bar: int = 4
    beat_unit: int = 4
    extras: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class RenderSettings:
    """Identifiers interpreted by OpenUtau, not independent Python engines."""

    renderer: str | None = None
    resampler: str | None = None
    wavtool: str | None = None
    extras: dict[str, Any] = field(default_factory=dict, repr=False)
