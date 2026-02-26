"""Tests for parser module (Layer 1a)."""

import pytest

from audiobook_producer.parser import parse_story, extract_metadata
from audiobook_producer.models import Segment
from audiobook_producer.constants import SEGMENT_SPLIT_THRESHOLD


def test_extract_metadata():
    """Title and author extracted from header."""
    text = "The Tell-Tale Heart\n\nby Edgar Allan Poe\n\nTRUE! -- nervous..."
    title, author = extract_metadata(text)
    assert title == "The Tell-Tale Heart"
    assert author == "Edgar Allan Poe"


def test_extract_metadata_fallback():
    """No 'by' line falls back to defaults."""
    text = "Just a random paragraph with no clear metadata."
    title, author = extract_metadata(text)
    assert title == "Untitled"
    assert author == "Unknown Author"


def test_parse_narration_only():
    """Plain paragraph becomes narration segment."""
    text = "Title\n\nby Author\n\nIt was a dark and stormy night."
    segments = parse_story(text)
    assert len(segments) >= 1
    assert segments[0].type == "narration"
    assert segments[0].speaker == "narrator"


def test_parse_dialogue():
    """Dialogue with post-attribution extracts speaker."""
    text = 'Title\n\nby Author\n\n"Hello," said John.'
    segments = parse_story(text)
    dialogue = [s for s in segments if s.type == "dialogue"]
    assert len(dialogue) >= 1
    assert dialogue[0].speaker.lower() == "john"
    assert "Hello" in dialogue[0].text


def test_parse_mixed_paragraph():
    """Narration + dialogue in one paragraph produces multiple segments."""
    text = 'Title\n\nby Author\n\nHe walked to the door. "Who goes there?" asked the guard. The night was cold.'
    segments = parse_story(text)
    types = [s.type for s in segments]
    assert "narration" in types
    assert "dialogue" in types


def test_parse_first_person():
    """First-person attribution maps to narrator."""
    text = 'Title\n\nby Author\n\n"Stop!" I cried.'
    segments = parse_story(text)
    dialogue = [s for s in segments if s.type == "dialogue"]
    assert len(dialogue) >= 1
    assert dialogue[0].speaker == "narrator"


def test_parse_no_attribution():
    """Dialogue with no attribution gets speaker='unknown'."""
    text = 'Title\n\nby Author\n\n"Hello."'
    segments = parse_story(text)
    dialogue = [s for s in segments if s.type == "dialogue"]
    assert len(dialogue) >= 1
    assert dialogue[0].speaker == "unknown"


def test_parse_long_segment_split():
    """>500 char segment splits at sentence boundary."""
    long_text = ". ".join(["This is a sentence"] * 40) + "."
    text = f"Title\n\nby Author\n\n{long_text}"
    segments = parse_story(text)
    for seg in segments:
        assert len(seg.text) <= SEGMENT_SPLIT_THRESHOLD + 100  # some tolerance


def test_parse_empty_paragraphs_skipped():
    """Whitespace-only paragraphs produce no segments."""
    text = "Title\n\nby Author\n\n\n\n   \n\nActual content here."
    segments = parse_story(text)
    for seg in segments:
        assert seg.text.strip() != ""


def test_parse_pre_attribution():
    """Pre-attribution: speaker before the quote."""
    text = 'Title\n\nby Author\n\nthe old man cried out, "Who\'s there?"'
    segments = parse_story(text)
    dialogue = [s for s in segments if s.type == "dialogue"]
    assert len(dialogue) >= 1
    assert "old man" in dialogue[0].speaker.lower()


def test_parse_variety_of_verbs():
    """Various speech verbs extract speakers correctly."""
    text = (
        'Title\n\nby Author\n\n'
        '"Come in," whispered Alice.\n\n'
        '"No!" exclaimed Bob.\n\n'
        '"Perhaps," pursued Clara.\n\n'
        '"Indeed," announced David.\n\n'
        '"Fine," admitted Eve.'
    )
    segments = parse_story(text)
    dialogue = [s for s in segments if s.type == "dialogue"]
    speakers = {s.speaker.lower() for s in dialogue}
    assert "alice" in speakers
    assert "bob" in speakers
    assert "clara" in speakers
    assert "david" in speakers
    assert "eve" in speakers
