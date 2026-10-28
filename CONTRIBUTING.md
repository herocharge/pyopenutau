# Contributing and reproducing checks

This is an [AI-generated project](AI_DISCLOSURE.md), including its initial tests
and documentation. Contributors must understand and verify their changes; state
material AI assistance in pull requests. Test results are not an independent audit.

Work from this repository root, not a parent application or OpenUtau source tree.
No prior audio-conversion project is required.

## Fresh development environment

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps --no-build-isolation -e .
python -m pytest
python -m mypy
```

Python 3.11 is the reference development interpreter. `requirements-dev.txt`
pins the tested direct dependencies/tools, with a NumPy compatibility pin for
Python 3.10. It is not a complete hash-locked transitive environment. Alternatively
use `pip install -e '.[dev]'` to test supported dependency ranges. Network access
is needed to provision Python dependencies/SDK/engine, not for ordinary authoring
or our synthetic/direct-alias test workflow afterward.

## Tests without OpenUtau

`python -m pytest` runs portable authoring, validation, serialization, process
control and output-safety tests. Engine tests are explicitly skipped; CI does
not misrepresent those as successful engine renders. No real bank/recording is
needed, and importing the package must not import numerical DSP or GUI modules.

CI tests Python 3.10–3.13 on Linux and Python 3.11 on Windows/macOS. These are
portable Python checks, not claims about native rendering on those platforms.
Strict typing covers the public implementation, examples and helper scripts.

## Tests with OpenUtau

Provision the tested compatible installation as described in [setup](docs/SETUP.md),
then explicitly opt in:

```sh
export OPENUTAU_ASSEMBLY_DIR="/path/to/OpenUtau/assemblies"
python -m pytest --run-integration
```

This runs **both** portable and real engine tests. An explicit opt-in with a
missing SDK/core fails instead of silently skipping. NumPy is a test-only
dependency. Tests create harmonic samples with known timing and pitch in temp
directories; they do not use or modify a personal voicebank. Rendering tests
check input hashes and absence of newly written bank files. They validate control
semantics and signal structure, not naturalness, lyric clarity or every plugin.

Native integration isn't provisioned in public CI yet: historical compatible
binary availability and CPU/native dependencies need a separately audited setup.
Don't substitute a moving latest release and claim the compatibility target passed.

## Build and test the distribution

```sh
python -m build --no-isolation
python scripts/check_dist.py dist
```

Build produces a wheel and source tarball. The check inspects their contents for
packaged bridge sources, typing marker and notices, and rejects bundled audio,
engine binaries, private absolute paths and local caches. Install the wheel in
a **fresh** environment and run examples outside the source directory to catch
imports that accidentally rely on an editable checkout:

```sh
python3 -m venv /tmp/pyopenutau-wheel-check
/tmp/pyopenutau-wheel-check/bin/python -m pip install dist/pyopenutau-0.3.0-py3-none-any.whl
cd /tmp
/tmp/pyopenutau-wheel-check/bin/python -c "from pyopenutau import Project; Project().save('fresh-project.ustx')"
```

Use a new temporary directory/filename each time. No automatic upload, release,
Git initialization or remote creation is performed by these commands.

## Design boundaries

Preserve concrete typed authoring objects and explicit unit names. Keep the
common `Vocal` path small without hiding low-level project controls. Never guess
lyrics/language, download trained models, change desktop registration, overwrite
an existing output silently, or weaken the bridge's fail-closed state isolation.

Changes to engine integration need synthetic regressions with known ground truth.
Update docs when support changes. Unknown USTX fields must survive round trips.
Respect upstream/voicebank licenses and keep the OpenUtau notice intact.
