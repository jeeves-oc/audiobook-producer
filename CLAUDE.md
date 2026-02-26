# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Audiobook Producer is a Python CLI app that transforms public domain text into full-cast audio dramas with distinct character voices, narration, and procedurally generated background music. Uses only free tools (no API keys required). See PLAN.md for the full implementation roadmap.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
# System dependency: ffmpeg (brew install ffmpeg)

# Run tests (TDD anchor — always run this first)
pytest test_producer.py -v

# Run with bundled demo story
python producer.py -v

# Run with custom input
python producer.py story.txt -o output.mp3

# List available TTS voices
python producer.py --list-voices
```

## Development Method — TDD via Ralph Loop

This project is built test-first in atomic phases. Each phase writes failing tests, implements until green, commits. A fresh agent session picks up from git state:

1. Run `pytest test_producer.py -v 2>&1 | tail -40` to see current state
2. First failing test = current phase's work
3. All green = check PLAN.md for next uncommitted phase
4. Implement current phase, verify green, commit with detailed message, stop

See PLAN.md "TDD Phases — Ralph Loop Iteration Guide" for the full phase list and test inventory.

**Done condition**: all tests green AND `python producer.py -v` produces a playable MP3.

## Architecture

Single-file design: everything lives in `producer.py`, organized by section comments (constants → dataclass → parse → voices → TTS → music → assemble → export → CLI → main). All magic numbers are module-level constants at the top of the file.

The pipeline runs 6 sequential steps:

1. **Parse** — Regex-based text segmentation. First-person "I" attributions map to narrator.
2. **Assign voices** — Hash-based deterministic mapping: `hash(speaker) % len(voices)`. Voice set directly on `Segment.voice`.
3. **Generate TTS** — Sequential `edge_tts.Communicate()` calls with exponential backoff retry (3 attempts). `generate_tts()` is sync, uses `asyncio.run()` internally per segment. Progress counter + ETA.
4. **Generate music** — Procedural ambient drone via numpy sine waves (A-minor).
5. **Assemble** — Concatenate with type-aware pauses (300/500/700ms), overlay music at -22dB, fade in/out.
6. **Export** — MP3 at 192kbps with metadata tags.

## Testing

`test_producer.py` is the single test file covering all phases. Tests use:
- **Pure function tests** for parse and voice logic (no mocks needed)
- **`unittest.mock.patch`** on `edge_tts.Communicate` for TTS tests (returns async mock writing tiny MP3)
- **`unittest.mock.patch("shutil.which")`** to mock ffmpeg availability
- **`tmp_path` fixture** for all file I/O
- **`AudioSegment.silent()`** to create real pydub objects without ffmpeg

## Key Conventions

- **pedalboard is optional**: imported via `try/except ImportError` with graceful fallback
- **Temp files**: created with `tempfile.mkdtemp()`, cleaned up in `finally` block via `shutil.rmtree()`
- **Voice assignment is deterministic**: hash-based, stable across text edits
- **Input validation**: fail fast — check file exists, non-empty, segments produced, ffmpeg installed
- **Demo story**: bundled at `demo/tell_tale_heart.txt` (Poe, public domain)
- **Commit convention**: detailed multi-line messages — short imperative subject, body explaining what and why
