"""USTX mappings. This is a file adapter, not a second synthesis engine."""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any, Callable, TypeVar

from .project import Note, Project, Track, VoicePart
from .types import (
    AutomationCurve, CurvePoint, ExpressionDescriptor, ExpressionKind, ExpressionValue,
    PhonemeOverride, Pitch, PitchCurve, PitchPoint, PitchShape, RenderSettings, Tempo,
    TimeSignature, Vibrato,
)

T = TypeVar("T")

VIBRATO = {"length_percent": "length", "period_ms": "period", "depth_cents": "depth",
           "fade_in_percent": "in", "fade_out_percent": "out", "phase_percent": "shift",
           "drift_percent": "drift", "volume_link_percent": "vol_link"}
OVERRIDE = {"index": "index", "phoneme": "phoneme", "offset_ticks": "offset",
            "preutter_delta_ms": "preutter_delta", "overlap_delta_ms": "overlap_delta",
            "attack_time_delta_ms": "attack_time_delta", "release_time_delta_ms": "release_time_delta"}
DESCRIPTOR = {"name": "name", "abbreviation": "abbr", "kind": "type", "minimum": "min",
              "maximum": "max", "default": "default_value", "options": "options",
              "flag": "flag", "is_flag": "is_flag"}
EXPRESSION = {"abbreviation": "abbr", "value": "value", "phoneme_index": "index"}
TEMPO = {"position_ticks": "position", "bpm": "bpm"}
SIGNATURE = {"bar_position": "bar_position", "beats_per_bar": "beat_per_bar", "beat_unit": "beat_unit"}
RENDER = {"renderer": "renderer", "resampler": "resampler", "wavtool": "wavtool"}
TRACK = {"name": "track_name", "singer": "singer", "phonemizer": "phonemizer", "volume_db": "volume",
         "pan": "pan", "mute": "mute", "solo": "solo", "color": "track_color",
         "voice_color_names": "voice_color_names"}
PART = {"name": "name", "position_ticks": "position", "duration_ticks": "duration", "comment": "comment"}
NOTE = {"lyric": "lyric", "position_ticks": "position", "duration_ticks": "duration", "tuning_cents": "tuning"}


def pack(obj: Any, keys: dict[str, str]) -> dict[str, Any]:
    doc: dict[str, Any] = deepcopy(obj.extras)
    for attribute, key in keys.items():
        value = getattr(obj, attribute)
        doc[key] = value.value if isinstance(value, Enum) else deepcopy(value)
    return doc


def unpack(cls: Callable[..., T], doc: dict[str, Any], keys: dict[str, str]) -> T:
    kwargs = {attribute: doc.pop(key) for attribute, key in keys.items() if key in doc}
    return cls(**kwargs, extras=doc)


def read_descriptor(doc: dict[str, Any]) -> ExpressionDescriptor:
    raw_kind = doc.get("type", "Numerical")
    doc["type"] = ExpressionKind(["Numerical", "Options", "Curve"][raw_kind]
                                 if type(raw_kind) is int and 0 <= raw_kind <= 2 else raw_kind)
    return unpack(ExpressionDescriptor, doc, DESCRIPTOR)


def encode(project: Project) -> dict[str, Any]:
    doc = deepcopy(project.extras)
    doc.setdefault("output_dir", "Vocal")
    doc.setdefault("cache_dir", "UCache")
    doc.setdefault("exp_selectors", ["dyn", "pitd", "clr", "eng", "vel", "vol", "atk", "dec", "gen", "bre"])
    doc.setdefault("exp_primary", 0)
    doc.setdefault("exp_secondary", 1)
    doc.setdefault("key", 0)
    doc.update(name=project.name, comment=project.comment, ustx_version=project.ustx_version,
               resolution=480, bpm=project.bpm,
               beat_per_bar=project.time_signatures[0].beats_per_bar,
               beat_unit=project.time_signatures[0].beat_unit,
               tempos=[pack(t, TEMPO) for t in project.tempos],
               time_signatures=[pack(t, SIGNATURE) for t in project.time_signatures],
               expressions={key: pack(exp, DESCRIPTOR) for key, exp in project.expressions.items()})
    tracks: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []
    waves: list[dict[str, Any]] = []
    for index, track in enumerate(project.tracks):
        track_doc = pack(track, TRACK)
        track_doc["renderer_settings"] = pack(track.render_settings, RENDER)
        track_doc["track_expressions"] = [pack(exp, DESCRIPTOR) for exp in track.expressions]
        tracks.append(track_doc)
        waves.extend({**deepcopy(wave), "track_no": index} for wave in track.wave_parts)
        for part in track.parts:
            part_doc = pack(part, PART)
            part_doc.update(track_no=index, duration=part.effective_duration_ticks)
            part_doc["curves"] = [{**deepcopy(curve.extras), "abbr": curve.abbreviation,
                                   "xs": [p.position_ticks for p in curve.points],
                                   "ys": [p.value for p in curve.points]} for curve in part.curves]
            notes = []
            for note in sorted(part.notes, key=lambda n: n.position_ticks):
                note_doc = pack(note, NOTE)
                note_doc["tone"] = note.pitch.midi
                note_doc["pitch"] = {
                    **deepcopy(note.portamento.extras), "snap_first": note.portamento.snap_first,
                    "data": [{**deepcopy(point.extras), "x": point.time_ms,
                              "y": point.cents / 10, "shape": point.shape.value}
                             for point in note.portamento.points],
                }
                note_doc["vibrato"] = pack(note.vibrato, VIBRATO)
                note_doc["phoneme_expressions"] = [pack(e, EXPRESSION) for e in note.expressions]
                note_doc["phoneme_overrides"] = [pack(o, OVERRIDE) for o in note.phoneme_overrides]
                notes.append(note_doc)
            part_doc["notes"] = notes
            parts.append(part_doc)
    doc.update(tracks=tracks, voice_parts=parts, wave_parts=waves)
    return doc


def decode(doc: dict[str, Any]) -> Project:
    try:
        return _decode(doc)
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError(f"Malformed USTX mapping: {error}") from error


def _decode(doc: dict[str, Any]) -> Project:
    if doc.pop("resolution", 480) != 480:
        raise ValueError("OpenUtau uses resolution=480; unsupported resolution")
    project = Project(doc.pop("name", "New Project"), ustx_version=str(doc.pop("ustx_version", "0.7")))
    project.comment = doc.pop("comment", "")
    project.tempos = [unpack(Tempo, t, TEMPO) for t in doc.pop("tempos", [{"position": 0, "bpm": doc.get("bpm", 120)}])]
    project.time_signatures = [unpack(TimeSignature, s, SIGNATURE) for s in doc.pop(
        "time_signatures", [{"bar_position": 0, "beat_per_bar": doc.get("beat_per_bar", 4), "beat_unit": doc.get("beat_unit", 4)}])]
    for key, exp in doc.pop("expressions", {}).items():
        project.expressions[key] = read_descriptor(exp)
    for track_doc in doc.pop("tracks", []):
        render = unpack(RenderSettings, track_doc.pop("renderer_settings", None) or {}, RENDER)
        exps = [read_descriptor(e) for e in track_doc.pop("track_expressions", [])]
        track = unpack(Track, track_doc, TRACK)
        track.render_settings = render
        track.expressions = exps
        project.tracks.append(track)
    for part_doc in doc.pop("voice_parts", []) or []:
        track_index = part_doc.pop("track_no")
        if type(track_index) is not int or not 0 <= track_index < len(project.tracks):
            raise ValueError(f"Invalid voice part track_no {track_index!r}")
        notes = []
        for note_doc in part_doc.pop("notes", []):
            pitch = Pitch(note_doc.pop("tone"))
            pitch_doc = note_doc.pop("pitch", {"data": [{"x": -5, "y": 0}, {"x": 5, "y": 0}]})
            points = []
            for p in pitch_doc.pop("data"):
                points.append(PitchPoint(p.pop("x"), p.pop("y") * 10,
                                         PitchShape(p.pop("shape", "io")), p))
            portamento = PitchCurve(points, pitch_doc.pop("snap_first", True), pitch_doc)
            vibrato = unpack(Vibrato, note_doc.pop("vibrato", {}), VIBRATO)
            values = [unpack(ExpressionValue, e, EXPRESSION) for e in note_doc.pop("phoneme_expressions", [])]
            overrides = [unpack(PhonemeOverride, o, OVERRIDE) for o in note_doc.pop("phoneme_overrides", [])]
            note = unpack(Note, note_doc, NOTE)
            note.pitch, note.portamento, note.vibrato = pitch, portamento, vibrato
            note.expressions, note.phoneme_overrides = values, overrides
            notes.append(note)
        curves = []
        for curve_doc in part_doc.pop("curves", []):
            abbr, xs, ys = (curve_doc.pop(key) for key in ("abbr", "xs", "ys"))
            if len(xs) != len(ys):
                raise ValueError(f"Curve {abbr!r}: xs and ys lengths differ")
            curves.append(AutomationCurve(abbr, [CurvePoint(x, y) for x, y in zip(xs, ys)], curve_doc))
        part = unpack(VoicePart, part_doc, PART)
        part.notes, part.curves = notes, curves
        project.tracks[track_index].parts.append(part)
    for wave in doc.pop("wave_parts", []) or []:
        track_index = wave.pop("track_no")
        if type(track_index) is not int or not 0 <= track_index < len(project.tracks):
            raise ValueError(f"Invalid wave part track_no {track_index!r}")
        project.tracks[track_index].wave_parts.append(wave)
    project.extras = doc
    return project
