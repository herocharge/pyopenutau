"""Render an original, wordless Teto phrase through the real OpenUtau engine.

PYTHONPATH=src python examples/teto_sample.py --bank /path/to/bank new-output-dir
The output directory must not already exist. No voicebank files are modified.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pyopenutau import EngineProgress, Vocal


def compose(bank: str | Path) -> Vocal:
    vocal = Vocal(bank, name="A little Teto phrase", bpm=120)
    vocal.track.volume_db = -6
    melody = (
        ("C4", 1), ("E4", 0.5), ("G4", 0.5), ("A4", 2),
        ("G4", 1), ("E4", 1), ("D4", 2),
        ("E4", 1), ("F4", 0.5), ("E4", 0.5), ("D4", 2), ("C4", 4),
    )
    for index, (pitch, length) in enumerate(melody):
        note = vocal.add_note("ら", pitch, beat=0.5 if index == 0 else None, length=length)
        if length >= 2:
            note.vibrato.length_percent = 55
            note.vibrato.period_ms = 180
            note.vibrato.depth_cents = 22
            note.vibrato.fade_in_percent = 25
            note.vibrato.fade_out_percent = 20
    vocal.part.curve("dyn").set(0.5, -15).set(1.5, 0).set(15, 0).set(16.5, -80)
    return vocal


def progress(event: EngineProgress) -> None:
    print(event.stage, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--bank", type=Path, required=True)
    args = parser.parse_args()
    vocal = compose(args.bank)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    vocal.save(args.output_dir / "sample.ustx")
    result = vocal.render(args.output_dir / "sample.wav", progress=progress)
    print(f"Rendered {result.duration_seconds:.3f} seconds; peak {result.peak_abs:.3f}")


if __name__ == "__main__":
    main()
