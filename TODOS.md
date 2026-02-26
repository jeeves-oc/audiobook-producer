# TODOS

Deferred work items with full context for future pickup.

---

## 1. Validate voice IDs in `set voice` subcommand

**What:** When a user runs `producer.py set <slug> voice "the old man" en-US-FakeVoice`, validate that the voice ID exists in the edge-tts voice pool before writing it to cast.json.

**Why:** Currently, an invalid voice ID is silently written to cast.json. The error only surfaces later during `run` when TTS fails with an opaque edge-tts error message. The user gets no feedback at `set` time that they made a typo. This violates the "fail fast with clear error messages" principle.

**Context:** The `voices.py` module has a hardcoded `VOICE_POOL` list of 14 English voices. The `set voice` subcommand in `cli.py` writes the voice ID directly to `cast.json` via `load_artifact` → update → `write_artifact`. Validation would check the provided voice ID against `VOICE_POOL` (or a broader list from `edge_tts.list_voices()`, though that requires async + network). The simplest approach: validate against `VOICE_POOL` with a warning for unknown IDs (not an error — the user might intentionally use a voice outside the pool).

**Depends on:** Layer 3 (cli.py) must be implemented first. Layer 1b (voices.py) provides the voice pool.

---

## 2. Handle corrupt JSON in `load_artifact()`

**What:** When `load_artifact()` reads a JSON file that has been hand-edited with invalid syntax, it should return a clear error instead of an unhandled `json.JSONDecodeError` traceback.

**Why:** The `set` subcommand loads artifacts, modifies them, and writes them back. If a user hand-edits cast.json (which is explicitly designed to be human-readable and inspectable), a syntax error causes a raw Python traceback. This is a poor experience for a tool designed around user inspection of intermediate files.

**Context:** `load_artifact(project_dir, filename)` in `artifacts.py` uses `json.load()`. The fix is a try/except around the load that catches `json.JSONDecodeError` and prints a clear message like `"Error: cast.json has invalid JSON syntax (line 5, column 12). Fix the file or run 'new' to regenerate."` The `voices.py` module already handles this pattern for `.cast.json` sidecar files (`test_load_cast_malformed_json` → logs warning, returns empty dict).

**Depends on:** Layer 2b (artifacts.py) must be implemented first.
