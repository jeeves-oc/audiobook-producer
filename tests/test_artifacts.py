"""Tests for artifacts module (Layer 2b) — stub."""

import pytest

from audiobook_producer.artifacts import init_output_dir


def test_init_output_dir(tmp_path):
    """Creates expected directory tree."""
    project_dir = init_output_dir(str(tmp_path / "story.txt"), output_base=str(tmp_path / "output"))
    assert project_dir  # placeholder — full tests added in Layer 2b
