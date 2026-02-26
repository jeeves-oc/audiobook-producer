# Audiobook Producer — Implementation Plan

## Context

Build a Python CLI app that transforms public domain text into full-cast audio dramas with distinct character voices, narration, and background music. The user has no API keys, so we use free tools only. MVP targets a single short story ("The Tell-Tale Heart" by Poe) as a bundled demo. New public GitHub repo.

**Development method**: Test-driven development (TDD), structured for autonomous iteration via the Ralph Loop. Each phase writes failing tests first, then implements until green, then commits. A fresh agent session can pick up from git state alone by running `pytest test_producer.py -v` to see what's red.

**Done condition**: `pytest test_producer.py -v` is all green AND `python producer.py -v` produces a playable MP3 file of "The Tell-Tale Heart" with distinct character voices and background music.

## Project Structure

```
audiobook-producer/
  audiobook_producer/          # main package
    __init__.py
    constants.py               # all magic numbers
    models.py                  # Segment dataclass
    parser.py                  # parse_story(), extract_metadata()
    voices.py                  # assign_voices(), voice pool, bookend scripts
    tts.py                     # generate_tts(), edge-tts integration, retry
    music.py                   # generate_ambient_music(), numpy synthesis
    effects.py                 # audio effects: reverb, procedural SFX
    assembly.py                # assemble(), bookend music structure
    exporter.py                # export() MP3 + metadata tags
    cli.py                     # argparse, input validation, main()
  tests/
    conftest.py                # shared fixtures (tiny_mp3, sample segments)
    test_parser.py
    test_voices.py
    test_tts.py
    test_music.py
    test_effects.py
    test_assembly.py
    test_exporter.py
    test_cli.py
    test_integration.py
  demo/
    tell_tale_heart.txt        # Bundled demo story (public domain)
    tell_tale_heart.cast.json  # Curated voice cast for Tell-Tale Heart
    the_open_window.txt        # Multi-voice demo story
    the_open_window.cast.json  # Curated voice cast for The Open Window
  producer.py                  # thin entry point: from audiobook_producer.cli import main
  requirements.txt
  README.md
  .gitignore
  LICENSE                      # MIT
```

## Tech Stack

| Component | Choice | Why |
|-----------|--------|-----|
| TTS | edge-tts | Free, 322 neural voices, no API key, high quality |
| Text parsing | Regex (rule-based) | Zero dependencies, works well for classic literature |
| Audio mixing | pydub + ffmpeg | Standard Python audio stack |
| Audio effects | pedalboard (optional) | Spotify's lib for reverb on dialogue; graceful fallback |
| Procedural SFX | numpy | Same stack as music — heartbeat, room tone, ambience |
| Background music | Procedurally generated (numpy) | No licensing, no downloads, reproducible |
| CLI | argparse (stdlib) | No extra dependency |
| Output | MP3 (192kbps) | Good quality, universal compatibility |
| Testing | pytest + unittest.mock | TDD with mocked I/O for edge-tts and ffmpeg |

## Module Architecture

Each module has a single responsibility, its own test file, and well-defined inputs/outputs. Modules at the same depth in the dependency graph can be developed in parallel.

```
DEPENDENCY GRAPH
════════════════

  constants.py ◄── models.py        (foundation — everything imports these)
       │                │
       ├────────────────┼────────────────────────────┐
       │                │                            │
       ▼                ▼                            ▼
  parser.py        voices.py       music.py    effects.py    tts.py
  (text→segments)  (assign voices,  (numpy      (reverb,      (edge-tts
                    bookend         synthesis)   proc. SFX)    HTTP calls)
                    scripts)
       │                │               │            │           │
       └────────────────┴───────┬───────┴────────────┘           │
                                │                                │
                         assembly.py ◄───────────────────────────┘
                         (bookend structure,
                          pauses, music overlay)
                                │
                          exporter.py
                          (MP3 output + metadata)
                                │
                            cli.py
                            (argparse, validation,
                             pipeline orchestration)
```

**Parallel development**: parser, voices, music, effects, and tts are independent — they can be built simultaneously by separate Ralph Loop agents. assembly.py is the merge gate.

## Constants

All magic numbers defined as module-level constants at the top of `producer.py`:

```python
SEGMENT_SPLIT_THRESHOLD = 500       # chars — split segments longer than this
PAUSE_SAME_TYPE_MS = 300            # ms pause between same-type segments
PAUSE_SPEAKER_CHANGE_MS = 500       # ms pause at speaker changes
PAUSE_TYPE_TRANSITION_MS = 700      # ms pause at narration/dialogue transitions
MUSIC_LOOP_SECONDS = 30             # duration of generated ambient loop
INTRO_MUSIC_SOLO_MS = 4000          # music-only before narrator starts
OUTRO_MUSIC_SOLO_MS = 4000          # music-only after "thank you" before final fade
MUSIC_BED_DB = -25                  # music volume under intro/outro narration
MUSIC_FADE_MS = 2000                # crossfade duration for music volume transitions
OUTPUT_BITRATE = "192k"             # MP3 output bitrate
TTS_RETRY_COUNT = 3                 # max retries per TTS segment
TTS_RETRY_BASE_DELAY = 1.0         # seconds — base delay for exponential backoff
NARRATOR_VOICE = "en-US-GuyNeural"           # narrator internal monologue / narration
NARRATOR_DIALOGUE_VOICE = "en-GB-RyanNeural" # narrator spoken dialogue (British accent)
REVERB_ROOM_SIZE = 0.3                       # pedalboard reverb: 0.0-1.0 (subtle)
REVERB_WET_LEVEL = 0.15                      # pedalboard reverb: dry/wet mix
ROOM_TONE_DB = -40                           # background room tone level
```

## Pipeline (6 Steps)

```
               ┌──────────────┐
               │  Input Text  │
               │  (.txt file) │
               └──────┬───────┘
                      │
               ┌──────▼────────┐
               │ parse_story() │  Regex: split paragraphs, extract
               │               │  dialogue, ID speakers
               │extract_meta() │  Title + author from first lines
               └──────┬────────┘
                      │
               (title, author) + list[Segment]
                      │
               ┌──────▼────────┐
               │assign_voices()│  hash(speaker) → voice pool index
               │               │  narrator split: narration vs dialogue
               │gen_bookends() │  Intro: "This is <title>..."
               │               │  Outro: "This has been..."
               └──────┬────────┘
                      │
               intro + story + outro segments (all with voices)
                      │
               ┌──────▼────────┐
               │generate_tts() │  N sequential HTTP calls
               │  (edge-tts)   │  w/ retry + backoff
               └──────┬────────┘
                      │
               N temp MP3 files (intro + story + outro)
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
  │            │  bookend     │           │
  │            │  music +     │           │
  │            │  intro/outro │           │
  │            │  + story     │           │
  │            └──────┬───────┘           │
  │                   │                   │
  └───────────────────┼───────────────────┘
                      │
               ┌──────▼───────┐
               │   export()   │  192kbps MP3 + metadata
               └──────────────┘
```

### Assembly structure (bookend music)

Music plays only at the beginning and end — not during the story body. This creates a polished radio-drama feel.

```
  ┌──────────┬──────────┬─────────────────┬──────────┬──────────┐
  │  MUSIC   │  MUSIC   │                 │  MUSIC   │  MUSIC   │
  │  SOLO    │  BED     │   NO MUSIC      │  BED     │  SOLO    │
  │  (full)  │  (-25dB) │                 │  (-25dB) │  (full)  │
  │          │          │                 │          │          │
  │          │  INTRO   │   STORY         │  OUTRO   │          │
  │          │  title,  │   segments +    │  credits │  FADE    │
  │          │  chars   │   pauses        │  thanks  │  OUT     │
  └──────────┴──────────┴─────────────────┴──────────┴──────────┘
  ├── intro bookend ───┤├── story body ──┤├── outro bookend ────┤
```

### Step 1: Parse text into segments
- **`extract_metadata(text)`**: Pull title and author from the text file header. Convention: first non-empty line = title, line matching `^by .+` = author. Returns `(title, author)` tuple. Falls back to `("Untitled", "Unknown Author")` if pattern not found.
- **`parse_story(text)`**: Split into segments after stripping the metadata header (title + author lines)
- Split on paragraphs (`\n\n`)
- Extract dialogue via regex on `"..."` double quotes
- Identify speakers from attribution patterns ("said John", "I shrieked")
- First-person attributions ("I said", "I shrieked") map to the narrator — not a separate character. This is critical for first-person stories like "The Tell-Tale Heart" where the narrator IS the main character.
- Split long segments (>SEGMENT_SPLIT_THRESHOLD chars) at sentence boundaries
- Skip empty/whitespace-only paragraphs
- Output: `list[Segment]` with type (narration/dialogue), text, speaker
- Known limitations: nested quotes, single-quote dialogue, dialogue split across paragraphs, and attribution-less dialogue are not handled. These are acceptable for the MVP demo.

### Step 2: Assign voices + generate bookend scripts

#### Voice assignment

- **`assign_voices(segments, cast=None)`**: Assign voices to story segments using a priority system:

```
Voice assignment (priority order):
┌─────────────────────────────────────────────────────┐
│ 1. NARRATOR RULES (always applied first)            │
│    narrator + narration → NARRATOR_VOICE             │
│    narrator + dialogue  → NARRATOR_DIALOGUE_VOICE    │
│                                                     │
│ 2. CAST FILE (if provided)                          │
│    cast["old man"]["voice"] → en-US-DavisNeural     │
│    Explicit, curated assignment per character        │
│                                                     │
│ 3. HASH FALLBACK (for unlisted/unknown characters)  │
│    sha256(speaker) % len(remaining_pool)            │
│    Deterministic, stable across runs                │
└─────────────────────────────────────────────────────┘
```

- Voice is assigned directly onto `Segment.voice` field (no separate dict)
- Cast data loaded from JSON sidecar file (see Cast File Format below)

#### Cast file format

Each story can have an optional `.cast.json` sidecar file alongside its `.txt` file. If present, it provides curated voice assignments and character descriptions for the intro.

```json
{
  "narrator": {
    "voice": "en-US-GuyNeural",
    "description": "a most unreliable narrator"
  },
  "cast": {
    "the old man": {
      "voice": "en-US-DavisNeural",
      "description": "a frail old man with a pale blue vulture eye"
    },
    "the niece": {
      "voice": "en-US-AriaNeural",
      "description": "Vera, a very self-possessed young lady of fifteen",
      "aliases": ["the child", "the self-possessed young lady"]
    }
  }
}
```

Fields:
- **`narrator`**: Optional narrator override (voice + description for intro). Falls back to NARRATOR_VOICE constant.
- **`cast`**: Map of parser-extracted speaker name → voice + description.
- **`aliases`** (optional): List of alternate names the parser might extract for the same character. `assign_voices()` resolves aliases to the primary name before assignment. This handles classic literature where one character is called "the niece", "the child", "Vera", etc.

- **`load_cast(story_path)`**: Look for `<basename>.cast.json` next to the `.txt` file (e.g., `demo/tell_tale_heart.cast.json`). Returns cast dict or empty dict if not found.
- Stories without a cast file still work — all characters get hash-based pool voices and names-only intros.

#### Bookend script generation

- **`generate_intro_segments(title, author, segments, cast=None)`**: Build the opening sequence. Uses voice assignments on segments + cast descriptions.

```
INTRO SCRIPT
════════════
  Narrator: "This is {title}, by {author}."
  Narrator: "The characters will be..."
  For each unique character (not narrator, not unknown):
    [Character voice]: "{speaker name},"
    Narrator: "{description}, using {voice_name}."
  Narrator: "And your narrator, using {NARRATOR_VOICE}."
```

Example for Tell-Tale Heart:
```
  Narrator: "This is The Tell-Tale Heart, by Edgar Allan Poe."
  Narrator: "The characters will be..."
  [en-US-DavisNeural]: "The Old Man,"
  Narrator: "a frail old man with a vulture eye, using en-US-DavisNeural."
  [en-GB-ThomasNeural]: "The Officers,"
  Narrator: "officers of the police, using en-GB-ThomasNeural."
  Narrator: "And your narrator, using en-US-GuyNeural."
```

- **`generate_outro_segments(title, author, segments)`**: Build the closing sequence.

```
OUTRO SCRIPT
════════════
  Narrator: "This has been a production of {title}, by {author},"
  Narrator: "with {character1}, {character2}, and {character3}."
  Narrator: "Thank you for listening."
```

### Step 3: Generate TTS audio (sequential, via edge-tts)
- `generate_tts()` is a **sync function** that calls `asyncio.run()` internally for each segment (edge-tts is async-only). This keeps the rest of the pipeline synchronous.
- One `edge_tts.Communicate()` call per segment
- Processes ALL segments: intro + story + outro
- Save to temp dir as individual MP3 files
- **Retry logic**: exponential backoff (base 1s), up to 3 retries per segment. Retries trigger on network errors, HTTP errors, or when the output file is 0 bytes (corrupted/empty response).
- **Progress output**: always print segment counter (`Generating segment 12/47...`). In verbose mode, include ETA (`~1 min remaining`). Non-verbose mode uses a compact single-line counter.
- Small sleep between successful calls to avoid throttling

### Step 4: Generate background music
- Procedural ambient drone using numpy sine waves (A-minor, low-frequency)
- MUSIC_LOOP_SECONDS loop with fade in/out
- No bundled files, no downloads — fully procedural

### Step 4b: Apply audio effects
- **`effects.py`** — processes individual segment audio files after TTS generation
- **Reverb on dialogue**: subtle room reverb via pedalboard on dialogue segments. Gives dialogue spatial depth vs flat narration. Pedalboard is optional — graceful fallback to unprocessed audio if not installed.
- **Procedural SFX**: generate sound effects via numpy (same approach as music):
  - **Heartbeat**: low-frequency double-pulse sine wave with envelope (for dramatic tension — e.g., Tell-Tale Heart)
  - **Room tone**: low-level filtered white noise (subtle background presence)
  - **Outdoor ambience**: shaped white noise with slow modulation (for outdoor scenes)
- **Effect mapping**: effects are applied based on segment type — all dialogue gets reverb, ambient backgrounds are scene-level. No NLP or story-specific annotation needed for MVP.
- **Processing pipeline per segment**:
  1. Load TTS MP3
  2. Apply reverb if dialogue (pedalboard, optional)
  3. Normalize volume levels across segments
  4. Save processed audio back
- SFX (heartbeat, room tone, outdoor) are returned as separate AudioSegments for assembly to overlay at appropriate points

### Step 5: Assemble (bookend music)
- **Intro bookend**:
  1. Music at full volume for INTRO_MUSIC_SOLO_MS (pure music, no narration)
  2. Music crossfades down to MUSIC_BED_DB over MUSIC_FADE_MS
  3. Intro narration segments play over the music bed (title, characters, narrator)
  4. Music fades out completely over MUSIC_FADE_MS as intro ends
- **Story body** (no music):
  - Concatenate story segment audio with type-aware pauses:
    - PAUSE_SAME_TYPE_MS between same-type segments
    - PAUSE_TYPE_TRANSITION_MS at narration/dialogue transitions
    - PAUSE_SPEAKER_CHANGE_MS at speaker changes
    - **Precedence**: when multiple rules apply (e.g., type transition + speaker change), use `max()` — the longest applicable pause wins
- **Outro bookend**:
  1. Music fades in to MUSIC_BED_DB over MUSIC_FADE_MS
  2. Outro narration segments play over the music bed (credits, thank you)
  3. Music swells to full volume over MUSIC_FADE_MS
  4. Music at full volume for OUTRO_MUSIC_SOLO_MS, then fades out
- **No-music mode**: skip all music sections, just concatenate intro + story + outro with pauses

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

- **Multi-module package**: `audiobook_producer/` package with one module per concern. `producer.py` is a thin entry point. Each module has its own test file under `tests/`.
- **Pedalboard optional**: `try/except ImportError` in `effects.py`, works without it (no reverb, just pass-through).
- **Hardcoded voice list**: Avoids async network call at startup; 14 English voices is plenty.
- **Sequential TTS**: Simple and sufficient for short stories. Wall-clock time for "The Tell-Tale Heart" (~40-60 segments) is ~1-2 minutes.
- **Temp files cleaned up**: `tempfile.mkdtemp()` with `finally: shutil.rmtree()`.
- **Hash-based voice assignment**: `sha256(name) % len(voices)` is stable across runs and text edits — only the new/removed character's voice changes, others stay the same. Uses `hashlib.sha256` (not `hash()`) because Python's built-in `hash()` is randomized per process since 3.3.
- **"I" = narrator**: First-person attributions map to the narrator speaker, preventing the narrator from being treated as a separate character in first-person stories.
- **Narrator voice split**: Narrator narration uses `en-US-GuyNeural` (American), narrator spoken dialogue uses `en-GB-RyanNeural` (British). Audible contrast between inner monologue and spoken words.
- **Bookend music**: Music plays only at the intro and outro — not during the story body. The intro features a title announcement and character introductions (each character says their name in their own voice). The outro has credits and "thank you for listening."
- **Metadata from file header**: Title is first non-empty line, author follows "by " pattern. Falls back gracefully.
- **Effects are additive**: All audio processing in `effects.py` is optional and layered on top of raw TTS output. The pipeline works without any effects applied.

## Testing Strategy — TDD with Mocks

All development is test-first. Each module in `audiobook_producer/` has a corresponding test file in `tests/`. Shared fixtures live in `tests/conftest.py`.

### Mock strategy

| Dependency | Mock approach | Why |
|-----------|--------------|-----|
| `edge_tts.Communicate` | `unittest.mock.patch` returning a mock whose `save()` is an `AsyncMock` that writes a valid tiny MP3. Tests call the sync wrapper, which calls `asyncio.run()` internally — no pytest-asyncio needed. | Avoids network calls; tests run in <1s |
| `ffmpeg` (subprocess) | `unittest.mock.patch("shutil.which")` returning `/usr/bin/ffmpeg` | Avoids system dependency check in tests |
| File I/O for TTS | `tmp_path` fixture (pytest built-in) | Real filesystem in temp dirs, auto-cleaned |
| `pydub.AudioSegment` | Real objects — `AudioSegment.silent(duration=100)` | pydub can create tiny silent segments without ffmpeg for basic ops |
| `pedalboard` | `unittest.mock.patch` or skip if not installed | Effects tests work with or without pedalboard |

### Shared fixtures (tests/conftest.py)

```python
@pytest.fixture
def tiny_mp3(tmp_path):
    """Generate a 100ms silent MP3 for testing."""
    path = tmp_path / "test.mp3"
    silence = AudioSegment.silent(duration=100)
    silence.export(str(path), format="mp3")
    return path

@pytest.fixture
def sample_segments():
    """Pre-built segments for voice/assembly/integration tests."""
    return [
        Segment(type="narration", text="It was dark.", speaker="narrator"),
        Segment(type="dialogue", text="Who's there?", speaker="old man"),
        Segment(type="dialogue", text="Villains!", speaker="narrator"),
    ]
```

## TDD Phases — Parallel Ralph Loop Iteration Guide

Modules are organized in layers by dependency. Modules at the same layer can be built **in parallel** by separate Ralph Loop agents. Each agent claims one module, implements its tests + code, and commits.

```
PARALLEL PHASE STRUCTURE
════════════════════════

  LAYER 0 (foundation — must be first)
  ┌──────────────────────────────────────────────┐
  │  constants.py + models.py + conftest.py      │
  │  + producer.py entry point + requirements.txt│
  └─────────────────────┬────────────────────────┘
                        │
  LAYER 1 (independent modules — build in parallel)
  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
  │ parser   │ │ voices   │ │ tts      │ │ music    │ │ effects  │
  │ [sonnet] │ │ [sonnet] │ │ [sonnet] │ │ [sonnet] │ │ [sonnet] │
  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
       │             │            │             │             │
       └─────────────┴─────┬──────┴─────────────┴─────────────┘
                           │
  LAYER 2 (merge gate — depends on all Layer 1 modules)
  ┌──────────────────────────────────────────────┐
  │  assembly.py + exporter.py      [opus]       │
  └─────────────────────┬────────────────────────┘
                        │
  LAYER 3 (pipeline orchestration)
  ┌──────────────────────────────────────────────┐
  │  cli.py                         [sonnet]     │
  └─────────────────────┬────────────────────────┘
                        │
  LAYER 4 (end-to-end verification)
  ┌──────────────────────────────────────────────┐
  │  test_integration.py            [opus]       │
  └─────────────────────┬────────────────────────┘
                        │
  LAYER 5 (documentation)
  ┌──────────────────────────────────────────────┐
  │  README.md + LICENSE            [sonnet]     │
  └──────────────────────────────────────────────┘
```

### Model strategy

```
MODEL ASSIGNMENTS
════════════════════════════════════════════════════

  Layer │ Module      │ Model  │ Why
  ──────┼─────────────┼────────┼──────────────────────────
    0   │ foundation  │ sonnet │ Copy from plan, boilerplate
    1   │ parser      │ sonnet │ Regex parsing, well-specified rules
    1   │ voices      │ sonnet │ Hash + branch, straightforward
    1   │ tts         │ sonnet │ Async mocks, moderate complexity
    1   │ music       │ sonnet │ Numpy math, self-contained
    1   │ effects     │ sonnet │ Pedalboard wrapper + numpy SFX
    2   │ assembly    │ opus   │ Bookend structure, pause logic, overlays
    2   │ exporter    │ sonnet │ Simple pydub export
    3   │ cli         │ sonnet │ Argparse boilerplate, validation
    4   │ integration │ opus   │ Full pipeline wiring, debugging
    5   │ docs        │ sonnet │ No code logic

  ESCALATION RULE: if a sonnet-tagged module fails
  2 iterations in a row → switch to opus for that module
```

### How a fresh agent session should start

1. Run `pytest tests/ -v 2>&1 | tail -40` to see current state
2. If `tests/` doesn't exist or is empty, start at Layer 0
3. If tests exist, find the first failing test — match it to a module below
4. If all tests pass, check the layer list below for the next unclaimed module
5. Check the **Model strategy** table for the recommended model
6. Implement the module (tests first if they don't exist yet)
7. Run `pytest tests/ -v` to verify green for your module
8. Commit and `git push` — next session picks up from remote

### How parallel agents claim modules

When multiple agents run simultaneously on Layer 1:
- Each agent runs `pytest tests/ -v` and sees which test files have failures
- Agent picks the **first failing test file** (alphabetical) that isn't already in a recent commit message (check `git log --oneline -5`)
- If no failing tests exist for unclaimed modules, agent creates test file + stub for the next unclaimed module
- **Conflict resolution**: if two agents commit the same module, the second push fails — that agent should `git pull --rebase` and resolve

---

### Layer 0: Foundation `[sonnet]`

**Creates**: `audiobook_producer/__init__.py`, `audiobook_producer/constants.py`, `audiobook_producer/models.py`, `tests/conftest.py`, `producer.py`, `requirements.txt`

**Tests** (in `tests/test_models.py` — green after implementation):
- `test_segment_dataclass` — fields exist, defaults work
- `test_constants_exist` — all module-level constants are defined

**Also creates test stubs** for all Layer 1 modules (red — provides targets for parallel agents):
- `tests/test_parser.py` with failing `test_parse_narration_only`
- `tests/test_voices.py` with failing `test_narrator_gets_narrator_voice`
- `tests/test_tts.py` with failing `test_tts_generates_files`
- `tests/test_music.py` with failing `test_music_returns_audio_segment`
- `tests/test_effects.py` with failing `test_reverb_on_dialogue`

Commit: "Add package skeleton with constants, models, and Layer 1 test stubs"

---

### Layer 1a: parser.py `[sonnet]`

**File**: `audiobook_producer/parser.py`
**Tests** (in `tests/test_parser.py` — green after implementation):
- `test_extract_metadata` — `"The Tell-Tale Heart\n\nby Edgar Allan Poe\n\n..."` → `("The Tell-Tale Heart", "Edgar Allan Poe")`
- `test_extract_metadata_fallback` — text with no "by" line → `("Untitled", "Unknown Author")`
- `test_parse_narration_only` — plain paragraph → narration Segment
- `test_parse_dialogue` — `"Hello," said John.` → dialogue Segment with speaker="John"
- `test_parse_mixed_paragraph` — narration + dialogue in one paragraph → multiple Segments
- `test_parse_first_person` — `"Stop!" I cried.` → speaker="narrator" (not "I")
- `test_parse_no_attribution` — `"Hello."` with no attribution → speaker="unknown"
- `test_parse_long_segment_split` — >500 char segment → split at sentence boundary
- `test_parse_empty_paragraphs_skipped` — whitespace-only paragraphs produce no segments

All tests use inline string inputs only. `test_parse_full_story` lives in Layer 4 (integration).

Commit: "Implement parser with dialogue extraction and speaker attribution"

---

### Layer 1b: voices.py `[sonnet]`

**File**: `audiobook_producer/voices.py`
**Tests** (in `tests/test_voices.py` — green after implementation):

Voice assignment:
- `test_narrator_gets_narrator_voice` — narrator narration segments get `en-US-GuyNeural`
- `test_narrator_dialogue_gets_distinct_voice` — narrator dialogue segments get `en-GB-RyanNeural` (British)
- `test_cast_overrides_hash` — character in cast file gets the cast voice, not a hash-based one
- `test_cast_missing_character_falls_back` — character NOT in cast falls back to sha256 hash pool
- `test_cast_alias_resolves` — "the child" resolves to "the niece" entry and gets the same voice
- `test_load_cast_file` — loads `.cast.json` sidecar, returns dict with voice + description + aliases
- `test_load_cast_missing_file` — no cast file → returns empty dict (no crash)
- `test_voice_determinism` — same speaker list → same assignments on repeated calls (sha256 is stable)
- `test_voice_stability` — adding a speaker doesn't change existing speakers' voices
- `test_many_speakers_wrap` — 20 speakers don't crash (hash wraps around pool)

Bookend scripts:
- `test_generate_intro_segments` — produces correct intro sequence: title, character intros with descriptions, narrator self-intro
- `test_generate_outro_segments` — produces credits and "thank you for listening"
- `test_intro_excludes_unknown_speakers` — speakers named "unknown" are not introduced
- `test_intro_character_speaks_own_name` — each character's name segment uses that character's voice
- `test_intro_includes_cast_descriptions` — when cast has descriptions, intro narration includes them

Commit: "Implement voice assignment with cast system and bookend scripts"

---

### Layer 1c: tts.py `[sonnet]`

**File**: `audiobook_producer/tts.py`
**Tests** (in `tests/test_tts.py` — green after implementation):
- `test_tts_generates_files` — mock edge_tts, verify N files created in temp dir
- `test_tts_retry_on_failure` — mock edge_tts to fail once then succeed, verify retry
- `test_tts_retry_exhausted` — mock edge_tts to always fail, verify raises after 3 retries
- `test_tts_validates_output_size` — mock edge_tts to write 0-byte file, verify treated as failure
- `test_tts_progress_output` — capture stdout, verify segment counter appears

Mock setup: `unittest.mock.patch("audiobook_producer.tts.edge_tts.Communicate")` — note the fully qualified patch path for the package structure.

Commit: "Implement TTS generation with exponential backoff retry"

---

### Layer 1d: music.py `[sonnet]`

**File**: `audiobook_producer/music.py`
**Tests** (in `tests/test_music.py` — green after implementation):
- `test_music_returns_audio_segment` — returns a pydub AudioSegment
- `test_music_correct_duration` — duration ≈ MUSIC_LOOP_SECONDS * 1000 ms (±100ms)
- `test_music_not_silent` — RMS > 0 (actually produces sound)

Commit: "Implement ambient music generation with numpy sine wave synthesis"

---

### Layer 1e: effects.py `[sonnet]`

**File**: `audiobook_producer/effects.py`
**Tests** (in `tests/test_effects.py` — green after implementation):
- `test_reverb_on_dialogue` — dialogue AudioSegment processed through reverb has different waveform than input (pedalboard installed)
- `test_reverb_fallback_no_pedalboard` — when pedalboard not installed, returns audio unchanged (no crash)
- `test_normalize_levels` — multiple segments at different volumes → output volumes are within 3dB of each other
- `test_generate_heartbeat` — returns AudioSegment with rhythmic amplitude pattern (peaks at ~1Hz intervals)
- `test_generate_room_tone` — returns AudioSegment with RMS > 0 and RMS < -30dB (subtle)
- `test_process_segments_passthrough` — when no effects enabled, output matches input

Commit: "Implement audio effects with reverb, normalization, and procedural SFX"

---

### Layer 2: assembly.py + exporter.py `[opus]`

**Files**: `audiobook_producer/assembly.py`, `audiobook_producer/exporter.py`

**Tests** (in `tests/test_assembly.py` — green after implementation):

Story body pause tests:
- `test_assemble_single_segment` — 1 segment → output audio with no pauses
- `test_assemble_same_type_pause` — 2 narration segments → total ≈ sum + 300ms (±100ms)
- `test_assemble_type_transition_pause` — narration then dialogue → total ≈ sum + 700ms (±100ms)
- `test_assemble_speaker_change_pause` — dialogue A then B → total ≈ sum + 500ms (±100ms)
- `test_assemble_pause_precedence` — type transition + speaker change → max(700, 500) = 700ms

Bookend structure tests:
- `test_assemble_bookend_has_intro` — output starts with intro segments before story
- `test_assemble_bookend_has_outro` — output ends with outro segments after story
- `test_assemble_bookend_music_intro` — first INTRO_MUSIC_SOLO_MS of output has music (RMS check)
- `test_assemble_bookend_no_music_mid` — middle section of output has no music background
- `test_assemble_no_music_flag` — when no_music=True, no music anywhere, just narration

**Tests** (in `tests/test_exporter.py` — green after implementation):
- `test_export_creates_file` — output file exists and is >0 bytes
- `test_export_is_valid_mp3` — pydub can reload the exported file
- `test_export_has_metadata` — exported MP3 has title/artist tags

Commit: "Implement assembly with bookend music structure and MP3 export"

---

### Layer 3: cli.py `[sonnet]`

**File**: `audiobook_producer/cli.py`

**Tests** (in `tests/test_cli.py` — green after implementation):
- `test_validate_missing_file` — SystemExit with clear message
- `test_validate_empty_file` — SystemExit with clear message
- `test_validate_no_segments` — SystemExit with clear message
- `test_validate_ffmpeg_missing` — SystemExit when ffmpeg not found
- `test_cli_default_args` — no args → uses bundled demo, default output path
- `test_cli_custom_input` — positional arg sets input file
- `test_cli_output_flag` — `-o` sets output path
- `test_cli_no_music_flag` — `--no-music` sets flag
- `test_cli_verbose_flag` — `-v` sets verbose
- `test_cli_list_voices` — `--list-voices` prints voices and exits

Commit: "Add CLI with argument parsing and input validation"

---

### Layer 4: Integration `[opus]`

**Tests** (in `tests/test_integration.py` — green after implementation):
- `test_parse_full_story` — parse `demo/tell_tale_heart.txt`, verify segments > 0 and no empty text fields
- `test_full_pipeline_mocked_tts` — mock edge_tts, run full pipeline on demo story, verify output MP3 exists and is valid
- `test_full_pipeline_no_music` — same as above with --no-music
- `test_full_pipeline_has_intro_outro` — verify intro title announcement and outro credits are present in segment list
- `test_full_pipeline_bookend_structure` — verify output audio has music at start and end, silence in the middle section

Commit: "Wire up full pipeline and verify end-to-end integration"

---

### Layer 5: Documentation `[sonnet]`

No new tests. Manual verification only.

- Write README.md, LICENSE (MIT)
- Run `python producer.py -v` for real (with actual edge-tts network calls)
- Verify output MP3 plays correctly with bookend intro/outro
- Commit: "Add documentation and verify end-to-end output"

---

## Future Work

### Multi-voice demo story
The Open Window by Saki is already staged at `demo/the_open_window.txt`. Add it as a second demo option via `--demo open-window` CLI flag. 6 speaking characters provide a good showcase for distinct voice assignment.

### Async/concurrent TTS generation
Sequential TTS takes ~1-2 minutes for a short story. Replace the sequential loop in `tts.py` with `asyncio.gather()` + `Semaphore(5)` to limit concurrency while still respecting rate limits. This is the single biggest performance win available.

### Advanced sound effects
- Story-specific effect annotations (e.g., heartbeat for Tell-Tale Heart confession scene)
- Environmental audio that adapts to scene content (indoor/outdoor detection)
- Foley effects library (footsteps, doors, weather)
