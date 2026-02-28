"""Tests for TTS module (Layer 1c)."""

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from pydub import AudioSegment

from audiobook_producer.models import Segment
from audiobook_producer.tts import generate_single, generate_tts


def _make_mock_communicate(tiny_mp3_path):
    """Create a mock edge_tts.Communicate that writes a tiny MP3."""
    def factory(text, voice, **kwargs):
        mock = MagicMock()
        async def save(path):
            silence = AudioSegment.silent(duration=100)
            silence.export(path, format="mp3")
        mock.save = save
        return mock
    return factory


@patch("audiobook_producer.tts.edge_tts.Communicate")
def test_tts_generate_single(mock_comm, tmp_path):
    """Single TTS file created at specified path."""
    output = tmp_path / "test.mp3"
    mock_comm.side_effect = _make_mock_communicate(None)
    generate_single("Hello world", "en-US-GuyNeural", str(output))
    assert output.exists()
    assert output.stat().st_size > 0


@patch("audiobook_producer.tts.edge_tts.Communicate")
def test_tts_generate_single_retry(mock_comm, tmp_path):
    """Retry works when first attempt fails."""
    output = tmp_path / "test.mp3"
    call_count = 0

    def fail_then_succeed(text, voice, **kwargs):
        nonlocal call_count
        call_count += 1
        mock = MagicMock()
        if call_count == 1:
            async def fail_save(path):
                raise Exception("Network error")
            mock.save = fail_save
        else:
            async def ok_save(path):
                AudioSegment.silent(duration=100).export(path, format="mp3")
            mock.save = ok_save
        return mock

    mock_comm.side_effect = fail_then_succeed
    generate_single("Hello", "en-US-GuyNeural", str(output))
    assert output.exists()
    assert call_count == 2


@patch("audiobook_producer.tts.edge_tts.Communicate")
def test_tts_generates_files(mock_comm, tmp_path):
    """N files created in output directory."""
    mock_comm.side_effect = _make_mock_communicate(None)
    segments = [
        Segment(type="narration", text="Dark.", speaker="narrator", voice="en-US-GuyNeural"),
        Segment(type="dialogue", text="Who?", speaker="old man", voice="en-US-DavisNeural"),
    ]
    seg_dir = tmp_path / "segments"
    seg_dir.mkdir()
    generate_tts(segments, str(seg_dir))
    mp3s = list(seg_dir.glob("*.mp3"))
    assert len(mp3s) == 2


@patch("audiobook_producer.tts.edge_tts.Communicate")
def test_tts_retry_exhausted(mock_comm, tmp_path):
    """Raises after all retries exhausted."""
    def always_fail(text, voice, **kwargs):
        mock = MagicMock()
        async def fail_save(path):
            raise Exception("Permanent failure")
        mock.save = fail_save
        return mock

    mock_comm.side_effect = always_fail
    output = tmp_path / "fail.mp3"
    with pytest.raises(Exception, match="Permanent failure"):
        generate_single("Hello", "en-US-GuyNeural", str(output))


@patch("audiobook_producer.tts.edge_tts.Communicate")
def test_tts_validates_output_size(mock_comm, tmp_path):
    """0-byte output treated as failure."""
    call_count_outer = [0]

    def write_empty(text, voice, **kwargs):
        mock = MagicMock()
        async def save(path):
            call_count_outer[0] += 1
            if call_count_outer[0] <= 2:
                open(path, "w").close()  # 0-byte file
            else:
                AudioSegment.silent(duration=100).export(path, format="mp3")
        mock.save = save
        return mock

    mock_comm.side_effect = write_empty
    output = tmp_path / "test.mp3"
    generate_single("Hello", "en-US-GuyNeural", str(output))
    assert output.stat().st_size > 0


@patch("audiobook_producer.tts.edge_tts.Communicate")
def test_tts_progress_output(mock_comm, tmp_path, capsys):
    """Segment counter appears in stdout."""
    mock_comm.side_effect = _make_mock_communicate(None)
    segments = [
        Segment(type="narration", text="Line one.", speaker="narrator", voice="en-US-GuyNeural"),
        Segment(type="narration", text="Line two.", speaker="narrator", voice="en-US-GuyNeural"),
    ]
    seg_dir = tmp_path / "segments"
    seg_dir.mkdir()
    generate_tts(segments, str(seg_dir))
    captured = capsys.readouterr()
    assert "1/" in captured.out or "2/" in captured.out
