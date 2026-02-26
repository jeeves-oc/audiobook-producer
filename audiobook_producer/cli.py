"""CLI interface with subcommand routing and pipeline orchestration."""

import argparse
import json
import os
import shutil
import sys

from pydub import AudioSegment

from audiobook_producer.constants import (
    OUTPUT_DIR,
    NARRATOR_VOICE,
    NARRATOR_DIALOGUE_VOICE,
    MUSIC_BED_DB,
    REVERB_ROOM_SIZE,
    REVERB_WET_LEVEL,
    VERSION,
)
from audiobook_producer.models import Segment
from audiobook_producer.parser import parse_story, extract_metadata
from audiobook_producer.voices import (
    assign_voices,
    load_cast,
    generate_intro_segments,
    generate_outro_segments,
    VOICE_POOL,
)
from audiobook_producer.tts import generate_tts
from audiobook_producer.music import generate_music, load_and_prepare_music
from audiobook_producer.effects import process_segments
from audiobook_producer.assembly import assemble
from audiobook_producer.exporter import export
from audiobook_producer.artifacts import (
    init_output_dir,
    slug_from_path,
    write_artifact,
    load_artifact,
    invalidate_downstream,
    get_project_status,
    list_projects,
    generate_voice_demos,
    generate_preview,
    split_chapters,
    check_step_fresh,
)


def _check_ffmpeg():
    """Verify ffmpeg is installed."""
    if not shutil.which("ffmpeg"):
        print("Error: ffmpeg is required but not found.", file=sys.stderr)
        print("Install with: brew install ffmpeg", file=sys.stderr)
        raise SystemExit(1)


def _get_project_dir(slug: str) -> str:
    """Get project directory path, verify it exists."""
    project_dir = os.path.join(OUTPUT_DIR, slug)
    if not os.path.isdir(project_dir):
        print(f"Error: Project '{slug}' not found.", file=sys.stderr)
        print(f"Run 'producer.py new <file>' to create a project.", file=sys.stderr)
        raise SystemExit(1)
    # Check for script.json
    if not os.path.exists(os.path.join(project_dir, "script.json")):
        print(f"Error: Project '{slug}' is incomplete (no script.json).", file=sys.stderr)
        raise SystemExit(1)
    return project_dir


def cmd_new(args):
    """Create a new project from a text file."""
    file_path = args.file

    # Validate input
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        raise SystemExit(1)

    with open(file_path) as f:
        text = f.read()

    if not text.strip():
        print(f"Error: File is empty: {file_path}", file=sys.stderr)
        raise SystemExit(1)

    # Check if project already exists
    slug = slug_from_path(file_path)
    project_dir = os.path.join(OUTPUT_DIR, slug)
    if os.path.exists(os.path.join(project_dir, "script.json")):
        print(f"Error: Project '{slug}' already exists.", file=sys.stderr)
        print(f"Use 'producer.py run {slug}' to generate audio, or 'producer.py set {slug} ...' to adjust.", file=sys.stderr)
        raise SystemExit(1)

    # Parse
    title, author = extract_metadata(text)
    segments = parse_story(text)

    if not segments:
        print(f"Error: Could not parse any segments from: {file_path}", file=sys.stderr)
        raise SystemExit(1)

    # Init output dir
    project_dir = init_output_dir(file_path, output_base=OUTPUT_DIR)

    # Load cast
    cast = load_cast(file_path)

    # Assign voices
    assign_voices(segments, cast=cast)

    # Generate bookend segments
    intro_segments = generate_intro_segments(title, author, segments, cast=cast)
    outro_segments = generate_outro_segments(title, author, segments)

    # Write artifacts
    script_data = {
        "metadata": {"title": title, "author": author},
        "source": os.path.abspath(file_path),
        "segments": [
            {"type": s.type, "text": s.text, "speaker": s.speaker}
            for s in segments
        ],
        "intro_segments": [
            {"type": s.type, "text": s.text, "speaker": s.speaker, "voice": s.voice}
            for s in intro_segments
        ],
        "outro_segments": [
            {"type": s.type, "text": s.text, "speaker": s.speaker, "voice": s.voice}
            for s in outro_segments
        ],
    }
    write_artifact(project_dir, "script.json", script_data)

    # Build cast.json
    cast_data = _build_cast_data(segments, cast)
    write_artifact(project_dir, "cast.json", cast_data)

    # Write direction.json (assembly defaults)
    direction = {
        "intro_music_solo_ms": 4000,
        "outro_music_solo_ms": 4000,
        "music_bed_db": MUSIC_BED_DB,
        "music_fade_ms": 2000,
        "pauses": {
            "same_type_ms": 300,
            "speaker_change_ms": 500,
            "type_transition_ms": 700,
        },
        "no_music": False,
        "music_source": None,
    }
    write_artifact(project_dir, "direction.json", direction)

    # Write effects.json (defaults)
    effects = {
        "global": {"normalize": True, "target_dbfs": -20},
        "per_segment": {
            "dialogue": {"reverb": {"room_size": REVERB_ROOM_SIZE, "wet_level": REVERB_WET_LEVEL}},
            "narration": {"reverb": None},
        },
    }
    write_artifact(project_dir, "effects.json", effects)

    # Summary
    narration_count = sum(1 for s in segments if s.type == "narration")
    dialogue_count = sum(1 for s in segments if s.type == "dialogue")
    print(f"Created project: {slug}")
    print(f"Parsed {len(segments)} segments ({narration_count} narration, {dialogue_count} dialogue)")
    print(f"Cast written to {OUTPUT_DIR}/{slug}/cast.json")
    print(f"Run 'producer.py status {slug}' to review, or 'producer.py run {slug}' to generate audio.")


def _build_cast_data(segments: list[Segment], cast: dict) -> dict:
    """Build cast.json structure from assigned segments and cast info."""
    cast_entries = cast.get("cast", {})
    narrator_info = cast.get("narrator", {})

    cast_data = {
        "narrator": {
            "voice": narrator_info.get("voice", NARRATOR_VOICE),
            "dialogue_voice": narrator_info.get("dialogue_voice", NARRATOR_DIALOGUE_VOICE),
        },
    }
    if narrator_info.get("description"):
        cast_data["narrator"]["description"] = narrator_info["description"]

    characters = {}
    seen = set()
    for seg in segments:
        speaker = seg.speaker.lower()
        if speaker in ("narrator", "unknown") or speaker in seen:
            continue
        seen.add(speaker)
        char_info = {"voice": seg.voice}
        # Check cast for description
        for name, info in cast_entries.items():
            if name.lower() == speaker:
                if info.get("description"):
                    char_info["description"] = info["description"]
                char_info["source"] = "cast_file"
                break
        else:
            char_info["source"] = "hash"
        characters[speaker] = char_info

    cast_data["characters"] = characters
    return cast_data


def cmd_run(args):
    """Run the production pipeline."""
    _check_ffmpeg()

    slug = args.slug
    project_dir = _get_project_dir(slug)
    verbose = args.verbose
    force = args.force

    # Load script.json
    script = load_artifact(project_dir, "script.json")
    cast_data = load_artifact(project_dir, "cast.json")
    direction = load_artifact(project_dir, "direction.json")
    effects_config = load_artifact(project_dir, "effects.json")

    if not script or not cast_data:
        print(f"Error: Project '{slug}' is missing required artifacts.", file=sys.stderr)
        raise SystemExit(1)

    metadata = script["metadata"]

    # Reconstruct segments
    segments = [
        Segment(type=s["type"], text=s["text"], speaker=s["speaker"])
        for s in script["segments"]
    ]
    assign_voices(segments, cast=_reconstruct_cast(cast_data))

    intro_segments = [
        Segment(type=s["type"], text=s["text"], speaker=s["speaker"], voice=s["voice"])
        for s in script.get("intro_segments", [])
    ]
    outro_segments = [
        Segment(type=s["type"], text=s["text"], speaker=s["speaker"], voice=s["voice"])
        for s in script.get("outro_segments", [])
    ]

    all_segments = intro_segments + segments + outro_segments

    # Force mode: delete generated artifacts
    if force:
        for subdir in ["voice_demos", "segments", "music", "samples", "chapters", "final"]:
            path = os.path.join(project_dir, subdir)
            if os.path.exists(path):
                shutil.rmtree(path)
                os.makedirs(path, exist_ok=True)

    # Step 1: Voice demos (verbose mode only generates them, always generated for -v)
    if verbose:
        demo_dir = os.path.join(project_dir, "voice_demos")
        existing_demos = len([f for f in os.listdir(demo_dir) if f.endswith(".mp3")]) if os.path.exists(demo_dir) else 0
        cast_fresh = check_step_fresh(project_dir, "voices", [os.path.join(project_dir, "cast.json")])

        if not cast_fresh or existing_demos == 0 or force:
            print("Generating voice demos...")
            generate_voice_demos(project_dir, cast_data, segments)
        else:
            print("[skip] Voice demos: up to date")

        # Preview gate — only in interactive terminal
        if sys.stdin.isatty():
            print(f"\nListen to voice demos in {OUTPUT_DIR}/{slug}/voice_demos/")
            response = input("Continue? [Y/n] ").strip().lower()
            if response == "n":
                print("Skipping preview, continuing to TTS...")

    # Step 2: TTS generation
    seg_dir = os.path.join(project_dir, "segments")
    os.makedirs(seg_dir, exist_ok=True)
    existing_mp3s = len([f for f in os.listdir(seg_dir) if f.endswith(".mp3")])

    if existing_mp3s >= len(all_segments) and not force:
        if verbose:
            print("[skip] TTS: segments/ is up to date")
    else:
        print(f"Generating TTS for {len(all_segments)} segments...")
        generate_tts(all_segments, seg_dir)

    # Step 3: Effects
    seg_dir = os.path.join(project_dir, "segments")
    seg_files = sorted([f for f in os.listdir(seg_dir) if f.endswith(".mp3")])

    # Load audio segments
    audio_map = {}
    for i, filename in enumerate(seg_files):
        path = os.path.join(seg_dir, filename)
        audio_map[f"{all_segments[i].type}_{i}"] = AudioSegment.from_mp3(path)

    # Apply effects
    reverb_on = True
    normalize_on = True
    if effects_config:
        per_seg = effects_config.get("per_segment", {})
        reverb_on = per_seg.get("dialogue", {}).get("reverb") is not None
        normalize_on = effects_config.get("global", {}).get("normalize", True)

    reverb_room = REVERB_ROOM_SIZE
    reverb_wet = REVERB_WET_LEVEL
    if effects_config:
        reverb_cfg = effects_config.get("per_segment", {}).get("dialogue", {}).get("reverb", {})
        if reverb_cfg:
            reverb_room = reverb_cfg.get("room_size", REVERB_ROOM_SIZE)
            reverb_wet = reverb_cfg.get("wet_level", REVERB_WET_LEVEL)

    if verbose:
        print("Applying effects...")
    processed = process_segments(
        all_segments, audio_map,
        reverb=reverb_on, normalize=normalize_on,
        reverb_room=reverb_room, reverb_wet=reverb_wet,
    )

    # Save processed audio back
    for i, filename in enumerate(seg_files):
        key = f"{all_segments[i].type}_{i}"
        if key in processed:
            path = os.path.join(seg_dir, filename)
            processed[key].export(path, format="mp3")

    # Step 4: Music
    no_music = direction.get("no_music", False) if direction else False
    music_audio = None
    music_source = None

    if not no_music:
        bg_path = os.path.join(project_dir, "music", "background.mp3")
        if os.path.exists(bg_path) and not force:
            if verbose:
                print("[skip] Music: background.mp3 exists")
            music_audio = AudioSegment.from_mp3(bg_path)
            # Read source from direction.json
            if direction and direction.get("music_source"):
                music_source = direction["music_source"]
        else:
            if verbose:
                print("Resolving music...")
            music_audio, music_source = generate_music(project_dir)

        # Write music_source to direction.json
        if music_source and direction:
            direction["music_source"] = music_source
            write_artifact(project_dir, "direction.json", direction)

    # Step 5: Assembly
    if verbose:
        print("Assembling production...")

    # Split audio lists for intro/story/outro
    intro_audio_list = []
    story_audio_list = []
    outro_audio_list = []

    intro_count = len(intro_segments)
    outro_count = len(outro_segments)
    story_count = len(segments)

    for i in range(intro_count):
        key = f"{all_segments[i].type}_{i}"
        intro_audio_list.append(processed.get(key, AudioSegment.silent(duration=100)))

    for i in range(intro_count, intro_count + story_count):
        key = f"{all_segments[i].type}_{i}"
        story_audio_list.append(processed.get(key, AudioSegment.silent(duration=100)))

    for i in range(intro_count + story_count, len(all_segments)):
        key = f"{all_segments[i].type}_{i}"
        outro_audio_list.append(processed.get(key, AudioSegment.silent(duration=100)))

    music_bed_db = direction.get("music_bed_db", MUSIC_BED_DB) if direction else MUSIC_BED_DB

    assembled = assemble(
        intro_segments, intro_audio_list,
        segments, story_audio_list,
        outro_segments, outro_audio_list,
        music=music_audio,
        no_music=no_music,
        music_bed_db=music_bed_db,
    )

    # Generate preview
    generate_preview(project_dir, assembled)

    # Step 6: Export
    if verbose:
        print("Exporting final MP3...")

    settings = {
        "music": not no_music,
        "music_source": music_source,
        "music_bed_db": music_bed_db,
        "reverb": reverb_on,
        "reverb_room_size": reverb_room,
        "reverb_wet_level": reverb_wet,
        "bitrate": "192k",
    }

    output_path = export(
        assembled, project_dir, slug,
        {**metadata, "source": script.get("source", "")},
        cast_data,
        settings,
        len(segments),
    )

    # Chapter split
    split_chapters(project_dir, assembled, segments)

    print(f"Done: {output_path}")


def _reconstruct_cast(cast_data: dict) -> dict:
    """Reconstruct cast dict format expected by assign_voices()."""
    result = {}
    if "narrator" in cast_data:
        result["narrator"] = cast_data["narrator"]
    if "characters" in cast_data:
        result["cast"] = cast_data["characters"]
    return result


def cmd_status(args):
    """Show project status."""
    slug = args.slug
    project_dir = _get_project_dir(slug)

    script = load_artifact(project_dir, "script.json")
    cast_data = load_artifact(project_dir, "cast.json")
    status = get_project_status(project_dir)

    metadata = script.get("metadata", {}) if script else {}
    print(f"Project: {slug}")
    print(f"Source:  {script.get('source', 'unknown')}")

    if script:
        segments = script.get("segments", [])
        narration = sum(1 for s in segments if s["type"] == "narration")
        dialogue = sum(1 for s in segments if s["type"] == "dialogue")
        print(f"Segments: {len(segments)} ({narration} narration, {dialogue} dialogue)")

    if cast_data:
        print("Cast:")
        narrator = cast_data.get("narrator", {})
        print(f"  narrator        → {narrator.get('voice', 'unset')}")
        for name, info in cast_data.get("characters", {}).items():
            print(f"  {name:<15} → {info.get('voice', 'unset')}")

    print("Steps:")
    step_names = ["parse", "voices", "tts", "effects", "music", "assembly", "export"]
    for step in step_names:
        info = status.get(step, {"state": "pending"})
        state = info["state"]
        marker = "[done]" if state == "done" else "[part]" if state == "partial" else "[----]"
        details = ""
        if state == "done" and "segments" in info:
            details = f" ({info['segments']} segments)"
        elif state == "done" and "files" in info:
            details = f" ({info['files']} files)"
        elif state == "partial" and "files" in info:
            details = f" ({info['files']}/{info.get('expected', '?')} files)"
        print(f"  {marker} {step:<12}{details}")


def cmd_set(args):
    """Update project settings."""
    slug = args.slug
    project_dir = _get_project_dir(slug)

    key = args.key
    values = args.values

    # Validate key
    valid_keys = {
        "voice", "narrator-voice", "narrator-dialogue",
        "music", "music-file", "music-db",
        "reverb", "reverb-room", "reverb-wet",
    }
    if key not in valid_keys:
        print(f"Error: Invalid setting key: {key}", file=sys.stderr)
        print(f"Valid keys: {', '.join(sorted(valid_keys))}", file=sys.stderr)
        raise SystemExit(1)

    if key == "voice":
        if len(values) < 2:
            print("Error: 'set voice' requires <speaker> and <voice_id>", file=sys.stderr)
            raise SystemExit(1)
        speaker = values[0].lower()
        voice_id = values[1]
        cast_data = load_artifact(project_dir, "cast.json")
        if not cast_data:
            cast_data = {"narrator": {}, "characters": {}}
        if speaker not in cast_data.get("characters", {}):
            print(f"Warning: Speaker '{speaker}' not in cast. Adding.", file=sys.stderr)
            cast_data.setdefault("characters", {})[speaker] = {}
        cast_data["characters"][speaker]["voice"] = voice_id
        write_artifact(project_dir, "cast.json", cast_data)
        print(f"Updated: {speaker} → {voice_id}")

    elif key == "narrator-voice":
        if not values:
            print("Error: 'set narrator-voice' requires <voice_id>", file=sys.stderr)
            raise SystemExit(1)
        voice_id = values[0]
        cast_data = load_artifact(project_dir, "cast.json") or {"narrator": {}, "characters": {}}
        cast_data.setdefault("narrator", {})["voice"] = voice_id
        write_artifact(project_dir, "cast.json", cast_data)
        print(f"Updated: narrator → {voice_id}")

    elif key == "narrator-dialogue":
        if not values:
            print("Error: 'set narrator-dialogue' requires <voice_id>", file=sys.stderr)
            raise SystemExit(1)
        voice_id = values[0]
        cast_data = load_artifact(project_dir, "cast.json") or {"narrator": {}, "characters": {}}
        cast_data.setdefault("narrator", {})["dialogue_voice"] = voice_id
        write_artifact(project_dir, "cast.json", cast_data)
        print(f"Updated: narrator dialogue → {voice_id}")

    elif key == "music":
        if not values or values[0] not in ("on", "off"):
            print("Error: 'set music' requires 'on' or 'off'", file=sys.stderr)
            raise SystemExit(1)
        direction = load_artifact(project_dir, "direction.json") or {}
        direction["no_music"] = values[0] == "off"
        write_artifact(project_dir, "direction.json", direction)
        print(f"Updated: music → {values[0]}")

    elif key == "music-file":
        if not values:
            print("Error: 'set music-file' requires <path>", file=sys.stderr)
            raise SystemExit(1)
        music_path = values[0]
        if not os.path.exists(music_path):
            print(f"Error: File not found: {music_path}", file=sys.stderr)
            raise SystemExit(1)
        # Validate by loading — load_and_prepare_music will raise if corrupt
        target = os.path.join(project_dir, "music", "background.mp3")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            load_and_prepare_music(music_path, target)
        except Exception as e:
            print(f"Error: Could not load audio file: {e}", file=sys.stderr)
            raise SystemExit(1)
        # Write provenance
        direction = load_artifact(project_dir, "direction.json") or {}
        direction["music_source"] = f"user:{os.path.basename(music_path)}"
        write_artifact(project_dir, "direction.json", direction)
        print(f"Updated: music file → {os.path.basename(music_path)}")

    elif key == "music-db":
        if not values:
            print("Error: 'set music-db' requires <float>", file=sys.stderr)
            raise SystemExit(1)
        try:
            db_val = float(values[0])
        except ValueError:
            print(f"Error: Invalid dB value: {values[0]}", file=sys.stderr)
            raise SystemExit(1)
        direction = load_artifact(project_dir, "direction.json") or {}
        direction["music_bed_db"] = db_val
        write_artifact(project_dir, "direction.json", direction)
        print(f"Updated: music bed → {db_val} dB")

    elif key == "reverb":
        if not values or values[0] not in ("on", "off"):
            print("Error: 'set reverb' requires 'on' or 'off'", file=sys.stderr)
            raise SystemExit(1)
        effects = load_artifact(project_dir, "effects.json") or {
            "global": {"normalize": True, "target_dbfs": -20},
            "per_segment": {"dialogue": {}, "narration": {"reverb": None}},
        }
        if values[0] == "on":
            effects.setdefault("per_segment", {}).setdefault("dialogue", {})["reverb"] = {
                "room_size": REVERB_ROOM_SIZE, "wet_level": REVERB_WET_LEVEL
            }
        else:
            effects.setdefault("per_segment", {}).setdefault("dialogue", {})["reverb"] = None
        write_artifact(project_dir, "effects.json", effects)
        print(f"Updated: reverb → {values[0]}")

    elif key == "reverb-room":
        if not values:
            print("Error: 'set reverb-room' requires <float>", file=sys.stderr)
            raise SystemExit(1)
        try:
            val = float(values[0])
        except ValueError:
            print(f"Error: Invalid value: {values[0]}", file=sys.stderr)
            raise SystemExit(1)
        effects = load_artifact(project_dir, "effects.json") or {
            "global": {"normalize": True, "target_dbfs": -20},
            "per_segment": {"dialogue": {"reverb": {}}, "narration": {"reverb": None}},
        }
        reverb = effects.setdefault("per_segment", {}).setdefault("dialogue", {}).setdefault("reverb", {})
        reverb["room_size"] = val
        write_artifact(project_dir, "effects.json", effects)
        print(f"Updated: reverb room size → {val}")

    elif key == "reverb-wet":
        if not values:
            print("Error: 'set reverb-wet' requires <float>", file=sys.stderr)
            raise SystemExit(1)
        try:
            val = float(values[0])
        except ValueError:
            print(f"Error: Invalid value: {values[0]}", file=sys.stderr)
            raise SystemExit(1)
        effects = load_artifact(project_dir, "effects.json") or {
            "global": {"normalize": True, "target_dbfs": -20},
            "per_segment": {"dialogue": {"reverb": {}}, "narration": {"reverb": None}},
        }
        reverb = effects.setdefault("per_segment", {}).setdefault("dialogue", {}).setdefault("reverb", {})
        reverb["wet_level"] = val
        write_artifact(project_dir, "effects.json", effects)
        print(f"Updated: reverb wet level → {val}")

    # Invalidate downstream artifacts
    deleted = invalidate_downstream(project_dir, key)
    if deleted:
        print(f"Invalidated: {', '.join(deleted)} (will regenerate on next run)")


def cmd_list(args):
    """List all projects."""
    projects = list_projects(output_base=OUTPUT_DIR)
    if not projects:
        print("No projects found.")
        return
    print("Projects:")
    for name in projects:
        project_dir = os.path.join(OUTPUT_DIR, name)
        status = get_project_status(project_dir)
        export_state = status.get("export", {}).get("state", "pending")
        marker = "[done]" if export_state == "done" else "[----]"
        print(f"  {marker} {name}")


def cmd_voices(args):
    """List available voices."""
    filter_str = args.filter.lower() if args.filter else None
    voices = VOICE_POOL
    if filter_str:
        voices = [v for v in voices if filter_str in v.lower()]
    if not voices:
        print("No matching voices found.")
        return
    print("Available voices:")
    for v in voices:
        print(f"  {v}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="producer.py",
        description="Audiobook Producer — transform text into full-cast audio dramas",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # new
    new_parser = subparsers.add_parser("new", help="Create a new project from a text file")
    new_parser.add_argument("file", help="Path to the story text file")
    new_parser.set_defaults(func=cmd_new)

    # run
    run_parser = subparsers.add_parser("run", help="Run the production pipeline")
    run_parser.add_argument("slug", help="Project slug (from filename)")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode with voice demos and preview")
    run_parser.add_argument("--force", action="store_true", help="Force re-run (delete generated artifacts)")
    run_parser.set_defaults(func=cmd_run)

    # status
    status_parser = subparsers.add_parser("status", help="Show project status")
    status_parser.add_argument("slug", help="Project slug")
    status_parser.set_defaults(func=cmd_status)

    # set
    set_parser = subparsers.add_parser("set", help="Update project settings")
    set_parser.add_argument("slug", help="Project slug")
    set_parser.add_argument("key", help="Setting key")
    set_parser.add_argument("values", nargs="*", help="Setting value(s)")
    set_parser.set_defaults(func=cmd_set)

    # list
    list_parser = subparsers.add_parser("list", help="List all projects")
    list_parser.set_defaults(func=cmd_list)

    # voices
    voices_parser = subparsers.add_parser("voices", help="List available voices")
    voices_parser.add_argument("--filter", help="Filter voices by substring")
    voices_parser.set_defaults(func=cmd_voices)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)
