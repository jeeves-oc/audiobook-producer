"""Assemble audio segments with bookend music structure."""

from pydub import AudioSegment

from audiobook_producer.constants import (
    PAUSE_SAME_TYPE_MS,
    PAUSE_SPEAKER_CHANGE_MS,
    PAUSE_TYPE_TRANSITION_MS,
    INTRO_MUSIC_SOLO_MS,
    OUTRO_MUSIC_SOLO_MS,
    MUSIC_BED_DB,
    MUSIC_FADE_MS,
)
from audiobook_producer.models import Segment


def _calculate_pause(prev: Segment, curr: Segment) -> int:
    """Calculate pause duration between two segments.

    Uses max() when multiple rules apply (e.g., type transition + speaker change).
    """
    pause = PAUSE_SAME_TYPE_MS  # base pause

    if prev.type != curr.type:
        pause = max(pause, PAUSE_TYPE_TRANSITION_MS)

    if prev.speaker != curr.speaker:
        pause = max(pause, PAUSE_SPEAKER_CHANGE_MS)

    return pause


def _concatenate_with_pauses(
    segments: list[Segment],
    audio_files: list[AudioSegment],
) -> AudioSegment:
    """Concatenate audio segments with type-aware pauses."""
    if not audio_files:
        return AudioSegment.silent(duration=0)

    result = audio_files[0]
    for i in range(1, len(audio_files)):
        pause_ms = _calculate_pause(segments[i - 1], segments[i])
        result += AudioSegment.silent(duration=pause_ms) + audio_files[i]

    return result


def _build_music_bed(music: AudioSegment, duration_ms: int) -> AudioSegment:
    """Loop or trim music to fit a given duration."""
    if len(music) == 0:
        return AudioSegment.silent(duration=duration_ms)

    # Loop music until it covers the needed duration
    result = music
    while len(result) < duration_ms:
        result += music

    return result[:duration_ms]


def assemble(
    intro_segments: list[Segment],
    intro_audio: list[AudioSegment],
    story_segments: list[Segment],
    story_audio: list[AudioSegment],
    outro_segments: list[Segment],
    outro_audio: list[AudioSegment],
    music: AudioSegment | None = None,
    no_music: bool = False,
    music_bed_db: float = MUSIC_BED_DB,
    intro_music_solo_ms: int = INTRO_MUSIC_SOLO_MS,
    outro_music_solo_ms: int = OUTRO_MUSIC_SOLO_MS,
    music_fade_ms: int = MUSIC_FADE_MS,
) -> AudioSegment:
    """Assemble the full production with bookend music structure.

    Structure:
      [MUSIC SOLO] [MUSIC BED + INTRO] [STORY (no music)] [MUSIC BED + OUTRO] [MUSIC SOLO + FADE]
    """
    # Concatenate intro narration
    intro_concat = _concatenate_with_pauses(intro_segments, intro_audio)

    # Concatenate story body with pauses
    story_concat = _concatenate_with_pauses(story_segments, story_audio)

    # Concatenate outro narration
    outro_concat = _concatenate_with_pauses(outro_segments, outro_audio)

    if no_music or music is None:
        # No music mode: just concatenate everything with pauses between sections
        section_pause = AudioSegment.silent(duration=PAUSE_TYPE_TRANSITION_MS)
        return intro_concat + section_pause + story_concat + section_pause + outro_concat

    # === Bookend music structure ===

    # --- INTRO BOOKEND ---
    # 1. Music solo at full volume
    intro_solo = _build_music_bed(music, intro_music_solo_ms)

    # 2. Music bed under intro narration (music fades down, plays under narration)
    intro_narration_duration = len(intro_concat)
    # Music bed: fade down + play under intro + fade out at end
    intro_bed_duration = music_fade_ms + intro_narration_duration + music_fade_ms
    intro_bed_music = _build_music_bed(music, intro_bed_duration)
    # Apply volume reduction and fades
    intro_bed_music = intro_bed_music + music_bed_db  # reduce volume
    intro_bed_music = intro_bed_music.fade_in(music_fade_ms)  # fade from silence to bed level
    intro_bed_music = intro_bed_music.fade_out(music_fade_ms)  # fade out at end

    # Overlay intro narration centered on the music bed
    intro_with_bed = intro_bed_music.overlay(intro_concat, position=music_fade_ms)

    # --- STORY BODY (no music) ---
    story_padding = AudioSegment.silent(duration=PAUSE_TYPE_TRANSITION_MS)

    # --- OUTRO BOOKEND ---
    outro_narration_duration = len(outro_concat)
    # Music bed under outro
    outro_bed_duration = music_fade_ms + outro_narration_duration + music_fade_ms
    outro_bed_music = _build_music_bed(music, outro_bed_duration)
    outro_bed_music = outro_bed_music + music_bed_db
    outro_bed_music = outro_bed_music.fade_in(music_fade_ms)
    outro_bed_music = outro_bed_music.fade_out(music_fade_ms)

    outro_with_bed = outro_bed_music.overlay(outro_concat, position=music_fade_ms)

    # Music solo at end with fade out
    outro_solo = _build_music_bed(music, outro_music_solo_ms)
    outro_solo = outro_solo.fade_out(music_fade_ms)

    # Assemble all sections
    result = (
        intro_solo
        + intro_with_bed
        + story_padding
        + story_concat
        + story_padding
        + outro_with_bed
        + outro_solo
    )

    return result
