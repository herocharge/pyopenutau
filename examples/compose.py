"""Run after installing pyopenutau: python examples/compose.py new-song.ustx.

The lyrics below are opaque example syllables; select aliases/phonemizer that
your singer actually supports. This authors a project, not an audio render.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pyopenutau import (
    PhonemeOverride, PitchCurve, PitchPoint, PitchShape, Project, RenderSettings,
)


def compose(singer: str | None = None) -> Project:
    project = Project("Python composition", bpm=140)
    lead = project.add_track("Lead", singer=singer)
    lead.render_settings = RenderSettings(renderer="WORLDLINE-R")
    phrase = lead.add_voice_part("Opening", beat=0)

    # Omitted beat means append. Explicit beat=4 leaves a one-beat rest.
    first = phrase.add_note("a", "C4", length=1)
    phrase.add_note("i", "D4", length=1)
    held = phrase.add_note("u", "E4", length=1)
    phrase.add_note("+", "G4", beat=4, length=2)

    # Note-local pitch points: milliseconds and cents, not ticks/semitones.
    first.portamento = PitchCurve([
        PitchPoint(-40, -80, PitchShape.SINE_IN_OUT),
        PitchPoint(100, 0, PitchShape.LINEAR),
    ], snap_first=False)
    held.vibrato.length_percent = 70
    held.vibrato.depth_cents = 35
    held.vibrato.period_ms = 170
    held.set_expression("vel", 120)
    held.phoneme_overrides.append(PhonemeOverride(index=0, offset_ticks=-10))

    # Part-level curves use beats in this helper and native expression units.
    phrase.curve("dyn").set(0, -60).set(.5, 0).set(5, 0).set(6, -60)
    phrase.curve("pitd").set(0, 0).set(2, 0).set(2.5, 25).set(3, 0)

    harmony = project.add_track("Harmony", singer=singer)
    harmony.volume_db = -6
    harmony.pan = 25
    harmony.parts.append(phrase.clone(transpose=7, at_beat=0))
    lead.parts.append(phrase.clone(at_beat=8))
    project.set_tempo(8, 120)
    return project


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--singer", help="Exact registered OpenUtau singer ID (not a bank path)")
    args = parser.parse_args()
    project = compose(args.singer)
    output = project.save(args.output)
    print(f"Authored {output}; {len(project.tracks)} tracks. No audio has been rendered.")


if __name__ == "__main__":
    main()
