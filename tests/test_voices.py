"""Tests for voices module (Layer 1b)."""

import json
import pytest

from audiobook_producer.models import Segment
from audiobook_producer.constants import NARRATOR_VOICE, NARRATOR_DIALOGUE_VOICE
from audiobook_producer.voices import (
    assign_voices,
    load_cast,
    generate_intro_segments,
    generate_outro_segments,
)


# --- Voice assignment ---

def test_narrator_gets_narrator_voice(sample_segments):
    """Narrator narration segments get NARRATOR_VOICE."""
    assign_voices(sample_segments)
    narrator_narration = [s for s in sample_segments if s.speaker == "narrator" and s.type == "narration"]
    assert all(s.voice == NARRATOR_VOICE for s in narrator_narration)


def test_narrator_dialogue_gets_distinct_voice(sample_segments):
    """Narrator dialogue segments get NARRATOR_DIALOGUE_VOICE."""
    assign_voices(sample_segments)
    narrator_dialogue = [s for s in sample_segments if s.speaker == "narrator" and s.type == "dialogue"]
    assert all(s.voice == NARRATOR_DIALOGUE_VOICE for s in narrator_dialogue)


def test_cast_overrides_hash():
    """Character in cast file gets the cast voice."""
    segments = [Segment(type="dialogue", text="Hello", speaker="bob")]
    cast = {"cast": {"bob": {"voice": "en-US-AriaNeural"}}}
    assign_voices(segments, cast=cast)
    assert segments[0].voice == "en-US-AriaNeural"


def test_cast_missing_character_falls_back():
    """Character NOT in cast falls back to hash pool."""
    segments = [Segment(type="dialogue", text="Hello", speaker="charlie")]
    cast = {"cast": {"bob": {"voice": "en-US-AriaNeural"}}}
    assign_voices(segments, cast=cast)
    assert segments[0].voice != ""
    assert segments[0].voice != "en-US-AriaNeural"  # not bob's voice


def test_cast_alias_resolves():
    """Alias resolves to primary character's voice."""
    segments = [Segment(type="dialogue", text="Hi", speaker="the child")]
    cast = {
        "cast": {
            "the niece": {
                "voice": "en-US-AriaNeural",
                "aliases": ["the child", "the self-possessed young lady"],
            }
        }
    }
    assign_voices(segments, cast=cast)
    assert segments[0].voice == "en-US-AriaNeural"


def test_load_cast_file(tmp_path):
    """Loads .cast.json sidecar file."""
    story = tmp_path / "story.txt"
    story.write_text("content")
    cast_file = tmp_path / "story.cast.json"
    cast_data = {"narrator": {"voice": "en-US-GuyNeural"}, "cast": {"bob": {"voice": "en-US-AriaNeural"}}}
    cast_file.write_text(json.dumps(cast_data))
    result = load_cast(str(story))
    assert "cast" in result
    assert result["cast"]["bob"]["voice"] == "en-US-AriaNeural"


def test_load_cast_missing_file(tmp_path):
    """No cast file returns empty dict."""
    story = tmp_path / "story.txt"
    story.write_text("content")
    result = load_cast(str(story))
    assert result == {}


def test_load_cast_malformed_json(tmp_path):
    """Invalid JSON logs warning and returns empty dict."""
    story = tmp_path / "story.txt"
    story.write_text("content")
    cast_file = tmp_path / "story.cast.json"
    cast_file.write_text("{bad json")
    result = load_cast(str(story))
    assert result == {}


def test_cast_narrator_override():
    """Cast file narrator key overrides NARRATOR_VOICE."""
    segments = [Segment(type="narration", text="Dark.", speaker="narrator")]
    cast = {"narrator": {"voice": "en-GB-RyanNeural"}}
    assign_voices(segments, cast=cast)
    assert segments[0].voice == "en-GB-RyanNeural"


def test_voice_determinism():
    """Same speaker list → same assignments on repeated calls."""
    segs1 = [Segment(type="dialogue", text="A", speaker="alice"),
             Segment(type="dialogue", text="B", speaker="bob")]
    segs2 = [Segment(type="dialogue", text="A", speaker="alice"),
             Segment(type="dialogue", text="B", speaker="bob")]
    assign_voices(segs1)
    assign_voices(segs2)
    assert segs1[0].voice == segs2[0].voice
    assert segs1[1].voice == segs2[1].voice


def test_voice_stability():
    """Adding a speaker doesn't change existing speakers' voices."""
    segs_before = [Segment(type="dialogue", text="A", speaker="alice")]
    segs_after = [Segment(type="dialogue", text="A", speaker="alice"),
                  Segment(type="dialogue", text="B", speaker="bob")]
    assign_voices(segs_before)
    assign_voices(segs_after)
    assert segs_before[0].voice == segs_after[0].voice


def test_many_speakers_wrap():
    """20 speakers don't crash (hash wraps around pool)."""
    segments = [Segment(type="dialogue", text=f"Line {i}", speaker=f"speaker_{i}")
                for i in range(20)]
    assign_voices(segments)
    assert all(s.voice != "" for s in segments)


# --- Bookend scripts ---

def test_generate_intro_segments():
    """Intro has title, character intros, narrator self-intro."""
    segments = [
        Segment(type="narration", text="Dark.", speaker="narrator", voice=NARRATOR_VOICE),
        Segment(type="dialogue", text="Who?", speaker="old man", voice="en-US-DavisNeural"),
    ]
    intro = generate_intro_segments("The Story", "Author", segments)
    texts = " ".join(s.text for s in intro)
    assert "The Story" in texts
    assert "Author" in texts
    assert any(s.speaker == "old man" for s in intro)


def test_generate_outro_segments():
    """Outro has credits and 'thank you'."""
    segments = [
        Segment(type="narration", text="Dark.", speaker="narrator", voice=NARRATOR_VOICE),
        Segment(type="dialogue", text="Who?", speaker="old man", voice="en-US-DavisNeural"),
    ]
    outro = generate_outro_segments("The Story", "Author", segments)
    texts = " ".join(s.text.lower() for s in outro)
    assert "the story" in texts.lower()
    assert "thank you" in texts


def test_intro_excludes_unknown_speakers():
    """Speakers named 'unknown' are not introduced."""
    segments = [
        Segment(type="narration", text="Dark.", speaker="narrator", voice=NARRATOR_VOICE),
        Segment(type="dialogue", text="Hi.", speaker="unknown", voice="en-US-DavisNeural"),
    ]
    intro = generate_intro_segments("Title", "Author", segments)
    assert not any(s.speaker == "unknown" for s in intro)


def test_intro_character_speaks_own_name():
    """Each character's name segment uses that character's voice."""
    segments = [
        Segment(type="narration", text="Dark.", speaker="narrator", voice=NARRATOR_VOICE),
        Segment(type="dialogue", text="Who?", speaker="old man", voice="en-US-DavisNeural"),
    ]
    intro = generate_intro_segments("Title", "Author", segments)
    char_segs = [s for s in intro if s.speaker == "old man"]
    assert len(char_segs) >= 1
    assert all(s.voice == "en-US-DavisNeural" for s in char_segs)


def test_intro_includes_cast_descriptions():
    """When cast has descriptions, intro narration includes them."""
    segments = [
        Segment(type="narration", text="Dark.", speaker="narrator", voice=NARRATOR_VOICE),
        Segment(type="dialogue", text="Who?", speaker="old man", voice="en-US-DavisNeural"),
    ]
    cast = {
        "cast": {"old man": {"voice": "en-US-DavisNeural", "description": "a frail old man"}}
    }
    intro = generate_intro_segments("Title", "Author", segments, cast=cast)
    texts = " ".join(s.text for s in intro)
    assert "frail old man" in texts


def test_intro_without_cast_file():
    """No cast file — intro uses speaker names only."""
    segments = [
        Segment(type="narration", text="Dark.", speaker="narrator", voice=NARRATOR_VOICE),
        Segment(type="dialogue", text="Who?", speaker="old man", voice="en-US-DavisNeural"),
    ]
    intro = generate_intro_segments("Title", "Author", segments, cast=None)
    # Should still have intro segments even without cast descriptions
    assert len(intro) >= 2
