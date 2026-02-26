"""Tests for artifacts module (Layer 2b)."""

import json
import os
import time
from unittest.mock import patch, MagicMock

import pytest
from pydub import AudioSegment

from audiobook_producer.models import Segment
from audiobook_producer.artifacts import (
    init_output_dir,
    slug_from_path,
    write_artifact,
    load_artifact,
    invalidate_downstream,
    get_project_status,
    list_projects,
    generate_voice_demos,
    generate_preview,
    split_chapters,
    check_step_fresh,
)


# --- Directory and file management ---

def test_init_output_dir(tmp_path):
    """Creates expected directory tree with all subdirs."""
    story = str(tmp_path / "story.txt")
    project_dir = init_output_dir(story, output_base=str(tmp_path / "output"))
    assert os.path.isdir(project_dir)
    for subdir in ["voice_demos", "segments", "music", "samples", "chapters", "final"]:
        assert os.path.isdir(os.path.join(project_dir, subdir))


def test_init_output_dir_existing(tmp_path):
    """Re-running on existing dir doesn't crash or delete files."""
    story = str(tmp_path / "story.txt")
    project_dir = init_output_dir(story, output_base=str(tmp_path / "output"))
    # Write a file
    marker = os.path.join(project_dir, "segments", "test.txt")
    with open(marker, "w") as f:
        f.write("marker")
    # Re-init
    project_dir2 = init_output_dir(story, output_base=str(tmp_path / "output"))
    assert project_dir == project_dir2
    assert os.path.exists(marker)


def test_slug_from_path():
    """Various filename formats → correct slugs."""
    assert slug_from_path("/path/to/Tell-Tale Heart.txt") == "tell_tale_heart"
    assert slug_from_path("the_open_window.txt") == "the_open_window"
    assert slug_from_path("/a/b/My Story.txt") == "my_story"


def test_write_artifact(tmp_path):
    """Writes valid JSON, round-trips correctly."""
    project_dir = str(tmp_path)
    data = {"key": "value", "num": 42}
    path = write_artifact(project_dir, "test.json", data)
    assert os.path.exists(path)
    with open(path) as f:
        loaded = json.load(f)
    assert loaded == data


def test_write_artifact_nested_data(tmp_path):
    """Handles nested dicts/lists correctly."""
    project_dir = str(tmp_path)
    data = {
        "narrator": {"voice": "en-US-GuyNeural"},
        "characters": {
            "bob": {"voice": "en-US-DavisNeural", "aliases": ["robert"]},
        },
    }
    write_artifact(project_dir, "cast.json", data)
    loaded = load_artifact(project_dir, "cast.json")
    assert loaded == data


# --- Voice demos ---

@patch("audiobook_producer.tts.generate_single")
def test_generate_voice_demos(mock_tts, tmp_path):
    """Mock TTS, verify 2 files per character with dialogue."""
    def write_mp3(text, voice, path):
        AudioSegment.silent(duration=100).export(path, format="mp3")

    mock_tts.side_effect = write_mp3
    project_dir = str(tmp_path)
    os.makedirs(os.path.join(project_dir, "voice_demos"), exist_ok=True)

    cast_data = {
        "narrator": {"voice": "en-US-GuyNeural"},
        "characters": {"bob": {"voice": "en-US-DavisNeural"}},
    }
    segments = [
        Segment(type="narration", text="Dark.", speaker="narrator", voice="en-US-GuyNeural"),
        Segment(type="dialogue", text="Hello.", speaker="bob", voice="en-US-DavisNeural"),
    ]

    paths = generate_voice_demos(project_dir, cast_data, segments)
    # narrator: pangram only (narration doesn't count as dialogue)
    # bob: pangram + story line
    assert len(paths) >= 3


@patch("audiobook_producer.tts.generate_single")
def test_voice_demo_filenames(mock_tts, tmp_path):
    """Verify slug-based naming."""
    def write_mp3(text, voice, path):
        AudioSegment.silent(duration=100).export(path, format="mp3")

    mock_tts.side_effect = write_mp3
    project_dir = str(tmp_path)
    os.makedirs(os.path.join(project_dir, "voice_demos"), exist_ok=True)

    cast_data = {
        "narrator": {"voice": "en-US-GuyNeural"},
        "characters": {"the old man": {"voice": "en-US-DavisNeural"}},
    }
    segments = [
        Segment(type="dialogue", text="Who?", speaker="the old man", voice="en-US-DavisNeural"),
    ]

    paths = generate_voice_demos(project_dir, cast_data, segments)
    filenames = [os.path.basename(p) for p in paths]
    assert "the_old_man_pangram.mp3" in filenames


@patch("audiobook_producer.tts.generate_single")
def test_voice_demo_story_line(mock_tts, tmp_path):
    """Each character's story demo uses their first dialogue line."""
    calls = []
    def write_mp3(text, voice, path):
        calls.append((text, voice, path))
        AudioSegment.silent(duration=100).export(path, format="mp3")

    mock_tts.side_effect = write_mp3
    project_dir = str(tmp_path)
    os.makedirs(os.path.join(project_dir, "voice_demos"), exist_ok=True)

    cast_data = {
        "narrator": {"voice": "en-US-GuyNeural"},
        "characters": {"bob": {"voice": "en-US-DavisNeural"}},
    }
    segments = [
        Segment(type="dialogue", text="First line.", speaker="bob", voice="en-US-DavisNeural"),
        Segment(type="dialogue", text="Second line.", speaker="bob", voice="en-US-DavisNeural"),
    ]

    generate_voice_demos(project_dir, cast_data, segments)
    story_calls = [c for c in calls if "_story.mp3" in os.path.basename(c[2])]
    bob_story = [c for c in story_calls if "bob" in os.path.basename(c[2])]
    assert len(bob_story) == 1
    assert bob_story[0][0] == "First line."


@patch("audiobook_producer.tts.generate_single")
def test_voice_demo_no_dialogue(mock_tts, tmp_path):
    """Character with no dialogue → pangram only, no crash."""
    def write_mp3(text, voice, path):
        AudioSegment.silent(duration=100).export(path, format="mp3")

    mock_tts.side_effect = write_mp3
    project_dir = str(tmp_path)
    os.makedirs(os.path.join(project_dir, "voice_demos"), exist_ok=True)

    cast_data = {
        "narrator": {"voice": "en-US-GuyNeural"},
        "characters": {"silent_char": {"voice": "en-US-DavisNeural"}},
    }
    segments = [
        Segment(type="narration", text="Story text.", speaker="narrator", voice="en-US-GuyNeural"),
    ]

    paths = generate_voice_demos(project_dir, cast_data, segments)
    filenames = [os.path.basename(p) for p in paths]
    assert "silent_char_pangram.mp3" in filenames
    assert "silent_char_story.mp3" not in filenames


# --- Preview and chapters ---

def test_generate_preview(tmp_path):
    """Output file exists, duration close to target."""
    project_dir = str(tmp_path)
    os.makedirs(os.path.join(project_dir, "samples"), exist_ok=True)
    audio = AudioSegment.silent(duration=120000)  # 2 minutes
    path = generate_preview(project_dir, audio)
    assert os.path.exists(path)
    preview = AudioSegment.from_mp3(path)
    assert abs(len(preview) - 60000) < 500


def test_generate_preview_short_story(tmp_path):
    """Story shorter than preview duration → preview = full length."""
    project_dir = str(tmp_path)
    os.makedirs(os.path.join(project_dir, "samples"), exist_ok=True)
    audio = AudioSegment.silent(duration=30000)  # 30 seconds
    path = generate_preview(project_dir, audio)
    preview = AudioSegment.from_mp3(path)
    assert abs(len(preview) - 30000) < 500


def test_split_chapters_short_story(tmp_path):
    """<50 segments → no chapter files."""
    project_dir = str(tmp_path)
    audio = AudioSegment.silent(duration=60000)
    segments = [Segment(type="narration", text="x", speaker="narrator") for _ in range(30)]
    paths = split_chapters(project_dir, audio, segments)
    assert paths == []


def test_split_chapters_long_story(tmp_path):
    """>50 segments → multiple chapter MP3s."""
    project_dir = str(tmp_path)
    os.makedirs(os.path.join(project_dir, "chapters"), exist_ok=True)
    audio = AudioSegment.silent(duration=25 * 60 * 1000)  # 25 minutes
    segments = [Segment(type="narration", text="x", speaker="narrator") for _ in range(60)]
    paths = split_chapters(project_dir, audio, segments)
    assert len(paths) >= 2
    for p in paths:
        assert os.path.exists(p)


# --- Resumability ---

def test_check_step_fresh_no_output(tmp_path):
    """No output file → returns False."""
    assert check_step_fresh(str(tmp_path), "parse") is False


def test_check_step_fresh_stale(tmp_path):
    """Output exists but input is newer → returns False."""
    project_dir = str(tmp_path)
    # Create output first
    output = os.path.join(project_dir, "script.json")
    with open(output, "w") as f:
        json.dump({}, f)
    time.sleep(0.05)
    # Create newer input
    input_file = os.path.join(project_dir, "source.txt")
    with open(input_file, "w") as f:
        f.write("newer")
    assert check_step_fresh(project_dir, "parse", [input_file]) is False


def test_check_step_fresh_current(tmp_path):
    """Output exists and input is older → returns True."""
    project_dir = str(tmp_path)
    # Create input first
    input_file = os.path.join(project_dir, "source.txt")
    with open(input_file, "w") as f:
        f.write("old")
    time.sleep(0.05)
    # Create output after
    output = os.path.join(project_dir, "script.json")
    with open(output, "w") as f:
        json.dump({}, f)
    assert check_step_fresh(project_dir, "parse", [input_file]) is True


def test_check_step_fresh_multiple_inputs(tmp_path):
    """Multiple inputs — editing one invalidates the step."""
    project_dir = str(tmp_path)
    input1 = os.path.join(project_dir, "script.json")
    input2 = os.path.join(project_dir, "story.cast.json")
    with open(input1, "w") as f:
        json.dump({}, f)
    with open(input2, "w") as f:
        json.dump({}, f)
    time.sleep(0.05)
    output = os.path.join(project_dir, "cast.json")
    with open(output, "w") as f:
        json.dump({}, f)
    # Both inputs older → fresh
    assert check_step_fresh(project_dir, "voices", [input1, input2]) is True
    # Touch one input to make it newer
    time.sleep(0.05)
    with open(input2, "w") as f:
        json.dump({"updated": True}, f)
    assert check_step_fresh(project_dir, "voices", [input1, input2]) is False


# --- Loading and invalidation ---

def test_load_artifact(tmp_path):
    """Round-trips with write_artifact."""
    data = {"test": "data"}
    write_artifact(str(tmp_path), "test.json", data)
    loaded = load_artifact(str(tmp_path), "test.json")
    assert loaded == data


def test_load_artifact_missing(tmp_path):
    """Returns None for non-existent file."""
    result = load_artifact(str(tmp_path), "nonexistent.json")
    assert result is None


def test_invalidate_voice_change(tmp_path):
    """Deletes voice_demos/, segments/, samples/, final/."""
    project_dir = str(tmp_path)
    for d in ["voice_demos", "segments", "samples", "final"]:
        path = os.path.join(project_dir, d)
        os.makedirs(path, exist_ok=True)
        # Put a file in each
        with open(os.path.join(path, "test.txt"), "w") as f:
            f.write("test")

    deleted = invalidate_downstream(project_dir, "voice")
    assert set(deleted) == {"voice_demos", "segments", "samples", "final"}
    # Dirs should exist but be empty
    for d in deleted:
        path = os.path.join(project_dir, d)
        assert os.path.isdir(path)
        assert os.listdir(path) == []


def test_invalidate_music_toggle(tmp_path):
    """Deletes music/, samples/, final/."""
    project_dir = str(tmp_path)
    for d in ["music", "samples", "final"]:
        path = os.path.join(project_dir, d)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "test.txt"), "w") as f:
            f.write("test")

    deleted = invalidate_downstream(project_dir, "music")
    assert "music" in deleted
    assert "samples" in deleted
    assert "final" in deleted


def test_invalidate_reverb_change(tmp_path):
    """Deletes segments/, samples/, final/."""
    project_dir = str(tmp_path)
    for d in ["segments", "samples", "final"]:
        path = os.path.join(project_dir, d)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "test.txt"), "w") as f:
            f.write("test")

    deleted = invalidate_downstream(project_dir, "reverb")
    assert set(deleted) == {"segments", "samples", "final"}


def test_invalidate_nonexistent_dirs(tmp_path):
    """Doesn't crash on missing subdirs."""
    project_dir = str(tmp_path)
    deleted = invalidate_downstream(project_dir, "voice")
    assert deleted == []


# --- Project status and listing ---

def test_get_project_status_empty(tmp_path):
    """New project → all steps pending."""
    project_dir = str(tmp_path)
    status = get_project_status(project_dir)
    assert status["parse"]["state"] == "pending"
    assert status["voices"]["state"] == "pending"
    assert status["tts"]["state"] == "pending"


def test_get_project_status_partial(tmp_path):
    """Some artifacts exist → mixed done/pending."""
    project_dir = str(tmp_path)
    # Write script.json
    script = {"segments": [{"type": "narration", "text": "x", "speaker": "narrator"}]}
    with open(os.path.join(project_dir, "script.json"), "w") as f:
        json.dump(script, f)
    status = get_project_status(project_dir)
    assert status["parse"]["state"] == "done"
    assert status["parse"]["segments"] == 1
    assert status["tts"]["state"] == "pending"


def test_list_projects(tmp_path):
    """Returns sorted list of project slugs."""
    output_base = str(tmp_path)
    # Create two projects with script.json
    for name in ["beta_story", "alpha_story"]:
        project = os.path.join(output_base, name)
        os.makedirs(project)
        with open(os.path.join(project, "script.json"), "w") as f:
            json.dump({}, f)
    # Create a dir without script.json
    os.makedirs(os.path.join(output_base, "not_a_project"))

    result = list_projects(output_base)
    assert result == ["alpha_story", "beta_story"]


def test_list_projects_empty(tmp_path):
    """Empty output dir → empty list."""
    result = list_projects(str(tmp_path))
    assert result == []
