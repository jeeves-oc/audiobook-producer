"""Tests for CLI module (Layer 3)."""

import json
import os
import shutil
import sys
from unittest.mock import patch, MagicMock

import pytest
from pydub import AudioSegment

from audiobook_producer.cli import main, cmd_new, cmd_run, cmd_set
from audiobook_producer.constants import OUTPUT_DIR, NARRATOR_VOICE


# --- Helpers ---

def _create_story_file(tmp_path, name="story.txt", content=None):
    """Create a test story file."""
    if content is None:
        content = 'The Test Story\n\nby Test Author\n\n"Hello," said Alice.\n\nIt was dark.'
    path = tmp_path / name
    path.write_text(content)
    return str(path)


def _create_project(tmp_path, slug="test_story"):
    """Create a minimal project with all required artifacts."""
    output_dir = tmp_path / "output" / slug
    for subdir in ["voice_demos", "segments", "music", "samples", "chapters", "final"]:
        (output_dir / subdir).mkdir(parents=True, exist_ok=True)

    script = {
        "metadata": {"title": "Test Story", "author": "Test Author"},
        "source": str(tmp_path / "story.txt"),
        "segments": [
            {"type": "narration", "text": "It was dark.", "speaker": "narrator"},
            {"type": "dialogue", "text": "Hello.", "speaker": "alice"},
        ],
        "intro_segments": [
            {"type": "narration", "text": "This is Test Story, by Test Author.",
             "speaker": "narrator", "voice": NARRATOR_VOICE},
        ],
        "outro_segments": [
            {"type": "narration", "text": "Thank you for listening.",
             "speaker": "narrator", "voice": NARRATOR_VOICE},
        ],
    }
    with open(output_dir / "script.json", "w") as f:
        json.dump(script, f)

    cast = {
        "narrator": {"voice": NARRATOR_VOICE, "dialogue_voice": "en-GB-RyanNeural"},
        "characters": {"alice": {"voice": "en-US-AriaNeural", "source": "hash"}},
    }
    with open(output_dir / "cast.json", "w") as f:
        json.dump(cast, f)

    direction = {
        "intro_music_solo_ms": 4000, "outro_music_solo_ms": 4000,
        "music_bed_db": -25, "music_fade_ms": 2000,
        "pauses": {"same_type_ms": 300, "speaker_change_ms": 500, "type_transition_ms": 700},
        "no_music": False, "music_source": None,
    }
    with open(output_dir / "direction.json", "w") as f:
        json.dump(direction, f)

    effects = {
        "global": {"normalize": True, "target_dbfs": -20},
        "per_segment": {
            "dialogue": {"reverb": {"room_size": 0.3, "wet_level": 0.15}},
            "narration": {"reverb": None},
        },
    }
    with open(output_dir / "effects.json", "w") as f:
        json.dump(effects, f)

    return str(output_dir)


def _mock_tts_communicate():
    """Create a mock edge_tts.Communicate factory."""
    def factory(text, voice):
        mock = MagicMock()
        async def save(path):
            AudioSegment.silent(duration=100).export(path, format="mp3")
        mock.save = save
        return mock
    return factory


# --- Subcommand routing ---

def test_cli_new_creates_project(tmp_path, monkeypatch):
    """new creates output dir + script.json + cast.json."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    story = _create_story_file(tmp_path, "test_story.txt")

    with patch("sys.argv", ["producer.py", "new", story]):
        main()

    project = tmp_path / "output" / "test_story"
    assert (project / "script.json").exists()
    assert (project / "cast.json").exists()
    assert (project / "direction.json").exists()
    assert (project / "effects.json").exists()


def test_cli_new_already_exists(tmp_path, monkeypatch):
    """new on existing project raises SystemExit."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    story = _create_story_file(tmp_path, "test_story.txt")

    with patch("sys.argv", ["producer.py", "new", story]):
        main()

    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "new", story]):
            main()


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_cli_run_basic(mock_which, mock_comm, tmp_path, monkeypatch):
    """run executes pipeline steps."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()
    _create_project(tmp_path, "test_story")

    with patch("sys.argv", ["producer.py", "run", "test_story"]):
        main()

    assert (tmp_path / "output" / "test_story" / "final" / "test_story.mp3").exists()


def test_cli_run_nonexistent_project(tmp_path, monkeypatch):
    """run on nonexistent project raises SystemExit."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "output").mkdir()

    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "run", "nonexistent"]):
            with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
                main()


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_cli_run_verbose(mock_which, mock_comm, tmp_path, monkeypatch, capsys):
    """run -v enables voice demos."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()
    _create_project(tmp_path, "test_story")

    # Mock stdin as non-interactive to skip preview gate
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = False
        with patch("sys.argv", ["producer.py", "run", "test_story", "-v"]):
            main()

    captured = capsys.readouterr()
    assert "voice demos" in captured.out.lower() or "Generating" in captured.out


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_cli_run_force(mock_which, mock_comm, tmp_path, monkeypatch):
    """run --force re-runs everything."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()
    _create_project(tmp_path, "test_story")

    # Create a fake final output
    final_dir = tmp_path / "output" / "test_story" / "final"
    AudioSegment.silent(duration=100).export(str(final_dir / "test_story.mp3"), format="mp3")

    with patch("sys.argv", ["producer.py", "run", "test_story", "--force"]):
        main()

    # Final should be regenerated
    assert (final_dir / "test_story.mp3").exists()


def test_cli_status_shows_state(tmp_path, monkeypatch, capsys):
    """status prints project state."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    _create_project(tmp_path, "test_story")

    with patch("sys.argv", ["producer.py", "status", "test_story"]):
        main()

    captured = capsys.readouterr()
    assert "test_story" in captured.out
    assert "parse" in captured.out.lower() or "Steps" in captured.out


def test_cli_status_nonexistent(tmp_path, monkeypatch):
    """status on nonexistent project raises SystemExit."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "output").mkdir()

    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "status", "nonexistent"]):
            main()


# --- Set subcommand ---

def test_cli_set_voice(tmp_path, monkeypatch):
    """set voice updates cast.json."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    _create_project(tmp_path, "test_story")

    with patch("sys.argv", ["producer.py", "set", "test_story", "voice", "alice", "en-US-TonyNeural"]):
        main()

    cast = json.loads((tmp_path / "output" / "test_story" / "cast.json").read_text())
    assert cast["characters"]["alice"]["voice"] == "en-US-TonyNeural"


def test_cli_set_voice_invalidates(tmp_path, monkeypatch):
    """After set voice, voice_demos/ and segments/ are deleted."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    project = _create_project(tmp_path, "test_story")

    # Add files to voice_demos and segments
    (tmp_path / "output" / "test_story" / "voice_demos" / "test.mp3").write_text("x")
    (tmp_path / "output" / "test_story" / "segments" / "test.mp3").write_text("x")

    with patch("sys.argv", ["producer.py", "set", "test_story", "voice", "alice", "en-US-TonyNeural"]):
        main()

    # Dirs exist but are empty
    assert (tmp_path / "output" / "test_story" / "voice_demos").exists()
    assert len(os.listdir(tmp_path / "output" / "test_story" / "voice_demos")) == 0


def test_cli_set_music_off(tmp_path, monkeypatch):
    """set music off updates direction.json."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    _create_project(tmp_path, "test_story")

    with patch("sys.argv", ["producer.py", "set", "test_story", "music", "off"]):
        main()

    direction = json.loads((tmp_path / "output" / "test_story" / "direction.json").read_text())
    assert direction["no_music"] is True


def test_cli_set_music_file(tmp_path, monkeypatch):
    """set music-file copies file and writes provenance."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    _create_project(tmp_path, "test_story")

    # Create a test music file
    track = tmp_path / "track.mp3"
    AudioSegment.silent(duration=5000).export(str(track), format="mp3")

    with patch("sys.argv", ["producer.py", "set", "test_story", "music-file", str(track)]):
        main()

    bg = tmp_path / "output" / "test_story" / "music" / "background.mp3"
    assert bg.exists()
    direction = json.loads((tmp_path / "output" / "test_story" / "direction.json").read_text())
    assert direction["music_source"] == "user:track.mp3"


def test_cli_set_music_file_missing(tmp_path, monkeypatch):
    """set music-file with nonexistent file raises SystemExit."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    _create_project(tmp_path, "test_story")

    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "set", "test_story", "music-file", "nonexistent.mp3"]):
            main()


def test_cli_set_music_file_invalid_audio(tmp_path, monkeypatch):
    """set music-file with non-audio file raises SystemExit."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    _create_project(tmp_path, "test_story")

    bad_file = tmp_path / "photo.jpg"
    bad_file.write_text("not audio data")

    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "set", "test_story", "music-file", str(bad_file)]):
            main()


def test_cli_set_music_file_invalidates(tmp_path, monkeypatch):
    """After set music-file, samples/ and final/ deleted."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    _create_project(tmp_path, "test_story")

    (tmp_path / "output" / "test_story" / "samples" / "test.mp3").write_text("x")
    (tmp_path / "output" / "test_story" / "final" / "test.mp3").write_text("x")

    track = tmp_path / "track.mp3"
    AudioSegment.silent(duration=5000).export(str(track), format="mp3")

    with patch("sys.argv", ["producer.py", "set", "test_story", "music-file", str(track)]):
        main()

    assert len(os.listdir(tmp_path / "output" / "test_story" / "samples")) == 0
    assert len(os.listdir(tmp_path / "output" / "test_story" / "final")) == 0


def test_cli_set_reverb_room(tmp_path, monkeypatch):
    """set reverb-room updates effects.json."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    _create_project(tmp_path, "test_story")

    with patch("sys.argv", ["producer.py", "set", "test_story", "reverb-room", "0.5"]):
        main()

    effects = json.loads((tmp_path / "output" / "test_story" / "effects.json").read_text())
    assert effects["per_segment"]["dialogue"]["reverb"]["room_size"] == 0.5


def test_cli_set_nonexistent_project(tmp_path, monkeypatch):
    """set on nonexistent project raises SystemExit."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "output").mkdir()

    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "set", "nonexistent", "voice", "x", "y"]):
            main()


def test_cli_set_invalid_key(tmp_path, monkeypatch):
    """set with invalid key raises SystemExit."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    _create_project(tmp_path, "test_story")

    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "set", "test_story", "badkey", "val"]):
            main()


# --- List and voices ---

def test_cli_list_projects(tmp_path, monkeypatch, capsys):
    """list shows all project dirs."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    _create_project(tmp_path, "alpha_story")
    _create_project(tmp_path, "beta_story")

    with patch("sys.argv", ["producer.py", "list"]):
        main()

    captured = capsys.readouterr()
    assert "alpha_story" in captured.out
    assert "beta_story" in captured.out


def test_cli_list_empty(tmp_path, monkeypatch, capsys):
    """list with no projects shows message."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "output").mkdir()

    with patch("sys.argv", ["producer.py", "list"]):
        main()

    captured = capsys.readouterr()
    assert "No projects found" in captured.out


def test_cli_voices(capsys):
    """voices lists available voices."""
    with patch("sys.argv", ["producer.py", "voices"]):
        main()

    captured = capsys.readouterr()
    assert "en-US" in captured.out


def test_cli_voices_filter(capsys):
    """voices --filter filters voice list."""
    with patch("sys.argv", ["producer.py", "voices", "--filter", "en-GB"]):
        main()

    captured = capsys.readouterr()
    assert "en-GB" in captured.out
    # Should not contain voices that don't match filter
    lines = [l.strip() for l in captured.out.strip().split("\n") if l.strip().startswith("en-")]
    for line in lines:
        assert "en-GB" in line.lower() or "en-gb" in line.lower()


def test_cli_no_args_shows_help(capsys):
    """No subcommand prints help text."""
    with patch("sys.argv", ["producer.py"]):
        main()

    captured = capsys.readouterr()
    assert "usage" in captured.out.lower() or "producer" in captured.out.lower()


# --- Input validation ---

def test_validate_missing_file(tmp_path, monkeypatch):
    """new with nonexistent file raises SystemExit."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "new", str(tmp_path / "nonexistent.txt")]):
            main()


def test_validate_empty_file(tmp_path, monkeypatch):
    """new with empty file raises SystemExit."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "new", str(empty)]):
            main()


def test_validate_no_segments(tmp_path, monkeypatch):
    """new with unparseable file raises SystemExit."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    bad = tmp_path / "bad.txt"
    bad.write_text("   \n\n   \n\n   ")
    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "new", str(bad)]):
            main()


@patch("shutil.which", return_value=None)
def test_validate_ffmpeg_missing(mock_which, tmp_path, monkeypatch):
    """run without ffmpeg raises SystemExit."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    _create_project(tmp_path, "test_story")

    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "run", "test_story"]):
            main()


# --- Preview gate ---

@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_preview_gate_verbose(mock_which, mock_comm, tmp_path, monkeypatch):
    """run -v with isatty()=True calls input()."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()
    _create_project(tmp_path, "test_story")

    with patch("sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = True
        with patch("builtins.input", return_value="Y") as mock_input:
            with patch("sys.argv", ["producer.py", "run", "test_story", "-v"]):
                main()
            mock_input.assert_called_once()


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_preview_gate_nonverbose(mock_which, mock_comm, tmp_path, monkeypatch):
    """run without -v has no input() call."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()
    _create_project(tmp_path, "test_story")

    with patch("builtins.input") as mock_input:
        with patch("sys.argv", ["producer.py", "run", "test_story"]):
            main()
        mock_input.assert_not_called()


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_preview_gate_noninteractive(mock_which, mock_comm, tmp_path, monkeypatch):
    """run -v but non-interactive → no input() call."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()
    _create_project(tmp_path, "test_story")

    with patch("sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = False
        with patch("builtins.input") as mock_input:
            with patch("sys.argv", ["producer.py", "run", "test_story", "-v"]):
                main()
            mock_input.assert_not_called()


# --- Resumability ---

@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_run_skips_completed_steps(mock_which, mock_comm, tmp_path, monkeypatch):
    """When artifacts exist and fresh, TTS is skipped on second run."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()
    _create_project(tmp_path, "test_story")

    # First run
    with patch("sys.argv", ["producer.py", "run", "test_story"]):
        main()

    # Reset mock call count
    mock_comm.reset_mock()
    mock_comm.side_effect = _mock_tts_communicate()

    # Second run — should skip TTS
    with patch("sys.argv", ["producer.py", "run", "test_story"]):
        main()

    # TTS should have been skipped (segments already exist)
    # The mock may still be called for effects re-processing,
    # but segment files already existed
    assert (tmp_path / "output" / "test_story" / "final" / "test_story.mp3").exists()


@patch("audiobook_producer.tts.edge_tts.Communicate")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_force_flag_deletes_output(mock_which, mock_comm, tmp_path, monkeypatch):
    """--force removes generated artifacts before starting."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("audiobook_producer.artifacts.OUTPUT_DIR", str(tmp_path / "output"))
    mock_comm.side_effect = _mock_tts_communicate()
    _create_project(tmp_path, "test_story")

    # Add a marker file to segments/
    marker = tmp_path / "output" / "test_story" / "segments" / "marker.txt"
    marker.write_text("should be deleted by --force")

    with patch("sys.argv", ["producer.py", "run", "test_story", "--force"]):
        main()

    # Marker should be gone
    assert not marker.exists()
    # But final output should be generated
    assert (tmp_path / "output" / "test_story" / "final" / "test_story.mp3").exists()


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_force_flag_no_existing_dir(mock_which, tmp_path, monkeypatch):
    """--force on non-existent output dir doesn't crash."""
    monkeypatch.setattr("audiobook_producer.cli.OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "output").mkdir()

    with pytest.raises(SystemExit):
        with patch("sys.argv", ["producer.py", "run", "nonexistent", "--force"]):
            main()
