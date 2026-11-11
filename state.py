"""Atomic, stdlib-only persistence for the design-discovery plugin."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ID = "design-discovery"
_PATH_PART = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_DIMENSIONS = ("typography", "color", "layout", "geometry", "motion")
_TEXT_EVENT_ROLES = {"user", "assistant", "understanding", "dimension_change"}
_CONFIRMATION_EVENT_ROLES = {"lock_confirmation", "approve_confirmation", "export_confirmation"}
_LOG = logging.getLogger(__name__)
_DEFAULT: dict[str, Any] = {
    "schema_version": 1, "active": False, "session_id": "", "rev": 0, "phase": "discovering", "brief": "", "answers": [], "user_messages": [], "assistant_messages": [], "message_events": [], "next_event_id": 1, "understanding": None, "directions": [],
    "working": {dimension: {"source": None, "status": "open"} for dimension in _DIMENSIONS},
    "adjustments": {}, "constraints": [], "sample": None,
    "rejected": {"archetypes": {dimension: [] for dimension in _DIMENSIONS}, "fonts": [], "accents": []}, "conflicts": [], "build_stamp": None, "exported_at": None, "workspace_cwd": None, "export_path": None,
}
_BUILD_STAMP_PATH = Path(__file__).resolve().parent / ".build-stamp.json"


def data_dir() -> Path:
    try:
        from plugins.plugin_storage import plugin_data_dir
        return plugin_data_dir(PLUGIN_ID)
    except Exception:
        home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        path = home / "plugin-data" / PLUGIN_ID
        path.mkdir(parents=True, exist_ok=True)
        return path


def sessions_dir() -> Path:
    return data_dir() / "sessions"


def _valid_session_id(session_id: object) -> str:
    value = str(session_id or "")
    if not _SESSION_ID.fullmatch(value):
        raise ValueError("session_id is required")
    return value


def state_path(session_id: str) -> Path:
    return sessions_dir() / _valid_session_id(session_id) / "state.json"


def tool_events_path(session_id: str) -> Path:
    return sessions_dir() / _valid_session_id(session_id) / "tool-events.jsonl"


def design_md_path(session_id: str) -> Path:
    return sessions_dir() / _valid_session_id(session_id) / "DESIGN.md"


def append_tool_event(session_id: str, event: dict[str, Any]) -> None:
    """Persist a deliberately small audit record, separate from design state."""
    session_id = _valid_session_id(session_id)
    allowed = {"timestamp", "tool", "action", "args", "ok", "error_code", "next_code", "rev", "confirmation"}
    record = {key: value for key, value in event.items() if key in allowed}
    path = tool_events_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def _migrate_global_state() -> None:
    """Preserve the old global file outside the per-session namespace exactly once."""
    source = data_dir() / "state.json"
    if not source.is_file():
        return
    destination = data_dir() / "legacy" / "state.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        _LOG.warning("legacy design-discovery state already exists; leaving global state in place")
        return
    os.replace(source, destination)


def available_session_ids() -> list[str]:
    directory = sessions_dir()
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.iterdir() if path.is_dir() and (path / "state.json").is_file())


def _log_build_stamp_error(path: Path, exc: Exception) -> None:
    try:
        message = f"{datetime.now(timezone.utc).isoformat()} {path}: {type(exc).__name__}: {exc}\n"
        with (data_dir() / "build-stamp-errors.log").open("a", encoding="utf-8") as log:
            log.write(message)
    except OSError:
        pass


def _read_build_stamp(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            return None
        git_sha = str(raw.get("git_sha") or "").strip()
        built_at = str(raw.get("built_at") or "").strip()
        return {"git_sha": git_sha, "built_at": built_at, "dirty": bool(raw.get("dirty"))} if git_sha and built_at else None
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        _log_build_stamp_error(path, exc)
        return None


def build_stamp() -> dict[str, Any] | None:
    return _read_build_stamp(_BUILD_STAMP_PATH)


LOADED_BUILD_STAMP = build_stamp()


def _normalise(raw: object) -> dict[str, Any]:
    state = json.loads(json.dumps(_DEFAULT))
    if isinstance(raw, dict):
        state.update(raw)
        if "adjustments" not in raw and isinstance(raw.get("overrides"), dict):
            legacy = raw["overrides"]
            state["adjustments"] = {path: {"value": legacy[key], "source": "agent"} for key, path in (("accent", "color.accent"), ("display_font", "typography.display_font"), ("body_font", "typography.body_font")) if legacy.get(key) is not None}
    state["schema_version"] = 1
    state["rev"] = state["rev"] if isinstance(state.get("rev"), int) and state["rev"] >= 0 else 0
    state["active"] = bool(state.get("active"))
    state["session_id"] = str(state.get("session_id") or "")[:200]
    state["brief"] = str(state.get("brief") or "")[:4000]
    state["answers"] = state.get("answers") if isinstance(state.get("answers"), list) else []
    state["user_messages"] = [item for item in state.get("user_messages", []) if isinstance(item, str)][-50:]
    state["assistant_messages"] = [item for item in state.get("assistant_messages", []) if isinstance(item, str)][-50:]
    events, next_event_id = [], 1
    for item in state.get("message_events", []):
        if not isinstance(item, dict): continue
        role = item.get("role")
        event_id = item.get("id")
        if not isinstance(event_id, int) or isinstance(event_id, bool) or event_id < next_event_id: event_id = next_event_id
        next_event_id = event_id + 1
        if role in _TEXT_EVENT_ROLES and isinstance(item.get("text"), str):
            event = {"role": role, "id": event_id, "text": item["text"]}
            if role == "dimension_change" and item.get("dimension") in _DIMENSIONS: event["dimension"] = item["dimension"]
            if role == "understanding" and isinstance(item.get("confirmed_reply"), str): event["confirmed_reply"] = item["confirmed_reply"]
            if role == "user" and item.get("source") == "clarify": event["source"] = "clarify"
            events.append(event)
        elif role in _CONFIRMATION_EVENT_ROLES and isinstance(item.get("message_index"), int) and not isinstance(item.get("message_index"), bool) and (isinstance(item.get("scope"), str) or isinstance(item.get("scope"), list) and all(isinstance(value, str) for value in item["scope"])):
            events.append({"role": role, "id": event_id, "message_event_id": item["message_index"], "scope": item["scope"]})
        elif role in _CONFIRMATION_EVENT_ROLES and isinstance(item.get("message_event_id"), int) and not isinstance(item.get("message_event_id"), bool) and (isinstance(item.get("scope"), str) or isinstance(item.get("scope"), list) and all(isinstance(value, str) for value in item["scope"])):
            events.append({"role": role, "id": event_id, "message_event_id": item["message_event_id"], "scope": item["scope"]})
    state["message_events"] = events[-100:]
    state["next_event_id"] = max(next_event_id, state["message_events"][-1]["id"] + 1 if state["message_events"] else 1)
    state["understanding"] = state.get("understanding") if isinstance(state.get("understanding"), dict) and isinstance(state["understanding"].get("summary"), str) else None
    state["directions"] = state.get("directions") if isinstance(state.get("directions"), list) else []
    for direction in state["directions"]:
        if not isinstance(direction, dict) or "adjustments" in direction or not isinstance(direction.get("overrides"), dict):
            continue
        legacy = direction.pop("overrides")
        direction["adjustments"] = {path: {"value": legacy[key], "source": "agent"} for key, path in (("accent", "color.accent"), ("display_font", "typography.display_font"), ("body_font", "typography.body_font")) if legacy.get(key) is not None}
    state["adjustments"] = state.get("adjustments") if isinstance(state.get("adjustments"), dict) else {}
    state["constraints"] = state.get("constraints") if isinstance(state.get("constraints"), list) else []
    state["sample"] = state.get("sample") if isinstance(state.get("sample"), dict) else None
    state["phase"] = state.get("phase") if state.get("phase") in {"discovering", "directions", "refining", "final"} else "discovering"
    return state


def _valid_loaded_state(raw: object, session_id: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or raw.get("session_id") != session_id:
        return None
    try:
        state = _normalise(raw)
        from .design_core import blank_rejected, validate_direction
        for direction in state["directions"]:
            validate_direction(direction, blank_rejected(), [], state["user_messages"])
        return state
    except (KeyError, TypeError, ValueError):
        return None


def _with_stamps(state: dict[str, Any]) -> dict[str, Any]:
    state["build_stamp"] = build_stamp()
    state["loaded_stamp"] = LOADED_BUILD_STAMP
    return state


def get_state(session_id: str | None = None) -> dict[str, Any]:
    _migrate_global_state()
    if not session_id:
        return _with_stamps(_normalise({}))
    session_id = _valid_session_id(session_id)
    try:
        raw = json.loads(state_path(session_id).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        return _with_stamps(_normalise({}))
    loaded = _valid_loaded_state(raw, session_id)
    return _with_stamps(loaded if loaded is not None else _normalise({}))


def has_valid_state(session_id: str) -> bool:
    try:
        session_id = _valid_session_id(session_id)
        raw = json.loads(state_path(session_id).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return False
    return _valid_loaded_state(raw, session_id) is not None


def save_state(state: dict[str, Any], session_id: str) -> dict[str, Any]:
    _migrate_global_state()
    session_id = _valid_session_id(session_id)
    persisted = dict(state)
    persisted.pop("build_stamp", None)
    persisted.pop("loaded_stamp", None)
    if persisted.get("session_id") != session_id:
        raise ValueError("state session_id does not match the current session")
    cleaned = _normalise(persisted)
    cleaned["rev"] += 1
    path = state_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    last_error = None
    for attempt in range(10):
        try:
            os.replace(temporary, path)
            last_error = None
            break
        except PermissionError as exc:
            last_error = exc
            if attempt < 9: time.sleep(.02 * (attempt + 1))
    if last_error is not None:
        try: temporary.unlink(missing_ok=True)
        except OSError: pass
        raise last_error
    return cleaned


def _set_path(state: dict[str, Any], field_path: str, value: Any) -> None:
    parts = field_path.split(".")
    if not parts or any(not _PATH_PART.fullmatch(part) for part in parts):
        raise ValueError("field_path must contain dot-separated identifier names")
    target: dict[str, Any] = state
    for part in parts[:-1]:
        child = target.get(part)
        if not isinstance(child, dict):
            child = {}
            target[part] = child
        target = child
    target[parts[-1]] = value


def apply_patch(field_path: str, value: Any, session_id: str, expected_rev: int | None = None) -> dict[str, Any]:
    state = get_state(session_id)
    state.pop("build_stamp", None)
    state.pop("loaded_stamp", None)
    if expected_rev is not None and expected_rev != state["rev"]:
        raise RuntimeError("revision conflict")
    _set_path(state, field_path, value)
    save_state(state, session_id)
    return get_state(session_id)


def replace_state(state: dict[str, Any], session_id: str) -> dict[str, Any]:
    save_state(state, session_id)
    return get_state(session_id)



def fresh_state() -> dict[str, Any]:
    return _normalise({})
