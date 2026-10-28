# Compatibility and evidence

## Supported boundary

| Feature | Status |
| --- | --- |
| Python project authoring / USTX import/export | Python 3.10+, portable Python tests |
| USTX schema | 0.7 default; explicit 0.8/0.9 authoring/import; no automatic backport |
| Headless engine | Experimental macOS ARM64, OpenUtau 0.1.565 / core USTX 0.7 |
| Synthesis | Classic voicebanks, actual managed WORLDLINE-R renderer |
| Contextual phonemization | Built-in Japanese VCV integration tested; direct aliases tested |
| Real-bank smoke test | Separately supplied Teto bank, metadata-selected Japanese Presamp |
| Windows/Linux engine or newer OpenUtau | Not integration-verified; no compatibility promise |
| DiffSinger/ENUNU/other renderers, external plugins/resamplers | Not implemented by the headless adapter |

See [engine guide](../HEADLESS.md) for the detailed capability boundary. Portable
CI on an OS does not imply its native renderer is validated. A successful
deserialization check also does not establish renderability or lyric quality.

## Reference engine installation

The verified local application identifies itself as `OpenUtau/0.1.565` in
`OpenUtau.deps.json`, targets .NET 8 / `osx-arm64`, and bundles runtime 8.0.19.
The bridge ran with .NET SDK **8.0.130**, runtime **8.0.30**, Python **3.11.14**
and USTX 0.7 on macOS ARM64. Its core assembly version reports `1.0.0.0`, and
its application plist reports `0.0.0`; neither is a useful release identifier.

[engine-fingerprint.json](engine-fingerprint.json) records SHA-256 hashes of key
files from the installation actually exercised. These identify that tested
installation; they are not publisher signatures, a complete dependency lock,
or proof that a different build with the same release label is compatible.
No proprietary bank data or personal paths are in the fingerprint.

The [upstream 0.1.565 tag](https://github.com/openutau/OpenUtau/releases/tag/0.1.565)
remains a source reference, but its release page may not expose historical
application binaries. **A new user without a compatible installation cannot
currently reproduce native rendering from this Python repository alone.** We
do not bundle binaries, promise that rebuilding upstream yields identical
hashes, or silently download a newer application. Authoring, portable tests and
synthetic bank generation remain reproducible independently.

Provision a trusted compatible application before running `--run-integration`.
Contributions should establish a pinned, auditable cross-platform engine build
before broadening that claim or enabling native integration CI. Mismatched
internal APIs fail explicitly; never bypass the state-isolation bootstrap to
make an unsupported version appear compatible.

## What is verified

Tests generate a bank from a harmonic waveform with known F0; no copyrighted
recording or downloaded bank is a test dependency. Checks cover emitted schema,
pitch-unit conversion, tempo/part offsets, OTO timing, phoneme overrides, VCV
context, rendered pitch/octave bends, automation, volume/pan, mute/solo,
cancellation/deadlines, file protection and unchanged bank inputs.

They do not establish natural singing, intelligible lyrics, the accuracy of
an arbitrary phonemizer, or coverage of every OpenUtau release. The optional
Teto example is a personal-bank smoke demonstration, not a redistributable test
fixture or automatic quality benchmark.
