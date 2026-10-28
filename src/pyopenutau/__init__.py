"""Python authoring for OpenUtau. No dependency on Voice2OpenUTAU experiments."""

from .project import Note, Project, Track, VoicePart
from .types import (
    RESOLUTION, AutomationCurve, CurvePoint, ExpressionDescriptor, ExpressionKind,
    ExpressionValue, PhonemeOverride, Pitch, PitchCurve, PitchPoint, PitchShape,
    RenderSettings, Tempo, TimeSignature, Vibrato,
)
from .validation import ValidationError
from .core import CoreCheckResult, CoreError, OpenUtauCore
from .engine import (CancellationToken, EngineCancelled, EngineCapabilities, EngineDiagnostic,
                     EngineProgress, EngineTimeout, OpenUtauEngine, PhonemeInfo,
                     PhonemizationResult, PhonemizerInfo, RenderResult, SingerInfo, OtoInfo, ProgressCallback)

from .vocal import Vocal

__all__ = [
    "Vocal", "Project", "Track", "VoicePart", "Note", "Pitch", "PitchPoint", "PitchCurve",
    "PitchShape", "Vibrato", "PhonemeOverride", "ExpressionValue", "ExpressionDescriptor",
    "ExpressionKind", "AutomationCurve", "CurvePoint", "RenderSettings", "Tempo",
    "TimeSignature", "ValidationError", "RESOLUTION", "OpenUtauCore", "CoreCheckResult", "CoreError",
    "OpenUtauEngine", "CancellationToken", "EngineCancelled", "EngineTimeout", "EngineProgress",
    "EngineCapabilities", "SingerInfo", "PhonemizerInfo", "EngineDiagnostic", "PhonemeInfo",
    "PhonemizationResult", "RenderResult", "OtoInfo", "ProgressCallback",
]
