# Setup and troubleshooting

## 1. Install the Python package

From a fresh clone, using Python 3.10+:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
python examples/compose.py first-song.ustx
```

Windows PowerShell activation: `.venv\Scripts\Activate.ps1`.
Authoring requires only Python and PyYAML. No GUI, GPU, audio input permission,
ffmpeg, source checkout, trained model, NumPy or .NET is needed for that step.

## 2. Provision the optional rendering engine

Install a **.NET 8 SDK** from [Microsoft](https://dotnet.microsoft.com/download/dotnet/8.0).
Keep an 8.x SDK and runtime installed even if newer SDKs are also present.
Confirm `dotnet --list-sdks` and `dotnet --list-runtimes` list 8.x entries.
The first operation compiles a small bridge into a temporary directory; its
NuGet sources are disabled and it references local OpenUtau assemblies at runtime.
The SDK's own first-time setup must already work on your machine.

Obtain OpenUtau from its [official repository](https://github.com/openutau/OpenUtau).
The compatibility target is the older **0.1.565 / USTX 0.7** API, not whichever
release is newest. [The upstream tag](https://github.com/openutau/OpenUtau/releases/tag/0.1.565)
identifies the source; historical binary assets may not be available. The SDK
does not ship or download them. See [compatibility](COMPATIBILITY.md) for the
tested local assembly fingerprints and this reproducibility limitation.

Keep the entire application distribution intact, including managed dependencies,
built-in phonemizers and native WORLDLINE libraries. Copying just
`OpenUtau.Core.dll` is insufficient. Python, dotnet and native libraries must
have compatible CPU architectures (the verified configuration is ARM64).
Do not copy binaries from untrusted mirrors or bypass OS security blindly.

macOS default: install the app at `/Applications/OpenUtau.app`.
Otherwise configure the directory **containing** `OpenUtau.Core.dll`:

```sh
export OPENUTAU_ASSEMBLY_DIR="/path/to/OpenUtau/assembly-directory"
```

PowerShell:

```powershell
$env:OPENUTAU_ASSEMBLY_DIR = "C:\path\to\OpenUtau"
```

Or choose explicitly without changing process configuration:

```python
from pyopenutau import OpenUtauEngine

with OpenUtauEngine("/path/to/assembly-directory") as engine:
    print(engine.capabilities())
    # vocal.render("new.wav", engine=engine)
```

Explicit paths override `OPENUTAU_ASSEMBLY_DIR`; the macOS path is only a final
default. Windows/Linux rendering is not yet integration-verified. Failures on an
untested platform are not evidence that ordinary Python authoring is unsupported.

## 3. Reproduce an engine smoke test

```sh
python examples/synthetic.py output/synthetic
```

This generates a one-second harmonic sample, an OTO file, a short authored
project and a three-note WAV plus a JSON report. It uses no third-party sample
or recording. The result is intentionally a synthetic test tone, not a singing
quality demonstration. Re-run with a new directory; existing directories are
refused. `--author-only` exercises everything except the engine.

For structural/pitch/timing regression checks, follow the opt-in engine-test
instructions in [CONTRIBUTING.md](../CONTRIBUTING.md).

## 4. Supply a real voicebank

Extract a legally obtained **Classic** bank. Pass the directory containing its
`character.txt`, not a ZIP, the enclosing downloads folder, or the sample's
subdirectory. Preserve filenames, encodings, OTO files and metadata. The SDK
does not distribute Teto or register your bank with the desktop application.

```sh
python examples/quickstart.py --bank "/path/to/bank" --lyric "a supported lyric" first-vocal.wav
```

`Vocal` honors UTF-8 `character.yaml`'s `default_phonemizer`. Without a declaration,
it uses direct aliases, not guessed language recognition. Explicitly select a
built-in class when required. Some built-ins need separately provisioned language
resources; only direct aliases, Japanese VCV and the local Teto metadata-selected
Presamp smoke test have been exercised. Other plugins are not promised to work.

## Common failures

| Symptom | Check |
| --- | --- |
| `No module named pyopenutau` | Activate the environment used for installation; use its `python -m pip`. |
| `OpenUtau.Core.dll not found` | Configure the assemblies directory, not `.app`, ZIP or source root. |
| `.NET 8 SDK` / build error | Check SDK **and** runtime, PATH, architecture, writable temp storage. |
| Reflection / missing member / isolation bootstrap error | Engine API mismatch. Compare the tested fingerprint; do not disable isolation. |
| Native library load error | Keep the full application intact; match CPU architecture and native dependencies. |
| Missing alias / phonemization error | Inspect `vocal.phonemize().diagnostics`, bank aliases and selected plugin. |
| `Project ... newer than core` | Use a supported project version; lowering the label does not backport unknown features. |
| Existing file / missing output directory | Create the parent or use a new filename; overwrites require explicit opt-in. |
| Loud distorted output | Float WAV retains peaks above 1. Lower track volume before playback/PCM conversion. |

Reports should include Python/OS/architecture, dotnet SDK/runtime versions,
OpenUtau version/fingerprint, a minimal authored example and redacted diagnostics.
Do not attach a full voicebank or copyrighted recording.
