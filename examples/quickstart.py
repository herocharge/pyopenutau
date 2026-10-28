"""Minimal single-voice render; provide your own bank and supported lyric."""

from __future__ import annotations

import argparse
from pathlib import Path

from pyopenutau import Vocal


def compose(bank: str | Path, lyric: str, *, bpm: float = 120) -> Vocal:
    vocal = Vocal(bank, bpm=bpm)
    vocal.add_note(lyric, "C4")
    vocal.add_note("+", "E4")
    vocal.add_note(lyric, "G4", length=2).vibrato.length_percent = 60
    return vocal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--lyric", required=True)
    args = parser.parse_args()
    result = compose(args.bank, args.lyric).render(args.output)
    print(f"{result.output}: {result.duration_seconds:.3f} seconds; peak {result.peak_abs:.3f}")


if __name__ == "__main__":
    main()
