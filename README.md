# pyopenutau

> **AI-GENERATED CODE — EXPERIMENTAL SOFTWARE.** This project's implementation,
> tests, examples, and documentation were generated using OpenAI Codex under human
> direction. They have not been independently audited. Passing AI-written tests
> is not a guarantee of correctness, safety, or compatibility. Review the code
> before relying on it. See [AI disclosure](AI_DISCLOSURE.md).

Compose and edit vocal tracks in Python, export OpenUtau projects, and render
Classic voicebanks through OpenUtau's own engine—without operating its GUI.

```python
from pyopenutau import Vocal

vocal = Vocal("/path/to/voicebank", bpm=120)
vocal.add_note("ら", "C4")
vocal.add_note("ら", "E4")
vocal.add_note("ら", "G4", length=2).vibrato.length_percent = 60
vocal.render("vocal.wav")
vocal.save("song.ustx")  # optional editable project
```

Use lyrics your bank supports. `Vocal` uses the bank's declared phonemizer, or
direct sample aliases when none is declared. There is no language recognition,
source-audio conversion, voice cloning, or generative audio model.
The **code was AI-generated**; the vocal rendering workflow itself does not use
a generative AI audio model.

**Experimental, unofficial SDK.** Python authoring is portable. Headless rendering
uses OpenUtau internals and is currently verified only on macOS ARM64 with the
local .NET 8/OpenUtau installation described in [compatibility](docs/COMPATIBILITY.md).
Installing an arbitrary newer OpenUtau is not a compatibility guarantee.

## Install from this repository

Use Python **3.10 or newer**. From the cloned repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

On Windows activate with `.venv\Scripts\Activate.ps1`. The only runtime Python
dependency is PyYAML. No OpenUtau or .NET installation is needed to author USTX:

```sh
python examples/compose.py first-song.ustx
```

This is a source installation guide, not a claim that the package is on PyPI.

## Render locally

You must separately supply:

1. An **OpenUtau installation with WORLDLINE-R** and its managed/native libraries.
2. A **.NET 8 SDK**, not just the runtime (`dotnet --list-sdks` must include 8.x).
3. A Classic voicebank you are permitted to use, with its sample files intact.

See [setup and troubleshooting](docs/SETUP.md) before rendering. On macOS the
standard `/Applications/OpenUtau.app/Contents/MacOS` location is the default.
For a different location, set `OPENUTAU_ASSEMBLY_DIR` to the directory containing
`OpenUtau.Core.dll`, not the source tree or `.app` root:

```sh
export OPENUTAU_ASSEMBLY_DIR="/path/to/OpenUtau/assemblies"
```

An explicit `OpenUtauEngine(assembly_dir=...)` takes precedence over the variable.
Nothing is installed, downloaded or registered with the desktop app by this SDK.
Plugins may need their own separately provisioned resources.

### Reproduce without a third-party voicebank

```sh
python examples/synthetic.py output/synthetic
```

This creates a tiny harmonic test bank and renders a three-note phrase. It is a
**test tone, not Teto or natural singing**. The destination must be new. With no
engine installed, `--author-only` still creates the bank and USTX for inspection.

### Render your own bank

```sh
python examples/quickstart.py --bank "/path/to/voicebank" --lyric "supported lyric" vocal.wav
```

For the optional Teto melody, supply your own licensed Japanese Teto bank:

```sh
python examples/teto_sample.py --bank "/path/to/Teto bank" output/teto
```

No recordings, songs, voicebank samples, or OpenUtau binaries are distributed.
Existing outputs are protected. Output parents must exist except where an
example explicitly creates a fresh output directory. WAVs are 44.1 kHz stereo
float32; render does not normalize away clipping. Lower `.track.volume_db` if
`audio.peak_abs > 1`.

## Simple by default, detailed when needed

`Vocal.add_note()` returns a typed, editable `Note`. `.project`, `.track`, and
`.part` expose ordinary authoring objects—not a second score format.

```python
vocal.track.volume_db = -6
vocal.part.curve("dyn").set(0, -30).set(1, 0)
vocal.project.set_tempo(8, 100)
phones = vocal.phonemize()  # optional preview; render checks errors itself
```

Use `Project → Track → VoicePart → Note` directly for multiple voices, harmonies,
exact ticks, portamento, automation, or edits to existing projects. Reuse an
`OpenUtauEngine` for repeated renders to avoid rebuilding its temporary bridge.

- [Authoring and type/unit conventions](docs/AUTHORING.md)
- [Engine, inspection, cancellation, diagnostics and limitations](HEADLESS.md)
- [Setup and troubleshooting](docs/SETUP.md)
- [Compatibility and tested environment](docs/COMPATIBILITY.md)
- [Contributing, tests and packaging](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Scope and safety

Authoring supports USTX 0.7/0.8/0.9, defaults to 0.7, and preserves unknown mapping
fields. Saving is not synthesis. Headless rendering currently supports **Classic
banks with WORLDLINE-R only**; other engines, external resamplers/plugins,
accompaniment parts, playback streaming and stem export are not implemented.

The bridge uses fresh temporary application state and does not alter desktop
singer registration. This is **not an OS security sandbox**: use only trusted
local assemblies, plugins and voicebanks. See [security notes](SECURITY.md).

## License and attribution

Original project code: [MIT](LICENSE). OpenUtau-derived conventions and expression
metadata: [upstream notice](NOTICE). OpenUtau and each voicebank keep their own
licenses. This project is not affiliated with or endorsed by OpenUtau or Teto.
