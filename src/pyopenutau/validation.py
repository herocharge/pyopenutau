"""Fail-fast errors with an address into the editable Python project."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .project import Project
from .types import ExpressionDescriptor, ExpressionKind, Pitch, PitchShape, integer, number


class ValidationError(ValueError):
    """A structural authoring error, distinct from an engine execution failure."""


@contextmanager
def at(path: str) -> Iterator[None]:
    try:
        yield
    except ValidationError:
        raise
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError(f"{path}: {error}") from error


def descriptor(exp: ExpressionDescriptor) -> None:
    if not exp.abbreviation or not exp.name:
        raise ValueError("expression needs a name and abbreviation")
    if not isinstance(exp.kind, ExpressionKind):
        raise ValueError("kind must be an ExpressionKind")
    number(exp.minimum, "minimum")
    number(exp.maximum, "maximum")
    number(exp.default, "default")
    if exp.kind == ExpressionKind.OPTIONS:
        if exp.options is None or not all(isinstance(option, str) for option in exp.options):
            raise ValueError("Options expressions need string options")
        if exp.minimum != 0 or exp.maximum != len(exp.options) - 1:
            raise ValueError("Options range must be 0..len(options)-1")
        if exp.options:
            number(exp.default, "default", 0, len(exp.options) - 1)
    else:
        number(exp.default, "default", exp.minimum, exp.maximum)


def validate(project: Project) -> None:
    with at("project"):
        if project.ustx_version not in ("0.7", "0.8", "0.9"):
            raise ValueError("supported ustx_version values are '0.7', '0.8', '0.9'; no silent upgrades/downgrades")
        if not isinstance(project.name, str) or not isinstance(project.comment, str):
            raise ValueError("name and comment must be strings")
        project._validate_tempos()
        selectors = project.extras.get("exp_selectors", ["dyn", "pitd", "clr", "eng", "vel", "vol", "atk", "dec", "gen", "bre"])
        if not isinstance(selectors, list) or len(selectors) < 10 or any(
                not isinstance(key, str) or key not in project.expressions for key in selectors):
            raise ValueError("exp_selectors needs at least ten registered expressions for legacy OpenUtau compatibility")
        if not project.time_signatures or project.time_signatures[0].bar_position != 0:
            raise ValueError("time_signatures must start at bar zero")
        previous_bar = -1
        for signature in project.time_signatures:
            integer(signature.bar_position, "bar_position")
            integer(signature.beats_per_bar, "beats_per_bar", 1)
            integer(signature.beat_unit, "beat_unit", 1, 64)
            if signature.beat_unit not in (1, 2, 4, 8, 16, 32, 64):
                raise ValueError("beat_unit must be a power of two from 1 to 64")
            if signature.bar_position <= previous_bar:
                raise ValueError("time signatures must be strictly increasing")
            previous_bar = signature.bar_position
    for key, exp in project.expressions.items():
        with at(f"expressions[{key!r}]"):
            descriptor(exp)
            if key != exp.abbreviation:
                raise ValueError("mapping key must match abbreviation")
    for ti, track in enumerate(project.tracks):
        path = f"tracks[{ti}]"
        with at(path):
            number(track.volume_db, "volume_db", -240, 120)
            number(track.pan, "pan", -100, 100)
            if track.singer is not None and not isinstance(track.singer, str):
                raise ValueError("singer must be a registered ID string or None")
            if not isinstance(track.phonemizer, str) or not track.phonemizer:
                raise ValueError("phonemizer must be a class-name string")
            if type(track.mute) is not bool or type(track.solo) is not bool:
                raise ValueError("mute and solo must be bool")
            if not all(isinstance(value, str) for value in track.voice_color_names):
                raise ValueError("voice_color_names must contain strings")
            for identifier in (track.render_settings.renderer, track.render_settings.resampler, track.render_settings.wavtool):
                if identifier is not None and not isinstance(identifier, str):
                    raise ValueError("render setting identifiers must be strings or None")
            for exp in track.expressions:
                descriptor(exp)
        expressions = {**project.expressions, **{e.abbreviation: e for e in track.expressions}}
        for pi, part in enumerate(track.parts):
            part_path = f"{path}.parts[{pi}]"
            with at(part_path):
                integer(part.position_ticks, "position_ticks")
                if part.duration_ticks is not None:
                    integer(part.duration_ticks, "duration_ticks")
                if part.effective_duration_ticks < max((n.end_ticks for n in part.notes), default=0):
                    raise ValueError("part duration_ticks does not contain all notes")
            previous_end = 0
            for ni, note in enumerate(sorted(part.notes, key=lambda n: n.position_ticks)):
                with at(f"{part_path}.notes[sorted:{ni}]"):
                    integer(note.position_ticks, "position_ticks")
                    integer(note.duration_ticks, "duration_ticks", 10)
                    if note.position_ticks < previous_end:
                        raise ValueError("notes overlap; use separate tracks for polyphony")
                    previous_end = note.end_ticks
                    if not isinstance(note.pitch, Pitch):
                        raise ValueError("pitch must be a Pitch; use Pitch.parse('C4')")
                    integer(note.tuning_cents, "tuning_cents", -(2**31), 2**31 - 1)
                    if not isinstance(note.lyric, str) or not note.lyric.strip():
                        raise ValueError("lyric must be a nonempty string")
                    if len(note.portamento.points) < 2:
                        raise ValueError("portamento needs at least two PitchPoints")
                    if type(note.portamento.snap_first) is not bool:
                        raise ValueError("portamento.snap_first must be bool")
                    last_ms = float("-inf")
                    for point in note.portamento.points:
                        number(point.time_ms, "PitchPoint.time_ms")
                        number(point.cents, "PitchPoint.cents")
                        if point.time_ms <= last_ms:
                            raise ValueError("PitchPoint times must be strictly increasing")
                        if not isinstance(point.shape, PitchShape):
                            raise ValueError("PitchPoint.shape must be a PitchShape")
                        last_ms = point.time_ms
                    vibrato = note.vibrato
                    number(vibrato.length_percent, "vibrato.length_percent", 0, 100)
                    number(vibrato.period_ms, "vibrato.period_ms", 5, 500)
                    number(vibrato.depth_cents, "vibrato.depth_cents", 5, 200)
                    for name in ("fade_in_percent", "fade_out_percent", "phase_percent"):
                        number(getattr(vibrato, name), f"vibrato.{name}", 0, 100)
                    if vibrato.fade_in_percent + vibrato.fade_out_percent > 100:
                        raise ValueError("vibrato fades must sum to <=100%")
                    number(vibrato.drift_percent, "vibrato.drift_percent", -100, 100)
                    number(vibrato.volume_link_percent, "vibrato.volume_link_percent", -100, 100)
                    used = set()
                    for value in note.expressions:
                        if value.phoneme_index is not None:
                            integer(value.phoneme_index, "phoneme_index")
                        expression_key = (value.abbreviation, value.phoneme_index)
                        if expression_key in used:
                            raise ValueError(f"duplicate expression {expression_key}")
                        used.add(expression_key)
                        value_descriptor = expressions.get(value.abbreviation)
                        if value_descriptor is None or value_descriptor.kind == ExpressionKind.CURVE:
                            raise ValueError(f"{value.abbreviation!r} needs a Numerical/Options expression descriptor")
                        maximum = value_descriptor.maximum
                        if value.abbreviation == "clr":
                            maximum = max(maximum, len(track.voice_color_names) - 1)
                        number(value.value, value.abbreviation, value_descriptor.minimum, maximum)
                        if value_descriptor.kind == ExpressionKind.OPTIONS and value.value != int(value.value):
                            raise ValueError("Options expression values must be integral indices")
                    used_overrides = set()
                    for override in note.phoneme_overrides:
                        integer(override.index, "override.index")
                        if override.index in used_overrides:
                            raise ValueError("duplicate phoneme override index")
                        used_overrides.add(override.index)
                        if override.phoneme is not None and not isinstance(override.phoneme, str):
                            raise ValueError("override.phoneme must be str or None")
                        if override.offset_ticks is not None:
                            integer(override.offset_ticks, "override.offset_ticks", -(2**31))
                        for name in ("preutter_delta_ms", "overlap_delta_ms", "attack_time_delta_ms", "release_time_delta_ms"):
                            value_ms = getattr(override, name)
                            if value_ms is not None:
                                number(value_ms, name)
            used_curves = set()
            for curve in part.curves:
                with at(f"{part_path}.curves[{curve.abbreviation!r}]"):
                    if curve.abbreviation in used_curves:
                        raise ValueError("duplicate curve")
                    used_curves.add(curve.abbreviation)
                    curve_descriptor = expressions.get(curve.abbreviation)
                    if curve_descriptor is None or curve_descriptor.kind != ExpressionKind.CURVE:
                        raise ValueError("curve needs a Curve expression descriptor")
                    previous_tick = -(2**31) - 1
                    for curve_point in curve.points:
                        integer(curve_point.position_ticks, "position_ticks", -(2**31))
                        integer(curve_point.value, "value", -(2**31))
                        number(curve_point.value, "value", curve_descriptor.minimum, curve_descriptor.maximum)
                        if curve_point.position_ticks <= previous_tick:
                            raise ValueError("curve points must be strictly increasing")
                        previous_tick = curve_point.position_ticks
