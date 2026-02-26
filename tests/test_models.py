"""Tests for constants and models (Layer 0)."""

from audiobook_producer.models import Segment
from audiobook_producer import constants


def test_segment_dataclass():
    """Segment fields exist and defaults work."""
    seg = Segment(type="narration", text="Hello.", speaker="narrator")
    assert seg.type == "narration"
    assert seg.text == "Hello."
    assert seg.speaker == "narrator"
    assert seg.voice == ""  # default


def test_segment_with_voice():
    """Segment accepts a voice field."""
    seg = Segment(type="dialogue", text="Hi.", speaker="bob", voice="en-US-GuyNeural")
    assert seg.voice == "en-US-GuyNeural"


def test_constants_exist():
    """All module-level constants are defined."""
    expected = [
        "SEGMENT_SPLIT_THRESHOLD",
        "PAUSE_SAME_TYPE_MS",
        "PAUSE_SPEAKER_CHANGE_MS",
        "PAUSE_TYPE_TRANSITION_MS",
        "MUSIC_LOOP_SECONDS",
        "INTRO_MUSIC_SOLO_MS",
        "OUTRO_MUSIC_SOLO_MS",
        "MUSIC_BED_DB",
        "MUSIC_FADE_MS",
        "OUTPUT_BITRATE",
        "TTS_RETRY_COUNT",
        "TTS_RETRY_BASE_DELAY",
        "NARRATOR_VOICE",
        "NARRATOR_DIALOGUE_VOICE",
        "REVERB_ROOM_SIZE",
        "REVERB_WET_LEVEL",
        "PREVIEW_DURATION_MS",
        "VOICE_DEMO_PANGRAM",
        "OUTPUT_DIR",
        "BUNDLED_MUSIC_DIR",
        "VERSION",
    ]
    for name in expected:
        assert hasattr(constants, name), f"Missing constant: {name}"
