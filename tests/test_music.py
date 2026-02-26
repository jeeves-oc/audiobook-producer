"""Tests for music module (Layer 1d)."""

import json
import os

import pytest
from pydub import AudioSegment

from audiobook_producer.music import (
    generate_music,
    generate_procedural_music,
    load_and_prepare_music,
)
from audiobook_producer.constants import MUSIC_LOOP_SECONDS, MUSIC_FADE_MS


# --- Procedural music ---

def test_procedural_music_returns_audio_segment():
    """Numpy fallback returns AudioSegment."""
    result = generate_procedural_music()
    assert isinstance(result, AudioSegment)


def test_procedural_music_correct_duration():
    """Duration ≈ MUSIC_LOOP_SECONDS * 1000 ms (±100ms)."""
    result = generate_procedural_music()
    expected_ms = MUSIC_LOOP_SECONDS * 1000
    assert abs(len(result) - expected_ms) < 100


def test_procedural_music_not_silent():
    """RMS > 0."""
    result = generate_procedural_music()
    assert result.rms > 0


# --- File-based music ---

def test_load_and_prepare_copies_to_target(tmp_path):
    """Source MP3 copied to target path."""
    source = tmp_path / "source.mp3"
    target = tmp_path / "target.mp3"
    AudioSegment.silent(duration=5000).export(str(source), format="mp3")
    load_and_prepare_music(str(source), str(target))
    assert target.exists()


def test_load_and_prepare_trims_long_file(tmp_path):
    """Long MP3 trimmed to MUSIC_LOOP_SECONDS."""
    source = tmp_path / "long.mp3"
    target = tmp_path / "trimmed.mp3"
    # Create a file longer than MUSIC_LOOP_SECONDS
    long_audio = AudioSegment.silent(duration=(MUSIC_LOOP_SECONDS + 30) * 1000)
    long_audio.export(str(source), format="mp3")
    result = load_and_prepare_music(str(source), str(target))
    expected_ms = MUSIC_LOOP_SECONDS * 1000
    assert abs(len(result) - expected_ms) < 200


def test_load_and_prepare_fade_out(tmp_path):
    """Last section of output fades to near-silence."""
    source = tmp_path / "source.mp3"
    target = tmp_path / "faded.mp3"
    # Use loud audio to detect fade
    import numpy as np
    samples = np.random.randint(-10000, 10000, 44100 * (MUSIC_LOOP_SECONDS + 5), dtype=np.int16)
    audio = AudioSegment(
        data=samples.tobytes(),
        sample_width=2,
        frame_rate=44100,
        channels=1,
    )
    audio.export(str(source), format="mp3")
    result = load_and_prepare_music(str(source), str(target))
    # Last 100ms should be quieter than the middle
    middle = result[len(result) // 2 : len(result) // 2 + 500]
    end = result[-200:]
    assert end.rms < middle.rms


def test_load_and_prepare_short_file_no_trim(tmp_path):
    """File shorter than MUSIC_LOOP_SECONDS used as-is."""
    source = tmp_path / "short.mp3"
    target = tmp_path / "out.mp3"
    short_audio = AudioSegment.silent(duration=5000)
    short_audio.export(str(source), format="mp3")
    result = load_and_prepare_music(str(source), str(target))
    # Should be approximately the same duration (MP3 encoding adds a few ms)
    assert abs(len(result) - 5000) < 200


# --- Source resolution ---

def _setup_project(tmp_path, slug="test_story"):
    """Helper to create a project directory structure."""
    project_dir = tmp_path / slug
    project_dir.mkdir()
    (project_dir / "music").mkdir()
    return str(project_dir)


def test_generate_music_existing_background(tmp_path):
    """Existing background.mp3 is loaded, not overwritten."""
    project_dir = _setup_project(tmp_path)
    bg = os.path.join(project_dir, "music", "background.mp3")
    AudioSegment.silent(duration=5000).export(bg, format="mp3")
    # Write direction.json with provenance
    direction = {"music_source": "bundled:test.mp3"}
    with open(os.path.join(project_dir, "direction.json"), "w") as f:
        json.dump(direction, f)
    audio, source = generate_music(project_dir)
    assert isinstance(audio, AudioSegment)
    assert source == "bundled:test.mp3"


def test_generate_music_existing_reads_provenance(tmp_path):
    """Existing background.mp3 preserves provenance from direction.json."""
    project_dir = _setup_project(tmp_path)
    bg = os.path.join(project_dir, "music", "background.mp3")
    AudioSegment.silent(duration=5000).export(bg, format="mp3")
    direction = {"music_source": "user:custom.mp3"}
    with open(os.path.join(project_dir, "direction.json"), "w") as f:
        json.dump(direction, f)
    audio, source = generate_music(project_dir)
    assert source == "user:custom.mp3"


def test_generate_music_user_file(tmp_path):
    """music_file arg copies to music/ and returns user: source."""
    project_dir = _setup_project(tmp_path)
    user_file = tmp_path / "my_track.mp3"
    AudioSegment.silent(duration=5000).export(str(user_file), format="mp3")
    audio, source = generate_music(project_dir, music_file=str(user_file))
    assert isinstance(audio, AudioSegment)
    assert source == "user:my_track.mp3"


def test_generate_music_bundled_demo(tmp_path, monkeypatch):
    """Project slug matching demo uses bundled music."""
    project_dir = _setup_project(tmp_path, slug="tell_tale_heart")
    # Create a fake bundled music file
    bundled_dir = tmp_path / "demo" / "music"
    bundled_dir.mkdir(parents=True)
    bundled_file = bundled_dir / "tell_tale_heart.mp3"
    AudioSegment.silent(duration=5000).export(str(bundled_file), format="mp3")
    monkeypatch.setattr("audiobook_producer.music.BUNDLED_MUSIC_DIR", str(bundled_dir))
    audio, source = generate_music(project_dir)
    assert isinstance(audio, AudioSegment)
    assert source == "bundled:tell_tale_heart.mp3"


def test_generate_music_procedural_fallback(tmp_path):
    """No file, no bundled → procedural fallback."""
    project_dir = _setup_project(tmp_path, slug="no_match_story")
    audio, source = generate_music(project_dir)
    assert isinstance(audio, AudioSegment)
    assert source == "procedural"


def test_generate_music_saves_to_project(tmp_path):
    """All paths save background.mp3 in project music/ dir."""
    project_dir = _setup_project(tmp_path, slug="save_test")
    audio, source = generate_music(project_dir)
    bg = os.path.join(project_dir, "music", "background.mp3")
    assert os.path.exists(bg)
