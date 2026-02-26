# Audiobook Producer — Implementation Plan

## Context

Build a Python CLI app that transforms public domain text into full-cast audio dramas with distinct character voices, narration, and background music. The user has no API keys, so we use free tools only. MVP targets a single short story ("The Tell-Tale Heart" by Poe) as a bundled demo. New public GitHub repo.

**Development method**: Test-driven development (TDD), structured for autonomous iteration via the Ralph Loop. Each phase writes failing tests first, then implements until green, then commits. A fresh agent session can pick up from git state alone by running `pytest test_producer.py -v` to see what's red.

**Done condition**: `pytest test_producer.py -v` is all green AND `python producer.py -v` produces a playable MP3 file of "The Tell-Tale Heart" with distinct character voices and background music.

## Project Structure

```
audiobook-producer/
  producer.py              # Single-file app (entire pipeline)
  test_producer.py         # Full test suite (pytest) — TDD anchor
  demo/
    tell_tale_heart.txt    # Bundled demo story (public domain)
  requirements.txt
  README.md
  .gitignore
  LICENSE                  # MIT
```

## Tech Stack

| Component | Choice | Why |
|-----------|--------|-----|
| TTS | edge-tts | Free, 322 neural voices, no API key, high quality |
| Text parsing | Regex (rule-based) | Zero dependencies, works well for classic literature |
| Audio mixing | pydub + ffmpeg | Standard Python audio stack |
| Audio effects | pedalboard (optional) | Spotify's lib for subtle reverb on dialogue |
| Background music | Procedurally generated (numpy) | No licensing, no downloads, reproducible |
| CLI | argparse (stdlib) | No extra dependency |
| Output | MP3 (192kbps) | Good quality, universal compatibility |
| Testing | pytest + unittest.mock | TDD with mocked I/O for edge-tts and ffmpeg |

## File Organization

`producer.py` uses section comments and a consistent ordering:

```
# ── Constants ──────────────────────────────────────────
# ── Data Classes ───────────────────────────────────────
# ── Parsing ────────────────────────────────────────────
# ── Voice Assignment ───────────────────────────────────
# ── TTS Generation ─────────────────────────────────────
# ── Background Music ───────────────────────────────────
# ── Assembly ───────────────────────────────────────────
# ── Export ─────────────────────────────────────────────
# ── CLI ────────────────────────────────────────────────
# ── Main ───────────────────────────────────────────────
```

## Constants

All magic numbers defined as module-level constants at the top of `producer.py`:

```python
SEGMENT_SPLIT_THRESHOLD = 500       # chars — split segments longer than this
PAUSE_SAME_TYPE_MS = 300            # ms pause between same-type segments
PAUSE_SPEAKER_CHANGE_MS = 500       # ms pause at speaker changes
PAUSE_TYPE_TRANSITION_MS = 700      # ms pause at narration/dialogue transitions
MUSIC_OVERLAY_DB = -22              # dB level for background music
MUSIC_LOOP_SECONDS = 30             # duration of generated ambient loop
OUTPUT_BITRATE = "192k"             # MP3 output bitrate
TTS_RETRY_COUNT = 3                 # max retries per TTS segment
TTS_RETRY_BASE_DELAY = 1.0         # seconds — base delay for exponential backoff
```

## Pipeline (6 Steps)

```
               ┌──────────────┐
               │  Input Text  │
               │  (.txt file) │
               └──────┬───────┘
                      │
               ┌──────▼───────┐
               │ parse_story() │  Regex: split paragraphs, extract
               │               │  dialogue, ID speakers
               └──────┬───────┘
                      │
               list[Segment(type, text, speaker)]
                      │
               ┌──────▼────────┐
               │assign_voices()│  hash(speaker) → voice pool index
               │               │  populates Segment.voice
               └──────┬────────┘
                      │
               list[Segment] (voice field now set)
                      │
               ┌──────▼────────┐
               │generate_tts() │  N sequential HTTP calls
               │  (edge-tts)   │  w/ retry + backoff
               └──────┬────────┘
                      │
               N temp MP3 files (validated >0 bytes)
                      │
  ┌───────────────────┼───────────────────┐
  │                   │                   │
  │  ┌────────────────▼───────────────┐   │
  │  │ generate_ambient_music()       │   │
  │  │ (numpy sine waves, A-minor)    │   │
  │  └────────────────┬───────────────┘   │
  │                   │                   │
  │            ┌──────▼───────┐           │
  │            │  assemble()  │           │
  │            │  concat +    │           │
  │            │  type-aware  │           │
  │            │  pauses +    │           │
  │            │  overlay     │           │
  │            │  music -22dB │           │
  │            └──────┬───────┘           │
  │                   │                   │
  └───────────────────┼───────────────────┘
                      │
               ┌──────▼───────┐
               │   export()   │  192kbps MP3 + metadata
               └──────────────┘
```

### Step 1: Parse text into segments
- Split on paragraphs (`\n\n`)
- Extract dialogue via regex on `"..."` double quotes
- Identify speakers from attribution patterns ("said John", "I shrieked")
- First-person attributions ("I said", "I shrieked") map to the narrator — not a separate character. This is critical for first-person stories like "The Tell-Tale Heart" where the narrator IS the main character.
- Split long segments (>SEGMENT_SPLIT_THRESHOLD chars) at sentence boundaries
- Skip empty/whitespace-only paragraphs
- Output: `list[Segment]` with type (narration/dialogue), text, speaker
- Known limitations: nested quotes, single-quote dialogue, dialogue split across paragraphs, and attribution-less dialogue are not handled. These are acceptable for the MVP demo.

### Step 2: Assign voices
- Narrator gets `en-US-GuyNeural` (deep, authoritative)
- 13 character voices pooled from EN-US/EN-GB male/female neural voices
- Deterministic via hash: `hash(speaker_name) % len(voices)` — stable across text edits (adding/removing a character doesn't reshuffle other assignments)
- Voice is assigned directly onto `Segment.voice` field (no separate dict)

### Step 3: Generate TTS audio (sequential, via edge-tts)
- `generate_tts()` is a **sync function** that calls `asyncio.run()` internally for each segment (edge-tts is async-only). This keeps the rest of the pipeline synchronous.
- One `edge_tts.Communicate()` call per segment
- Save to temp dir as individual MP3 files
- **Retry logic**: exponential backoff (base 1s), up to 3 retries per segment. Retries trigger on network errors, HTTP errors, or when the output file is 0 bytes (corrupted/empty response).
- **Progress output**: always print segment counter (`Generating segment 12/47...`). In verbose mode, include ETA (`~1 min remaining`). Non-verbose mode uses a compact single-line counter.
- Small sleep between successful calls to avoid throttling

### Step 4: Generate background music
- Procedural ambient drone using numpy sine waves (A-minor, low-frequency)
- MUSIC_LOOP_SECONDS loop with fade in/out
- No bundled files, no downloads

### Step 5: Assemble
- Concatenate all segment audio with type-aware pauses:
  - PAUSE_SAME_TYPE_MS between same-type segments
  - PAUSE_TYPE_TRANSITION_MS at narration/dialogue transitions
  - PAUSE_SPEAKER_CHANGE_MS at speaker changes
  - **Precedence**: when multiple rules apply (e.g., type transition + speaker change), use `max()` — the longest applicable pause wins
- Overlay background music at MUSIC_OVERLAY_DB (subtle, atmospheric)
- Fade in/out on final mix

### Step 6: Export MP3
- OUTPUT_BITRATE, tagged with title/artist metadata

## Segment Dataclass

```python
@dataclass
class Segment:
    type: str          # "narration" or "dialogue"
    text: str
    speaker: str       # "narrator", character name, or "unknown"
    voice: str = ""    # populated by assign_voices()
```

## Input Validation

Validate early, fail fast with clear error messages:
1. Check input file exists and is readable
2. Check file is non-empty
3. Check `parse_story()` produced at least 1 segment
4. Check ffmpeg is installed (at startup)

## CLI Interface

```
python producer.py                              # Run with bundled demo
python producer.py story.txt -o output.mp3      # Custom input
python producer.py --list-voices                # Show available voices
python producer.py story.txt --no-music         # Skip background music
python producer.py story.txt --narrator-voice en-GB-RyanNeural
python producer.py story.txt -v                 # Verbose progress
```

## Dependencies

```
edge-tts>=6.1.0
pydub>=0.25.1
numpy>=1.24.0
pytest>=7.0.0
pedalboard>=0.9.0   # optional, graceful fallback
```

System: `ffmpeg` (`brew install ffmpeg`) — checked at startup with clear error message.

## Commit Convention

Detailed, multi-line commit messages: short imperative subject line, blank line, then a body explaining what changed and why. Focus on intent and context, not just a summary of the diff.

## Key Design Decisions

- **Single file**: `producer.py` contains everything, organized by section comments. Can refactor to modules when it exceeds ~600 lines.
- **Pedalboard optional**: `try/except ImportError`, works without it.
- **Hardcoded voice list**: Avoids async network call at startup; 14 English voices is plenty.
- **Sequential TTS**: Simple and sufficient for short stories. Wall-clock time for "The Tell-Tale Heart" (~40-60 segments) is ~1-2 minutes.
- **Temp files cleaned up**: `tempfile.mkdtemp()` with `finally: shutil.rmtree()`.
- **Hash-based voice assignment**: `hash(name) % len(voices)` is stable across text edits — only the new/removed character's voice changes, others stay the same.
- **"I" = narrator**: First-person attributions map to the narrator voice, preventing the narrator from being assigned two different voices in first-person stories.

## Testing Strategy — TDD with Mocks

All development is test-first. `test_producer.py` is the single test file. Each phase below writes failing tests, then implements until green.

### Mock strategy

| Dependency | Mock approach | Why |
|-----------|--------------|-----|
| `edge_tts.Communicate` | `unittest.mock.patch` returning a mock whose `save()` is an `AsyncMock` that writes a valid tiny MP3. Tests call the sync wrapper, which calls `asyncio.run()` internally — no pytest-asyncio needed. | Avoids network calls; tests run in <1s |
| `ffmpeg` (subprocess) | `unittest.mock.patch("shutil.which")` returning `/usr/bin/ffmpeg` | Avoids system dependency check in tests |
| File I/O for TTS | `tmp_path` fixture (pytest built-in) | Real filesystem in temp dirs, auto-cleaned |
| `pydub.AudioSegment` | Real objects — `AudioSegment.silent(duration=100)` | pydub can create tiny silent segments without ffmpeg for basic ops |

### Test fixture: minimal valid MP3

Tests that need a real MP3 file (TTS output, assembly input) use a shared fixture that generates a tiny valid MP3 via pydub:

```python
@pytest.fixture
def tiny_mp3(tmp_path):
    """Generate a 100ms silent MP3 for testing."""
    path = tmp_path / "test.mp3"
    silence = AudioSegment.silent(duration=100)
    silence.export(str(path), format="mp3")
    return path
```

## TDD Phases — Ralph Loop Iteration Guide

**One numbering system.** Each phase below lists its own tests. When a phase says "also writes Phase N+1 tests", those tests are listed under Phase N+1's heading. A Ralph Loop agent finds its current phase by matching the first failing test name to a phase heading.

```
PHASE PROGRESSION (each phase = one atomic commit)
═══════════════════════════════════════════════════

  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
  │ Phase 1     │──▶│ Phase 2     │──▶│ Phase 3     │──▶ ...
  │ Skeleton    │   │ Parsing     │   │ Voices      │
  │ + constants │   │ + tests     │   │ + tests     │
  └─────────────┘   └─────────────┘   └─────────────┘

Each phase:
  1. Read PLAN.md to find current phase
  2. Run pytest — see what's red (or no tests yet)
  3. Write failing tests for this phase
  4. Implement until green
  5. Commit with detailed message and push
  6. Next agent picks up from git
```

### How a fresh agent session should start

1. Run `pytest test_producer.py -v 2>&1 | tail -40` to see current state
2. If no test file exists, start at Phase 1
3. If tests exist, find the first failing test — that's the current phase
4. If all tests pass, check the phase list below for the next uncommitted phase
5. Implement the current phase (tests first if tests don't exist for it yet)
6. Run `pytest test_producer.py -v` to verify green
7. Commit and `git push` — next session picks up from remote

### Phase 1: Skeleton + constants + dataclass

**Tests for this phase** (green after implementation):
- `test_segment_dataclass` — fields exist, defaults work
- `test_constants_exist` — all module-level constants are defined

**Implementation:**
- Create `producer.py` with all constants, `Segment` dataclass, section comment structure, and empty function stubs that raise `NotImplementedError`
- Create `test_producer.py` with Phase 1 tests (green) + Phase 2 tests (red — that's correct, they're next phase's work)
- Create `requirements.txt`
- Commit: "Add project skeleton with constants, Segment dataclass, and parse tests"

### Phase 2: parse_story()

**Tests for this phase** (green after implementation):
- `test_parse_narration_only` — plain paragraph → narration Segment
- `test_parse_dialogue` — `"Hello," said John.` → dialogue Segment with speaker="John"
- `test_parse_mixed_paragraph` — narration + dialogue in one paragraph → multiple Segments
- `test_parse_first_person` — `"Stop!" I cried.` → speaker="narrator" (not "I")
- `test_parse_no_attribution` — `"Hello."` with no attribution → speaker="unknown"
- `test_parse_long_segment_split` — >500 char segment → split at sentence boundary
- `test_parse_empty_paragraphs_skipped` — whitespace-only paragraphs produce no segments

Note: `test_parse_full_story` (which uses the demo file) lives in Phase 8, not here. All Phase 2 tests use inline string inputs only.

**Implementation:**
- Implement `parse_story()` until all Phase 2 tests pass
- Also write Phase 3 tests (will be red)
- Commit: "Implement parse_story() with dialogue extraction and speaker attribution"

### Phase 3: assign_voices()

**Tests for this phase** (green after implementation):
- `test_narrator_gets_narrator_voice` — narrator segments get `en-US-GuyNeural`
- `test_character_gets_voice` — non-narrator speaker gets a voice from the pool
- `test_voice_determinism` — same speaker list → same assignments on repeated calls
- `test_voice_stability` — adding a speaker doesn't change existing speakers' voices
- `test_many_speakers_wrap` — 20 speakers don't crash (hash wraps around pool)

**Implementation:**
- Implement `assign_voices()` with hash-based voice mapping
- Also write Phase 4 tests (will be red)
- Commit: "Implement assign_voices() with hash-based deterministic assignment"

### Phase 4: generate_tts()

**Tests for this phase** (green after implementation):
- `test_tts_generates_files` — mock edge_tts, verify N files created in temp dir
- `test_tts_retry_on_failure` — mock edge_tts to fail once then succeed, verify retry
- `test_tts_retry_exhausted` — mock edge_tts to always fail, verify raises after 3 retries
- `test_tts_validates_output_size` — mock edge_tts to write 0-byte file, verify treated as failure
- `test_tts_progress_output` — capture stdout, verify segment counter appears

Mock setup: `unittest.mock.patch("edge_tts.Communicate")` returns a mock instance whose `save()` is an `AsyncMock` that writes a tiny valid MP3 to the given path. `generate_tts()` is sync — it calls `asyncio.run()` internally per segment, so tests don't need pytest-asyncio.

**Implementation:**
- Implement `generate_tts()` as sync function using `asyncio.run()` per segment
- Add retry logic with exponential backoff + 0-byte file check
- Add progress counter output
- Also write Phase 5 tests (will be red)
- Commit: "Implement generate_tts() with exponential backoff retry and progress output"

### Phase 5: generate_ambient_music()

**Tests for this phase** (green after implementation):
- `test_music_returns_audio_segment` — returns a pydub AudioSegment
- `test_music_correct_duration` — duration ≈ MUSIC_LOOP_SECONDS * 1000 ms (±100ms)
- `test_music_not_silent` — RMS > 0 (actually produces sound)

**Implementation:**
- Implement numpy-based ambient music generation (A-minor sine waves)
- Also write Phase 6 tests (will be red)
- Commit: "Implement generate_ambient_music() with numpy sine wave synthesis"

### Phase 6: assemble() + export()

**Tests for this phase** (green after implementation):
- `test_assemble_single_segment` — 1 segment → output audio with no pauses
- `test_assemble_same_type_pause` — 2 narration segments → total duration ≈ sum of segments + 300ms (±100ms tolerance)
- `test_assemble_type_transition_pause` — narration then dialogue → total duration ≈ sum + 700ms (±100ms)
- `test_assemble_speaker_change_pause` — dialogue speaker A then B → total duration ≈ sum + 500ms (±100ms)
- `test_assemble_with_music` — output RMS > voice-only RMS (music adds energy; overlay does NOT change duration)
- `test_assemble_no_music_flag` — when no_music=True, output ≈ sum of segments + pauses
- `test_export_creates_file` — output file exists and is >0 bytes
- `test_export_is_valid_mp3` — pydub can reload the exported file

**Implementation:**
- Implement `assemble()` with type-aware pauses and music overlay
- Implement `export()` for MP3 output
- Also write Phase 7 tests (will be red)
- Commit: "Implement assemble() and export() with type-aware pauses and music overlay"

### Phase 7: Input validation + CLI

**Tests for this phase** (green after implementation):
- `test_validate_missing_file` — SystemExit with clear message
- `test_validate_empty_file` — SystemExit with clear message
- `test_validate_no_segments` — SystemExit with clear message
- `test_cli_default_args` — no args → uses bundled demo, default output path
- `test_cli_custom_input` — positional arg sets input file
- `test_cli_output_flag` — `-o` sets output path
- `test_cli_no_music_flag` — `--no-music` sets flag
- `test_cli_verbose_flag` — `-v` sets verbose
- `test_cli_list_voices` — `--list-voices` prints voices and exits

**Implementation:**
- Implement input validation checks (file exists, non-empty, segments produced, ffmpeg installed)
- Implement CLI arg parsing with argparse
- Also write Phase 8 tests (will be red)
- Commit: "Add input validation and CLI argument parsing"

### Phase 8: Demo story + integration

**Tests for this phase** (green after implementation):
- `test_parse_full_story` — parse `demo/tell_tale_heart.txt`, verify segments > 0 and no empty text fields
- `test_full_pipeline_mocked_tts` — mock edge_tts, run full pipeline on demo story, verify output MP3 exists and is valid
- `test_full_pipeline_no_music` — same as above with --no-music

**Implementation:**
- `demo/tell_tale_heart.txt` is already committed (sourced from eapoe.org, public domain)
- Wire up `main()` to run the full pipeline
- **Green tests**: ALL tests
- Commit: "Add demo story and wire up full pipeline"

### Phase 9: Documentation + final

No new tests. Manual verification only.

**Implementation:**
- Write README.md, LICENSE (MIT)
- Run `python producer.py -v` for real (with actual edge-tts network calls)
- Verify output MP3 plays correctly
- Commit: "Add documentation and verify end-to-end output"

## Future Work

### Multi-voice demo story
The Tell-Tale Heart is ~95% first-person narration — the output is mostly one voice. To showcase distinct character voices, add a second dialogue-heavy demo. Candidates (all public domain, short, with male/female and young/old speakers):
- **"The Open Window" by Saki** (~1200 words) — Vera (young female), Framton Nuttel (male), Mrs. Sappleton (older female). Almost entirely dialogue. Great contrast to Tell-Tale Heart.
- **"The Monkey's Paw" by W.W. Jacobs** (~4000 words) — Mr. White (old male), Mrs. White (old female), Herbert (young male), Sergeant-Major Morris (male). Dramatic, dialogue-heavy throughout.

### Async/concurrent TTS generation
Sequential TTS takes ~1-2 minutes for a short story. For longer texts (novel chapters, ~10K words), this could be 5-10 minutes. Replace the sequential loop in `generate_tts()` with `asyncio.gather()` + `Semaphore(5)` to limit concurrency while still respecting rate limits. This is the single biggest performance win available.
