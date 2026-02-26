"""Shared fixtures for audiobook producer tests."""

import pytest
from pydub import AudioSegment

from audiobook_producer.models import Segment


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
