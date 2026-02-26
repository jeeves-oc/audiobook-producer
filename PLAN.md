# Audiobook Producer — Implementation Plan

## Context

Build a Python CLI app that transforms public domain text into full-cast audio dramas with distinct character voices, narration, and background music. The user has no API keys, so we use free tools only. MVP targets a single short story ("The Tell-Tale Heart" by Poe) as a bundled demo. New public GitHub repo.

## Project Structure

```
audiobook-producer/
  producer.py              # Single-file app (entire pipeline)
  test_producer.py         # Unit tests (pytest) for parse + voice logic
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
| Testing | pytest | Unit tests for parse and voice assignment logic |

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

## Testing

### Automated (pytest)

`test_producer.py` covers the pure functions with the most branching logic:

**parse_story() tests:**
- Paragraph with only narration → `Segment(type="narration")`
- Paragraph with quoted dialogue → `Segment(type="dialogue")`
- Mixed narration + dialogue paragraph → multiple Segments
- Speaker from attribution ("said John") → speaker field set
- First-person "I" attribution → speaker = narrator
- Dialogue with no attribution → speaker = unknown/default
- Long segment >500 chars → split at sentence boundary
- Empty/whitespace paragraph → skipped

**assign_voices() tests:**
- Narrator always gets narrator voice
- Character gets hash-based voice from pool
- Same speaker always gets same voice (determinism)
- More speakers than voices → hash wraps around gracefully

Run tests: `pytest test_producer.py -v`

### Manual verification

1. Run `python producer.py -v` (uses bundled demo)
2. Verify verbose output shows correct segment count, speakers, voice assignments, progress + ETA
3. Play output MP3 — confirm:
   - Narrator voice is clear and consistent
   - Character dialogue uses distinct voices
   - Background music is subtle but present
   - Natural pauses between segments
   - Fade in/out at start and end
4. Run `python producer.py --list-voices` — confirm voice list prints
5. Run `python producer.py --no-music` — confirm music-free output

## Implementation Order

1. CLI skeleton + `Segment` dataclass + constants
2. `parse_story()` + unit tests
3. `assign_voices()` + unit tests
4. `generate_tts()` with retry logic + progress output
5. `generate_ambient_music()`
6. `assemble()` + `export()` — wire up full pipeline
7. Input validation (file checks, ffmpeg check)
8. Add `demo/tell_tale_heart.txt` (from Wikisource, clean text only)
9. Write README, LICENSE, requirements.txt
10. Manual verification pass
11. Create GitHub repo and push

## Future Work

### Async/concurrent TTS generation
Sequential TTS takes ~1-2 minutes for a short story. For longer texts (novel chapters, ~10K words), this could be 5-10 minutes. Replace the sequential loop in `generate_tts()` with `asyncio.gather()` + `Semaphore(5)` to limit concurrency while still respecting rate limits. This is the single biggest performance win available.

### Integration tests for TTS + assembly
Unit tests cover parse and voice logic, but the TTS and audio assembly pipeline is only manually verified. Add mock-based integration tests: mock `edge_tts.Communicate` with pre-recorded fixtures, verify `assemble()` produces non-zero audio with correct approximate duration. This would enable safe refactoring from single-file to modules.

### TTS output validation
After each TTS call, verify the output file exists and is >0 bytes. If the file is empty or corrupted, treat it as a retry-able failure within the existing retry logic. This prevents a confusing pydub crash during assembly when edge-tts returns a 200 OK with empty content. Implementation: add `os.path.getsize(path) > 0` check to the retry loop's success condition (~3 lines).
