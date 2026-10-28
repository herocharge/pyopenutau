"""Reproduce an engine render with a generated test bank, not a human voice.

python examples/synthetic.py output/synthetic
python examples/synthetic.py output/authoring --author-only
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import struct
import wave

from pyopenutau import Vocal


def create_demo(output_dir: Path) -> Vocal:
    """Create a fresh reproducible input; refuse existing output directories."""
    output_dir.mkdir(parents=True, exist_ok=False)
    bank = output_dir / "synthetic-bank"
    bank.mkdir()
    (bank / "character.txt").write_text("name=Synthetic test tone (not a human voice)\n", encoding="utf-8")
    (bank / "oto.ini").write_text("a.wav=a,0,40,-800,20,10\n", encoding="utf-8")
    samples = bytearray()
    for frame in range(44100):
        sample = sum(0.12 / harmonic * math.sin(2 * math.pi * 220 * harmonic * frame / 44100)
                     for harmonic in range(1, 13))
        samples.extend(struct.pack("<h", round(sample * 32767)))
    with wave.open(str(bank / "a.wav"), "wb") as writer:
        writer.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
        writer.writeframes(samples)
    vocal = Vocal(bank, name="Reproducible synthetic engine demo", bpm=120)
    vocal.track.volume_db = -6
    vocal.add_note("a", "A3", beat=1)
    vocal.add_note("a", "A4")
    vocal.add_note("a", "A5", length=2)
    vocal.save(output_dir / "project.ustx")
    return vocal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--author-only", action="store_true", help="Do not start OpenUtau or require .NET")
    args = parser.parse_args()
    vocal = create_demo(args.output_dir)
    if args.author_only:
        print(f"Created synthetic bank and project: {args.output_dir}")
        return
    result = vocal.render(args.output_dir / "render.wav")
    (args.output_dir / "render.json").write_text(
        json.dumps(asdict(result), indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Synthetic test tone: {result.output}; {result.duration_seconds:.3f}s; peak {result.peak_abs:.3f}")


if __name__ == "__main__":
    main()
