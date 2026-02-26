# Audiobook Producer — Implementation Plan

## Context

Build a Python CLI app that transforms public domain text into full-cast audio dramas with distinct character voices, narration, and background music. The user has no API keys, so we use free tools only. Two bundled demos: "The Tell-Tale Heart" (Poe, first-person, 3 characters) and "The Open Window" (Saki, third-person, 6 characters with aliases). New public GitHub repo.

**Development method**: Test-driven development (TDD), structured for autonomous iteration via the Ralph Loop. Each phase writes failing tests first, then implements until green, then commits. A fresh agent session can pick up from git state alone by running `pytest tests/ -v` to see what's red.

**Done condition**: `pytest tests/ -v` is all green AND both demo stories produce playable MP3s:
1. `python producer.py new demo/tell_tale_heart.txt && python producer.py run tell_tale_heart -v` → `output/tell_tale_heart/final/tell_tale_heart.mp3`
2. `python producer.py new demo/the_open_window.txt && python producer.py run the_open_window -v` → `output/the_open_window/final/the_open_window.mp3`

Each output must have distinct character voices, bookend intro/outro with cast introductions, background music, and all intermediate artifacts (script.json, cast.json, direction.json, effects.json, voice_demos/, segments/).

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
    music.py                   # generate_music(), source priority + numpy fallback
    effects.py                 # audio effects: reverb, normalization
    assembly.py                # assemble(), bookend music structure
    exporter.py                # export() MP3 + metadata tags
    artifacts.py               # output directory, intermediate files, resumability
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
    test_artifacts.py
    test_cli.py
    test_integration.py
  demo/
    tell_tale_heart.txt        # Bundled demo story (public domain)
    tell_tale_heart.cast.json  # Curated voice cast for Tell-Tale Heart
    the_open_window.txt        # Multi-voice demo story
    the_open_window.cast.json  # Curated voice cast for The Open Window
    music/                     # Bundled CC0 classical pieces (gitignore exception)
      tell_tale_heart.mp3      # Satie Gymnopédie No. 1 (minimalist, eerie)
      the_open_window.mp3      # Debussy Clair de Lune (dreamy, ironic contrast)
  output/                      # gitignored — one subfolder per production
    tell_tale_heart/           # example production directory
      script.json              # parsed segments as JSON
      cast.json                # resolved voice assignments
      direction.json           # assembly instructions (pauses, bookend timing)
      effects.json             # effects applied per segment
      voice_demos/             # character voice samples
        narrator_pangram.mp3
        narrator_story.mp3
        the_old_man_pangram.mp3
        the_old_man_story.mp3
      segments/                # individual TTS files, numbered
        000_intro_narrator.mp3
        001_intro_old_man.mp3
        ...
        042_story_narrator.mp3
        043_outro_narrator.mp3
      music/
        background.mp3         # resolved music (bundled, user, or procedural)
      samples/
        preview_60s.mp3        # first ~60s of assembled audio
      chapters/                # chapter-level splits (longer stories)
        chapter_01.mp3
      final/
        tell_tale_heart.mp3    # complete assembled production
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
| Background music | Bundled CC0 classical + user-provided + numpy fallback | Production-quality defaults, user-customizable, always works |
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
  (text→segments)  (assign voices,  (source     (reverb,      (edge-tts
                    bookend         priority +   normalize)    HTTP calls)
                    scripts)        fallback)
       │                │               │            │           │
       └────────────────┴───────┬───────┴────────────┘           │
                                │                                │
                         assembly.py ◄───────────────────────────┘
                         (bookend structure,              │
                          pauses, music overlay)          │
                                │                         │
                          exporter.py                     │
                          (MP3 output + metadata)         │
                                │                         │
                          artifacts.py ◄──────────────────┘
                          (output dirs, intermediate      (voice demos
                           JSON, voice demos, preview,     use tts.
                           resumability, chapter split)    generate_single)
                                │
                            cli.py
                            (argparse, validation,
                             pipeline orchestration)
```

**Parallel development**: parser, voices, music, effects, and tts are independent — they can be built simultaneously by separate Ralph Loop agents. assembly.py is the merge gate. artifacts.py depends on exporter.py and tts.py (for voice demos).

## Constants

All magic numbers defined as module-level constants in `audiobook_producer/constants.py`:

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
PREVIEW_DURATION_MS = 60000                  # 60s preview sample
VOICE_DEMO_PANGRAM = "The quick brown fox jumps over the lazy dog."
OUTPUT_DIR = "output"
BUNDLED_MUSIC_DIR = "demo/music"                 # bundled CC0 classical pieces
VERSION = "0.1.0"                        # top-level output directory
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
               │assign_voices()│  cast file → hash fallback
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
               N MP3 files in output/<slug>/segments/
                      │
  ┌───────────────────┼───────────────────┐
  │                   │                   │
  │  ┌────────────────▼───────────────┐   │
  │  │ generate_music()              │   │
  │  │ (bundled CC0 → user file →   │   │
  │  │  numpy sine wave fallback)   │   │
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
- Identify speakers from attribution patterns — both post-attribution and pre-attribution:
  - **Post-attribution**: `"Hello," said John.` — speaker after the quote
  - **Pre-attribution**: `John said, "Hello."` or `the old man sprang up, crying out -- "Who's there?"` — speaker before the quote
- First-person attributions ("I said", "I shrieked") map to the narrator — not a separate character. This is critical for first-person stories like "The Tell-Tale Heart" where the narrator IS the main character.
- Split long segments (>SEGMENT_SPLIT_THRESHOLD chars) at sentence boundaries
- Skip empty/whitespace-only paragraphs
- Output: `list[Segment]` with type (narration/dialogue), text, speaker
- Known limitations: nested quotes, single-quote dialogue, dialogue split across paragraphs, and attribution-less dialogue (quotes with no nearby "said/cried/asked" verb) are not handled. These are acceptable for the MVP demo.

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

- **`load_cast(story_path)`**: Look for `<basename>.cast.json` next to the `.txt` file (e.g., `demo/tell_tale_heart.cast.json`). Returns cast dict or empty dict if not found. **Error handling**: catches `json.JSONDecodeError` on malformed files — logs a warning and falls back to empty dict instead of crashing.
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
- **`generate_single(text, voice, output_path)`**: Generate one TTS clip. Sync wrapper around `asyncio.run()` + `edge_tts.Communicate()`. Includes retry logic. Used by both `generate_tts()` and voice demo generation in `artifacts.py`.
- **`generate_tts(segments, output_dir)`**: Generate TTS for all segments. Calls `generate_single()` per segment.
- Processes ALL segments: intro + story + outro
- Save directly to `output_dir` as numbered MP3 files (e.g., `000_intro_narrator.mp3`)
- **Retry logic**: exponential backoff (base 1s), up to 3 retries per segment. Retries trigger on network errors, HTTP errors, or when the output file is 0 bytes (corrupted/empty response).
- **Progress output**: always print segment counter (`Generating segment 12/47...`). In verbose mode, include ETA (`~1 min remaining`). Non-verbose mode uses a compact single-line counter.
- Small sleep between successful calls to avoid throttling

### Step 4: Resolve and prepare background music

Music source is resolved with a priority chain. All paths end with a file at `output/<slug>/music/background.mp3`.

```
MUSIC SOURCE RESOLUTION
═══════════════════════

  music.py: generate_music(project_dir, music_file=None)
       │
       ├─ 1. Check output/<slug>/music/background.mp3 exists?
       │     YES → load it (user already ran `set music-file` or previous run)
       │     NO  ↓
       │
       ├─ 2. music_file argument provided?
       │     YES → copy to output/<slug>/music/background.mp3, load it
       │     NO  ↓
       │
       ├─ 3. Bundled music for this story? (demo stories only)
       │     YES → copy from demo/music/<slug>.mp3 to output/<slug>/music/background.mp3
       │     NO  ↓
       │
       └─ 4. Procedural fallback
             Generate numpy sine wave ambient → save as output/<slug>/music/background.mp3
```

- **Bundled demo music**: `demo/music/tell_tale_heart.mp3` (Satie Gymnopédie No. 1) and `demo/music/the_open_window.mp3` (Debussy Clair de Lune). CC0 recordings from Musopen. Checked into the repo via a `.gitignore` exception for `demo/music/*.mp3`.
- **User-provided music**: `set <slug> music-file <path>` copies the file into the project. See set subcommand below.
- **Procedural fallback**: numpy sine wave ambient drone (A-minor, low-frequency), MUSIC_LOOP_SECONDS duration.
- **Trim + fade**: If the source file is longer than MUSIC_LOOP_SECONDS, take the first N seconds and apply MUSIC_FADE_MS fade-out. Files shorter than the target are used as-is.
- **Provenance tracking**: `direction.json` records `music_source` (e.g., `"bundled:tell_tale_heart.mp3"`, `"user:ambient.mp3"`, `"procedural"`).

### Step 4b: Apply audio effects
- **`effects.py`** — per-segment audio processing after TTS generation
- **Reverb on dialogue**: subtle room reverb via pedalboard on dialogue segments. Gives dialogue spatial depth vs flat narration. Pedalboard is optional — graceful fallback to unprocessed audio if not installed.
- **Volume normalization**: normalize levels across all segments so quiet and loud speakers are balanced.
- **Processing pipeline per segment** (in-place in `output/<slug>/segments/` — overwrites raw TTS files):
  1. Load TTS MP3 from `output/<slug>/segments/`
  2. Apply reverb if dialogue (pedalboard, optional)
  3. Normalize volume levels across segments
  4. Save processed audio back to same path (overwrite)
- Procedural SFX (heartbeat, room tone, ambience) deferred to Future Work — requires a scene annotation system that doesn't exist yet. See Future Work section.

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

Project-centric subcommand workflow. The project slug (derived from the input filename) is the key for all operations.

```
SUBCOMMAND WORKFLOW
═══════════════════

  producer.py new <file>              Parse + assign voices + write configs
  producer.py run <slug> [-v]         Run pipeline (TTS → effects → music → assembly → export)
  producer.py status <slug>           Read-only view of project state
  producer.py set <slug> <key> ...    Fine-tune one element, invalidate downstream
  producer.py list                    List all projects under output/
  producer.py voices [--filter STR]   List available edge-tts voices

TYPICAL SESSION
═══════════════

  $ python producer.py new demo/tell_tale_heart.txt
  Created project: tell_tale_heart
  Parsed 42 segments, assigned 3 voices
  Cast written to output/tell_tale_heart/cast.json
  Run 'producer.py status tell_tale_heart' to review, or 'producer.py run tell_tale_heart' to generate audio.

  $ python producer.py status tell_tale_heart
  Project: tell_tale_heart
  Source:  demo/tell_tale_heart.txt
  Segments: 42 (38 narration, 4 dialogue)
  Cast:
    narrator        → en-US-GuyNeural (American)
    the old man     → en-US-TonyNeural
    officers        → en-US-DavisNeural
  Steps:
    [done] parse         script.json (42 segments)
    [done] voices        cast.json (3 voices assigned)
    [----] tts           0/42 segments generated
    [----] effects       not started
    [----] music         not started
    [----] assembly      not started
    [----] export        not started

  $ python producer.py set tell_tale_heart voice "the old man" en-GB-RyanNeural
  Updated: the old man → en-GB-RyanNeural
  Invalidated: voice_demos/, segments/ (will regenerate on next run)

  $ python producer.py run tell_tale_heart -v
  [voice demos, preview gate, TTS, effects, music, assembly, export]
  Done: output/tell_tale_heart/final/tell_tale_heart.mp3

SET SUBCOMMAND OPTIONS
══════════════════════

  set <slug> voice <speaker> <voice_id>     Change one character's voice
  set <slug> narrator-voice <voice_id>      Change narrator's narration voice
  set <slug> narrator-dialogue <voice_id>   Change narrator's dialogue voice
  set <slug> music on|off                   Enable/disable background music
  set <slug> music-file <path>              Provide custom music file (copies into project)
  set <slug> music-db <float>               Change music bed volume (e.g., -25)
  set <slug> reverb on|off                  Enable/disable dialogue reverb
  set <slug> reverb-room <float>            Change reverb room size (0.0-1.0)
  set <slug> reverb-wet <float>             Change reverb wet level (0.0-1.0)
```

- Default output location: `output/<story_slug>/final/<story_slug>.mp3`
- No args → prints help (not run demo)
- `new` validates input, parses, assigns voices, writes configs — no audio generation
- `run` picks up from where `new` left off (voice demos → TTS → effects → music → assembly → export)
- `run -v` enables: detailed progress, ETA, voice demo preview gate with prompt
- `run --force` deletes generated artifacts (preserves configs) and re-runs audio generation
- `set` updates config and deletes stale downstream artifacts; next `run` regenerates them
- `status` is purely read-only — shows project state without modifying anything

### Invalidation Cascade

When `set` changes a config value, downstream artifacts become stale and must be deleted so the next `run` regenerates them.

```
INVALIDATION MAP
════════════════

  What changed              │ What gets deleted
  ──────────────────────────┼───────────────────────────────────
  voice (any speaker)       │ voice_demos/, segments/, samples/, final/
  narrator-voice            │ voice_demos/, segments/, samples/, final/
  narrator-dialogue         │ voice_demos/, segments/, samples/, final/
  music on|off              │ music/, samples/, final/
  music-file                │ samples/, final/ (music/ replaced directly)
  music-db                  │ samples/, final/
  reverb on|off             │ segments/ (effects applied in-place), samples/, final/
  reverb-room, reverb-wet   │ segments/ (effects applied in-place), samples/, final/
```

Implementation: a dict mapping setting keys to lists of subdirectories to delete. Simple `shutil.rmtree()` for each with `os.path.exists()` guard.

### `set` Key → Artifact → Field Mapping

```
SET KEY → ARTIFACT MAPPING
══════════════════════════

  Key               │ Artifact File    │ JSON Path                              │ Value Type
  ──────────────────┼──────────────────┼────────────────────────────────────────┼───────────
  voice             │ cast.json        │ .characters[<speaker>].voice           │ string (voice ID)
  narrator-voice    │ cast.json        │ .narrator.voice                        │ string (voice ID)
  narrator-dialogue │ cast.json        │ .narrator.dialogue_voice               │ string (voice ID)
  music             │ direction.json   │ .no_music                              │ bool (on→false, off→true)
  music-file        │ (file copy)      │ output/<slug>/music/background.mp3     │ path (source file to copy)
  music-db          │ direction.json   │ .music_bed_db                          │ float (negative dB)
  reverb            │ effects.json     │ .per_segment.dialogue.reverb           │ dict or null (on→defaults, off→null)
  reverb-room       │ effects.json     │ .per_segment.dialogue.reverb.room_size │ float (0.0-1.0)
  reverb-wet        │ effects.json     │ .per_segment.dialogue.reverb.wet_level │ float (0.0-1.0)
```

Note: `set voice` requires `<speaker>` argument to identify which character. `set music-file` copies a file instead of updating JSON — it validates the source exists and is loadable by pydub, copies to `output/<slug>/music/background.mp3`, and updates `direction.json` with `music_source`. All other keys take a single value argument. The `set` subcommand validates the project exists before loading artifacts.

### output.json Manifest

Generated at export time (Step 6), saved alongside the final MP3 in `output/<slug>/final/output.json`. Read-only provenance — not consumed by the pipeline.

```json
{
  "project": "tell_tale_heart",
  "source": "demo/tell_tale_heart.txt",
  "generated_at": "2026-02-26T14:30:00Z",
  "producer_version": "0.1.0",
  "metadata": {
    "title": "The Tell-Tale Heart",
    "author": "Edgar Allan Poe"
  },
  "cast": {
    "narrator": {"voice": "en-US-GuyNeural", "dialogue_voice": "en-GB-RyanNeural"},
    "the old man": {"voice": "en-US-TonyNeural"},
    "officers": {"voice": "en-US-DavisNeural"}
  },
  "settings": {
    "music": true,
    "music_source": "bundled:tell_tale_heart.mp3",
    "music_bed_db": -25,
    "reverb": true,
    "reverb_room_size": 0.3,
    "reverb_wet_level": 0.15,
    "bitrate": "192k"
  },
  "stats": {
    "segments": 42,
    "duration_seconds": 312,
    "characters": 3
  }
}
```

## Output Directory Structure

Each production creates a project folder under `output/` containing intermediate artifacts for inspection, iteration, and resumability. The folder name is derived from the story filename (slugified).

```
OUTPUT DIRECTORY LIFECYCLE
══════════════════════════

  producer.py new story.txt    ──► parse + assign + write configs
  producer.py run story -v    ──► TTS + effects + music + assembly + export
       │
       ▼
  output/story/               ◄── created by `new`
       │
       ├── 1. Parse
       │   ├── script.json         segments as JSON (text, speaker, type)
       │   └── cast.json           resolved voice assignments + descriptions
       │
       ├── 2. Plan
       │   ├── direction.json      assembly plan: pause durations, bookend timing
       │   └── effects.json        effects config per segment (reverb, normalize)
       │
       ├── 3. Voice Demos  (-v only, before full TTS)
       │   └── voice_demos/
       │       ├── narrator_pangram.mp3        "The quick brown fox..."
       │       ├── narrator_story.mp3          first line from story
       │       ├── the_old_man_pangram.mp3
       │       └── the_old_man_story.mp3
       │
       │   ◄── PREVIEW GATE (-v mode): user hears demos, prompted to continue
       │
       ├── 4. TTS Generation
       │   └── segments/
       │       ├── 000_intro_narrator.mp3
       │       ├── 001_intro_the_old_man.mp3
       │       ├── ...
       │       └── 043_outro_narrator.mp3
       │
       ├── 5. Music (source priority: existing → user file → bundled → procedural)
       │   └── music/
       │       └── background.mp3
       │
       ├── 6. Assembly + Preview
       │   └── samples/
       │       └── preview_60s.mp3     first ~60s of assembled output
       │
       └── 7. Export
           ├── chapters/               (longer stories only)
           │   ├── chapter_01.mp3
           │   └── chapter_02.mp3
           └── final/
               ├── story.mp3           complete production
               └── output.json         provenance manifest (read-only)
```

### Artifact formats

**script.json** — parsed segments, written after Step 1:
```json
{
  "metadata": {"title": "The Tell-Tale Heart", "author": "Edgar Allan Poe"},
  "segments": [
    {"type": "narration", "text": "TRUE! -- nervous...", "speaker": "narrator"},
    {"type": "dialogue", "text": "Who's there?", "speaker": "the old man"}
  ]
}
```

**cast.json** — resolved voice assignments, written after Step 2:
```json
{
  "narrator": {
    "voice": "en-US-GuyNeural",
    "dialogue_voice": "en-GB-RyanNeural",
    "description": "a most unreliable narrator"
  },
  "characters": {
    "the old man": {
      "voice": "en-US-DavisNeural",
      "description": "a frail old man with a pale blue vulture eye",
      "source": "cast_file"
    },
    "officers": {
      "voice": "en-GB-ThomasNeural",
      "description": "three officers of the police",
      "source": "cast_file"
    }
  }
}
```

**direction.json** — assembly instructions, written after Step 2:
```json
{
  "intro_music_solo_ms": 4000,
  "outro_music_solo_ms": 4000,
  "music_bed_db": -25,
  "music_fade_ms": 2000,
  "pauses": {
    "same_type_ms": 300,
    "speaker_change_ms": 500,
    "type_transition_ms": 700
  },
  "no_music": false,
  "music_source": null
}
```

`music_source` is populated at run time by `generate_music()`. Possible values: `"bundled:<filename>"` (e.g., `"bundled:tell_tale_heart.mp3"`), `"user:<original_filename>"`, `"procedural"`, or `null` (not yet resolved). Written back to `direction.json` after music step completes.

**effects.json** — effects applied per segment, written after Step 2:
```json
{
  "global": {
    "normalize": true,
    "target_dbfs": -20
  },
  "per_segment": {
    "dialogue": {
      "reverb": {"room_size": 0.3, "wet_level": 0.15}
    },
    "narration": {
      "reverb": null
    }
  }
}
```

### Voice demos

Each unique character (including narrator) gets two demo clips generated before the full TTS run:

1. **Pangram**: "The quick brown fox jumps over the lazy dog." — tests the voice with all English phonemes
2. **Story line**: The character's first line of dialogue from the parsed segments — lets the user hear how the voice sounds with actual story content

Demo filenames are slugified: `the_old_man_pangram.mp3`, `the_old_man_story.mp3`. Narrator demos use the narration voice (not the dialogue voice).

**No-dialogue fallback**: Characters who appear in the cast file but never speak in the story get a pangram demo only (no story line demo). This handles characters mentioned by the narrator but without direct dialogue.

### Preview gate (verbose/interactive mode only)

When running with `-v`, the pipeline pauses after voice demo generation:

```
PREVIEW GATE FLOW
═════════════════
                                    ┌──────────────┐
  Parse → Assign → Write demos ───►│ Play demos?  │
                                    │   [Y/n]      │
                                    └──────┬───────┘
                                           │
                              ┌────────────┴────────────┐
                              │                         │
                           Y (enter)                  n (skip)
                              │                         │
                         Continue to                 Skip to
                         full TTS                    full TTS
                                                     silently
```

- Prints a summary table: each character, their assigned voice, and the demo file path
- Prompts: `"Listen to voice demos in output/<project>/voice_demos/. Continue? [Y/n] "`
- `Y` or Enter → proceed to full TTS generation
- `n` → skip preview, proceed to TTS silently
- The gate is ONLY active in `-v` mode AND when `sys.stdin.isatty()` is True (interactive terminal). Without `-v`, or in non-interactive environments (Ralph Loop, CI, piped stdin), voice demos are still generated but no prompt is shown. This prevents the pipeline from hanging in automated environments.

### Resumability

Resumability is split between `new` and `run` to match the two-step workflow:

```
RESUMABILITY CHECKS
═══════════════════

  `new` owns parse + voices (Steps 1-2):
  ─────────────────────────────────────────
  `new` always writes fresh configs. To re-parse after editing the source
  .txt file, run `new` again. It overwrites script.json, cast.json,
  direction.json, effects.json.

  `run` owns audio generation (Steps 3-7):
  ─────────────────────────────────────────
  Step 3 (Demos):     skip if voice_demos/ has expected file count AND cast.json mtime unchanged
  Step 4 (TTS):       skip if segments/ has expected file count matching script.json
  Step 5 (Music):     skip if music/background.mp3 exists
  Step 6 (Assembly):  always re-run (fast, depends on all prior outputs)
  Step 7 (Export):    always re-run (fast, final output)
```

- `run` assumes script.json and cast.json exist (created by `new`). If missing → SystemExit.
- Resumability uses **mtime comparison** — simple, no hashing of content
- When a step is skipped, verbose mode prints `"[skip] TTS: segments/ is up to date"`
- `run --force` deletes generated artifacts (voice_demos/, segments/, music/, samples/, final/) but preserves configs (script.json, cast.json, direction.json, effects.json)
- Partial TTS runs resume: if `segments/` has 20 of 43 expected files, TTS starts from segment 21
- **Editing source .txt**: requires running `new` again to re-parse. `run` does NOT re-check source file freshness — this is by design to keep the new/run boundary clean.

### Chapter splitting (longer stories)

Stories with >50 segments get chapter-level splits in `chapters/`:
- Split at the longest pause gap that falls near a chapter boundary (every ~10 minutes of audio)
- Each chapter is a standalone MP3 with no music (music only on the first and last chapter)
- Chapter naming: `chapter_01.mp3`, `chapter_02.mp3`, etc.
- Short stories (like Tell-Tale Heart) produce no chapter files — only `final/`

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
- **TTS writes to output directory**: Segments save directly to `output/<slug>/segments/` — no temp dir. This enables resumability (partial TTS runs resume from where they left off) and lets users inspect individual segments.
- **Hash-based voice assignment**: `sha256(name) % len(voices)` is stable across runs and text edits — only the new/removed character's voice changes, others stay the same. Uses `hashlib.sha256` (not `hash()`) because Python's built-in `hash()` is randomized per process since 3.3.
- **"I" = narrator**: First-person attributions map to the narrator speaker, preventing the narrator from being treated as a separate character in first-person stories.
- **Narrator voice split**: Narrator narration uses `en-US-GuyNeural` (American), narrator spoken dialogue uses `en-GB-RyanNeural` (British). Audible contrast between inner monologue and spoken words.
- **Bookend music**: Music plays only at the intro and outro — not during the story body. The intro features a title announcement and character introductions (each character says their name in their own voice). The outro has credits and "thank you for listening."
- **Music source priority**: Bundled CC0 classical pieces for demo stories (Satie for Tell-Tale Heart, Debussy for Open Window), user-provided via `set music-file`, procedural numpy sine wave fallback. All sources are copied to `output/<slug>/music/background.mp3` — no external references survive into the slug folder.
- **Metadata from file header**: Title is first non-empty line, author follows "by " pattern. Falls back gracefully.
- **Effects are additive**: All audio processing in `effects.py` is optional and layered on top of raw TTS output. The pipeline works without any effects applied.
- **Output directory per production**: Each story gets its own folder under `output/` with intermediate artifacts (script, cast, segments, music, etc.). Enables resumability, iteration on individual steps, and easy inspection.
- **Resumability via mtime**: Pipeline checks whether each step's output exists and is newer than its input. Simple, no content hashing. `--force` flag overrides and re-runs everything.
- **Voice demos as a quality gate**: Each character gets a pangram + first story line demo before the full TTS run. In verbose mode, the user is prompted to listen and approve before committing to the full (slow) TTS generation pass.
- **Artifacts are JSON, not pickle**: All intermediate files use human-readable JSON so users can inspect, edit, and version-control them.

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
  LAYER 2b (output management — depends on exporter + tts)
  ┌──────────────────────────────────────────────┐
  │  artifacts.py                   [sonnet]     │
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
    1   │ effects     │ sonnet │ Pedalboard wrapper, normalize
    2   │ assembly    │ opus   │ Bookend structure, pause logic, overlays
    2   │ exporter    │ sonnet │ Simple pydub export
    2b  │ artifacts   │ sonnet │ File I/O, JSON, directory management
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

**Creates**: `audiobook_producer/__init__.py`, `audiobook_producer/constants.py`, `audiobook_producer/models.py`, `tests/conftest.py`

**Pre-existing** (already committed): `producer.py`, `requirements.txt`

**Tests** (in `tests/test_models.py` — green after implementation):
- `test_segment_dataclass` — fields exist, defaults work
- `test_constants_exist` — all module-level constants are defined

**Also creates test stubs** for all Layer 1+ modules (red — provides targets for parallel agents):
- `tests/test_parser.py` with failing `test_parse_narration_only`
- `tests/test_voices.py` with failing `test_narrator_gets_narrator_voice`
- `tests/test_tts.py` with failing `test_tts_generates_files`
- `tests/test_music.py` with failing `test_procedural_music_returns_audio_segment`
- `tests/test_effects.py` with failing `test_reverb_on_dialogue`
- `tests/test_artifacts.py` with failing `test_init_output_dir`

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
- `test_parse_pre_attribution` — `the old man cried out, "Who's there?"` → dialogue Segment with speaker="the old man"
- `test_parse_variety_of_verbs` — test with "whispered", "exclaimed", "pursued", "announced", "admitted" — all should extract speaker correctly (The Open Window uses these)

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
- `test_load_cast_malformed_json` — invalid JSON → logs warning, returns empty dict (no crash)
- `test_cast_narrator_override` — cast file `"narrator"` key overrides NARRATOR_VOICE constant and provides description for intro
- `test_voice_determinism` — same speaker list → same assignments on repeated calls (sha256 is stable)
- `test_voice_stability` — adding a speaker doesn't change existing speakers' voices
- `test_many_speakers_wrap` — 20 speakers don't crash (hash wraps around pool)

Bookend scripts:
- `test_generate_intro_segments` — produces correct intro sequence: title, character intros with descriptions, narrator self-intro
- `test_generate_outro_segments` — produces credits and "thank you for listening"
- `test_intro_excludes_unknown_speakers` — speakers named "unknown" are not introduced
- `test_intro_character_speaks_own_name` — each character's name segment uses that character's voice
- `test_intro_includes_cast_descriptions` — when cast has descriptions, intro narration includes them
- `test_intro_without_cast_file` — no cast file → intro uses speaker names only, no descriptions

Commit: "Implement voice assignment with cast system and bookend scripts"

---

### Layer 1c: tts.py `[sonnet]`

**File**: `audiobook_producer/tts.py`
**Tests** (in `tests/test_tts.py` — green after implementation):

generate_single:
- `test_tts_generate_single` — mock edge_tts, verify single MP3 file created at specified output_path
- `test_tts_generate_single_retry` — mock edge_tts to fail once then succeed, verify retry works for single call

generate_tts:
- `test_tts_generates_files` — mock edge_tts, verify N files created in specified output directory
- `test_tts_retry_exhausted` — mock edge_tts to always fail, verify raises after 3 retries
- `test_tts_validates_output_size` — mock edge_tts to write 0-byte file, verify treated as failure
- `test_tts_progress_output` — capture stdout, verify segment counter appears

Mock setup: `unittest.mock.patch("audiobook_producer.tts.edge_tts.Communicate")` — note the fully qualified patch path for the package structure.

Commit: "Implement TTS generation with exponential backoff retry"

---

### Layer 1d: music.py `[sonnet]`

**File**: `audiobook_producer/music.py`

**Functions**:
- **`generate_music(project_dir, music_file=None)`**: Resolve music source and return AudioSegment. Priority: (1) existing `background.mp3` in project `music/` dir, (2) `music_file` argument → copy to project then load, (3) bundled demo music matching project slug, (4) procedural numpy fallback. All sources are trimmed/faded to MUSIC_LOOP_SECONDS and saved as `output/<slug>/music/background.mp3`. Returns `(AudioSegment, music_source_str)` tuple.
- **`generate_procedural_music()`**: Original numpy sine wave ambient drone. A-minor, MUSIC_LOOP_SECONDS duration. Returns AudioSegment.
- **`load_and_prepare_music(source_path, target_path)`**: Load MP3, trim to MUSIC_LOOP_SECONDS if longer, apply MUSIC_FADE_MS fade-out at the end, save to target_path. Returns AudioSegment.

**Tests** (in `tests/test_music.py` — green after implementation):

Procedural (existing, renamed):
- `test_procedural_music_returns_audio_segment` — numpy fallback returns AudioSegment
- `test_procedural_music_correct_duration` — duration ≈ MUSIC_LOOP_SECONDS * 1000 ms (±100ms)
- `test_procedural_music_not_silent` — RMS > 0

File-based music:
- `test_load_and_prepare_copies_to_target` — source MP3 copied to target path
- `test_load_and_prepare_trims_long_file` — 5-min MP3 trimmed to MUSIC_LOOP_SECONDS
- `test_load_and_prepare_fade_out` — last MUSIC_FADE_MS of output fades to near-silence
- `test_load_and_prepare_short_file_no_trim` — file shorter than MUSIC_LOOP_SECONDS used as-is

Source resolution:
- `test_generate_music_existing_background` — background.mp3 already exists → load it, don't overwrite
- `test_generate_music_user_file` — music_file arg → copies to music/, returns AudioSegment
- `test_generate_music_bundled_demo` — project slug matches demo → uses bundled music
- `test_generate_music_procedural_fallback` — no file, no bundled → numpy sine wave
- `test_generate_music_saves_to_project` — all paths save background.mp3 in project music/ dir

Commit: "Implement music with bundled CC0, user-provided, and procedural fallback"

---

### Layer 1e: effects.py `[sonnet]`

**File**: `audiobook_producer/effects.py`
**Tests** (in `tests/test_effects.py` — green after implementation):
- `test_reverb_on_dialogue` — dialogue AudioSegment processed through reverb has different waveform than input (pedalboard installed)
- `test_reverb_fallback_no_pedalboard` — when pedalboard not installed, returns audio unchanged (no crash)
- `test_reverb_skips_narration` — narration segments are not reverbed (only dialogue gets reverb)
- `test_normalize_levels` — multiple segments at different volumes → output volumes are within 3dB of each other
- `test_process_segments_passthrough` — when no effects enabled, output matches input

Commit: "Implement audio effects with reverb and volume normalization"

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
- `test_export_creates_manifest` — output.json exists alongside MP3 in final/
- `test_manifest_has_required_fields` — project, source, generated_at, metadata, cast, settings, stats
- `test_manifest_cast_matches_actual` — cast in manifest matches what was used

Commit: "Implement assembly with bookend music structure, MP3 export, and output.json manifest"

---

### Layer 2b: artifacts.py `[sonnet]`

**File**: `audiobook_producer/artifacts.py`

Manages the output directory structure, intermediate artifact files, voice demo generation, preview samples, resumability checks, and chapter splitting.

**Functions**:
- **`init_output_dir(story_path, output_base=OUTPUT_DIR)`**: Create `output/<slug>/` and all subdirectories. Returns the project directory path. Slug derived from story filename: `tell_tale_heart.txt` → `tell_tale_heart/`.
- **`write_artifact(project_dir, filename, data)`**: Generic JSON artifact writer. `json.dump(data, indent=2)` to `project_dir/filename`. Used for all 4 artifact files (script.json, cast.json, direction.json, effects.json).
- **`load_artifact(project_dir, filename)`**: Read JSON artifact back. Returns parsed dict. Returns None if file doesn't exist. Used by `set` subcommand to update cast.json, direction.json, effects.json.
- **`invalidate_downstream(project_dir, setting_key)`**: Given a setting key (e.g., "voice"), delete the appropriate downstream subdirectories per the invalidation map. Uses a dict mapping keys to lists of subdirs. `shutil.rmtree()` with `os.path.exists()` guard.
- **`get_project_status(project_dir)`**: Returns a dict describing the current state of each pipeline step (done/pending/partial). Checks for existence of artifacts and counts files in segments/. Used by `status` subcommand.
- **`list_projects(output_base=OUTPUT_DIR)`**: List all project slugs under the output directory. Returns sorted list of directory names that contain a script.json.
- **`generate_voice_demos(project_dir, cast, segments)`**: For each character + narrator, generate TTS clips. Characters with dialogue get 2 clips (pangram + first story line). Characters with no dialogue get pangram only. Saves to `voice_demos/`. Uses `tts.generate_single()` internally.
- **`generate_preview(project_dir, assembled_audio, duration_ms=PREVIEW_DURATION_MS)`**: Trim assembled audio to first N ms, export to `samples/preview_60s.mp3`.
- **`split_chapters(project_dir, assembled_audio, segments)`**: For stories with >50 segments, split into chapter-level MP3s in `chapters/`. No-op for short stories.
- **`check_step_fresh(project_dir, step_name, input_path=None)`**: Resumability check — returns True if step's output exists and input mtime is older than output mtime. Accepts a list of input paths (e.g., both `.txt` and `.cast.json` for the voices step). Used by CLI to skip completed steps.
- **`slug_from_path(story_path)`**: Convert story filename to output directory slug.

**Tests** (in `tests/test_artifacts.py` — green after implementation):

Directory and file management:
- `test_init_output_dir` — creates expected directory tree with all subdirs
- `test_init_output_dir_existing` — re-running on existing dir doesn't crash or delete files
- `test_slug_from_path` — `"/path/to/Tell-Tale Heart.txt"` → `"tell_tale_heart"`
- `test_write_artifact` — writes valid JSON, round-trips through json.load, creates file at correct path
- `test_write_artifact_nested_data` — handles nested dicts/lists correctly (cast.json structure)

Voice demos:
- `test_generate_voice_demos` — mock TTS, verify 2 files per character with dialogue (pangram + story line)
- `test_voice_demo_filenames` — verify slug-based naming: `the_old_man_pangram.mp3`
- `test_voice_demo_story_line` — each character's story demo uses their first dialogue line
- `test_voice_demo_no_dialogue` — character in cast but with no dialogue → pangram only, no crash

Preview and chapters:
- `test_generate_preview` — output file exists, duration ≈ PREVIEW_DURATION_MS (±500ms)
- `test_generate_preview_short_story` — story shorter than preview duration → preview = full length
- `test_split_chapters_short_story` — <50 segments → no chapter files created
- `test_split_chapters_long_story` — >50 segments → multiple chapter MP3s in chapters/

Resumability:
- `test_check_step_fresh_no_output` — no output file → returns False (step needs to run)
- `test_check_step_fresh_stale` — output exists but input is newer → returns False
- `test_check_step_fresh_current` — output exists and input is older → returns True (skip)
- `test_check_step_fresh_multiple_inputs` — cast.json check with both script.json and .cast.json as inputs; editing .cast.json alone invalidates the step

Loading and invalidation:
- `test_load_artifact` — round-trips with write_artifact
- `test_load_artifact_missing` — returns None for non-existent file
- `test_invalidate_voice_change` — deletes voice_demos/, segments/, samples/, final/
- `test_invalidate_music_toggle` — deletes music/, samples/, final/
- `test_invalidate_reverb_change` — deletes segments/, samples/, final/
- `test_invalidate_nonexistent_dirs` — doesn't crash on missing subdirs

Project status and listing:
- `test_get_project_status_empty` — new project → all steps pending
- `test_get_project_status_partial` — some artifacts exist → mixed done/pending
- `test_list_projects` — returns sorted list of project slugs
- `test_list_projects_empty` — empty output dir → empty list

Commit: "Implement output artifacts, voice demos, preview, resumability, and project management"

---

### Layer 3: cli.py `[sonnet]`

**File**: `audiobook_producer/cli.py`

Uses `argparse` with `add_subparsers()`. Each subcommand gets its own parser. The `new` subcommand runs parse + assign + write configs. The `run` subcommand picks up from where `new` left off (voice demos → TTS → effects → music → assembly → export). The `set` subcommand modifies JSON artifacts in-place and calls `invalidate_downstream()`. The `status` subcommand is purely read-only.

**Tests** (in `tests/test_cli.py` — green after implementation):

Subcommand routing:
- `test_cli_new_creates_project` — `new demo/tell_tale_heart.txt` creates output dir + script.json + cast.json
- `test_cli_new_already_exists` — `new` on existing project → error with message to use `run` or `set`
- `test_cli_run_basic` — `run tell_tale_heart` executes pipeline steps
- `test_cli_run_nonexistent_project` — `run nonexistent` → SystemExit with clear message
- `test_cli_run_verbose` — `run tell_tale_heart -v` enables voice demos + preview gate
- `test_cli_run_force` — `run tell_tale_heart --force` deletes generated artifacts, re-runs everything
- `test_cli_status_shows_state` — `status tell_tale_heart` prints project state without modifying anything
- `test_cli_status_nonexistent` — `status nonexistent` → SystemExit with clear message
- `test_cli_set_voice` — `set tell_tale_heart voice "the old man" en-US-TonyNeural` updates cast.json
- `test_cli_set_voice_invalidates` — after set voice, voice_demos/ and segments/ are deleted
- `test_cli_set_music_off` — `set tell_tale_heart music off` updates direction.json
- `test_cli_set_music_file` — `set tell_tale_heart music-file path/to/track.mp3` copies file to music/background.mp3
- `test_cli_set_music_file_missing` — `set tell_tale_heart music-file nonexistent.mp3` → SystemExit
- `test_cli_set_music_file_invalidates` — after set music-file, samples/ and final/ deleted
- `test_cli_set_reverb_room` — `set tell_tale_heart reverb-room 0.5` updates effects.json
- `test_cli_set_nonexistent_project` — `set nonexistent voice "x" en-US-TonyNeural` → SystemExit with clear message
- `test_cli_set_invalid_key` — `set tell_tale_heart badkey val` → SystemExit
- `test_cli_list_projects` — `list` shows all project dirs under output/
- `test_cli_list_empty` — `list` with no projects → "No projects found"
- `test_cli_voices` — `voices` lists available edge-tts voices
- `test_cli_voices_filter` — `voices --filter en-US` filters voice list
- `test_cli_no_args_shows_help` — no subcommand → prints help text

Input validation (in `new` subcommand):
- `test_validate_missing_file` — `new nonexistent.txt` → SystemExit with clear message
- `test_validate_empty_file` — `new empty.txt` → SystemExit with clear message
- `test_validate_no_segments` — `new` with unparseable file → SystemExit with clear message
- `test_validate_ffmpeg_missing` — any `run` → SystemExit when ffmpeg not found

Preview gate (in `run -v`):
- `test_preview_gate_verbose` — `run -v` with isatty()=True calls input() after voice demo step (mock input)
- `test_preview_gate_nonverbose` — `run` without `-v`, no input() call — proceeds silently
- `test_preview_gate_noninteractive` — `run -v` but isatty()=False (piped stdin) — no input() call, proceeds silently

Resumability (in `run`):
- `test_run_skips_completed_steps` — when artifacts exist and are fresh, pipeline skips those steps (verify via call counts on mocked functions)
- `test_force_flag_deletes_output` — `--force` removes generated artifacts (preserves configs) before starting
- `test_force_flag_no_existing_dir` — `--force` on non-existent output dir doesn't crash (os.path.exists guard)

Commit: "Add CLI with subcommand routing, validation, preview gate, and resumability"

---

### Layer 4: Integration `[opus]`

**Tests** (in `tests/test_integration.py` — green after implementation):

Tell-Tale Heart (first-person narrator, 3 cast members):
- `test_parse_tell_tale_heart` — parse `demo/tell_tale_heart.txt`, verify segments > 0 and no empty text fields
- `test_pipeline_tell_tale_heart` — mock edge_tts, run full pipeline, verify output MP3 exists and is valid. Verify uses bundled Satie (music_source = "bundled:tell_tale_heart.mp3"), not procedural.
- `test_pipeline_tell_tale_heart_intro_outro` — verify intro has title/author/cast, outro has credits + "thank you"

The Open Window (third-person, 6 cast members with aliases):
- `test_parse_open_window` — parse `demo/the_open_window.txt`, verify segments > 0 and multiple speakers found
- `test_pipeline_open_window` — mock edge_tts, run full pipeline, verify output MP3 exists and is valid. Verify uses bundled Debussy (music_source = "bundled:the_open_window.mp3"), not procedural.
- `test_pipeline_open_window_aliases` — verify "the child" and "the niece" map to the same voice (alias resolution)

Cross-cutting:
- `test_full_pipeline_no_music` — run with `set music off` then `run`, verify no music in output
- `test_full_pipeline_bookend_structure` — verify output audio has music at start and end, silence in the middle
- `test_full_pipeline_output_dir` — verify output directory contains script.json, cast.json, direction.json, effects.json, segments/, music/background.mp3, final/, output.json. Verify `output.json` includes `music_source` in settings.
- `test_full_pipeline_resume` — run pipeline twice; second run skips TTS (verify TTS mock call count = 0 on second run)

Commit: "Wire up full pipeline and verify end-to-end integration"

---

### Layer 5: Documentation `[sonnet]`

No new tests. Manual verification only.

- Write README.md, LICENSE (MIT)
- Run both demos for real (with actual edge-tts network calls):
  - `python producer.py new demo/tell_tale_heart.txt && python producer.py run tell_tale_heart -v`
  - `python producer.py new demo/the_open_window.txt && python producer.py run the_open_window -v`
- Verify both output MP3s play correctly with bookend intro/outro and distinct character voices
- Verify `output/<slug>/final/output.json` exists with correct provenance data
- Commit: "Add documentation and verify end-to-end output for both demos"

---

## Future Work

### Async/concurrent TTS generation
Sequential TTS takes ~1-2 minutes for a short story. Replace the sequential loop in `tts.py` with `asyncio.gather()` + `Semaphore(5)` to limit concurrency while still respecting rate limits. This is the single biggest performance win available.

### Procedural SFX + scene annotation
The effects.py module currently handles per-segment processing (reverb, normalization). Adding procedural SFX (heartbeat, room tone, outdoor ambience) requires a scene annotation system to specify *when* effects play — the current architecture has no mechanism for this. Options:
- **Cast file extension**: add an `"effects"` key to `.cast.json` mapping scene ranges to SFX
- **Inline text markers**: `[SFX: heartbeat]` annotations in the story text
- **Automatic detection**: NLP-based scene classification (most complex, least reliable)

Candidate SFX (all procedurally generated via numpy, no downloads):
- Heartbeat: low-frequency double-pulse sine wave with envelope
- Room tone: filtered white noise at -40dB
- Outdoor ambience: shaped white noise with slow modulation
- Clock ticking: periodic short clicks

### Advanced sound effects
- Environmental audio that adapts to scene content (indoor/outdoor detection)
- Foley effects library (footsteps, doors, weather)
