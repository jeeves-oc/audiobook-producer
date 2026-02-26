"""Output directory management, intermediate artifacts, voice demos, and resumability."""

import json
import os
import re
import shutil

from pydub import AudioSegment

from audiobook_producer.constants import (
    OUTPUT_DIR,
    VOICE_DEMO_PANGRAM,
    PREVIEW_DURATION_MS,
)
from audiobook_producer.models import Segment


# Invalidation map: setting key → list of subdirs to delete
INVALIDATION_MAP = {
    "voice": ["voice_demos", "segments", "samples", "final"],
    "narrator-voice": ["voice_demos", "segments", "samples", "final"],
    "narrator-dialogue": ["voice_demos", "segments", "samples", "final"],
    "music": ["music", "samples", "final"],
    "music-file": ["samples", "final"],
    "music-db": ["samples", "final"],
    "reverb": ["segments", "samples", "final"],
    "reverb-room": ["segments", "samples", "final"],
    "reverb-wet": ["segments", "samples", "final"],
}


def slug_from_path(story_path: str) -> str:
    """Convert story filename to output directory slug.

    "Tell-Tale Heart.txt" → "tell_tale_heart"
    "/path/to/The Open Window.txt" → "the_open_window"
    """
    basename = os.path.splitext(os.path.basename(story_path))[0]
    # Replace non-alphanumeric with underscore, collapse multiples, strip edges
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", basename).strip("_").lower()
    return slug


def init_output_dir(story_path: str, output_base: str = OUTPUT_DIR) -> str:
    """Create output/<slug>/ and all subdirectories.

    Returns the project directory path.
    """
    slug = slug_from_path(story_path)
    project_dir = os.path.join(output_base, slug)

    subdirs = [
        "voice_demos",
        "segments",
        "music",
        "samples",
        "chapters",
        "final",
    ]

    for subdir in subdirs:
        os.makedirs(os.path.join(project_dir, subdir), exist_ok=True)

    return project_dir


def write_artifact(project_dir: str, filename: str, data: dict) -> str:
    """Write JSON artifact to project_dir/filename.

    Returns path to the written file.
    """
    path = os.path.join(project_dir, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def load_artifact(project_dir: str, filename: str) -> dict | None:
    """Read JSON artifact. Returns None if file doesn't exist."""
    path = os.path.join(project_dir, filename)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def invalidate_downstream(project_dir: str, setting_key: str) -> list[str]:
    """Delete downstream subdirectories for a given setting change.

    Returns list of deleted subdirectory names.
    """
    dirs_to_delete = INVALIDATION_MAP.get(setting_key, [])
    deleted = []
    for subdir in dirs_to_delete:
        path = os.path.join(project_dir, subdir)
        if os.path.exists(path):
            shutil.rmtree(path)
            os.makedirs(path, exist_ok=True)  # recreate empty dir
            deleted.append(subdir)
    return deleted


def get_project_status(project_dir: str) -> dict:
    """Return dict describing current state of each pipeline step."""
    status = {}

    # Parse step
    script = os.path.join(project_dir, "script.json")
    if os.path.exists(script):
        with open(script) as f:
            data = json.load(f)
        seg_count = len(data.get("segments", []))
        status["parse"] = {"state": "done", "segments": seg_count}
    else:
        status["parse"] = {"state": "pending"}

    # Voices step
    cast = os.path.join(project_dir, "cast.json")
    if os.path.exists(cast):
        with open(cast) as f:
            data = json.load(f)
        char_count = len(data.get("characters", {})) + 1  # +1 for narrator
        status["voices"] = {"state": "done", "voices": char_count}
    else:
        status["voices"] = {"state": "pending"}

    # TTS step
    seg_dir = os.path.join(project_dir, "segments")
    if os.path.exists(seg_dir):
        mp3s = [f for f in os.listdir(seg_dir) if f.endswith(".mp3")]
        if mp3s:
            expected = status.get("parse", {}).get("segments", 0)
            if expected and len(mp3s) >= expected:
                status["tts"] = {"state": "done", "files": len(mp3s)}
            else:
                status["tts"] = {"state": "partial", "files": len(mp3s), "expected": expected}
        else:
            status["tts"] = {"state": "pending"}
    else:
        status["tts"] = {"state": "pending"}

    # Effects step
    effects_json = os.path.join(project_dir, "effects.json")
    status["effects"] = {"state": "done" if os.path.exists(effects_json) else "pending"}

    # Music step
    bg = os.path.join(project_dir, "music", "background.mp3")
    status["music"] = {"state": "done" if os.path.exists(bg) else "pending"}

    # Assembly step (check for preview or final)
    preview = os.path.join(project_dir, "samples", "preview_60s.mp3")
    status["assembly"] = {"state": "done" if os.path.exists(preview) else "pending"}

    # Export step
    final_dir = os.path.join(project_dir, "final")
    if os.path.exists(final_dir):
        mp3s = [f for f in os.listdir(final_dir) if f.endswith(".mp3")]
        status["export"] = {"state": "done" if mp3s else "pending"}
    else:
        status["export"] = {"state": "pending"}

    return status


def list_projects(output_base: str = OUTPUT_DIR) -> list[str]:
    """List all project slugs under the output directory.

    Returns sorted list of directory names that contain a script.json.
    """
    if not os.path.exists(output_base):
        return []
    projects = []
    for name in os.listdir(output_base):
        project_dir = os.path.join(output_base, name)
        if os.path.isdir(project_dir):
            script = os.path.join(project_dir, "script.json")
            if os.path.exists(script):
                projects.append(name)
    return sorted(projects)


def generate_voice_demos(
    project_dir: str,
    cast_data: dict,
    segments: list[Segment],
) -> list[str]:
    """Generate voice demo clips for each character.

    Characters with dialogue: pangram + first story line.
    Characters with no dialogue: pangram only.
    Uses tts.generate_single() internally.

    Returns list of generated file paths.
    """
    from audiobook_producer.tts import generate_single

    demo_dir = os.path.join(project_dir, "voice_demos")
    os.makedirs(demo_dir, exist_ok=True)

    paths = []

    # Collect all unique characters + narrator
    characters = {}  # speaker -> voice
    narrator_voice = cast_data.get("narrator", {}).get("voice", "en-US-GuyNeural")
    characters["narrator"] = narrator_voice

    for name, info in cast_data.get("characters", {}).items():
        characters[name] = info.get("voice", "")

    # Find first dialogue line per character
    first_lines = {}
    for seg in segments:
        speaker = seg.speaker.lower()
        if speaker not in first_lines and seg.type == "dialogue":
            first_lines[speaker] = seg.text

    for speaker, voice in characters.items():
        if not voice:
            continue

        speaker_slug = speaker.replace(" ", "_").lower()

        # Pangram demo
        pangram_path = os.path.join(demo_dir, f"{speaker_slug}_pangram.mp3")
        if not os.path.exists(pangram_path):
            generate_single(VOICE_DEMO_PANGRAM, voice, pangram_path)
        paths.append(pangram_path)

        # Story line demo (if character has dialogue)
        story_line = first_lines.get(speaker.lower())
        if story_line:
            story_path = os.path.join(demo_dir, f"{speaker_slug}_story.mp3")
            if not os.path.exists(story_path):
                generate_single(story_line, voice, story_path)
            paths.append(story_path)

    return paths


def generate_preview(
    project_dir: str,
    assembled_audio: AudioSegment,
    duration_ms: int = PREVIEW_DURATION_MS,
) -> str:
    """Generate a preview clip from assembled audio.

    Trims to first duration_ms, saves to samples/preview_60s.mp3.
    Returns path to preview file.
    """
    samples_dir = os.path.join(project_dir, "samples")
    os.makedirs(samples_dir, exist_ok=True)

    preview = assembled_audio[:duration_ms]
    path = os.path.join(samples_dir, "preview_60s.mp3")
    preview.export(path, format="mp3")
    return path


def split_chapters(
    project_dir: str,
    assembled_audio: AudioSegment,
    segments: list[Segment],
) -> list[str]:
    """Split long stories into chapter-level MP3s.

    Stories with >50 segments get chapter splits (~10 min each).
    Short stories return empty list (no chapters).
    """
    if len(segments) <= 50:
        return []

    chapters_dir = os.path.join(project_dir, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    # Target ~10 minutes per chapter
    target_chapter_ms = 10 * 60 * 1000
    total_ms = len(assembled_audio)

    if total_ms <= target_chapter_ms:
        return []

    paths = []
    chapter_num = 1
    pos = 0

    while pos < total_ms:
        end = min(pos + target_chapter_ms, total_ms)
        chapter = assembled_audio[pos:end]
        path = os.path.join(chapters_dir, f"chapter_{chapter_num:02d}.mp3")
        chapter.export(path, format="mp3")
        paths.append(path)
        chapter_num += 1
        pos = end

    return paths


def check_step_fresh(
    project_dir: str,
    step_name: str,
    input_paths: list[str] | None = None,
) -> bool:
    """Resumability check: is a step's output up-to-date?

    Returns True if output exists and all input mtimes are older than output.
    """
    # Map step names to their output indicators
    output_map = {
        "parse": os.path.join(project_dir, "script.json"),
        "voices": os.path.join(project_dir, "cast.json"),
        "tts": os.path.join(project_dir, "segments"),
        "effects": os.path.join(project_dir, "effects.json"),
        "music": os.path.join(project_dir, "music", "background.mp3"),
        "assembly": os.path.join(project_dir, "samples", "preview_60s.mp3"),
        "export": os.path.join(project_dir, "final"),
    }

    output_path = output_map.get(step_name)
    if not output_path or not os.path.exists(output_path):
        return False

    # For directories, check if they have any files
    if os.path.isdir(output_path):
        contents = os.listdir(output_path)
        if not contents:
            return False
        # Use most recent file in directory
        output_mtime = max(
            os.path.getmtime(os.path.join(output_path, f))
            for f in contents
        )
    else:
        output_mtime = os.path.getmtime(output_path)

    # If no input paths specified, just check existence
    if not input_paths:
        return True

    # Check all inputs are older than output
    for input_path in input_paths:
        if not os.path.exists(input_path):
            continue
        if os.path.getmtime(input_path) > output_mtime:
            return False

    return True
