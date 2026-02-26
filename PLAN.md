# Audiobook Producer — Implementation Plan

## Context

Build a Python CLI app that transforms public domain text into full-cast audio dramas with distinct character voices, narration, and background music. The user has no API keys, so we use free tools only. MVP targets a single short story ("The Tell-Tale Heart" by Poe) as a bundled demo. New public GitHub repo.

## Project Structure

```
audiobook-producer/
  producer.py              # Single-file app (entire pipeline)
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

## Pipeline (6 Steps)

### Step 1: Parse text into segments
- Split on paragraphs (`\n\n`)
- Extract dialogue via regex on `"..."` double quotes
- Identify speakers from attribution patterns ("said John", "I shrieked")
- Split long segments (>500 chars) at sentence boundaries
- Output: `list[Segment]` with type (narration/dialogue), text, speaker

### Step 2: Assign voices
- Narrator gets `en-US-GuyNeural` (deep, authoritative)
- 13 character voices pooled from EN-US/EN-GB male/female neural voices
- Deterministic: sort speakers alphabetically, assign in order
- Same story always produces same voice assignments

### Step 3: Generate TTS audio (async, via edge-tts)
- One `edge_tts.Communicate()` call per segment
- Save to temp dir as individual MP3 files
- Small sleep between calls to avoid throttling

### Step 4: Generate background music
- Procedural ambient drone using numpy sine waves (A-minor, low-frequency)
- 30-second loop with fade in/out
- No bundled files, no downloads

### Step 5: Assemble
- Concatenate all segment audio with type-aware pauses:
  - 300ms between same-type segments
  - 700ms at narration/dialogue transitions
  - 500ms at speaker changes
- Overlay background music at -22dB (subtle, atmospheric)
- Fade in/out on final mix

### Step 6: Export MP3
- 192kbps, tagged with title/artist metadata

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
pedalboard>=0.9.0   # optional, graceful fallback
```

System: `ffmpeg` (`brew install ffmpeg`) — checked at startup with clear error message.

## Key Design Decisions

- **Single file**: `producer.py` contains everything. Can refactor later.
- **Pedalboard optional**: `try/except ImportError`, works without it.
- **Hardcoded voice list**: Avoids async network call at startup; 14 English voices is plenty.
- **Sequential TTS**: Simple and sufficient for short stories.
- **Temp files cleaned up**: `tempfile.mkdtemp()` with `finally: shutil.rmtree()`.

## Implementation Order

1. CLI skeleton + `Segment` dataclass
2. `parse_story()` — test by printing segments
3. `assign_voices()` — test by printing voice map
4. `generate_tts()` — test by generating a few MP3s
5. `generate_ambient_music()` — test by exporting music alone
6. `assemble()` + `export()` — wire up full pipeline
7. Add `demo/tell_tale_heart.txt` (from Wikisource, clean text only)
8. Write README, .gitignore, LICENSE, requirements.txt
9. Create GitHub repo and push

## Verification

1. Run `python producer.py -v` (uses bundled demo)
2. Verify verbose output shows correct segment count, speakers, voice assignments
3. Play output MP3 — confirm:
   - Narrator voice is clear and consistent
   - Character dialogue uses distinct voices
   - Background music is subtle but present
   - Natural pauses between segments
   - Fade in/out at start and end
4. Run `python producer.py --list-voices` — confirm voice list prints
5. Run `python producer.py --no-music` — confirm music-free output
6. Push to GitHub: `gh repo create audiobook-producer --public`
