# Headless OpenUtau engine

The engine milestone is implemented in `OpenUtauEngine`: discover local singers,
inspect aliases, run built-in phonemizers, and render a vocal project to a WAV.
These operations use **OpenUtau's own managed core and WORLDLINE-R phrase
renderer**, not a substitute Python synthesis engine.

## First render

For a single voice, use the managed shortcut:

```python
from pyopenutau import Vocal

vocal = Vocal("/path/to/voicebank", bpm=120)
vocal.add_note("a", "C4")
vocal.add_note("+", "E4")
vocal.add_note("a", "G4", length=2).vibrato.length_percent = 60
audio = vocal.render("new-vocal.wav")
```

Replace the lyrics with ones supported by your bank. `Vocal` honors its
`character.yaml` default phonemizer, falling back to direct aliases only when no
preference is declared. `phonemizer="Full.Plugin.ClassName"` is an explicit
override. No lyric/language detection or automatic singer search occurs.
`.project`, `.track`, `.part`, and returned notes retain full low-level control.
`.save()` is optional; `.phonemize()` is optional inspection. Rendering validates
phonemes itself, so a second validation pass is not required.

For repeated jobs, pass a caller-owned engine (including custom assembly paths):

```python
from pyopenutau import OpenUtauEngine

with OpenUtauEngine() as engine:
    inspected = vocal.phonemize(engine=engine)
    audio = vocal.render("another-take.wav", engine=engine)
```

Otherwise every call creates and reliably closes its own engine, also on errors.
Cancellation, timeout, progress and overwrite options are accepted by the
shortcut with the same semantics as the low-level engine. Rendering doesn't
save a USTX or sidecar report. `Vocal` binds only its original bank; use the
explicit API for a multi-singer project:

```python
from pathlib import Path
from pyopenutau import OpenUtauEngine, Project

song = Project("Written in Python", bpm=120)
lead = song.add_track("Lead", singer="voice")
phrase = lead.add_voice_part(beat=1)
phrase.add_note("a", "C4")
phrase.add_note("+", "E4")
held = phrase.add_note("a", "G4", length=2)
held.vibrato.length_percent = 60
held.vibrato.depth_cents = 30

with OpenUtauEngine() as engine:
    bindings = {"voice": Path("/path/to/voicebank")}
    inspected = engine.phonemize(song, singers=bindings)
    for phone in inspected.phonemes:
        print(phone.position_ms, phone.mapped_alias, phone.sample_path)
    if inspected.has_errors:
        raise RuntimeError(inspected.diagnostics)

    audio = engine.render(song, "new-vocal.wav", singers=bindings)
    print(audio.output, audio.duration_seconds, audio.peak_abs)
```

Replace `a` with a real alias, or select a built-in phonemizer and its supported
lyrics. This example's default phonemizer uses direct aliases. The `+` note is
OpenUtau's native melisma convention: it extends the preceding syllable with a
new pitch, rather than retriggering an independent consonant.

In the explicit API, `voice` is a **session-local binding ID**. It needn't be installed/registered in
the desktop app. Bind several IDs for several tracks/singers. No singer is
automatically selected or registered, and nothing is specific to Teto or a
particular language. Every nonempty track needs a singer binding, including
muted tracks, because phoneme inspection validates them too. Empty unassigned
tracks are allowed.

The output directory must exist. Existing output files require explicit
`overwrite=True`; publication uses a temporary file on the destination filesystem
and an atomic link/replace. Validation, crashes, callback exceptions, timeouts,
and cancellation before publication do not overwrite the destination. File
systems must support hard links for non-overwriting atomic publication.

## Discover singers, aliases, and phonemizers

```python
with OpenUtauEngine() as engine:
    for singer in engine.singers(["/path/to/Singers", "/another/bank-parent"]):
        print(singer.id, singer.name, singer.path, singer.singer_type)

    for oto in engine.otos("/path/to/voicebank"):
        print(oto.alias, oto.sample_path, oto.preutter_ms, oto.consonant_ms)

    capabilities = engine.capabilities()
    print(capabilities.supported_version, capabilities.renderers)
    for plugin in capabilities.phonemizers:
        print(plugin.class_name, plugin.tag, plugin.language)
```

Only explicitly supplied singer roots are searched, including the root itself.
Discovery IDs are informational and can collide across roots; bindings explicitly
choose each bank directory. Invalid bank metadata raises an error rather than
being silently omitted. Use `otos()` to read OpenUtau's OTO interpretation,
including aliases from subdirectories. Singer discovery can report non-Classic
banks, but OTO inspection and this host's rendering currently require Classic.

The bundled phonemizer assembly is loaded from the specified OpenUtau install.
Only core/built-in plugins are discovered; external plugin directories aren't
scanned. Discovery doesn't establish that every plugin's language resources are
installed. A selected plugin's initialization/phonemization can fail; it will
not silently fall back to the default plugin. This release verifies the direct
phonemizer and the built-in Japanese VCV phonemizer against a synthetic bank.

## Detailed control and diagnostics

Use the existing typed project controls before rendering: note portamento in
milliseconds/cents, vibrato, per-phoneme expressions and overrides, part-level
automation, tempo changes, multiple tracks and voice parts, volume and pan.
OpenUtau performs phonemization, alias/pitch mapping, consonant timing,
crossfades/envelopes, phrase synthesis, and mixing. The host also initializes
derived mute/solo state normally provided by the GUI.

Phonemization returns immutable `PhonemeInfo` and `EngineDiagnostic` records:

- Track, part, note, and phoneme indices are zero-based. Part indices are local
  to their track. Note indices follow OpenUtau's time-sorted note order.
- `position_ticks` is **part-local**; `position_ms` is **project-absolute**.
  Negative onset ticks are allowed for consonant lead-ins. Durations, preutter,
  and overlap are explicit tick/ms fields, not guessed audio timings.
- `mapped_alias` and `sample_path` identify what OpenUtau resolved.
- Missing aliases produce diagnostics and `has_errors=True`. Render refuses
  phonemization errors instead of silently returning a partial or empty vocal.
- Global diagnostics use index `-1` where no track/part/note applies.

`RenderResult` includes the output path, rate, channels, frame count, peak,
core assembly version, and SHA-256 of the exact serialized project snapshot
executed by the host. The input Python project is not changed by rendering.
Callbacks or another thread changing it after the snapshot cannot change that
operation's authored controls. Sample/bank files are not snapshotted; don't
change those concurrently while rendering.

Output is interleaved **44.1 kHz stereo IEEE-float32 WAV**, without an added peak
normalization pass. Peaks above full scale are retained and produce a warning;
lower track volume before PCM conversion/playback if needed. Track volume uses
OpenUtau's fader law (including its low-end mute threshold), not an independent
Python gain law. Renders start at project time zero, preserve leading rests,
and retain OpenUtau's synthesized tail; arbitrary trailing empty part display
space is not guaranteed to become silence. Fully muted projects with notes
produce silence. Empty/unrenderable projects fail explicitly. Headless projects
must be shorter than one hour; this is checked before core curve allocation,
and a corresponding safety limit also bounds output accumulation.

## Progress, cancellation, and deadlines

```python
from pyopenutau import CancellationToken, EngineCancelled, OpenUtauEngine

token = CancellationToken()

def on_progress(event):
    print(event.stage, event.fraction)
    # A UI/another thread may call token.cancel().

with OpenUtauEngine() as engine:
    try:
        result = engine.render(song, "another-new-vocal.wav", singers=bindings,
                               cancel=token, timeout=120, progress=on_progress)
    except EngineCancelled:
        print("Cancelled; no new output was published")
```

This is a synchronous API; run it in your own worker thread if your application
must remain interactive. Progress callbacks run on the calling Python thread.
Stages are `building`, `phonemizing`, `rendering`, and `complete`. Intermediate
fractions are `None`; the API doesn't invent a percentage/ETA. `complete` means
engine work finished and precedes final output publication, so cancelling from
that callback can still prevent publication. Recursively calling or closing the
same session from a callback is rejected immediately; calls are serialized.
Callbacks may cancel or edit a
project for a subsequent operation. Callback exceptions abort before publication.

Tokens are one-way; use a new token for a new cancellable operation. Cancellation
and `EngineTimeout` stop the isolated host, including native synthesis, rather
than waiting for the next note. POSIX child process groups are killed; Windows
uses process termination and is not integration-tested in this release. A
cancelled/failed operation doesn't poison the session. Timeouts cover host
build, waiting for the session lock, and execution, not just synthesis. Output
copy/publication is a short final filesystem operation, not interruptible audio
processing. Cleanup/`close()` waits for a running operation; cancel it first if
immediate shutdown is needed.

## Installation, isolation, and current limits

- Requires a separately installed **OpenUtau with native WORLDLINE-R** and a
  **.NET 8 SDK**. Normal macOS installation is the default. Other locations use
  `OPENUTAU_ASSEMBLY_DIR` or `OpenUtauEngine(assembly_dir="...")` (explicit paths
  take precedence); `dotnet="..."` selects the executable.
- A session compiles the small host once, with no NuGet packages/downloads.
  Each operation runs a new subprocess and has separate temporary preferences,
  cache, dictionaries, and document scheduling state. Use a context manager or
  call `close()` to remove that session's temporary build.
- The SDK/host protocol is explicitly versioned (version 1). Final responses
  use a separate JSON file so native stdout logging cannot corrupt results;
  progress notifications use a separate, version-tagged message envelope.
- The host bypasses OpenUtau's normal profile/cache-migration constructor and
  refuses to continue if state isolation cannot be established. It doesn't
  search the user's application profile or register singers. It reads the bank
  paths you bind; integration tests check that rendering/inspection leave those
  fixture banks unchanged, including no new analysis sidecars.
- This is **state isolation, not an OS security sandbox**. OpenUtau assemblies,
  built-in plugins and native libraries are trusted local executable code.
  Plugins may have their own resource/network behavior; use locally provisioned
  plugins/resources you trust. No resource downloader is implemented by this SDK.
- Verified on macOS ARM64 with OpenUtau 0.1.565 supporting USTX 0.7; see the
  [compatibility record](docs/COMPATIBILITY.md). The adapter
  uses internal managed APIs and fails explicitly for mismatches; untested
  versions/platforms aren't promised compatible merely because they deserialize.
- The supported headless renderer is **WORLDLINE-R with Classic voicebanks**.
  Other renderers, external plugins/resamplers, wave/accompaniment parts,
  playback streaming, arbitrary render ranges, and per-track stem export are
  not implemented. Those settings can still be authored in USTX for the desktop
  app, but the headless host rejects unsupported settings rather than ignoring
  them. No GUI is opened.

## Runnable example and verification

```sh
python examples/render.py --bank /path/to/bank --lyric 'a supported alias' new.wav
```

The example authors a short melody, prints resolved phonemes, and renders it.
It takes no reference recording. For another phonemizer, pass its installed
class name with `--phonemizer`.

Tests use a generated harmonic waveform as a voicebank sample. They verify
absolute timing and tempo integration, OTO overrides, contextual VCV aliases,
actual rendered pitch and octave bends, part automation, volume, pan, mute,
solo, cancellation, deadlines, output preservation, and unchanged input banks.
These are engine-control/structural tests—not a claim about natural singing
quality, lyric intelligibility, or coverage of every OpenUtau plugin.
