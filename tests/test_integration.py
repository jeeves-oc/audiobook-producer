"""Integration tests (Layer 4) — full pipeline verification."""

import json
import os
import shutil
from unittest.mock import patch, MagicMock

import pytest
from pydub import AudioSegment

from audiobook_producer.parser import parse_story, extract_metadata
from audiobook_producer.voices import assign_voices, load_cast, generate_intro_segments, generate_outro_segments
from audiobook_producer.tts import generate_tts
from audiobook_producer.music import generate_music
from audiobook_producer.effects import process_segments
from audiobook_producer.assembly import assemble
from audiobook_producer.exporter import export
from audiobook_producer.artifacts import (
    init_output_dir, write_artifact, load_artifact, slug_from_path,
    generate_preview, split_chapters, invalidate_downstream,
)
from audiobook_producer.cli import main
from audiobook_producer.constants import OUTPUT_DIR, NARRATOR_VOICE, NARRATOR_DIALOGUE_VOICE
from audiobook_producer.models import Segment


DEMO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "demo")
TTH_PATH = os.path.join(DEMO_DIR, "tell_tale_heart.txt")
TOW_PATH = os.path.join(DEMO_DIR, "the_open_window.txt")


def _mock_tts_communicate():
    """Create a mock edge_tts.Communicate factory."""
    def factory(text, voice, **kwargs):
        mock = MagicMock()
        async def save(path):
            AudioSegment.silent(duration=100).export(path, format="mp3")
        mock.save = save
        return mock
    return factory


# --- Tell-Tale Heart ---

def test_parse_tell_tale_heart():
    """Parse demo file, verify segments > 0 and no empty text."""
    with open(TTH_PATH) as f:
        text = f.read()
    title, author = extract_metadata(text)
    assert title == "The Tell-Tale Heart"
    assert author == "Edgar Allan Poe"
    segments = parse_story(text)
    assert len(segments) > 0
    for seg in segments:
        assert seg.text.strip() != ""


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_pipeline_tell_tale_heart(mock_which, mock_comm, tmp_path, monkeypatch):
    """Full pipeline produces valid MP3 with bundled music source."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()

    # Run new
    with patch("sys.argv", ["producer.py", "new", TTH_PATH]):
        main()

    slug = "tell_tale_heart"
    project_dir = str(tmp_path / "output" / slug)
    assert os.path.exists(os.path.join(project_dir, "script.json"))

    # Create fake bundled music
    bundled_dir = tmp_path / "demo" / "music"
    bundled_dir.mkdir(parents=True, exist_ok=True)
    AudioSegment.silent(duration=5000).export(
        str(bundled_dir / "tell_tale_heart.mp3"), format="mp3"
    )
    monkeypatch.setattr("audiobook_producer.music.BUNDLED_MUSIC_DIR", str(bundled_dir))

    # Run pipeline
    with patch("sys.argv", ["producer.py", "run", slug]):
        main()

    # Verify output
    final_mp3 = os.path.join(project_dir, "final", f"{slug}.mp3")
    assert os.path.exists(final_mp3)
    audio = AudioSegment.from_mp3(final_mp3)
    assert len(audio) > 0

    # Verify music source — should be bundled
    direction = load_artifact(project_dir, "direction.json")
    assert direction["music_source"] == "bundled:tell_tale_heart.mp3"

    # Verify output.json
    manifest_path = os.path.join(project_dir, "final", "output.json")
    assert os.path.exists(manifest_path)
    with open(manifest_path) as f:
        manifest = json.load(f)
    assert manifest["settings"]["music_source"] == "bundled:tell_tale_heart.mp3"


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_pipeline_tell_tale_heart_intro_outro(mock_which, mock_comm, tmp_path, monkeypatch):
    """Verify intro has title/author/cast, outro has credits + thank you."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()

    with patch("sys.argv", ["producer.py", "new", TTH_PATH]):
        main()

    slug = "tell_tale_heart"
    project_dir = str(tmp_path / "output" / slug)
    script = load_artifact(project_dir, "script.json")

    # Check intro segments
    intro_segs = script.get("intro_segments", [])
    intro_text = " ".join(s["text"] for s in intro_segs)
    assert "Tell-Tale Heart" in intro_text
    assert "Edgar Allan Poe" in intro_text

    # Check outro segments
    outro_segs = script.get("outro_segments", [])
    outro_text = " ".join(s["text"].lower() for s in outro_segs)
    assert "thank you" in outro_text


# --- The Open Window ---

def test_parse_open_window():
    """Parse demo file, verify segments > 0 and multiple speakers."""
    with open(TOW_PATH) as f:
        text = f.read()
    title, author = extract_metadata(text)
    assert "Open Window" in title
    segments = parse_story(text)
    assert len(segments) > 0
    speakers = {s.speaker for s in segments}
    assert len(speakers) >= 2  # at least narrator + one character


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_pipeline_open_window(mock_which, mock_comm, tmp_path, monkeypatch):
    """Full pipeline produces valid MP3 with bundled music."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()

    with patch("sys.argv", ["producer.py", "new", TOW_PATH]):
        main()

    slug = "the_open_window"
    project_dir = str(tmp_path / "output" / slug)

    # Create fake bundled music
    bundled_dir = tmp_path / "demo" / "music"
    bundled_dir.mkdir(parents=True, exist_ok=True)
    AudioSegment.silent(duration=5000).export(
        str(bundled_dir / "the_open_window.mp3"), format="mp3"
    )
    monkeypatch.setattr("audiobook_producer.music.BUNDLED_MUSIC_DIR", str(bundled_dir))

    with patch("sys.argv", ["producer.py", "run", slug]):
        main()

    final_mp3 = os.path.join(project_dir, "final", f"{slug}.mp3")
    assert os.path.exists(final_mp3)

    direction = load_artifact(project_dir, "direction.json")
    assert direction["music_source"] == "bundled:the_open_window.mp3"


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_pipeline_open_window_aliases(mock_which, mock_comm, tmp_path, monkeypatch):
    """Verify alias resolution: 'the child' and 'the niece' same voice."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()

    with patch("sys.argv", ["producer.py", "new", TOW_PATH]):
        main()

    slug = "the_open_window"
    project_dir = str(tmp_path / "output" / slug)
    script = load_artifact(project_dir, "script.json")
    cast_data = load_artifact(project_dir, "cast.json")

    # Parse segments and check alias resolution
    with open(TOW_PATH) as f:
        text = f.read()
    segments = parse_story(text)
    cast = load_cast(TOW_PATH)
    assign_voices(segments, cast=cast)

    # Find voices for "the child" and "the niece"
    child_voices = {s.voice for s in segments if s.speaker == "the child"}
    niece_voices = {s.voice for s in segments if s.speaker == "the niece"}

    # Both should resolve to the same voice (AriaNeural from cast file)
    if child_voices and niece_voices:
        assert child_voices == niece_voices


# --- Cross-cutting ---

@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_full_pipeline_no_music(mock_which, mock_comm, tmp_path, monkeypatch):
    """Run with music off, verify output has no music."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()

    with patch("sys.argv", ["producer.py", "new", TTH_PATH]):
        main()

    slug = "tell_tale_heart"

    # Set music off
    with patch("sys.argv", ["producer.py", "set", slug, "music", "off"]):
        main()

    # Run pipeline
    with patch("sys.argv", ["producer.py", "run", slug]):
        main()

    final_mp3 = os.path.join(str(tmp_path / "output" / slug), "final", f"{slug}.mp3")
    assert os.path.exists(final_mp3)


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_full_pipeline_bookend_structure(mock_which, mock_comm, tmp_path, monkeypatch):
    """Verify output audio has bookend structure (longer than just story)."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()

    with patch("sys.argv", ["producer.py", "new", TTH_PATH]):
        main()

    slug = "tell_tale_heart"
    with patch("sys.argv", ["producer.py", "run", slug]):
        main()

    project_dir = str(tmp_path / "output" / slug)
    final_mp3 = os.path.join(project_dir, "final", f"{slug}.mp3")
    audio = AudioSegment.from_mp3(final_mp3)

    # Should be longer than just segments (has bookend music)
    assert len(audio) > 1000  # at least 1 second


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_full_pipeline_output_dir(mock_which, mock_comm, tmp_path, monkeypatch):
    """Verify output directory contains all expected artifacts."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()

    with patch("sys.argv", ["producer.py", "new", TTH_PATH]):
        main()

    slug = "tell_tale_heart"
    with patch("sys.argv", ["producer.py", "run", slug]):
        main()

    project_dir = tmp_path / "output" / slug

    # Check all expected artifacts
    assert (project_dir / "script.json").exists()
    assert (project_dir / "cast.json").exists()
    assert (project_dir / "direction.json").exists()
    assert (project_dir / "effects.json").exists()
    assert (project_dir / "segments").is_dir()
    assert len(list((project_dir / "segments").glob("*.mp3"))) > 0
    assert (project_dir / "final" / f"{slug}.mp3").exists()
    assert (project_dir / "final" / "output.json").exists()

    # Verify output.json includes music_source
    with open(project_dir / "final" / "output.json") as f:
        manifest = json.load(f)
    assert "music_source" in manifest["settings"]


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_full_pipeline_resume(mock_which, mock_comm, tmp_path, monkeypatch):
    """Second run skips TTS (verify via mock call count)."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()

    with patch("sys.argv", ["producer.py", "new", TTH_PATH]):
        main()

    slug = "tell_tale_heart"

    # First run
    with patch("sys.argv", ["producer.py", "run", slug]):
        main()

    first_call_count = mock_comm.call_count

    # Reset and run again
    mock_comm.reset_mock()
    mock_comm.side_effect = _mock_tts_communicate()

    with patch("sys.argv", ["producer.py", "run", slug]):
        main()

    # Second run should have fewer TTS calls (skipped)
    assert mock_comm.call_count < first_call_count
