"""Voice assignment and bookend script generation."""

import hashlib
import json
import logging
import os

from audiobook_producer.models import Segment
from audiobook_producer.constants import NARRATOR_VOICE, NARRATOR_DIALOGUE_VOICE

logger = logging.getLogger(__name__)

# Hardcoded English voice pool (avoids network call at startup)
VOICE_POOL = [
    "en-US-AriaNeural",
    "en-US-DavisNeural",
    "en-US-TonyNeural",
    "en-US-JennyNeural",
    "en-US-SaraNeural",
    "en-GB-SoniaNeural",
    "en-GB-ThomasNeural",
    "en-AU-NatashaNeural",
    "en-AU-WilliamNeural",
    "en-CA-ClaraNeural",
    "en-CA-LiamNeural",
    "en-IN-NeerjaNeural",
    "en-IN-PrabhatNeural",
    "en-IE-EmilyNeural",
]


def load_cast(story_path: str) -> dict:
    """Load .cast.json sidecar file if it exists.

    Returns cast dict or empty dict if not found or malformed.
    """
    base = os.path.splitext(story_path)[0]
    cast_path = base + ".cast.json"
    if not os.path.exists(cast_path):
        return {}
    try:
        with open(cast_path) as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.warning("Malformed cast file: %s — using hash fallback", cast_path)
        return {}


def _resolve_alias(speaker: str, cast: dict) -> str:
    """Resolve a speaker name through alias mappings in cast data."""
    cast_entries = cast.get("cast", {})
    for primary_name, info in cast_entries.items():
        aliases = info.get("aliases", [])
        if speaker.lower() in [a.lower() for a in aliases]:
            return primary_name.lower()
    return speaker.lower()


def _hash_voice(speaker: str, pool: list[str]) -> str:
    """Deterministic voice assignment via sha256 hash."""
    h = hashlib.sha256(speaker.encode()).hexdigest()
    idx = int(h, 16) % len(pool)
    return pool[idx]


def assign_voices(segments: list[Segment], cast: dict | None = None) -> None:
    """Assign voices to all segments in-place.

    Priority: narrator rules → cast file → hash fallback.
    """
    if cast is None:
        cast = {}

    cast_entries = cast.get("cast", {})
    narrator_info = cast.get("narrator", {})
    narrator_voice = narrator_info.get("voice", NARRATOR_VOICE)
    narrator_dialogue_voice = narrator_info.get("dialogue_voice", NARRATOR_DIALOGUE_VOICE)

    # Build alias resolution map
    # Exclude narrator and cast voices from the hash pool
    used_voices = {NARRATOR_VOICE, NARRATOR_DIALOGUE_VOICE, narrator_voice, narrator_dialogue_voice}
    for info in cast_entries.values():
        if "voice" in info:
            used_voices.add(info["voice"])

    available_pool = [v for v in VOICE_POOL if v not in used_voices]
    if not available_pool:
        available_pool = list(VOICE_POOL)  # fallback to full pool if all taken

    for seg in segments:
        speaker = seg.speaker.lower()

        # 1. Narrator rules
        if speaker == "narrator":
            if seg.type == "dialogue":
                seg.voice = narrator_dialogue_voice
            else:
                seg.voice = narrator_voice
            continue

        # 2. Resolve aliases
        resolved = _resolve_alias(speaker, cast)

        # 3. Cast file lookup
        cast_voice = None
        for name, info in cast_entries.items():
            if name.lower() == resolved:
                cast_voice = info.get("voice")
                break

        if cast_voice:
            seg.voice = cast_voice
        else:
            # 4. Hash fallback
            seg.voice = _hash_voice(resolved, available_pool)


def generate_intro_segments(
    title: str,
    author: str,
    segments: list[Segment],
    cast: dict | None = None,
) -> list[Segment]:
    """Generate intro sequence segments.

    Structure:
      Narrator: "This is {title}, by {author}."
      Narrator: "The characters will be..."
      For each unique character (not narrator, not unknown):
        [Character voice]: "{Speaker Name},"
        Narrator: "{description}, using {voice_name}."
      Narrator: "And your narrator, using {narrator_voice}."
    """
    if cast is None:
        cast = {}

    cast_entries = cast.get("cast", {})
    narrator_info = cast.get("narrator", {})
    narrator_voice = narrator_info.get("voice", NARRATOR_VOICE)

    intro = []

    # Title announcement
    intro.append(Segment(
        type="narration",
        text=f"This is {title}, by {author}.",
        speaker="narrator",
        voice=narrator_voice,
    ))

    # Collect unique characters (excluding narrator and unknown)
    seen = set()
    characters = []
    for seg in segments:
        speaker = seg.speaker.lower()
        if speaker in ("narrator", "unknown") or speaker in seen:
            continue
        seen.add(speaker)
        characters.append((seg.speaker, seg.voice))

    if characters:
        intro.append(Segment(
            type="narration",
            text="The characters will be...",
            speaker="narrator",
            voice=narrator_voice,
        ))

        for speaker_name, voice in characters:
            # Character says their own name
            display_name = speaker_name.title()
            intro.append(Segment(
                type="dialogue",
                text=f"{display_name},",
                speaker=speaker_name.lower(),
                voice=voice,
            ))

            # Narrator describes the character
            description = ""
            for name, info in cast_entries.items():
                if name.lower() == speaker_name.lower():
                    description = info.get("description", "")
                    break

            if description:
                intro.append(Segment(
                    type="narration",
                    text=f"{description}, using {voice}.",
                    speaker="narrator",
                    voice=narrator_voice,
                ))
            else:
                intro.append(Segment(
                    type="narration",
                    text=f"using {voice}.",
                    speaker="narrator",
                    voice=narrator_voice,
                ))

    # Narrator self-intro
    narrator_desc = narrator_info.get("description", "")
    if narrator_desc:
        intro.append(Segment(
            type="narration",
            text=f"And your narrator, {narrator_desc}, using {narrator_voice}.",
            speaker="narrator",
            voice=narrator_voice,
        ))
    else:
        intro.append(Segment(
            type="narration",
            text=f"And your narrator, using {narrator_voice}.",
            speaker="narrator",
            voice=narrator_voice,
        ))

    return intro


def generate_outro_segments(
    title: str,
    author: str,
    segments: list[Segment],
) -> list[Segment]:
    """Generate outro sequence segments.

    Structure:
      Narrator: "This has been a production of {title}, by {author},"
      Narrator: "with {character1}, {character2}, and {character3}."
      Narrator: "Thank you for listening."
    """
    # Get narrator voice from segments
    narrator_voice = NARRATOR_VOICE
    for seg in segments:
        if seg.speaker == "narrator" and seg.type == "narration" and seg.voice:
            narrator_voice = seg.voice
            break

    outro = []

    # Credits
    outro.append(Segment(
        type="narration",
        text=f"This has been a production of {title}, by {author},",
        speaker="narrator",
        voice=narrator_voice,
    ))

    # Character list
    seen = set()
    char_names = []
    for seg in segments:
        speaker = seg.speaker.lower()
        if speaker in ("narrator", "unknown") or speaker in seen:
            continue
        seen.add(speaker)
        char_names.append(seg.speaker.title())

    if char_names:
        if len(char_names) == 1:
            char_list = char_names[0]
        elif len(char_names) == 2:
            char_list = f"{char_names[0]} and {char_names[1]}"
        else:
            char_list = ", ".join(char_names[:-1]) + f", and {char_names[-1]}"
        outro.append(Segment(
            type="narration",
            text=f"with {char_list}.",
            speaker="narrator",
            voice=narrator_voice,
        ))

    # Thank you
    outro.append(Segment(
        type="narration",
        text="Thank you for listening.",
        speaker="narrator",
        voice=narrator_voice,
    ))

    return outro
