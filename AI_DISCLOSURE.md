# AI-generated code disclosure

**This repository was initially generated and iteratively developed using
OpenAI Codex under human direction.** Substantial portions of its Python/C#
implementation, API design, tests, examples, packaging, CI configuration, and
documentation were AI-generated. It should not be represented as an independently
human-written or independently audited implementation.

## What that means for users

- Treat it as experimental software and review changes before relying on them.
- Tests and documentation were also AI-generated. Passing those tests provides
  regression evidence, not independent proof that the design or implementation
  is correct, secure, portable, or musically useful.
- Compatibility claims are limited to the recorded checks and environment in
  [the compatibility document](docs/COMPATIBILITY.md). No broad security audit,
  production-readiness certification, or cross-platform native-rendering
  guarantee has been performed.
- Use trusted inputs and dependencies, preserve your originals, and follow the
  [security notes](SECURITY.md).

## Code generation is not audio generation

The development process used a generative AI coding assistant. The library's
rendering workflow uses separately installed OpenUtau and sample-based Classic
voicebanks; it does not use a generative audio model, voice-cloning model, or
language-recognition model to create the vocal.

## Upstream work and future contributions

This disclosure describes this project's development process, not the provenance
of upstream OpenUtau, Python dependencies, or voicebanks. Their authorship and
licenses remain separate; see [NOTICE](NOTICE) and [LICENSE](LICENSE).
Future contributors should describe material AI assistance in their pull
requests and remain responsible for understanding and verifying submitted code.
