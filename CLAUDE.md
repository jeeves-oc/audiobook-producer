# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Audiobook Producer is a Python CLI app that transforms public domain text into full-cast audio dramas with distinct character voices, narration, and procedurally generated background music. Uses only free tools (no API keys required). See PLAN.md for the full implementation roadmap.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
# System dependency: ffmpeg (brew install ffmpeg)

# Run with bundled demo story
python producer.py -v

# Run with custom input
python producer.py story.txt -o output.mp3

# List available TTS voices
python producer.py --list-voices

# Run tests
pytest test_producer.py -v
```

## Architecture

Single-file design: everything lives in `producer.py`, organized by section comments (constants → dataclass → parse → voices → TTS → music → assemble → export → CLI → main). All magic numbers are module-level constants at the top of the file.

The pipeline runs 6 sequential steps:

1. **Parse** — Regex-based text segmentation (paragraphs → dialogue/narration `Segment` dataclass instances). First-person "I" attributions map to narrator.
2. **Assign voices** — Hash-based deterministic mapping: `hash(speaker) % len(voices)` from a pool of 14 edge-tts neural voices. Voice is set directly on `Segment.voice`.
3. **Generate TTS** — Sequential `edge_tts.Communicate()` calls with exponential backoff retry (3 attempts). Always shows progress counter + ETA.
4. **Generate music** — Procedural ambient drone via numpy sine waves (A-minor), no external files
5. **Assemble** — Concatenate segments with type-aware pauses (300/500/700ms constants), overlay music at -22dB, fade in/out
6. **Export** — MP3 at 192kbps with metadata tags

## Key Conventions

- **pedalboard is optional**: imported via `try/except ImportError` with graceful fallback
- **Temp files**: created with `tempfile.mkdtemp()`, cleaned up in `finally` block via `shutil.rmtree()`
- **Voice assignment is deterministic**: hash-based, stable across text edits (adding a character doesn't reshuffle others)
- **Input validation**: fail fast — check file exists, non-empty, segments produced, ffmpeg installed
- **Demo story**: bundled at `demo/tell_tale_heart.txt` (Poe, public domain)

## Testing

`test_producer.py` covers the pure functions with branching logic:
- `parse_story()`: narration segments, dialogue extraction, speaker attribution, first-person handling, long segment splitting, empty paragraph skipping
- `assign_voices()`: narrator voice, hash-based assignment, determinism, wrap-around with many speakers
