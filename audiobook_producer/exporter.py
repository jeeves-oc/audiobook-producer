"""Export assembled audio as MP3 with metadata tags."""

import json
import os
from datetime import datetime, timezone

from pydub import AudioSegment

from audiobook_producer.constants import OUTPUT_BITRATE, VERSION


def export(
    assembled: AudioSegment,
    project_dir: str,
    slug: str,
    metadata: dict,
    cast_data: dict,
    settings: dict,
    segment_count: int,
) -> str:
    """Export assembled audio as MP3 with metadata tags.

    Creates:
      - output/<slug>/final/<slug>.mp3 (the production)
      - output/<slug>/final/output.json (provenance manifest)

    Returns path to the final MP3 file.
    """
    final_dir = os.path.join(project_dir, "final")
    os.makedirs(final_dir, exist_ok=True)

    output_path = os.path.join(final_dir, f"{slug}.mp3")

    # Export MP3 with metadata tags
    tags = {}
    if metadata.get("title"):
        tags["title"] = metadata["title"]
    if metadata.get("author"):
        tags["artist"] = metadata["author"]

    assembled.export(
        output_path,
        format="mp3",
        bitrate=OUTPUT_BITRATE,
        tags=tags,
    )

    # Write output.json manifest
    manifest = {
        "project": slug,
        "source": metadata.get("source", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer_version": VERSION,
        "metadata": {
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
        },
        "cast": cast_data,
        "settings": settings,
        "stats": {
            "segments": segment_count,
            "duration_seconds": round(len(assembled) / 1000, 1),
            "characters": len([k for k in cast_data if k != "narrator"]),
        },
    }

    manifest_path = os.path.join(final_dir, "output.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    return output_path
