"""Data models for audiobook production."""

from dataclasses import dataclass


@dataclass
class Segment:
    type: str          # "narration" or "dialogue"
    text: str
    speaker: str       # "narrator", character name, or "unknown"
    voice: str = ""    # populated by assign_voices()
