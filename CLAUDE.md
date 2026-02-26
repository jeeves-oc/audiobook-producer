# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Audiobook Producer is a Python CLI app that transforms public domain text into full-cast audio dramas with distinct character voices, narration, sound effects, and procedurally generated background music. Uses only free tools (no API keys required). See PLAN.md for the full implementation roadmap.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
# System dependency: ffmpeg (brew install ffmpeg)

# Run tests (TDD anchor — always run this first)
pytest tests/ -v

# Run with bundled demo story
python producer.py -v

# Run with custom input (output to output/<slug>/)
python producer.py story.txt -o mydir/

# List available TTS voices
python producer.py --list-voices
```

## Development Method — Parallel TDD via Ralph Loop

This project is built test-first with **parallel module development**. Modules at the same dependency layer can be built simultaneously by separate Ralph Loop agents. Each agent claims one module, writes tests, implements until green, commits.

1. Run `pytest tests/ -v 2>&1 | tail -40` to see current state
2. First failing test file = current module's work
3. All green = check PLAN.md for next unclaimed layer/module
4. **Check the Model strategy table in PLAN.md** for the recommended model
5. Implement module, verify green, commit with detailed message, `git push`, stop

**Model strategy**: Each module is tagged `[sonnet]` or `[opus]` in PLAN.md. Default to Sonnet (~5x cheaper). Assembly and integration use Opus. If a Sonnet module fails 2 iterations in a row, escalate to Opus.

See PLAN.md "TDD Phases — Parallel Ralph Loop Iteration Guide" for the full layer structure and test inventory.

**Done condition**: all tests green AND both demos produce playable MP3s:
1. `python producer.py demo/tell_tale_heart.txt -v` → `output/tell_tale_heart/final/tell_tale_heart.mp3`
2. `python producer.py demo/the_open_window.txt -v` → `output/the_open_window/final/the_open_window.mp3`

## Architecture

Multi-module package: `audiobook_producer/` with one module per concern. `producer.py` is a thin entry point.

```
audiobook_producer/
  constants.py    # all magic numbers
  models.py       # Segment dataclass
  parser.py       # parse_story(), extract_metadata()
  voices.py       # assign_voices(), bookend scripts (intro/outro)
  tts.py          # generate_tts(), edge-tts, retry logic
  music.py        # generate_ambient_music(), numpy synthesis
  effects.py      # reverb (pedalboard), normalization
  assembly.py     # assemble(), bookend music structure
  exporter.py     # export() MP3 + metadata
  artifacts.py    # output dirs, intermediate JSON, voice demos, resumability
  cli.py          # argparse, validation, pipeline orchestration
```

The pipeline:

1. **Parse** — Regex-based text segmentation + metadata extraction (title, author). First-person "I" attributions map to narrator.
2. **Assign voices + bookends** — sha256-based deterministic voice mapping. Narrator narration → American, narrator dialogue → British. Generate intro/outro segment scripts.
3. **Generate TTS** — Sequential `edge_tts.Communicate()` calls with exponential backoff retry (3 attempts). Processes all segments: intro + story + outro.
4. **Generate music** — Procedural ambient drone via numpy sine waves (A-minor).
4b. **Apply effects** — Reverb on dialogue (pedalboard, optional), volume normalization.
5. **Assemble** — Bookend structure: music intro → narrator intro over music bed → story with type-aware pauses (no music) → narrator outro over music bed → music fade out.
6. **Export** — MP3 at 192kbps with metadata tags to `output/<slug>/final/`.

Each pipeline step writes intermediate artifacts to `output/<slug>/` (script.json, cast.json, segments/, etc.) for inspection and resumability. In `-v` mode, voice demos are generated before full TTS with a preview gate prompt.

## Testing

Each module has its own test file in `tests/`. Shared fixtures in `tests/conftest.py`. Tests use:
- **Pure function tests** for parse and voice logic (no mocks needed)
- **`unittest.mock.patch`** on `audiobook_producer.tts.edge_tts.Communicate` for TTS tests (fully qualified path)
- **`unittest.mock.patch("shutil.which")`** to mock ffmpeg availability
- **`tmp_path` fixture** for all file I/O
- **`AudioSegment.silent()`** to create real pydub objects without ffmpeg
- **pedalboard mocks** in effects tests for environments without pedalboard

## Key Conventions

- **pedalboard is optional**: imported via `try/except ImportError` in effects.py with graceful fallback
- **hashlib.sha256 for voice assignment**: NOT `hash()` — Python's `hash()` is randomized per process since 3.3
- **Output directory**: `output/<slug>/` per production with intermediate JSON artifacts, voice demos, segments, music, and final MP3. Gitignored.
- **Resumability**: pipeline checks mtime on artifacts and skips fresh steps. `--force` to re-run everything.
- **Voice assignment is deterministic**: sha256-based, stable across runs and text edits
- **Input validation**: fail fast — check file exists, non-empty, segments produced, ffmpeg installed
- **Demo stories**: bundled at `demo/tell_tale_heart.txt` (Poe) and `demo/the_open_window.txt` (Saki), both public domain
- **Commit convention**: detailed multi-line messages — short imperative subject, body explaining what and why
