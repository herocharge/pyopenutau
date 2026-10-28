# Authoring API guide

A standalone, typed project interface. No source recording, particular singer,
recognition, acoustic matching, or audio DSP is required for authoring.
The object model follows OpenUtau: **Project → Track → VoicePart → Note**.

## Install and render a first phrase

From this package directory:

```sh
python -m pip install -e .
```

For the common one-voice case, there is no engine context, singer-ID lookup,
binding dictionary, track/part setup, or separate phonemization pass to write:

```python
from pyopenutau import Vocal

vocal = Vocal("/path/to/voicebank", bpm=120)
vocal.add_note("ら", "C4")
vocal.add_note("ら", "E4")
held = vocal.add_note("ら", "G4", length=2)
held.vibrato.length_percent = 60
audio = vocal.render("new-vocal.wav")
```

Use lyrics supported by **your** bank. `Vocal` reads its declared
`default_phonemizer` from UTF-8 `character.yaml`; with no preference it uses
direct aliases. Override with `Vocal(bank, phonemizer="Full.Plugin.ClassName")`.
It never guesses a language, searches your Downloads, or silently changes plugins.
Unsupported plugins still fail explicitly in the engine.

`Vocal` creates an ordinary `Project`, `Track`, and `VoicePart`, exposed as
`.project`, `.track`, and `.part`. `add_note()` returns the same editable `Note`
as the low-level API. Beats, gaps, controls, validation and overwrite protection
are unchanged. `vocal.save("new-song.ustx")` optionally saves the project; render
only writes a WAV and already rejects phoneme errors. Use `vocal.phonemize()`
when you want an inspection preview. Construction and save require no .NET or
OpenUtau; phonemize/render still require the installed OpenUtau and .NET 8 SDK.
Output directories must exist; existing files require `overwrite=True`.

Each render/inspection owns and closes a temporary engine by default. For repeated
jobs, reuse a build with `vocal.render("take.wav", engine=engine)` inside an
`OpenUtauEngine` context. Borrowed engines are never closed by `Vocal`.
The bank folder name is used as a stable local singer binding; a saved project
still needs a matching registered singer in the desktop app. For several singers,
use the explicit project/engine API below. The shortcut doesn't store global
configuration or change desktop registration.

## Explicit project authoring

```python
from pyopenutau import Project

song = Project("My song", bpm=140)
lead = song.add_track("Lead", singer="your-registered-singer-id")
phrase = lead.add_voice_part("Verse")

note = phrase.add_note("a", pitch="C4", length=1)
phrase.add_note("i", pitch="D4", length=1)  # appends after the previous note
phrase.add_note("u", pitch="E4", beat=3, length=2)  # a one-beat rest

note.vibrato.length_percent = 60  # 0 disables vibrato
note.vibrato.depth_cents = 30
song.save("new-song.ustx")  # refuses existing files
```

Lyrics are opaque strings passed to the selected OpenUtau phonemizer. They are
not automatically translated or transcribed. By default, tracks use
`OpenUtau.Core.DefaultPhonemizer` (direct aliases). Supply the actual phonemizer
class name for a bank needing VCV, CVVC, English, or another realization. Singer
IDs are OpenUtau's registered IDs, **not filesystem paths**. `singer=None` leaves
assignment for later. Missing singers do not prevent authoring, but will prevent
successful synthesis in OpenUtau.

Open the saved project in OpenUtau, or use `OpenUtauEngine` for headless
phonemization and WAV rendering. [The engine guide](../HEADLESS.md) covers local
singer bindings, alias/OTO inspection, built-in phonemizers, progress,
cancellation and diagnostics. Classic banks with WORLDLINE-R are supported;
other engines, wave parts and playback aren't implemented. `save()` still only
writes a project and never implies that audio was rendered.

```python
from pyopenutau import OpenUtauEngine

with OpenUtauEngine() as engine:
    audio = engine.render(song, "new-vocal.wav",
                          singers={"your-registered-singer-id": "/path/to/bank"})
    print(audio.output)
```

## Convenient entry points, explicit low-level controls

```python
from pyopenutau import (
    Note, PhonemeOverride, Pitch, PitchCurve, PitchPoint, PitchShape,
    RenderSettings,
)

# Exact ticks instead of beat helpers. OpenUtau fixes 480 ticks per quarter note.
phrase.notes.append(Note("+", Pitch.parse("G4"),
                         position_ticks=2400, duration_ticks=960))

# A fresh pitch curve, in ms relative to note onset and cents of deviation.
note.portamento = PitchCurve([
    PitchPoint(-40, -100, PitchShape.LINEAR),
    PitchPoint(80, 0),
], snap_first=False)

# Per-generated-phoneme controls, not a separate custom phonetic language.
note.set_expression("vel", 120, phoneme_index=0)
note.phoneme_overrides.append(PhonemeOverride(
    index=0, offset_ticks=-10, preutter_delta_ms=5,
))

# Part-level automation. pitd: cents; dyn: tenths of a dB.
phrase.curve("pitd").set(0, 0).set(1, 50).set(2, 0)
phrase.curve("dyn").set(0, -60).set(1, 0).set(2, -30)

lead.render_settings = RenderSettings(renderer="WORLDLINE-R")
lead.volume_db = -3
lead.pan = -20  # OpenUtau's -100..100 pan scale
```

`PitchPoint` converts cents to OpenUtau's native 0.1-semitone Y values on export.
Its `shape` describes interpolation from that point toward the next one.
`snap_first=True` lets OpenUtau replace the first point's pitch for adjoining
notes; set it to False when that point is explicitly authored.

Vibrato uses OpenUtau's native semantics: `length_percent` is a percentage of
note duration; fades are percentages of the **vibrato region**; period is ms;
depth is cents. Invalid values are rejected, not silently clamped.

## Patterns, harmonies, and time

```python
harmony = song.add_track("Harmony", singer=lead.singer)
harmony.parts.append(phrase.clone(transpose=7, at_beat=0))
lead.parts.append(phrase.clone(at_beat=8))

song.set_tempo(8, 110)
seconds = song.seconds_at(10)  # integrates the complete tempo map
beat = song.beat_at(seconds)
```

Cloning deep-copies mutable controls. Editing the harmony will not edit its
source phrase. Overlapping notes within one voice part are invalid; use separate
tracks for polyphony. Note positions and automation are **part-local**; part
positions and tempo changes are **project-absolute**. Beat helpers always mean
quarter-note beats, independently of time signatures, rounded to 1/480 beat.
There are no implicit beats/seconds conversions. Use `TimeSignature` for meter
changes at explicit bar positions.

## Edit existing projects without stripping settings

```python
song = Project.load("original.ustx")
song.tracks[0].parts[0].notes[0].pitch = Pitch.parse("F#4")
song.validate()
song.save("revision.ustx")
```

Unknown mapping fields are retained through loading/saving at project, track,
render-settings, part, note, pitch, vibrato, phoneme, descriptor, and curve levels.
Each object's `extras` is an explicit escape hatch. `to_document()` returns an
independent complete USTX mapping; `from_document()` validates the result.
Known typed fields take precedence over same-name `extras` entries.

Wave parts are retained as opaque mappings in their owning track's `wave_parts`;
track reordering updates their track numbers. A typed audio-part editing API is
not implemented. Save/load preserve data semantics, not YAML formatting,
comments, or unknown future schema versions. Expression descriptors and
per-track overrides can be authored through `ExpressionDescriptor`.

New projects default to USTX **0.7** for the installed older OpenUtau. Versions
0.7, 0.8 and 0.9 can be loaded and explicitly authored; the version is preserved,
not silently upgraded. The installed core was checked against 0.7 only. A newer
project may require a newer OpenUtau; selecting an older version does not
backport arbitrary future fields in `extras`.

Objects and lists are intentionally mutable, as editing is the central workflow.
Convenience methods catch immediate errors. `validate()` and `save()` check
direct low-level edits and include object paths in errors. Existing files require
explicit `overwrite=True`; validation/serialization complete before opening the
destination. Keep revisions if you need recoverable history. Save is not a
transactional multi-file operation.

## Actual OpenUtau compatibility check (optional)

```python
from pyopenutau import OpenUtauCore

check = OpenUtauCore().check(song)
print(check.notes, check.supported_version, check.scope)

# For a nonstandard installation:
# OpenUtauCore("/path/to/directory-containing-OpenUtau.Core.dll").check(song)
```

Requires a .NET 8 **SDK**, not just its runtime, plus a separately installed
OpenUtau. The normal macOS app directory is detected. A small subprocess bridge
uses the real C# deserializer, time axis, and note validation. All helper builds
and OpenUtau profile/cache state are isolated in temporary directories; it does
not register singers, search plugins, edit preferences, or change bank files.
No NuGet packages are fetched. The probe is version-sensitive and fails explicitly
if its isolation bootstrap is unsupported. It is not a renderability test:
singer resolution, phonemization, rendering, and GUI round-trip listening have
not been checked by it.

## Type-system decisions

- Concrete dataclasses for OpenUtau concepts; no public untyped score dictionary.
- Immutable `Pitch` value objects inside mutable notes; names/MIDI coercion only
  at the convenience boundary (`add_note` / `Pitch.parse`).
- Separate `PitchCurve`, `AutomationCurve`, and `PhonemeOverride` types. These are
  not interchangeable merely because they contain numbers.
- Explicit `_ticks`, `_ms`, `_cents`, `_percent`, and `_db` names at the low-level
  boundary. No float subclass trying to guess units; ordinary beat helpers stay
  concise. Python won't statically distinguish two raw integers, so units are
  also documented and validated at persistence boundaries.
- `ExpressionKind` and `PitchShape` enums, native expression descriptors, and a
  `py.typed` marker for downstream autocomplete/type checking.
- Dynamic `Any` is confined to USTX serialization, forward-compatible `extras`,
  and the optional subprocess response—not normal note/track authoring.

## Verification

See the [engine guide](../HEADLESS.md) for capabilities and deliberate boundaries,
and [contributing guide](../CONTRIBUTING.md) for portable and engine test commands.

```sh
python -m pip install -e '.[dev]'
python -m pytest
mypy
python examples/compose.py new-song.ustx
```

Engine integration tests require an explicit `--run-integration` opt-in and a
separately installed .NET SDK/OpenUtau. Portable tests need neither.
The bridge test verifies real pitch-unit conversion and part
offsets, but makes no claim about audible quality.

OpenUtau is a separate project, not bundled or represented as Python code.
Schema references: `OpenUtau.Core/Ustx/{UProject,UTrack,UPart,UNote,UCurve,UPhoneme,UExpression}.cs`
and `OpenUtau.Core/Format/USTx.cs` in the upstream source. See [NOTICE](../NOTICE)
for the upstream license notice. This package is not an official OpenUtau SDK.
