"""All magic numbers and configuration constants."""

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
BUNDLED_MUSIC_DIR = "demo/music"             # bundled CC0 classical pieces
VERSION = "0.1.0"
