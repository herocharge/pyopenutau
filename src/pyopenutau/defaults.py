"""OpenUtau stock expression descriptors, independent of the old experiments."""

from .types import ExpressionDescriptor, ExpressionKind


def expressions() -> dict[str, ExpressionDescriptor]:
    specs = [
        ("dyn", "dynamics (curve)", -240, 120, 0, "", True),
        ("pitd", "pitch deviation (curve)", -1200, 1200, 0, "", True),
        ("vel", "velocity", 0, 200, 100, "", False),
        ("vol", "volume", 0, 200, 100, "", False),
        ("atk", "attack", 0, 200, 100, "", False),
        ("dec", "decay", 0, 100, 0, "", False),
        ("gen", "gender", -100, 100, 0, "g", False),
        ("genc", "gender (curve)", -100, 100, 0, "", True),
        ("bre", "breath", 0, 100, 0, "B", False),
        ("brec", "breathiness (curve)", -100, 100, 0, "", True),
        ("lpf", "lowpass", 0, 100, 0, "H", False),
        ("norm", "normalize", 0, 100, 86, "P", False),
        ("mod", "modulation", 0, 100, 0, "", False),
        ("mod+", "modulation plus", 0, 100, 0, "", False),
        ("alt", "alternate", 0, 16, 0, "", False),
        ("shft", "tone shift", -36, 36, 0, "", False),
        ("shfc", "tone shift (curve)", -1200, 1200, 0, "", True),
        ("tenc", "tension (curve)", -100, 100, 0, "", True),
        ("voic", "voicing (curve)", 0, 100, 100, "", True),
    ]
    result = {abbr: ExpressionDescriptor(name, abbr, ExpressionKind.CURVE if curve
                                       else ExpressionKind.NUMERICAL, low, high, default,
                                       flag=flag, is_flag=bool(flag))
              for abbr, name, low, high, default, flag, curve in specs}
    for abbr, name, choices in [("clr", "voice color", []), ("eng", "resampler engine", ["", "worldline"]),
                                ("dir", "direct", ["off", "on"])]:
        result[abbr] = ExpressionDescriptor(name, abbr, ExpressionKind.OPTIONS,
                                           0, len(choices) - 1, 0, choices)
    return result
