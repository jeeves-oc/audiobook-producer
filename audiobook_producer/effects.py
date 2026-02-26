"""Audio effects: reverb on dialogue and volume normalization."""

import numpy as np
from pydub import AudioSegment

from audiobook_producer.constants import REVERB_ROOM_SIZE, REVERB_WET_LEVEL
from audiobook_producer.models import Segment

# Try to import pedalboard — graceful fallback if not installed
try:
    import pedalboard
    PEDALBOARD_AVAILABLE = True
except ImportError:
    PEDALBOARD_AVAILABLE = False


def apply_reverb(
    audio: AudioSegment,
    room_size: float = REVERB_ROOM_SIZE,
    wet_level: float = REVERB_WET_LEVEL,
) -> AudioSegment:
    """Apply subtle room reverb to an AudioSegment.

    Returns processed audio if pedalboard is available, otherwise returns
    the original audio unchanged.
    """
    if not PEDALBOARD_AVAILABLE:
        return audio

    # Convert pydub AudioSegment to numpy array for pedalboard
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    sample_rate = audio.frame_rate

    # Reshape for multi-channel if needed
    if audio.channels > 1:
        samples = samples.reshape((-1, audio.channels)).T
    else:
        samples = samples.reshape((1, -1))

    # Normalize to [-1, 1] range
    samples = samples / 32768.0

    # Apply reverb
    board = pedalboard.Pedalboard([
        pedalboard.Reverb(room_size=room_size, wet_level=wet_level),
    ])
    processed = board(samples, sample_rate)

    # Convert back to int16
    processed = np.clip(processed * 32768.0, -32768, 32767).astype(np.int16)

    # Reshape back
    if audio.channels > 1:
        processed = processed.T.flatten()
    else:
        processed = processed.flatten()

    result = AudioSegment(
        data=processed.tobytes(),
        sample_width=2,
        frame_rate=sample_rate,
        channels=audio.channels,
    )
    return result


def normalize_levels(
    audio_map: dict[str, AudioSegment],
    target_dbfs: float = -20.0,
) -> dict[str, AudioSegment]:
    """Normalize volume levels across all segments.

    Adjusts each segment so its dBFS is close to target_dbfs.
    Silent segments (dBFS = -inf) are left unchanged.
    """
    result = {}
    for key, audio in audio_map.items():
        if audio.dBFS == float("-inf"):
            result[key] = audio
            continue
        change = target_dbfs - audio.dBFS
        result[key] = audio + change
    return result


def process_segments(
    segments: list[Segment],
    audio_map: dict[str, AudioSegment],
    reverb: bool = True,
    normalize: bool = True,
    reverb_room: float = REVERB_ROOM_SIZE,
    reverb_wet: float = REVERB_WET_LEVEL,
) -> dict[str, AudioSegment]:
    """Process all segments with effects.

    - Reverb on dialogue segments only (if reverb=True)
    - Volume normalization across all segments (if normalize=True)
    """
    result = {}

    for key, audio in audio_map.items():
        # Find corresponding segment to check type
        seg = None
        for s_idx, s in enumerate(segments):
            seg_key = f"{s.type}_{s_idx}"
            if seg_key == key:
                seg = s
                break

        if reverb and seg and seg.type == "dialogue":
            result[key] = apply_reverb(audio, reverb_room, reverb_wet)
        else:
            result[key] = audio

    if normalize:
        result = normalize_levels(result)

    return result
