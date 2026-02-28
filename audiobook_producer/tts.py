"""TTS generation via edge-tts with retry logic."""

import asyncio
import os
import time

import edge_tts

from audiobook_producer.constants import TTS_RETRY_COUNT, TTS_RETRY_BASE_DELAY, TTS_RATE
from audiobook_producer.models import Segment


def generate_single(text: str, voice: str, output_path: str, rate: str = TTS_RATE) -> None:
    """Generate a single TTS clip with retry logic.

    Sync wrapper around edge_tts.Communicate(). Retries on network errors,
    HTTP errors, or 0-byte output files. Rate is a relative string like "-10%".
    """
    last_error = None
    for attempt in range(TTS_RETRY_COUNT):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            asyncio.run(communicate.save(output_path))

            # Validate output: 0-byte file counts as failure
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return

            # 0-byte file — treat as failure
            last_error = Exception(f"TTS produced 0-byte file for: {text[:50]}...")
        except Exception as e:
            last_error = e

        # Exponential backoff
        if attempt < TTS_RETRY_COUNT - 1:
            delay = TTS_RETRY_BASE_DELAY * (2 ** attempt)
            time.sleep(delay)

    raise last_error


def _segment_filename(index: int, segment: Segment) -> str:
    """Generate filename for a TTS segment."""
    # Determine prefix from segment position context
    speaker_slug = segment.speaker.replace(" ", "_").lower()
    return f"{index:03d}_{segment.type}_{speaker_slug}.mp3"


def generate_tts(segments: list[Segment], output_dir: str, rate: str = TTS_RATE) -> list[str]:
    """Generate TTS for all segments.

    Returns list of output file paths. Prints progress counter.
    """
    total = len(segments)
    paths = []

    for i, seg in enumerate(segments):
        filename = _segment_filename(i, seg)
        output_path = os.path.join(output_dir, filename)

        # Skip if already exists (resumability)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"  [skip] Segment {i + 1}/{total}: {filename}")
            paths.append(output_path)
            continue

        print(f"  Generating segment {i + 1}/{total}: {filename}")
        generate_single(seg.text, seg.voice, output_path, rate=rate)
        paths.append(output_path)

    return paths
