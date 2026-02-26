"""Parse story text into segments with speaker attribution."""

import re

from audiobook_producer.models import Segment
from audiobook_producer.constants import SEGMENT_SPLIT_THRESHOLD

# Speech verbs for attribution detection
SPEECH_VERBS = (
    "said", "asked", "replied", "cried", "whispered", "exclaimed",
    "shouted", "murmured", "muttered", "screamed", "shrieked",
    "called", "answered", "demanded", "insisted", "suggested",
    "pleaded", "begged", "groaned", "moaned", "sighed", "gasped",
    "laughed", "sobbed", "wept", "hissed", "snapped", "growled",
    "roared", "yelled", "bellowed", "announced", "declared",
    "remarked", "observed", "noted", "commented", "added",
    "continued", "went on", "pursued", "admitted", "confessed",
    "acknowledged", "agreed", "conceded", "protested", "objected",
    "interrupted", "interjected", "urged", "warned", "cautioned",
    "promised", "vowed", "swore", "stammered", "stuttered",
    "babbled", "blurted", "chanted", "recited", "sang",
)

# Build regex alternation from speech verbs
_VERB_PATTERN = "|".join(re.escape(v) for v in SPEECH_VERBS)

# Post-attribution: "Hello," said John. / "Hello," I cried.
_POST_ATTR_RE = re.compile(
    rf'"([^"]+)"\s*[,.]?\s*(?:{_VERB_PATTERN})\s+(I|[A-Za-z][\w\s.]*?)(?:\s*[,;.\-—!?]|$)',
    re.IGNORECASE,
)

# First-person post-attribution: "Stop!" I cried. (verb before speaker)
_FIRST_PERSON_POST_RE = re.compile(
    rf'"([^"]+)"\s*[,.]?\s*(I)\s+(?:{_VERB_PATTERN})(?:\s*[,;.\-—!?]|$)',
    re.IGNORECASE,
)

# Pre-attribution: John said, "Hello." / the old man cried out, "Hello."
_PRE_ATTR_RE = re.compile(
    rf'([\w][\w\s.]*?)\s+(?:{_VERB_PATTERN})(?:\s+\w+){{0,3}}\s*[,:]?\s*(?:--|—)?\s*"([^"]+)"',
    re.IGNORECASE,
)

# Standalone dialogue with no attribution
_DIALOGUE_RE = re.compile(r'"([^"]+)"')

# First-person pronouns that map to narrator
_FIRST_PERSON = {"i", "we"}


def extract_metadata(text: str) -> tuple[str, str]:
    """Extract title and author from the text file header.

    Convention: first non-empty line = title, line matching ^by .+ = author.
    Falls back to ("Untitled", "Unknown Author").
    """
    lines = text.strip().split("\n")
    title = "Untitled"
    author = "Unknown Author"

    # Only treat first line as title if we also find a "by Author" line
    has_by_line = False
    for line in lines:
        stripped = line.strip()
        match = re.match(r"^by\s+(.+)$", stripped, re.IGNORECASE)
        if match:
            author = match.group(1).strip()
            has_by_line = True
            break

    if has_by_line:
        non_empty = [line.strip() for line in lines if line.strip()]
        if non_empty:
            title = non_empty[0]

    return title, author


def _strip_metadata_header(text: str) -> str:
    """Remove title and author lines from the beginning of the text."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    # Skip paragraphs that are the title or "by Author" line
    start_idx = 0
    for i, para in enumerate(paragraphs):
        stripped = para.strip()
        if not stripped:
            continue
        # Check if this is a single-line title or "by ..." line
        lines = stripped.split("\n")
        is_metadata = True
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if re.match(r"^by\s+", line, re.IGNORECASE):
                continue
            # Could be the title (short single line at start)
            if i == 0 and len(lines) <= 2:
                continue
            is_metadata = False
            break
        if is_metadata:
            start_idx = i + 1
        else:
            break
    return "\n\n".join(paragraphs[start_idx:])


def _normalize_speaker(name: str) -> str:
    """Normalize a speaker name: lowercase, strip trailing punctuation/whitespace."""
    name = name.strip().rstrip(".,;:!?—-").strip()
    # Map first-person to narrator
    if name.lower() in _FIRST_PERSON:
        return "narrator"
    return name.lower()


def _split_long_segment(text: str, threshold: int = SEGMENT_SPLIT_THRESHOLD) -> list[str]:
    """Split text longer than threshold at sentence boundaries."""
    if len(text) <= threshold:
        return [text]

    # Split at sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = ""

    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > threshold:
            chunks.append(current.strip())
            current = sentence
        else:
            current = (current + " " + sentence).strip() if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text]


def _extract_from_paragraph(paragraph: str) -> list[Segment]:
    """Extract segments (narration + dialogue) from a single paragraph."""
    segments = []
    text = paragraph.strip()
    if not text:
        return segments

    # Track which character ranges are dialogue
    dialogue_ranges = []

    # Try first-person post-attribution: "Stop!" I cried.
    for match in _FIRST_PERSON_POST_RE.finditer(text):
        quote_text = match.group(1).strip()
        speaker = _normalize_speaker(match.group(2))
        if quote_text:
            dialogue_ranges.append((match.start(), match.end(), quote_text, speaker))

    # Try post-attribution: "Hello," said John.
    for match in _POST_ATTR_RE.finditer(text):
        quote_text = match.group(1).strip()
        speaker = _normalize_speaker(match.group(2))
        if quote_text:
            # Check for overlap with existing ranges
            overlap = False
            for start, end, _, _ in dialogue_ranges:
                if not (match.end() <= start or match.start() >= end):
                    overlap = True
                    break
            if not overlap:
                dialogue_ranges.append((match.start(), match.end(), quote_text, speaker))

    # Try pre-attribution: John said, "Hello."
    for match in _PRE_ATTR_RE.finditer(text):
        speaker = _normalize_speaker(match.group(1))
        quote_text = match.group(2).strip()
        if quote_text:
            # Check for overlap with existing ranges
            overlap = False
            for start, end, _, _ in dialogue_ranges:
                if not (match.end() <= start or match.start() >= end):
                    overlap = True
                    break
            if not overlap:
                dialogue_ranges.append((match.start(), match.end(), quote_text, speaker))

    # If no attributed dialogue found, look for standalone quotes
    if not dialogue_ranges:
        for match in _DIALOGUE_RE.finditer(text):
            quote_text = match.group(1).strip()
            if quote_text:
                dialogue_ranges.append((match.start(), match.end(), quote_text, "unknown"))

    if not dialogue_ranges:
        # Pure narration paragraph
        for chunk in _split_long_segment(text):
            segments.append(Segment(type="narration", text=chunk, speaker="narrator"))
        return segments

    # Sort by position
    dialogue_ranges.sort(key=lambda x: x[0])

    # Extract narration between dialogue blocks
    pos = 0
    for start, end, quote_text, speaker in dialogue_ranges:
        # Narration before this dialogue
        before = text[pos:start].strip()
        # Remove trailing attribution words from narration
        before = re.sub(rf'\s*(?:{_VERB_PATTERN})\s*[,:]?\s*(?:--|—)?\s*$', '', before, flags=re.IGNORECASE).strip()
        before = before.rstrip(".,;:!?—- ").strip()
        if before:
            for chunk in _split_long_segment(before):
                segments.append(Segment(type="narration", text=chunk, speaker="narrator"))

        # The dialogue itself
        for chunk in _split_long_segment(quote_text):
            segments.append(Segment(type="dialogue", text=chunk, speaker=speaker))

        pos = end

    # Narration after last dialogue
    after = text[pos:].strip()
    if after:
        # Clean up leftover attribution words
        after = re.sub(rf'^\s*(?:{_VERB_PATTERN})\s+\w[\w\s.]*?[,;.!?—-]*\s*', '', after, flags=re.IGNORECASE).strip()
        if after:
            for chunk in _split_long_segment(after):
                segments.append(Segment(type="narration", text=chunk, speaker="narrator"))

    return segments


def parse_story(text: str) -> list[Segment]:
    """Parse story text into a list of Segments.

    Strips the metadata header (title + author), then splits on paragraph
    boundaries and extracts dialogue with speaker attribution.
    """
    body = _strip_metadata_header(text)
    paragraphs = re.split(r"\n\s*\n", body)

    all_segments = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        segs = _extract_from_paragraph(para)
        all_segments.extend(segs)

    return all_segments
