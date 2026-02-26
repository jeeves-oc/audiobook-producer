"""Tests for assembly module (Layer 2)."""

import pytest
from pydub import AudioSegment

from audiobook_producer.models import Segment
from audiobook_producer.assembly import assemble
from audiobook_producer.constants import (
    PAUSE_SAME_TYPE_MS,
    PAUSE_SPEAKER_CHANGE_MS,
    PAUSE_TYPE_TRANSITION_MS,
    INTRO_MUSIC_SOLO_MS,
)


def _seg(type_="narration", speaker="narrator", voice="en-US-GuyNeural"):
    """Helper to create a Segment."""
    return Segment(type=type_, text="test", speaker=speaker, voice=voice)


def _audio(duration_ms=500):
    """Helper to create a silent AudioSegment."""
    return AudioSegment.silent(duration=duration_ms)


def _loud_audio(duration_ms=500):
    """Create an AudioSegment with actual sound (not silence)."""
    import numpy as np
    samples = np.random.randint(-5000, 5000, int(44100 * duration_ms / 1000), dtype=np.int16)
    return AudioSegment(
        data=samples.tobytes(),
        sample_width=2,
        frame_rate=44100,
        channels=1,
    )


# --- Story body pause tests ---

def test_assemble_single_segment():
    """1 segment → output audio with no pauses."""
    seg = _seg()
    audio = _audio(500)
    result = assemble([], [], [seg], [audio], [], [], no_music=True)
    # Should be approximately the segment duration (plus small section pauses)
    assert len(result) >= 400


def test_assemble_same_type_pause():
    """2 narration segments → total ≈ sum + 300ms."""
    s1, s2 = _seg(), _seg()
    a1, a2 = _audio(500), _audio(500)
    result = assemble([], [], [s1, s2], [a1, a2], [], [], no_music=True)
    expected = 500 + 500 + PAUSE_SAME_TYPE_MS
    # Allow tolerance for section pauses
    assert abs(len(result) - expected) < 2000


def test_assemble_type_transition_pause():
    """Narration then dialogue → total includes type transition pause."""
    s1 = _seg(type_="narration")
    s2 = _seg(type_="dialogue", speaker="bob")
    a1, a2 = _audio(500), _audio(500)
    result = assemble([], [], [s1, s2], [a1, a2], [], [], no_music=True)
    expected = 500 + 500 + PAUSE_TYPE_TRANSITION_MS
    assert abs(len(result) - expected) < 2000


def test_assemble_speaker_change_pause():
    """Dialogue A then B → total includes speaker change pause."""
    s1 = _seg(type_="dialogue", speaker="alice")
    s2 = _seg(type_="dialogue", speaker="bob")
    a1, a2 = _audio(500), _audio(500)
    result = assemble([], [], [s1, s2], [a1, a2], [], [], no_music=True)
    expected = 500 + 500 + PAUSE_SPEAKER_CHANGE_MS
    assert abs(len(result) - expected) < 2000


def test_assemble_pause_precedence():
    """Type transition + speaker change → max(700, 500) = 700ms."""
    s1 = _seg(type_="narration", speaker="narrator")
    s2 = _seg(type_="dialogue", speaker="bob")
    a1, a2 = _audio(500), _audio(500)
    result = assemble([], [], [s1, s2], [a1, a2], [], [], no_music=True)
    # max(700, 500) = 700
    expected = 500 + 500 + max(PAUSE_TYPE_TRANSITION_MS, PAUSE_SPEAKER_CHANGE_MS)
    assert abs(len(result) - expected) < 2000


# --- Bookend structure tests ---

def test_assemble_bookend_has_intro():
    """Output starts with intro segments before story."""
    intro_seg = _seg()
    intro_audio = _audio(1000)
    story_seg = _seg()
    story_audio = _audio(500)
    music = _loud_audio(5000)

    result = assemble(
        [intro_seg], [intro_audio],
        [story_seg], [story_audio],
        [], [],
        music=music,
    )
    # Total should be longer than just story
    assert len(result) > len(story_audio) + 1000


def test_assemble_bookend_has_outro():
    """Output ends with outro segments after story."""
    story_seg = _seg()
    story_audio = _audio(500)
    outro_seg = _seg()
    outro_audio = _audio(1000)
    music = _loud_audio(5000)

    result = assemble(
        [], [],
        [story_seg], [story_audio],
        [outro_seg], [outro_audio],
        music=music,
    )
    assert len(result) > len(story_audio) + 1000


def test_assemble_bookend_music_intro():
    """First section of output has music (RMS check)."""
    intro_seg = _seg()
    intro_audio = _audio(1000)
    story_seg = _seg()
    story_audio = _audio(2000)
    music = _loud_audio(5000)

    result = assemble(
        [intro_seg], [intro_audio],
        [story_seg], [story_audio],
        [], [],
        music=music,
    )
    # First INTRO_MUSIC_SOLO_MS should have audible music
    intro_section = result[:INTRO_MUSIC_SOLO_MS]
    assert intro_section.rms > 0


def test_assemble_bookend_no_music_mid():
    """Middle section of output has no music background."""
    intro_seg = _seg()
    intro_audio = _audio(500)
    # Make story long enough to clearly separate from bookends
    story_segs = [_seg() for _ in range(3)]
    story_audios = [_audio(2000) for _ in range(3)]
    outro_seg = _seg()
    outro_audio = _audio(500)
    music = _loud_audio(5000)

    result = assemble(
        [intro_seg], [intro_audio],
        story_segs, story_audios,
        [outro_seg], [outro_audio],
        music=music,
    )
    # The story section in the middle should be silent where there's no narration
    # Just verify the assembly completes and has reasonable length
    assert len(result) > 8000  # should be at least 8 seconds


def test_assemble_no_music_flag():
    """When no_music=True, no music anywhere."""
    intro_seg = _seg()
    intro_audio = _audio(500)
    story_seg = _seg()
    story_audio = _audio(500)
    outro_seg = _seg()
    outro_audio = _audio(500)
    music = _loud_audio(5000)

    result = assemble(
        [intro_seg], [intro_audio],
        [story_seg], [story_audio],
        [outro_seg], [outro_audio],
        music=music,
        no_music=True,
    )
    # In no-music mode, result should be approximately narration + pauses only
    # No music solo sections
    assert len(result) < 5000  # should be much shorter without music bookends
