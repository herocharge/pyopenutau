"""Author and render through OpenUtau, without opening its desktop interface.

python examples/render.py --bank /path/to/bank --lyric 'actual alias' new.wav
Use --phonemizer with an installed built-in class name for non-direct lyrics.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pyopenutau import EngineProgress, OpenUtauEngine, Project


def compose(lyric: str, phonemizer: str = "OpenUtau.Core.DefaultPhonemizer") -> Project:
    project = Project("Headless Python vocal", bpm=120)
    track = project.add_track("Voice", singer="voice", phonemizer=phonemizer)
    phrase = track.add_voice_part(beat=1)
    phrase.add_note(lyric, "C4", length=1)
    phrase.add_note("+", "E4", length=1)
    held = phrase.add_note(lyric, "G4", beat=2.5, length=2)
    held.vibrato.length_percent = 60
    held.vibrato.depth_cents = 30
    phrase.curve("dyn").set(0, 0).set(3.5, 0).set(4.5, -60)
    return project


def progress(event: EngineProgress) -> None:
    print(event.stage, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bank", required=True, type=Path, help="Folder containing character.txt")
    parser.add_argument("--lyric", required=True, help="A supported alias/lyric for this bank and phonemizer")
    parser.add_argument("--phonemizer", default="OpenUtau.Core.DefaultPhonemizer")
    parser.add_argument("--assemblies", type=Path, help="Nonstandard OpenUtau assembly directory")
    args = parser.parse_args()
    project = compose(args.lyric, args.phonemizer)
    bindings = {"voice": args.bank}
    with OpenUtauEngine(args.assemblies) as engine:
        inspected = engine.phonemize(project, singers=bindings, progress=progress)
        for phone in inspected.phonemes:
            print(f"{phone.position_ms:8.1f} ms  {phone.mapped_alias or phone.phoneme}")
        if inspected.has_errors:
            for diagnostic in inspected.diagnostics:
                print(diagnostic.message)
            raise SystemExit("Fix the phoneme diagnostics before rendering")
        result = engine.render(project, args.output, singers=bindings, progress=progress)
        print(f"Rendered {result.output}: {result.duration_seconds:.3f} seconds, peak {result.peak_abs:.3f}")


if __name__ == "__main__":
    main()
