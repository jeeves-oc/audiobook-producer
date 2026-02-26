"""Music source resolution with bundled CC0, user-provided, and procedural fallback."""

import json
import os
import shutil

import numpy as np
from pydub import AudioSegment

from audiobook_producer.constants import MUSIC_LOOP_SECONDS, MUSIC_FADE_MS, BUNDLED_MUSIC_DIR


def generate_procedural_music() -> AudioSegment:
    """Generate a procedural ambient drone using numpy sine waves.

    A-minor chord (A2 + C3 + E3) with slow amplitude modulation
    for an atmospheric, ambient feel.
    """
    sample_rate = 44100
    duration = MUSIC_LOOP_SECONDS
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

    # A-minor chord: A2 (110 Hz), C3 (130.81 Hz), E3 (164.81 Hz)
    a2 = np.sin(2 * np.pi * 110.0 * t) * 0.3
    c3 = np.sin(2 * np.pi * 130.81 * t) * 0.25
    e3 = np.sin(2 * np.pi * 164.81 * t) * 0.2

    # Slow amplitude modulation for movement
    mod = 0.7 + 0.3 * np.sin(2 * np.pi * 0.1 * t)
    combined = (a2 + c3 + e3) * mod

    # Normalize to int16 range
    peak = np.max(np.abs(combined))
    if peak > 0:
        combined = combined / peak * 0.8
    samples = (combined * 32767).astype(np.int16)

    audio = AudioSegment(
        data=samples.tobytes(),
        sample_width=2,
        frame_rate=sample_rate,
        channels=1,
    )
    return audio


def load_and_prepare_music(source_path: str, target_path: str) -> AudioSegment:
    """Load, trim, fade, and save music to target path.

    If source is longer than MUSIC_LOOP_SECONDS, takes the first N seconds
    and applies a fade-out. Shorter files are used as-is.
    Returns the prepared AudioSegment.

    Also serves as validation — if source is corrupt, AudioSegment.from_mp3() raises.
    """
    audio = AudioSegment.from_mp3(source_path)

    target_ms = MUSIC_LOOP_SECONDS * 1000
    if len(audio) > target_ms:
        audio = audio[:target_ms]
        audio = audio.fade_out(MUSIC_FADE_MS)

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    audio.export(target_path, format="mp3")
    return audio


def generate_music(
    project_dir: str,
    music_file: str | None = None,
) -> tuple[AudioSegment, str]:
    """Resolve music source and return (AudioSegment, source_string).

    Priority:
    1. Existing background.mp3 in project music/ dir
    2. music_file argument (user-provided)
    3. Bundled demo music matching project slug
    4. Procedural numpy fallback

    Does NOT write direction.json — caller handles provenance persistence.
    Step 1 reads direction.json to recover existing provenance.
    """
    music_dir = os.path.join(project_dir, "music")
    os.makedirs(music_dir, exist_ok=True)
    bg_path = os.path.join(music_dir, "background.mp3")

    # Step 1: Check existing background.mp3
    if os.path.exists(bg_path) and os.path.getsize(bg_path) > 0:
        try:
            audio = AudioSegment.from_mp3(bg_path)
            # Read provenance from direction.json
            source = _read_provenance(project_dir)
            return audio, source
        except Exception:
            # Corrupt file — delete and fall through
            os.remove(bg_path)

    # Step 2: User-provided music file
    if music_file and os.path.exists(music_file):
        audio = load_and_prepare_music(music_file, bg_path)
        filename = os.path.basename(music_file)
        return audio, f"user:{filename}"

    # Step 3: Bundled demo music
    slug = os.path.basename(project_dir.rstrip("/"))
    bundled_path = os.path.join(BUNDLED_MUSIC_DIR, f"{slug}.mp3")
    if os.path.exists(bundled_path):
        audio = load_and_prepare_music(bundled_path, bg_path)
        return audio, f"bundled:{slug}.mp3"

    # Step 4: Procedural fallback
    audio = generate_procedural_music()
    audio.export(bg_path, format="mp3")
    return audio, "procedural"


def _read_provenance(project_dir: str) -> str:
    """Read music_source from direction.json, or return 'existing'."""
    direction_path = os.path.join(project_dir, "direction.json")
    if os.path.exists(direction_path):
        try:
            with open(direction_path) as f:
                data = json.load(f)
            source = data.get("music_source")
            if source:
                return source
        except (json.JSONDecodeError, OSError):
            pass
    return "existing"
