# Changelog

## 0.3.0 — first standalone repository candidate

- Typed project authoring, USTX import/export, preservation of unknown mapping
  fields, validation, exact-unit controls and musical beat helpers.
- Optional isolated headless OpenUtau bridge: discovery, phonemization and
  WORLDLINE-R rendering with Classic banks, typed diagnostics, progress,
  cancellation, deadlines and output protection.
- `Vocal` single-voice convenience API, voicebank metadata preferences, optional
  project save and access to underlying project/track/part/note objects.
- `OPENUTAU_ASSEMBLY_DIR` for portable engine configuration; explicit constructor
  paths take precedence. No engine downloads or global singer registration.
- Standalone setup docs, generated synthetic demo, portable tests, opt-in engine
  tests, type checks, package-build verification and CI configuration.
- Original code licensed under MIT; upstream OpenUtau notice retained. No
  recordings, real voicebank samples or engine binaries are included.

Earlier 0.1/0.2 wheels were local development artifacts, not public releases.
