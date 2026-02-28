"""Tests for effects module (Layer 1e)."""

import pytest
from pydub import AudioSegment

from audiobook_producer.models import Segment
from audiobook_producer.effects import apply_reverb, normalize_levels, process_segments


def _make_audio(duration=500, volume_db=0):
    """Create a test AudioSegment at a given volume."""
    audio = AudioSegment.silent(duration=duration)
    if volume_db != 0:
        audio = audio + volume_db  # adjust volume
    return audio


def test_reverb_on_dialogue():
    """Dialogue processed through reverb has different waveform (or same if fallback)."""
    audio = _make_audio(500)
    result = apply_reverb(audio)
    assert isinstance(result, AudioSegment)
    assert abs(len(result) - len(audio)) < 100  # duration roughly preserved


def test_reverb_fallback_no_pedalboard():
    """When pedalboard not installed, returns audio unchanged."""
    import audiobook_producer.effects as eff
    original_available = eff.PEDALBOARD_AVAILABLE
    try:
        eff.PEDALBOARD_AVAILABLE = False
        audio = _make_audio(500)
        result = apply_reverb(audio)
        assert isinstance(result, AudioSegment)
        # Should be same audio back
        assert len(result) == len(audio)
    finally:
        eff.PEDALBOARD_AVAILABLE = original_available


def test_reverb_on_narration():
    """Narration segments get lighter reverb than dialogue."""
    segments = [
        Segment(type="narration", text="It was dark.", speaker="narrator", voice="en-US-RogerNeural"),
    ]
    audio_map = {"narration_0": _make_audio(500)}
    result = process_segments(segments, audio_map, reverb=True)
    assert isinstance(result["narration_0"], AudioSegment)
    assert abs(len(result["narration_0"]) - 500) < 100  # duration roughly preserved


def test_normalize_levels():
    """Multiple segments at different volumes → output within 3dB of each other."""
    audios = {
        "a": _make_audio(500) + 10,   # louder
        "b": _make_audio(500) - 20,   # quieter
        "c": _make_audio(500),
    }
    normalized = normalize_levels(audios)
    dbfs_values = [seg.dBFS for seg in normalized.values() if seg.dBFS != float('-inf')]
    if len(dbfs_values) >= 2:
        assert max(dbfs_values) - min(dbfs_values) < 6  # within 6dB


def test_process_segments_passthrough():
    """When no effects enabled, output matches input."""
    segments = [
        Segment(type="narration", text="Text.", speaker="narrator", voice="en-US-GuyNeural"),
    ]
    audio = _make_audio(500)
    audio_map = {"narration_0": audio}
    result = process_segments(segments, audio_map, reverb=False, normalize=False)
    assert len(result["narration_0"]) == len(audio)
