"""Hermes Design Discovery plugin: revisioned design-session state."""
from __future__ import annotations
import colorsys, json, os, re, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
_ROOT = str(Path(__file__).resolve().parent)
if _ROOT not in sys.path: sys.path.insert(0, _ROOT)
from contrast import report as contrast_report
from design_core import ADJUSTMENT_PATHS, DIMENSIONS, VOCABULARY, archetypes, auto_correct_composed_palette, catalog, color_variety_error, detect_conflicts, enums, filter_composed_words, fonts, resolve_direction, validate_adjustments, validate_direction
from state import append_tool_event, design_md_path, fresh_state, get_state, replace_state
TYPOGRAPHY_VARIETY_ENABLED = True

GENERATE_SCHEMA = {"name":"generate_directions","description":"Validate and store exactly three directions after recorded understanding and user confirmation. Example sample: {title: Morning bake list, body: Fresh loaves ready for pickup, items: [{label: Country loaf, status: success, status_label: Ready}, {label: Cardamom bun, status: warning, status_label: Limited}], primary: Order bakes, secondary: View menu}.","parameters":{"type":"object","properties":{"directions":{"type":"array","items":{"type":"object","properties":{"voice":{"type":"object","properties":{"tone":{"type":"string","maxLength":60},"do":{"type":"array","minItems":3,"maxItems":3,"items":{"type":"string","maxLength":30}},"dont":{"type":"array","minItems":3,"maxItems":3,"items":{"type":"string","maxLength":30}},"example":{"type":"string","maxLength":100}},"required":["tone","do","dont","example"]}}}},"brief":{"type":"string"},"answers":{"type":"array"},"sample":{"type":"object","properties":{"title":{"type":"string","maxLength":40},"body":{"type":"string","maxLength":140},"items":{"type":"array","minItems":2,"maxItems":2,"items":{"type":"object","properties":{"label":{"type":"string","maxLength":28},"status":{"type":"string","enum":["success","warning","neutral"]},"status_label":{"type":"string","maxLength":18}},"required":["label","status","status_label"]}},"primary":{"type":"string","maxLength":20},"secondary":{"type":"string","maxLength":20}},"required":["title","body","items","primary","secondary"]},"confirmed_by_user":{"type":"string"}},"required":["directions","confirmed_by_user"]}}
GENERATE_SCHEMA = {"name":"generate_directions","description":"Validate and store exactly three directions after recorded understanding and user confirmation. Example sample: {title: Morning bake list, body: Fresh loaves ready for pickup, items: [{label: Country loaf, status: success, status_label: Ready}, {label: Cardamom bun, status: warning, status_label: Limited}], primary: Order bakes, secondary: View menu}.","parameters":{"type":"object","properties":{"directions":{"type":"array","items":{"type":"object","properties":{"voice":{"type":"object","description":"Optional voice: tone is up to 60 characters, do and dont are three lines up to 48 characters each, and example is up to 100 characters.","properties":{"tone":{"type":"string"},"do":{"type":"array","items":{"type":"string"}},"dont":{"type":"array","items":{"type":"string"}},"example":{"type":"string"}}}}}},"brief":{"type":"string"},"answers":{"type":"array"},"sample":{"type":"object","description":"Optional specimen: title up to 40 characters, body up to 140, two items with label up to 28 and status_label up to 18, and primary and secondary up to 20.","properties":{"title":{"type":"string"},"body":{"type":"string"},"items":{"type":"array","items":{"type":"object","properties":{"label":{"type":"string"},"status":{"type":"string","enum":["success","warning","neutral"]},"status_label":{"type":"string"}}}},"primary":{"type":"string"},"secondary":{"type":"string"}}},"confirmed_by_user":{"type":"string"}},"required":["directions","confirmed_by_user"]}}
UNDERSTANDING_SCHEMA = {"name":"record_understanding","description":"Record a plain-language, two-sentence playback of what the user wants before directions are generated.","parameters":{"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"]}}
UPDATE_SCHEMA = {"name":"update_choice","description":"Try, approve, or lock directions; adjust tokens; reject values; or manage constraints. Example try: {\"action\":\"try\",\"directions\":{\"typography\":\"dir-a\",\"color\":\"option 2\"}}. Approve unchanged direction: {\"action\":\"approve_direction\",\"direction\":\"1\",\"confirmed_by_user\":\"I am happy with it\"}. Described accent: {\"action\":\"adjust\",\"path\":\"color.accent\",\"value\":\"#C65A22\",\"source\":\"described\",\"user_words\":\"orange like a tangerine\"}.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["try","approve_direction","lock","unlock","reject","clear_reject","adjust","add_constraint","remove_constraint"],"description":"Required action."},"dimension":{"type":"string","enum":list(DIMENSIONS),"description":"Dimension for lock, unlock, reject, or clear_reject."},"direction_id":{"type":"string","description":"Direction reference for lock or unlock."},"direction":{"type":"string","description":"Direction id, exact label, or ordinal for approve_direction."},"directions":{"type":"object","additionalProperties":{"type":"string"},"description":"Dimension-to-direction references for try."},"archetype_id":{"type":"string","description":"Archetype id for reject or clear_reject."},"path":{"type":"string","enum":list(ADJUSTMENT_PATHS),"description":"Supported token path for adjust."},"value":{"description":"Replacement value for adjust, or null to remove."},"source":{"type":"string","enum":["agent","user","direction","described"],"description":"Provenance for adjust."},"from_direction":{"type":"string","description":"Direction reference when borrowing an accent."},"user_words":{"type":"string","description":"Exact user color words for described accents."},"constraint":{"type":"object","description":"Constraint object for add_constraint."},"constraint_id":{"type":"string","description":"Constraint id for remove_constraint."},"confirmed_by_user":{"type":"string","description":"Exact user approval for approve_direction, lock, reject, or add_constraint."}},"required":["action"]}}
EXPORT_SCHEMA = {"name":"export_design_md","description":"Export deterministic DESIGN.md once all dimensions are locked.","parameters":{"type":"object","properties":{"confirmed_by_user":{"type":"string"},"folder":{"type":"string","description":"An existing folder path the user typed."}},"required":["confirmed_by_user"]}}
GET_STATE_SCHEMA = {"name":"design_discovery_get_state","description":"Read the authoritative persistent design state, resolved directions, and catalog. Example: {} returns catalog.archetypes and catalog.fonts; use adjustments in the exact shape {\"typography.display_font\":{\"value\":\"inter\",\"source\":\"agent\"}}. This read-only tool has no confirmed_by_user parameter.","parameters":{"type":"object","properties":{}}}
_RECENT_USER_MESSAGES: dict[str, list[str]] = {}
_RECENT_ASSISTANT_MESSAGES: dict[str, list[str]] = {}
_RECENT_MESSAGE_EVENTS: dict[str, list[dict]] = {}
_CONFIRMATION_ERROR = "Ask the user to approve this in their own words, then pass their exact words as confirmed_by_user."
_NEXT_GET_STATE = "Ask the user what they’re making, who it’s for, how it should feel, and what they don’t want. Then call record_understanding with what you understood, show it to the user, and wait for them to confirm before generating directions."
_NEXT_INTERVIEW = "Ask the user at least one round of questions (what it's for, how it should feel, what to avoid), then wait for their reply."
_NO_INTERNALS = " Keep the reply focused on the selected direction and its design, using plain language rather than implementation terms."
_NEXT_GENERATE = "Describe each direction in one plain sentence and tell the user the pane shows them. Ask which is closest and what they would change, then stop. Do not recommend one. Do not offer to build, mock up, or render anything outside the pane. Do not lock anything until the user says so. Never name archetypes or design systems; describe what each direction does. When the user likes a direction but wants a change, use try for that whole direction, then adjust only what they asked for. Never lock until they approve what the pane shows."
_NEXT_UPDATE = "Tell the user in one sentence what changed and that the pane shows it. Ask what they think, then stop."
_NEXT_TRY = "Tell the user in one sentence what you combined and that the pane shows it at the top. Ask what they think, then stop. If they approve the whole direction, use approve_direction, not lock."
_NEXT_BORROWED_ACCENT = "Tell the user in one sentence which color you borrowed and from which direction, and that the pane shows it. Ask what they think, then stop."
_NEXT_ACCENT_CONTRAST = "Describe the color’s legibility in plain words and offer the closest option that works. Use design language rather than implementation details."
_NEXT_CONFIRMATION = "Ask the user in plain words whether they want this. Do not suggest wording for their reply."
_NEXT_EXPORT = "Tell the user DESIGN.md is ready in the pane. Point them to Copy DESIGN.md and say it was saved at the returned path. Do not write or link to files yourself."
_NEXT_UNDERSTANDING = "Show the user this summary in your own words and ask if it’s right. Then stop and wait for their reply."
_NEXT_MISSING_UNDERSTANDING = "Nothing was generated. Call record_understanding with what you understood, show it to the user, and wait for their reply. Never describe directions that haven’t been generated."
_NEXT_UNCONFIRMED_UNDERSTANDING = "Nothing was generated. An understanding was recorded, but no confirmation of it is on record. If the user has already confirmed it, call record_understanding with the summary you showed them, then call generate_directions with their reply, word for word, as confirmed_by_user. If they have not replied yet, show them the summary and wait for their reply."
_NEXT_MISSING_UNDERSTANDING_CONFIRMATION = "The user has replied to the summary. Call generate_directions with that reply, word for word, as confirmed_by_user. Do not call record_understanding again."
_NEXT_QUOTED_CONSENT = "Ask the user in your own words whether they approve. Do not suggest how to reply, then wait."
_NEXT_GENERIC_REFUSAL = "Resolve this within the design workflow when possible. If input is needed, ask in plain words. Keep the reply about the design and report only completed changes."
_NEXT_RENAME = "Rename the direction to describe what it does. Never use starting point names."
_NEXT_UNSEEN = "The user hasn’t seen this yet. Use try to show it, tell them the pane shows it, and wait for their reply."
_NEXT_UNEXPECTED_ARGUMENT = "Remove the unexpected argument. Valid fields include action, dimension, direction, direction_id, directions, path, value, source, and confirmed_by_user."
_NEXT_DESCRIBED_ACCENT = "Tell the user in one sentence that you matched the color they described and the pane shows it. Ask if it’s the shade they meant, then stop. If they approve the whole direction, use approve_direction, not lock."
_NEXT_CONFIRMATION_MISMATCH = "Pass the user’s reply exactly as they wrote it as confirmed_by_user."
_NEXT_AWAITING_UNDERSTANDING_REPLY = "The user hasn’t replied yet. Show them your understanding and wait for their reply."
_NEXT_ALREADY_CONFIRMED_UNDERSTANDING = "The understanding is already confirmed. Call generate_directions with the user’s reply as confirmed_by_user. Do not call record_understanding again."
_NEXT_NO_CHANGE = "Report only the changes listed; if none, ask the user what they meant."
_NEXT_NOTHING_REMOVE = "Nothing to remove; the pane is unchanged."
_NEXT_CHANGED = "Tell the user exactly these changes in plain words, nothing else, then stop."
_NEXT_ALREADY_LOCKED = "This dimension is already locked. Move on to the next unlocked dimension, or export DESIGN.md if all dimensions are locked."
_NEXT_ALREADY_UNLOCKED = "This dimension is already unlocked. Choose a direction to show the user, or ask what they want to change."
_NEXT_ALREADY_SHOWN = "The pane already shows this combination. Tell the user what they see and ask what they would change."
_NEXT_SHORT_DIRECTION_NAME = "Give this direction a short name of 2 to 4 words that describes what it does."
_NEXT_INVALID_ACCENT = "Nothing changed. Use a valid color value that fits the current direction, or use the user’s exact color words."
_NEXT_MISSING_DESCRIBED_WORDS = "Nothing changed. Pass the user’s exact color words as user_words, then try again."
_NEXT_DESCRIBED_ACCENT_SOURCE = "Nothing changed. To match a color the user described, use source described with their exact words as user_words."
_NEXT_SHARED_ACCENT = "These directions share this accent. If the user named a color, use source described with their exact words as user_words."
_NEXT_SIMILAR_COLORS = "Create directions that differ in color in a way the user would notice."
_NO_INTERVIEW = "The user hasn't answered any interview questions yet. Ask what they're making and how it should feel, then wait."
_UPDATE_ARGUMENTS = {
    "try": {"action", "directions"}, "approve_direction": {"action", "direction", "confirmed_by_user"},
    "lock": {"action", "dimension", "direction_id", "confirmed_by_user"},
    "unlock": {"action", "dimension", "direction_id"},
    "reject": {"action", "dimension", "archetype_id", "confirmed_by_user"},
    "clear_reject": {"action", "dimension", "archetype_id"},
    "adjust": {"action", "path", "value", "source", "from_direction", "user_words"},
    "add_constraint": {"action", "constraint", "confirmed_by_user"},
    "remove_constraint": {"action", "constraint_id"},
}

def _clean(state): state.pop("build_stamp", None); state.pop("loaded_stamp", None); return state
def _validate_text(value, field, limit, no_dashes=False):
    invalid_dash = "–" in value or "—" in value or (no_dashes and "-" in value) if isinstance(value, str) else False
    if not isinstance(value, str) or not value or len(value) > limit or invalid_dash: raise ValueError(field + " must be 1 to " + str(limit) + " characters with no " + ("dashes" if no_dashes else "em or en dash"))
def _validate_sample(sample):
    if sample is None: return None
    if not isinstance(sample, dict) or set(sample) != {"title", "body", "items", "primary", "secondary"}: raise ValueError("sample must contain title, body, items, primary, and secondary")
    for key, limit in (("title",40),("body",140),("primary",20),("secondary",20)): _validate_text(sample[key], "sample." + key, limit)
    if not isinstance(sample["items"], list) or len(sample["items"]) != 2: raise ValueError("sample.items must contain exactly two items")
    for item in sample["items"]:
        if not isinstance(item, dict) or set(item) != {"label","status","status_label"} or item["status"] not in {"success","warning","neutral"}: raise ValueError("sample item requires label, status, and status_label")
        _validate_text(item["label"], "sample.items.label", 28); _validate_text(item["status_label"], "sample.items.status_label", 18)
    return sample
def _validate_voice(voice):
    if voice is None: return None
    if not isinstance(voice, dict) or set(voice) != {"tone","do","dont","example"}: raise ValueError("voice must contain tone, do, dont, and example")
    _validate_text(voice["tone"], "voice.tone", 60, no_dashes=True); _validate_text(voice["example"], "voice.example", 100, no_dashes=True)
    for key in ("do","dont"):
        if not isinstance(voice[key], list) or len(voice[key]) != 3: raise ValueError("voice." + key + " must contain exactly three items")
        for value in voice[key]: _validate_text(value, "voice." + key, 30, no_dashes=True)
    return voice
def _lenient_sample(sample, warnings):
    if sample is None: return None
    if not isinstance(sample, dict) or not {"title", "body", "items", "primary", "secondary"} <= set(sample):
        warnings.append("Dropped invalid sample; the fixed specimen content will be used.")
        return None
    def text(value, limit): return _lenient_text(value, limit, warnings, "sample")
    items = sample.get("items") if isinstance(sample.get("items"), list) else []
    normal_items = []
    for item in items[:2]:
        if isinstance(item, dict) and item.get("status") in {"success", "warning", "neutral"}:
            label, status_label = text(item.get("label"), 28), text(item.get("status_label"), 18)
            if label: normal_items.append({"label": label, "status": item["status"], "status_label": status_label or "Open"})
    title = text(sample.get("title"), 40)
    if not title and not normal_items:
        warnings.append("Dropped unusable sample; the fixed specimen content will be used.")
        return None
    while len(normal_items) < 2:
        normal_items.append({"label": "Example item", "status": "neutral", "status_label": "Open"})
        warnings.append("Padded sample items with fixed specimen content.")
    return {"title": title or "Example specimen", "body": text(sample.get("body"), 140) or "Example content.", "items": normal_items, "primary": text(sample.get("primary"), 20) or "Primary action", "secondary": text(sample.get("secondary"), 20) or "Secondary action"}
def _lenient_text(value, limit, warnings, kind):
    text = value if isinstance(value, str) else ""
    if "—" in text or "–" in text:
        pieces = re.split(r"([—–])", text)
        normalized = []
        for index, piece in enumerate(pieces):
            if piece not in {"—", "–"}: normalized.append(piece); continue
            normalized.append(", " if pieces[index - 1].strip() and pieces[index + 1].strip() else " ")
        text = "".join(normalized)
        warnings.append("Replaced dashes in " + kind + " content.")
    if len(text) <= limit: return text.strip()
    clipped = text[:limit + 1].rsplit(" ", 1)[0].rstrip() or text[:limit]
    warnings.append("Trimmed " + kind + " content to its display limit.")
    return clipped
def _lenient_voice(direction, warnings):
    if "voice" not in direction: return
    voice = direction["voice"]
    if not isinstance(voice, dict) or not isinstance(voice.get("tone"), str) or not isinstance(voice.get("example"), str):
        direction.pop("voice", None)
        warnings.append("Dropped invalid voice for " + str(direction.get("label", "a direction")) + "; the typography voice will be used.")
        return
    if any("-" in value for key in ("tone", "example", "do", "dont") for value in (voice.get(key, []) if isinstance(voice.get(key), list) else [voice.get(key)]) if isinstance(value, str)):
        direction.pop("voice", None)
        warnings.append("Dropped invalid voice for " + str(direction.get("label", "a direction")) + "; the typography voice will be used.")
        return
    def trim(value, limit): return _lenient_text(value, limit, warnings, "voice")
    result = {"tone": trim(voice["tone"], 60), "example": trim(voice["example"], 100)}
    for key, fallback in (("do", "Keep it clear"), ("dont", "Use empty jargon")):
        values = voice.get(key) if isinstance(voice.get(key), list) else []
        result[key] = [trim(value, 48) for value in values if isinstance(value, str) and value][:3]
        while len(result[key]) < 3:
            result[key].append(fallback)
            warnings.append("Padded voice." + key + " to three lines.")
    if not result["tone"] or not result["example"]:
        direction.pop("voice", None)
        warnings.append("Dropped invalid voice for " + str(direction.get("label", "a direction")) + "; the typography voice will be used.")
    else:
        direction["voice"] = result
def _lenient_words(direction, warnings):
    palette = direction.get("composed_palette")
    if not isinstance(palette, dict) or "words" not in palette: return
    kept, dropped = filter_composed_words(palette["words"])
    if dropped:
        palette["words"] = kept
        warnings.append("Dropped unknown composed palette words for " + str(direction.get("label", "a direction")) + ": " + ", ".join(dropped) + ".")
def _valid_values(path):
    kind = ADJUSTMENT_PATHS[path]
    return list(fonts()) if kind in {"display", "body"} else list(enums()[kind]["enum"])
def _source_value(direction, path):
    dimension, key = path.split(".", 1)
    source = direction["sources"][dimension]
    return archetypes()[source][dimension][key]
def _lenient_direction_values(direction, warnings, user_messages=None):
    available = archetypes(); sources = direction.get("sources")
    if not isinstance(sources, dict): return
    palette_keys = {"background", "surface", "text", "muted", "border", "border_strong", "accent", "words"}
    color_source, palette = sources.get("color"), direction.get("composed_palette")
    usable_palette = isinstance(palette, dict) and set(palette) == palette_keys
    if palette is not None and color_source != "composed:" + str(direction.get("id")) and usable_palette:
        sources["color"] = "composed:" + str(direction.get("id"))
        warnings.append("Used composed_palette for color; replaced archetype source " + repr(color_source) + ".")
    elif isinstance(color_source, str) and color_source.startswith("composed:") and not usable_palette:
        other = [value for dimension, value in sources.items() if dimension != "color" and value in available]
        kept = max(set(other), key=other.count) if other else next(iter(available))
        sources["color"] = kept; direction.pop("composed_palette", None)
        warnings.append("Dropped unusable composed_palette; kept color source " + repr(kept) + ". Valid values: " + ", ".join(available) + ".")
    for dimension in DIMENSIONS:
        source = sources.get(dimension)
        if dimension == "color" and isinstance(source, str) and source.startswith("composed:"): continue
        if source in available: continue
        other = [value for other_dimension, value in sources.items() if other_dimension != dimension and value in available]
        kept = max(set(other), key=other.count) if other else next(iter(available))
        warnings.append("Dropped sources." + dimension + " value " + repr(source) + "; kept " + repr(kept) + ". Valid values: " + ", ".join(available) + ".")
        sources[dimension] = kept
    adjustments = direction.get("adjustments")
    if not isinstance(adjustments, dict): return
    for path, entry in list(adjustments.items()):
        if path not in ADJUSTMENT_PATHS or not isinstance(entry, dict): continue
        if entry.get("source") == "user" and not any(str(entry.get("value")).casefold() in message.casefold() for message in (user_messages or [])):
            entry["source"] = "agent"
            warnings.append("Recorded " + path + " value " + repr(entry.get("value")) + " as agent because it was not found in user messages.")
        kind, value = ADJUSTMENT_PATHS[path], entry.get("value")
        if (kind in {"display", "body"} and value not in fonts()) or (kind not in {"display", "body", "accent"} and value not in enums()[kind]["enum"]):
            kept, valid = _source_value(direction, path), _valid_values(path)
            warnings.append("Dropped " + path + " value " + repr(value) + "; kept " + repr(kept) + ". Valid values: " + ", ".join(map(str, valid)) + ".")
            adjustments.pop(path)
    accent = adjustments.get("color.accent")
    color_source = sources.get("color")
    if isinstance(accent, dict) and accent.get("source") == "agent" and color_source in available:
        valid = available[color_source]["color"]["accent_alternates"]
        if accent.get("value") not in valid:
            kept = available[color_source]["color"]["accent"]
            warnings.append("Dropped color.accent value " + repr(accent.get("value")) + "; kept " + repr(kept) + ". Valid values: " + ", ".join(valid) + ".")
            adjustments.pop("color.accent")
def _public_conflicts(conflicts):
    ordered = sorted(conflicts, key=lambda item: item["severity"] != "clash")[:2]
    return [{"tradeoff": item["tradeoff"], "resolution": item["resolution"]} for item in ordered]
def _working_direction(state):
    color = state["working"]["color"]
    direction = {"id":"working","label":"Working direction","rationale":state["brief"],"sources":{dimension: state["working"][dimension]["source"] for dimension in DIMENSIONS},"adjustments":state["adjustments"]}
    if color.get("palette"):
        direction["composed_palette"] = dict(color["palette"])
    typography = state["working"]["typography"]
    if isinstance(typography.get("voice"), dict):
        direction["voice"] = dict(typography["voice"])
    return direction
def _sources(state): return {dimension: state["working"][dimension]["source"] for dimension in DIMENSIONS}
def _direction(state, direction_id): return next((item for item in state["directions"] if item["id"] == direction_id), None)
def _direction_reference_error(state, value):
    if not state["directions"]: return "No directions have been generated yet. Call generate_directions first before referring to a direction."
    choices = ", ".join(str(index + 1) + " (" + item["label"] + ", " + item["id"] + ")" for index, item in enumerate(state["directions"]))
    return "Unknown direction reference " + repr(value) + ". Valid directions: " + choices
def _direction_by_reference(state, value):
    if not isinstance(value, str): return None
    exact_id = _direction(state, value)
    exact_label = next((item for item in state["directions"] if item["label"].casefold() == value.casefold()), None)
    if exact_id or exact_label: return exact_id or exact_label
    match = re.fullmatch(r"(?:option\s+|the\s+)?(first|second|third|[1-9]\d*)(?:\s+one)?", value.strip().casefold())
    if not match: return None
    token = match.group(1)
    ordinal = {"first": 1, "second": 2, "third": 3}.get(token, int(token) if token.isdigit() else 0)
    return state["directions"][ordinal - 1] if 1 <= ordinal <= len(state["directions"]) else None
class _Guidance(Exception):
    """A recoverable update_choice problem: nothing changes and the next text says how to proceed."""
_REFERENCE_EXAMPLES = {
    "try": '{"action":"try","directions":{"color":"2"}}',
    "approve_direction": '{"action":"approve_direction","direction":"2","confirmed_by_user":"<the words the user wrote>"}',
    "lock": '{"action":"lock","dimension":"color","direction_id":"2","confirmed_by_user":"<the words the user wrote>"}',
    "unlock": '{"action":"unlock","dimension":"color","direction_id":"2"}',
    "adjust": '{"action":"adjust","path":"color.accent","value":"<accent hex of that direction>","source":"direction","from_direction":"2"}',
}
def _reference_matches(state, value):
    text = value.casefold()
    matches = set()
    for token in re.findall(r"\b(first|second|third|\d+)\b", text):
        ordinal = {"first": 1, "second": 2, "third": 3}.get(token, int(token) if token.isdigit() else 0)
        if not 1 <= ordinal <= len(state["directions"]): return set()
        matches.add(state["directions"][ordinal - 1]["id"])
    for item in state["directions"]:
        if re.search(r"(?<![\w-])" + re.escape(item["id"].casefold()) + r"(?![\w-])", text) or re.search(r"\b" + re.escape(item["label"].casefold()) + r"\b", text): matches.add(item["id"])
    return matches
def _resolve_reference(state, value, action, warnings):
    direction = _direction_by_reference(state, value)
    if direction: return direction
    if not state["directions"]: raise ValueError(_direction_reference_error(state, value))
    matches = _reference_matches(state, value) if isinstance(value, str) else set()
    if len(matches) == 1:
        index, direction = next((index, item) for index, item in enumerate(state["directions"]) if item["id"] in matches)
        warnings.append("Read direction reference " + repr(value) + " as " + str(index + 1) + " (" + direction["label"] + ", " + direction["id"] + ").")
        return direction
    choices = ", ".join(str(index + 1) + " (" + item["label"] + ", " + item["id"] + ")" for index, item in enumerate(state["directions"]))
    raise _Guidance("Nothing changed. The direction reference " + repr(value) + " did not match one direction. Use a number, label or id from this list: " + choices + ". Example call: " + _REFERENCE_EXAMPLES.get(action, _REFERENCE_EXAMPLES["try"]))
def _set_working(state, dimension, direction, status):
    value = {"source":direction["sources"][dimension], "status":status, "direction_id":direction["id"]}
    if dimension == "color" and direction["sources"]["color"].startswith("composed:"):
        value["palette"] = dict(direction["composed_palette"])
    if dimension == "typography" and isinstance(direction.get("voice"), dict):
        value["voice"] = dict(direction["voice"])
    state["working"][dimension] = value
    # A current user decision remains authoritative, but otherwise the selected
    # card's adjustment is part of the direction and must travel with it.
    retained = {path: entry for path, entry in state["adjustments"].items()
                if path.split(".", 1)[0] == dimension and entry.get("source") in {"user", "described", "direction"}}
    for path in [path for path in state["adjustments"] if path.split(".", 1)[0] == dimension]: state["adjustments"].pop(path)
    state["adjustments"].update({path: dict(entry) for path, entry in direction.get("adjustments", {}).items() if path.split(".", 1)[0] == dimension})
    state["adjustments"].update(retained)
def _append_event(state, event):
    event = {**event, "id": state.get("next_event_id", 1)}
    state["next_event_id"] = event["id"] + 1
    state["message_events"] = [*state.get("message_events", []), event][-100:]
    return event
def _record_dimension_change(state, dimension): _append_event(state, {"role":"dimension_change","text":dimension,"dimension":dimension})
def _fill_unset_dimensions(state, direction, record=True):
    filled = []
    for dimension in DIMENSIONS:
        if not state["working"][dimension]["source"]:
            _set_working(state, dimension, direction, "open")
            if record: _record_dimension_change(state, dimension)
            filled.append(dimension)
    return filled
def _enforce_working(state):
    if all(_sources(state).values()): validate_direction(_working_direction(state), state["rejected"], state["constraints"], state["user_messages"])
def _user_decisions(state):
    labels = {direction["id"]: direction["label"] for direction in state["directions"]}
    return [{"path": path, **item, **({"from_direction_label": labels.get(item.get("from_direction"), item.get("from_direction"))} if item.get("source") == "direction" else {})} for path, item in state["adjustments"].items() if item["source"] in {"user", "described", "direction"}]
def _normal(value): return re.sub(r"[^a-z0-9]+", "", str(value).casefold())
def _contrast_safe_accent(value, background):
    from contrast import contrast_ratio
    if contrast_ratio(value, background) >= 3: return value, None
    rgb = tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))
    hue, lightness, saturation = colorsys.rgb_to_hls(*rgb)
    background_rgb = tuple(int(background[index:index + 2], 16) / 255 for index in (1, 3, 5))
    background_lightness = colorsys.rgb_to_hls(*background_rgb)[1]
    direction = -1 if background_lightness >= .5 else 1
    for step in range(1, 101):
        candidate_lightness = lightness + direction * step / 100
        if not 0 <= candidate_lightness <= 1: break
        candidate_rgb = colorsys.hls_to_rgb(hue, candidate_lightness, saturation)
        candidate = "#" + "".join(f"{round(channel * 255):02X}" for channel in candidate_rgb)
        if contrast_ratio(candidate, background) >= 3: return candidate, "deepened" if direction < 0 else "lightened"
    return None, None
def _contains(message, value): return _normal(value) in _normal(message)
def _check_arguments(args, allowed):
    if not isinstance(args, dict): raise ValueError("arguments must be an object")
    unexpected = next((key for key in args if key not in allowed), None)
    if unexpected is not None: raise ValueError(f"unexpected argument: {unexpected}")
def _append_message(state, role, message):
    key = f"{role}_messages"
    state[key] = [*state.get(key, []), message][-50:]
    return _append_event(state, {"role":role,"text":message})
def _quoted_by_assistant(state, value):
    if not state.get("assistant_messages"): return False
    if _normal(value) in {"yes", "yep", "yeah", "ok", "okay", "sure", "correct", "thatsright", "thatisright", "soundsgood", "looksgood", "goahead", "yesplease", "okayplease", "okplease", "sureplease"}: return False
    quoted = re.findall(r'[“"]([^”"]+)[”"]', state["assistant_messages"][-1])
    return any(_contains(part, value) for part in quoted)
def _confirmation(state, value):
    matching = next((event for event in reversed(state["message_events"]) if event.get("role") == "user" and _contains(event.get("text", ""), value)), None)
    if not isinstance(value, str) or matching is None:
        raise ValueError(_CONFIRMATION_ERROR)
    if _quoted_by_assistant(state, value): raise ValueError("confirmation was suggested by the assistant")
    return matching["id"]

def _record_confirmation(state, message_event_id, scope, role): _append_event(state, {"role": role, "message_event_id": message_event_id, "scope": scope})
def _lock_confirmation_used(state, message_event_id, dimension): return any(event.get("role") == "lock_confirmation" and event.get("message_event_id") == message_event_id and dimension not in event.get("scope", []) for event in state.get("message_events", []))
def _export_confirmation_after_last_lock(state, value):
    message_event_id = _confirmation(state, value)
    lock_messages = [event.get("message_event_id", 0) for event in state.get("message_events", []) if event.get("role") in {"lock_confirmation", "approve_confirmation"}]
    latest_lock_message = max(lock_messages, default=0)
    events = state.get("message_events", [])
    user_index = next((index for index, event in enumerate(events) if event.get("id") == message_event_id), -1)
    prior = events[user_index - 1] if user_index > 0 else {}
    after_summary = prior.get("role") == "assistant" and ("final direction" in prior.get("text", "").casefold() or "export" in prior.get("text", "").casefold())
    if message_event_id < latest_lock_message or (message_event_id == latest_lock_message and not after_summary): raise ValueError("export confirmation must come after the final lock")
    return message_event_id
def _google_font_url(tokens):
    library = fonts(); terms = []; requested: dict[str, set[int]] = {}
    contrast = tokens["typography"]["weight_contrast"]
    display_weight = {"low":500, "medium":600, "high":700, "inverted":300}[contrast]
    for font_id, weights in ((tokens["typography"]["display_font"], {display_weight}), (tokens["typography"]["body_font"], {400, 600}), (tokens["typography"]["ui_font"], {400, 600})):
        if font_id: requested.setdefault(font_id, set()).update(weights)
    for font_id, weights in requested.items():
        if not font_id or font_id not in library: continue
        item = library[font_id]; available = set(item["weights"])
        resolved = {min(available, key=lambda candidate: (abs(candidate - weight), candidate)) for weight in weights}
        terms.append("family=" + item["family"].replace(" ", "+") + ":wght@" + ";".join(map(str, sorted(resolved))))
    return "https://fonts.googleapis.com/css2?" + "&".join(terms) + "&display=swap"
def _export_tokens(tokens):
    exported, library = json.loads(json.dumps(tokens)), fonts()
    for key in ("display_font", "body_font", "ui_font", "mono_font"):
        font_id = exported["typography"].get(key)
        if font_id in library: exported["typography"][key] = {"id": font_id, "family": library[font_id]["family"]}
    return exported
def _token_values(): return json.loads((Path(__file__).resolve().parent / "data" / "enums.json").read_text(encoding="utf-8"))["token_values"]
def _font_family(font_id): return fonts()[font_id]["family"] if font_id else "system-ui"
def _font_stack(font_id):
    item = fonts().get(font_id, {})
    return '"' + _font_family(font_id) + '", ' + item.get("fallback", "system-ui, sans-serif")
def _working_label(state, dimension):
    direction = _direction(state, state["working"][dimension].get("direction_id"))
    return direction["label"] if direction else "the selected direction"
def _css_shadow(elevation):
    return {"flat": "none", "soft": "0 8px 24px rgba(0, 0, 0, 0.12)", "layered": "0 2px 8px rgba(0, 0, 0, 0.10), 0 16px 32px rgba(0, 0, 0, 0.14)"}[elevation]
def _css_easing(value): return {"ease-out": "ease-out", "ease-in-out": "ease-in-out", "none": "linear", "spring, gentle": "cubic-bezier(0.2, 0.8, 0.2, 1)"}[value]
def _user_decision_text(item):
    path, value = item["path"], item["value"]
    if path == "color.accent":
        if item.get("source") == "direction": return "Primary action color: from " + str(item.get("from_direction_label", "another direction")) + ", your choice."
        text = "Primary action color: " + (item.get("user_words") or str(value)) + ", your choice."
        return text + (" " + item["contrast_adjusted"].capitalize() + " slightly so it stays readable." if item.get("contrast_adjusted") else "")
    labels = {"typography.display_font": "Display font", "typography.body_font": "Body font", "typography.scale": "Type scale", "typography.weight_contrast": "Type weight contrast", "layout.density": "Layout density", "geometry.radius": "Corner radius", "geometry.border": "Borders", "geometry.elevation": "Elevation", "motion.preset": "Motion"}
    shown = _font_family(value) if path in {"typography.display_font", "typography.body_font"} else str(value).replace("_", " ")
    return labels.get(path, path) + ": " + shown + " (your choice)"
def _brief_from_user_messages(state):
    for message in state.get("user_messages", []):
        if not isinstance(message, str): continue
        remainder = re.split(r"The user has provided the following instruction alongside the skill invocation:\s*", message, maxsplit=1, flags=re.I)
        if len(remainder) == 2 and remainder[1].strip(): return remainder[1].strip()
        if not _is_design_invocation(message): return message
        command_remainder = re.sub(r"^\s*(?:/)?design-discovery\b[:\s]*", "", message, flags=re.I).strip()
        if command_remainder and command_remainder != message.strip(): return command_remainder
    return state["brief"]
def _dont_item(item):
    text = item.strip()
    for prefix in ("don't ", "don’t ", "do not ", "never "):
        if text.casefold().startswith(prefix):
            rest = text[len(prefix):].lstrip()
            return rest[:1].upper() + rest[1:] if rest else text
    if text.casefold().startswith("avoid "):
        rest = text[6:].lstrip()
        if not rest: return text
        first = re.split(r"[^A-Za-z]", rest, 1)[0]
        if first.casefold().endswith("ing"): return rest[:1].upper() + rest[1:]
        return "Use " + rest
    return item
def _render_design_md(state, tokens):
    values, typography, color, layout, geometry, motion = _token_values(), tokens["typography"], tokens["color"], tokens["layout"], tokens["geometry"], tokens["motion"]
    density = values["densities"][layout["density"]]; scale = values["type_scales"][typography["scale"]]; weights = values["weight_contrasts"][typography["weight_contrast"]]; radius = values["radii"][geometry["radius"]]; border = values["borders"][geometry["border"]]; elevation = values["elevations"][geometry["elevation"]]; motion_value = values["motion_presets"][motion["preset"]]
    labels = [_working_label(state, dimension) for dimension in DIMENSIONS]
    title = labels[0] if len(set(labels)) == 1 else "Custom direction"
    base, ratio = density["body_size_px"], scale["ratio"]
    sizes = {"caption": round(base / ratio), "body": base, "h4": round(base * ratio), "h3": round(base * ratio ** 2), "h2": round(base * ratio ** 3), "h1": round(base * ratio ** 4), "display": round(base * ratio ** 5)}
    font_link = _google_font_url(tokens)
    css = [":root {"]
    css += [f"  --color-{name.replace('_', '-')}: {color.get(name, color['accent'])};" for name in ("background", "surface", "text", "muted", "border", "border_strong", "accent", "accent_text", "success", "warning", "danger", "focus")]
    css += [f"  --font-display: {_font_stack(typography['display_font'])};", f"  --font-body: {_font_stack(typography['body_font'])};", f"  --font-ui: {_font_stack(typography['ui_font'])};", f"  --type-ratio: {ratio};"]
    css += [f"  --text-{name}: {value}px;" for name, value in sizes.items()]
    css += [f"  --space-unit: {density['unit_px']}px;", *[f"  --space-{index}: {density['unit_px'] * multiplier}px;" for index, multiplier in enumerate((1, 2, 3, 4, 6, 8, 12, 16), 1)], f"  --gap-related: {density['related_px']}px;", f"  --gap-group: {density['group_px']}px;", f"  --gap-section: {density['section_px']}px;", f"  --inset: {density['inset_px']}px;", f"  --line-height-body: {density['line_height']};"]
    if density.get("max_measure_ch"): css.append(f"  --max-measure: {density['max_measure_ch']}ch;")
    css += [f"  --radius-component: {radius['component_px']}px;", f"  --radius-button: {radius['button_px']}px;", f"  --border: {'none' if geometry['border'] == 'none' else str(border['width_px']) + 'px solid ' + ('var(--color-text)' if border.get('contrast') == 'full_text' else 'var(--color-border)')};", f"  --shadow: {_css_shadow(geometry['elevation'])};", f"  --duration-micro: {motion_value['micro_ms']}ms;", f"  --duration-navigation: {motion_value['navigation_ms']}ms;", f"  --easing: {_css_easing(motion_value['easing'])};", "}"]
    first_user = _brief_from_user_messages(state)
    lines = [f"# {title}", "", "## Brief", "", '"' + first_user + '"', "", "Export date: " + datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat(), "", "## How it was assembled", ""]
    assembly = {"typography": "Type", "color": "Color", "layout": "Layout", "geometry": "Geometry", "motion": "Motion"}
    lines += [f"- Everything from {labels[0]}." if len(set(labels)) == 1 else f"- {assembly[dimension]} from {_working_label(state, dimension)}." for dimension in (DIMENSIONS if len(set(labels)) != 1 else ("typography",))]
    lines += ["", "### Your decisions", ""]
    decisions = [_user_decision_text(item) for item in _user_decisions(state)] + [item["text"] for item in state["constraints"]]
    lines += ["- " + item if item.endswith(".") else "- " + item + "." for item in decisions] or ["- No additional decisions."]
    body_ui = "Body and UI: " + _font_family(typography["body_font"]) if typography["body_font"] == typography["ui_font"] else f"Body and UI: {_font_family(typography['body_font'])} and {_font_family(typography['ui_font'])} for reading and controls."
    lines += ["", "## Tokens", "", "Google Fonts: <link rel=\"stylesheet\" href=\"" + font_link + "\">", "", "```css", *css, "```", "", "## Typography", "", f"Display: {_font_family(typography['display_font'])} for headlines and display text.", body_ui, f"Weights: display {weights.get('display', weights.get('display_min'))}, body {weights['body']}.", "Type scale: " + ", ".join(name + " " + str(value) + "px" for name, value in sizes.items()) + ".", f"Case: {typography['case']}. Tracking for display: {typography['tracking_display']}.", scale["guidance"], weights["guidance"], "", "## Color", "", "Mode: " + color["mode"] + ".", "", "| Role | Hex | Usage |", "| --- | --- | --- |"]
    usages = {"background": "Page ground", "surface": "Cards and raised areas", "text": "Primary reading text", "muted": "Supporting text", "border": "Subtle separators", "border_strong": "Strong structure", "accent": "Primary action", "accent_text": "Text on primary action", "success": "Success status only", "warning": "Warning status only", "danger": "Error status only"}
    lines += [f"| {name.replace('_', ' ').title()} | {color[name]} | {usages[name]} |" for name in usages]
    lines += ["", "Accent rule: " + ("The accent may be used for text and fills." if tokens["accent_usage"] == "text_and_fill" else values["color"]["fill_only"]), "", "| Pair | Ratio | Required | Result |", "| --- | ---: | ---: | --- |"]
    contrast = contrast_report(tokens)
    for name, item in contrast.items():
        lines.append(f"| {name.replace('_', ' ')} | {item['ratio']:.1f}:1 | {item['minimum']:.1f}:1 | {'Pass' if item['passes'] else 'Fail'} |")
        if not item["passes"]: lines.append("Warning: " + item["label"] + ".")
    border_text = "none" if geometry["border"] == "none" else str(border["width_px"]) + "px solid, " + ("text color" if border.get("contrast") == "full_text" else "border color")
    lines += ["", *values["color"]["always"], "", "## Layout and spacing", "", f"Unit: {density['unit_px']}px. Scale: " + ", ".join(str(density['unit_px'] * multiplier) + "px" for multiplier in (1, 2, 3, 4, 6, 8, 12, 16)) + ".", f"Body: {base}px at {density['line_height']} line height. Related: {density['related_px']}px. Group: {density['group_px']}px. Section: {density['section_px']}px. Inset: {density['inset_px']}px." + (f" Maximum measure: {density['max_measure_ch']}ch." if density.get("max_measure_ch") else ""), density["guidance"], *values["densities"]["always"], "", "## Geometry", "", f"Components: {radius['component_px']}px radius. Buttons: {radius['button_px']}px radius.", "Border: " + border_text + ".", "Shadow: " + _css_shadow(geometry["elevation"]) + ".", radius["guidance"], border["guidance"], elevation["guidance"], "", "## Motion", "", f"Micro changes: {motion_value['micro_ms']}ms. Navigation: {motion_value['navigation_ms']}ms. Easing: {_css_easing(motion_value['easing'])}. Overshoot: {'allowed' if motion_value['overshoot'] else 'not allowed'}.", motion_value["guidance"], *values["motion_presets"]["always"], "", "## Voice", "", "Tone: " + tokens["voice"]["tone"], "", "Do:", *["- " + item for item in tokens["voice"]["do"]], "", "Don't:", *["- " + _dont_item(item) for item in tokens["voice"]["dont"]], "", "Example: " + tokens["voice"]["example"]]
    conflicts = detect_conflicts(_working_direction(state))
    if conflicts:
        lines += ["", "## Tensions", ""]
        lines += ["- " + item["tradeoff"] + " Resolution: " + item["resolution"] for item in conflicts]
    lines += ["", "## Instructions for the implementing agent", "", "Use only these tokens; prefer the CSS custom properties; respect the contrast table; when something isn't specified, choose what fits the direction's character as detailed above."]
    return "\n".join(lines) + "\n"
def _latest_understanding(state):
    events = state.get("message_events", [])
    index = next((index for index in range(len(events) - 1, -1, -1) if events[index]["role"] == "understanding"), None)
    return (events, index, events[index] if index is not None else None)
def _understanding_reply(state):
    events, understanding_index, understanding = _latest_understanding(state)
    if understanding_index is None: return None
    replies = [event["text"] for event in events[understanding_index + 1:] if event["role"] == "user"]
    return replies[-1] if replies else understanding.get("confirmed_reply")
def _recorded_interview_answers(state):
    events, understanding_index, _ = _latest_understanding(state)
    if understanding_index is None: return []
    answers, question = [], None
    for event in events[:understanding_index]:
        if event.get("role") == "assistant":
            question = event.get("text") if "?" in str(event.get("text", "")) else None
        elif event.get("role") == "user" and question and isinstance(event.get("text"), str) and event["text"].strip():
            answers.append({"q": question, "a": event["text"]})
            question = None
    if answers: return answers
    first_user = next((event.get("text") for event in events[:understanding_index] if event.get("role") == "user" and isinstance(event.get("text"), str) and event["text"].strip()), None)
    if first_user:
        brief = _brief_from_user_messages({"user_messages": [first_user], "brief": ""})
        if brief: return [{"q": "What are you making and how should it feel?", "a": brief}]
    return []
def _has_interview_reply(state):
    return len([event for event in state.get("message_events", []) if event.get("role") == "user" and str(event.get("text", "")).strip()]) >= 2
def _summary_was_shown_before_latest_user_message(state, summary):
    events = [event for event in state.get("message_events", []) if event.get("role") in {"assistant", "user"}]
    if len(events) < 2 or events[-1].get("role") != "user" or events[-2].get("role") != "assistant": return None
    words = set(re.findall(r"[a-z0-9]{3,}", str(summary).casefold()))
    shown = set(re.findall(r"[a-z0-9]{3,}", str(events[-2].get("text", "")).casefold()))
    shared = words & shown
    return events[-1]["text"] if len(shared) >= 6 and len(shared) / max(len(words), 1) >= 0.6 else None
def _understanding_confirmation(state, value):
    _, understanding_index, _ = _latest_understanding(state)
    if understanding_index is None: raise ValueError("understanding confirmation is required")
    reply = _understanding_reply(state)
    if not reply: raise ValueError("understanding reply is required")
    if not isinstance(value, str) or not value.strip(): raise ValueError("understanding confirmation is missing")
    if not _contains(reply, value): raise ValueError("understanding confirmation did not match the latest user reply")
    _confirmation(state, value)
def _seen_after_last_change(state, dimension, value):
    events = state.get("message_events", [])
    change_index = next((index for index in range(len(events) - 1, -1, -1) if events[index].get("role") == "dimension_change" and events[index].get("dimension") == dimension), None)
    return change_index is not None and any(event.get("role") == "user" and _contains(event.get("text", ""), value) for event in events[change_index + 1:])
def _has_starting_point_name(label):
    normalized = _normal(label)
    return any(_normal(item[field]) in normalized for item in archetypes().values() for field in ("id", "name"))
def _has_long_direction_label(label): return len(re.findall(r"\S+", str(label))) > 4
def _next_after_seed(next_step, direction):
    if not direction: return next_step
    return "The pane was filled from " + direction["label"] + ". If that is not the direction the user chose, call try with their chosen direction now, then adjust again. Otherwise, " + next_step[0].lower() + next_step[1:]
def _result(next_step, **payload): return json.dumps({"ok":True, "next":next_step, **payload}, ensure_ascii=False)
def _resolved_working_tokens(state):
    if not all(_sources(state).values()): return None
    return resolve_direction(_working_direction(state), state["rejected"], constraints=state["constraints"], user_messages=state["user_messages"])
def _token_leaves(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items(): yield from _token_leaves(item, key if not prefix else prefix + "." + key)
    elif isinstance(value, list):
        for index, item in enumerate(value): yield from _token_leaves(item, str(index) if not prefix else prefix + "." + str(index))
    else: yield prefix, value
def _token_changes(before, after):
    # Provenance explains a token; it is not itself a rendered token.
    if isinstance(before, dict): before = {key: value for key, value in before.items() if key != "provenance"}
    if isinstance(after, dict): after = {key: value for key, value in after.items() if key != "provenance"}
    before = dict(_token_leaves(before)) if before is not None else {}
    after = dict(_token_leaves(after)) if after is not None else {}
    return [{"path": path, "from": before.get(path), "to": after.get(path)} for path in sorted(set(before) | set(after)) if before.get(path) != after.get(path)]
def _refusal(exc):
    message = str(exc)
    supported = ", ".join(sorted(ADJUSTMENT_PATHS))
    enum_match = re.fullmatch(r"invalid ([a-z._]+): .+", message)
    if isinstance(exc, PermissionError): return json.dumps({"ok":False, "error":message, "next":"A temporary save error occurred. Call the same tool once more. If it fails again, tell the user saving failed and stop."}, ensure_ascii=False)
    if enum_match and enum_match.group(1) in ADJUSTMENT_PATHS and ADJUSTMENT_PATHS[enum_match.group(1)] in enums():
        return json.dumps({"ok":False, "error":message, "next":"Use one of these values for " + enum_match.group(1) + ": " + ", ".join(map(str, enums()[ADJUSTMENT_PATHS[enum_match.group(1)]]["enum"])) + "."}, ensure_ascii=False)
    if message.startswith("generation validation failed:") or message.startswith("directions are too similar in color:"):
        return json.dumps({"ok":False, "error":message, "next":message}, ensure_ascii=False)
    if message.startswith("sample.") or message.startswith("voice."):
        return json.dumps({"ok":False, "error":message, "next":message}, ensure_ascii=False)
    if message.startswith("composed palette ") or message.startswith("composed_palette must"):
        return json.dumps({"ok":False, "error":message, "next":message}, ensure_ascii=False)
    if message.startswith('Use sources.color "composed"'):
        return json.dumps({"ok":False, "error":message, "next":message}, ensure_ascii=False)
    if message.startswith("described accent value must be"):
        return json.dumps({"ok":False, "error":message, "next":"Put the user's color words in user_words and pass a matching #RRGGBB hex color as value."}, ensure_ascii=False)
    if re.fullmatch(r"(?:agent|user) accent value must be a #RRGGBB hex color", message) or message == "color.accent must be a #RRGGBB hex value":
        return json.dumps({"ok":False, "error":message, "next":"Use source described, put the user's color words in user_words, and pass a matching #RRGGBB hex as value."}, ensure_ascii=False)
    unknown_source = re.fullmatch(r"unknown (typography|color|layout|geometry|motion) archetype: .+", message)
    if unknown_source:
        dimension = unknown_source.group(1); choices = sorted(archetypes())
        color_note = ' For color, use an archetype id or "composed" with composed_palette.words.' if dimension == "color" else ""
        return json.dumps({"ok":False, "error":message, "next":"Use a valid " + dimension + " archetype: " + ", ".join(choices) + ". Vocabulary words belong in composed_palette.words; set density, radius, and similar token values with adjust." + color_note}, ensure_ascii=False)
    if message == "export confirmation must come after the final lock":
        return _result("Summarize the final direction in plain words and ask what they think, then wait.", exported=False)
    if message == "archetype color directions cannot also include composed_palette":
        return json.dumps({"ok":False, "error":message, "next":"Use either an archetype color source or sources.color composed with one composed_palette, not both."}, ensure_ascii=False)
    next_step = "Call try with the direction the user chose, tell them the pane shows it, then apply the requested change." if message == "try a direction before changing an individual value" else message if message.startswith("Unknown direction reference") or message.startswith("No directions have been generated") or message == _NO_INTERVIEW else "Use one of these actions: try, approve_direction, lock, unlock, reject, clear_reject, adjust, add_constraint, or remove_constraint." if message == "unknown action" else _NEXT_CONFIRMATION if message == _CONFIRMATION_ERROR else _NEXT_QUOTED_CONSENT if message == "confirmation was suggested by the assistant" else "Ask whether they want the remaining dimensions kept as they are. If so, use approve_direction with their reply." if message == "this approval already locked another dimension" else "Summarize the final direction in a few plain sentences, ask the user to confirm, and wait." if message == "export confirmation must come after the final lock" else _NEXT_MISSING_UNDERSTANDING if message == "understanding confirmation is required" else _NEXT_AWAITING_UNDERSTANDING_REPLY if message == "understanding reply is required" else _NEXT_MISSING_UNDERSTANDING_CONFIRMATION if message == "understanding confirmation is missing" else _NEXT_CONFIRMATION_MISMATCH if message == "understanding confirmation did not match the latest user reply" else _NEXT_RENAME if message == "direction labels cannot use starting point names" else _NEXT_SHORT_DIRECTION_NAME if message == "direction labels must contain at most four words" else _NEXT_SIMILAR_COLORS if message == "directions are too similar in color" else _NEXT_ALREADY_LOCKED if message == "dimension is already locked" else _NEXT_ALREADY_UNLOCKED if message == "dimension is already unlocked" else _NEXT_ALREADY_SHOWN if message == "working direction is already shown" else "There is no adjustment to remove at that path. Tell the user the pane is unchanged and stop." if message == "no adjustment exists at path" else _NEXT_NO_CHANGE if message in {"nothing changed", "adjustment already matches the current token"} else _NEXT_MISSING_DESCRIBED_WORDS if message == "described color words must come from the user" else "Use source described with the user's exact color words, not source user." if message.startswith("That value wasn't given by the user") else "Use one of these adjustment paths: " + supported + ". color.accent_usage is set automatically for readability." if message.startswith("unsupported adjustment path") else "Use approve_direction for the selected direction, then export with the user's approval. Unlocked dimensions: " + message.split("unlocked: ", 1)[1] if message.startswith("all five dimensions must be locked; unlocked: ") else _NEXT_DESCRIBED_ACCENT_SOURCE if message == "color.accent must be a #RRGGBB hex value" else _NEXT_SHARED_ACCENT if message == "directions share this accent" else _NEXT_INVALID_ACCENT if message == "agent-sourced accent must be from the color source alternates" else _NEXT_UNSEEN if message == "dimension has not been seen since its last change" else _NEXT_UNEXPECTED_ARGUMENT if message.startswith("unexpected argument:") else _NEXT_ACCENT_CONTRAST if "accent" in message and "cannot reach" in message else "Correct this input before continuing: " + message
    return json.dumps({"ok":False, "error":message, "next":next_step}, ensure_ascii=False)
def _activate(session_id):
    state = _clean(get_state(session_id))
    if not state.get("active"):
        state["active"], state["session_id"], state["phase"] = True, session_id, "discovering"
        state["user_messages"] = list(_RECENT_USER_MESSAGES.get(session_id, []))
        state["assistant_messages"] = list(_RECENT_ASSISTANT_MESSAGES.get(session_id, []))
        state["message_events"] = list(_RECENT_MESSAGE_EVENTS.get(session_id, []))[-100:]
        state = replace_state(state, session_id)
    return state
def _is_design_invocation(message): return isinstance(message, str) and 'user has invoked the "design-discovery" skill' in message.casefold()

def record_understanding(args: dict, **kwargs) -> str:
    try:
        _check_arguments(args, {"summary"})
        session_id, summary = str(kwargs.get("session_id") or ""), args.get("summary")
        if not session_id: raise ValueError("session_id is required")
        if not isinstance(summary, str) or not summary.strip(): raise ValueError("summary is required")
        state = _activate(session_id)
        if not _has_interview_reply(state): return _result(_NEXT_INTERVIEW, recorded=False, state=state)
        confirmed_reply = _understanding_reply(state) or _summary_was_shown_before_latest_user_message(state, summary)
        state["understanding"] = {"summary":summary}
        understanding_event = {"role":"understanding","text":summary}
        if confirmed_reply: understanding_event["confirmed_reply"] = confirmed_reply
        _append_event(state, understanding_event)
        return _result(_NEXT_ALREADY_CONFIRMED_UNDERSTANDING if confirmed_reply else _NEXT_UNDERSTANDING, recorded=True, state=replace_state(state, session_id))
    except Exception as exc: return _refusal(exc)

def generate_directions(args: dict, **kwargs) -> str:
    try:
        _check_arguments(args, {"directions", "brief", "answers", "sample", "confirmed_by_user"})
        directions, brief, answers = args.get("directions", []), args.get("brief"), args.get("answers")
        session_id = str(kwargs.get("session_id") or "")
        if not session_id: raise ValueError("session_id is required")
        state = _activate(session_id)
        if not isinstance(answers, list) or not answers:
            answers = _recorded_interview_answers(state)
            if not answers or not _has_interview_reply(state): return _result(_NEXT_INTERVIEW, generated=False, warnings=[])
        if not isinstance(directions, list) or len(directions) != 3: raise ValueError("Provide exactly three directions, each with a distinct user-noticeable approach.")
        try: _understanding_confirmation(state, args.get("confirmed_by_user"))
        except ValueError as exc:
            if str(exc) == "understanding confirmation is required" and state.get("understanding"):
                return json.dumps({"ok":False, "error":str(exc), "next":_NEXT_UNCONFIRMED_UNDERSTANDING}, ensure_ascii=False)
            raise
        state["active"], state["session_id"], state["phase"] = True, session_id, "directions"
        if brief is not None: state["brief"] = str(brief)
        if answers is not None: state["answers"] = answers
        warnings = []
        sample = _lenient_sample(args.get("sample"), warnings)
        directions = [dict(direction, id=f"dir-{chr(ord('a') + index)}") if isinstance(direction, dict) else direction for index, direction in enumerate(directions)]
        for direction in directions:
            if isinstance(direction, dict) and direction.get("sources", {}).get("color") == "composed":
                direction["sources"] = {**direction["sources"], "color": "composed:" + direction["id"]}
            elif isinstance(direction, dict) and str(direction.get("sources", {}).get("color", "")).startswith("composed:"):
                raise ValueError('Use sources.color "composed" for a composed palette. The plugin assigns the direction id.')
        validation_errors, valid_directions = [], []
        for direction in directions:
            if not isinstance(direction, dict) or _has_starting_point_name(direction.get("label", "")): raise ValueError("direction labels cannot use starting point names")
            if _has_long_direction_label(direction.get("label", "")): raise ValueError("direction labels must contain at most four words")
            _lenient_direction_values(direction, warnings, [*state["user_messages"], *_RECENT_USER_MESSAGES.get(session_id, [])])
            _lenient_voice(direction, warnings)
            _lenient_words(direction, warnings)
            if str(direction.get("sources", {}).get("color", "")).startswith("composed:"):
                changes = auto_correct_composed_palette(direction.get("composed_palette", {}))
                if changes:
                    direction["auto_adjusted"] = changes
            try:
                validate_direction(direction, state["rejected"], state["constraints"], state["user_messages"])
                valid_directions.append(direction)
            except ValueError as exc:
                if not str(exc).startswith("composed palette "):
                    raise
                validation_errors.append(direction.get("label", "Unnamed direction") + ": " + str(exc))
        variety_error = color_variety_error(valid_directions, typography_variety=TYPOGRAPHY_VARIETY_ENABLED) if len(valid_directions) > 1 else None
        if variety_error:
            return _result("Nothing was generated and the pane is unchanged. " + variety_error + " Resubmit generate_directions with these moves applied before replying.", generated=False, status="needs_changes", guidance=variety_error, warnings=warnings)
        if validation_errors: raise ValueError("generation validation failed:\n" + "\n".join(validation_errors))
        state["directions"] = directions
        state["sample"] = sample
        for dimension in DIMENSIONS: _record_dimension_change(state, dimension)
        state["conflicts"] = detect_conflicts(directions[0]) if directions else []
        ids = ", ".join(item["id"] + " (" + item["label"] + ")" for item in directions)
        generated = [{"id": item["id"], "label": item["label"], "sources": item["sources"], "adjustment_paths": sorted(item["adjustments"]), **({"composed_palette": item["composed_palette"]} if item["sources"]["color"].startswith("composed:") else {})} for item in directions]
        next_step = _NEXT_GENERATE + (" Continue normally; no retry is needed." if warnings else "") + " Use these direction ids for try and lock: " + ids + "."
        return _result(next_step, generated=True, state=replace_state(state, session_id), generated_directions=generated, warnings=warnings)
    except Exception as exc: return _refusal(exc)

def update_choice(args: dict, **kwargs) -> str:
    try:
        session_id = str(kwargs.get("session_id") or "")
        if not session_id: raise ValueError("session_id is required")
        if not isinstance(args, dict): raise ValueError("arguments must be an object")
        action = args.get("action")
        _check_arguments(args, _UPDATE_ARGUMENTS.get(action, {"action"}))
        state = _activate(session_id)
        before_tokens = _resolved_working_tokens(state)
        reference_warnings = []
        def complete(payload):
            if reference_warnings: payload["warnings"] = list(dict.fromkeys([*reference_warnings, *payload.get("warnings", [])]))
            changes = _token_changes(before_tokens, _resolved_working_tokens(state))
            payload["changes"] = changes
            payload["changed"] = bool(changes)
            return _result(_NEXT_CHANGED if changes else _NEXT_NO_CHANGE, **payload)
        seeded_from = None
        if action == "approve_direction":
            confirmation_event_id = _confirmation(state, args.get("confirmed_by_user"))
            direction = _resolve_reference(state, args.get("direction"), action, reference_warnings)
            changed, kept = [], []
            for dimension in DIMENSIONS:
                current = state["working"][dimension]
                if current["status"] == "locked": continue
                # Approval locks what the pane shows: a dimension being tried keeps its source and adjustments.
                if current["source"]:
                    state["working"][dimension] = {**current, "status": "locked"}
                    if current.get("direction_id") and current["direction_id"] != direction["id"]:
                        kept.append(dimension + " as shown from " + (_direction(state, current["direction_id"]) or {}).get("label", "another direction"))
                else:
                    _set_working(state, dimension, direction, "locked")
                _record_dimension_change(state, dimension)
                changed.append(dimension)
            if kept: reference_warnings.append("Kept " + ", ".join(kept) + ".")
            _enforce_working(state)
            state["conflicts"] = detect_conflicts(_working_direction(state))
            _record_confirmation(state, confirmation_event_id, changed, "approve_confirmation")
            return complete({"state":replace_state(state, session_id), "confirmation":{"message_event_id": confirmation_event_id, "scope": changed}})
        if action == "try":
            selections = args.get("directions")
            if not isinstance(selections, dict) or not selections: raise ValueError("directions must map one or more dimensions to direction ids")
            bad = next(((dimension, direction_id) for dimension, direction_id in selections.items() if dimension not in DIMENSIONS or not isinstance(direction_id, str)), None)
            if bad: raise ValueError("invalid directions entry " + repr(bad[0]) + "=" + repr(bad[1]) + "; use dimensions " + ", ".join(DIMENSIONS) + " with string direction references")
            locked = next((dimension for dimension in selections if state["working"][dimension]["status"] == "locked"), None)
            if locked: raise ValueError(f"Cannot try {locked} because it is locked.")
            selected = {dimension: _resolve_reference(state, direction_id, action, reference_warnings) for dimension, direction_id in selections.items()}
            if all(state["working"][dimension] == {"source": direction["sources"][dimension], "status": "open", "direction_id": direction["id"]} for dimension, direction in selected.items()) and all(_sources(state).values()): raise ValueError("working direction is already shown")
            for dimension, direction in selected.items():
                _set_working(state, dimension, direction, "open")
                _record_dimension_change(state, dimension)
            fallback = next(iter(selected.values()))
            filled = _fill_unset_dimensions(state, fallback)
            _enforce_working(state)
            state["conflicts"] = detect_conflicts(_working_direction(state))
            detail = " Filled unset dimensions from " + fallback["label"] + ": " + ", ".join(filled) + "." if filled else ""
            return complete({"state":replace_state(state, session_id), "detail":detail})
        if action in {"lock", "unlock"}:
            dimension, direction_id = args.get("dimension"), args.get("direction_id")
            if dimension not in DIMENSIONS: raise ValueError("unknown dimension")
            if action == "lock":
                if state["working"][dimension]["status"] == "locked": raise ValueError("dimension is already locked")
                confirmation_event_id = _confirmation(state, args.get("confirmed_by_user"))
                if not _seen_after_last_change(state, dimension, args.get("confirmed_by_user")): raise ValueError("dimension has not been seen since its last change")
                if _lock_confirmation_used(state, confirmation_event_id, dimension): raise ValueError("this approval already locked another dimension")
            direction = _resolve_reference(state, direction_id, action, reference_warnings) if direction_id else None
            if direction is None and state["working"][dimension]["source"]:
                direction = _direction(state, state["working"][dimension].get("direction_id"))
            if direction is None and state["working"][dimension]["source"]:
                direction = next((item for item in state["directions"] if item["sources"][dimension] == state["working"][dimension]["source"]), None)
            if not direction: raise ValueError("direction_id is required when this dimension has not been tried")
            if state["working"][dimension] == {"source": direction["sources"][dimension], "status": "locked" if action == "lock" else "open", "direction_id": direction["id"]}: raise ValueError("dimension is already locked" if action == "lock" else "dimension is already unlocked")
            _set_working(state, dimension, direction, "locked" if action == "lock" else "open")
            filled = _fill_unset_dimensions(state, direction, record=False) if action == "lock" else []
            if action == "lock": _record_confirmation(state, confirmation_event_id, [dimension], "lock_confirmation")
        elif action in {"reject", "clear_reject"}:
            dimension = args.get("dimension")
            if dimension not in DIMENSIONS: raise ValueError("unknown dimension")
            if action == "reject": _confirmation(state, args.get("confirmed_by_user"))
            target, values = args.get("archetype_id"), state["rejected"]["archetypes"][dimension]
            if not target: raise ValueError("archetype_id is required")
            if action == "reject" and target not in values: values.append(target)
            elif action == "clear_reject" and target in values: values.remove(target)
            else: raise ValueError("nothing changed")
        elif action == "adjust":
            path, value, source = args.get("path"), args.get("value"), args.get("source")
            if path not in ADJUSTMENT_PATHS: raise ValueError("unsupported adjustment path")
            if value is None:
                if path not in state["adjustments"]: raise ValueError("no adjustment exists at path")
                state["adjustments"].pop(path)
            else:
                if path == "color.accent" and source in {"agent", "user"} and (not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value)):
                    return _result("Use source described, put the user's color words in user_words, and pass a matching #RRGGBB hex as value.", changed=False, changes=[], warnings=["Dropped color.accent value " + repr(value) + "; kept the current source value."])
                entry = {"value":value,"source":source}
                downgrade_warning = None
                if source == "user" and not any(str(value).casefold() in message.casefold() for message in state["user_messages"]):
                    entry["source"] = "agent"
                    downgrade_warning = "Recorded " + path + " value " + repr(value) + " as agent because it was not found in user messages."
                borrowed = None
                filled = []
                if not all(_sources(state).values()):
                    fallback = _resolve_reference(state, args.get("from_direction"), action, reference_warnings) if source == "direction" else (state["directions"][0] if state["directions"] else None)
                    if not fallback: raise ValueError("try a direction before changing an individual value")
                    filled = _fill_unset_dimensions(state, fallback)
                    seeded_from = fallback if filled else None
                kind = ADJUSTMENT_PATHS[path]
                invalid_value = (kind in {"display", "body"} and value not in fonts()) or (kind not in {"display", "body", "accent"} and value not in enums()[kind]["enum"])
                if invalid_value:
                    working = _working_direction(state); kept, valid = _source_value(working, path), _valid_values(path)
                    state["adjustments"].pop(path, None)
                    _enforce_working(state)
                    state["conflicts"] = detect_conflicts(_working_direction(state))
                    warning = "Dropped " + path + " value " + repr(value) + "; kept " + repr(kept) + ". Valid values: " + ", ".join(map(str, valid)) + "."
                    return complete({"state":replace_state(state, session_id), "warnings":[warning]})
                if source == "direction":
                    if path != "color.accent": raise ValueError("direction source is only available for color.accent")
                    borrowed = _resolve_reference(state, args.get("from_direction"), action, reference_warnings)
                    borrowed_tokens = resolve_direction(borrowed, state["rejected"], constraints=state["constraints"], user_messages=state["user_messages"])
                    if not seeded_from and all(_sources(state).values()) and value == resolve_direction(_working_direction(state), state["rejected"], constraints=state["constraints"], user_messages=state["user_messages"])["color"]["accent"]: raise ValueError("directions share this accent")
                    allowed = {borrowed_tokens["color"]["accent"], *borrowed_tokens["color"]["accent_alternates"]}
                    if value not in allowed:
                        alternates = [item for item in borrowed_tokens["color"]["accent_alternates"] if item != borrowed_tokens["color"]["accent"]]
                        raise _Guidance("Nothing changed. " + repr(value) + " is not one of " + borrowed["label"] + "'s accent colors. Its accent is " + borrowed_tokens["color"]["accent"] + ("; its accent alternates are " + ", ".join(alternates) if alternates else "; it has no accent alternates") + ". To borrow its accent, call update_choice with {\"action\":\"adjust\",\"path\":\"color.accent\",\"value\":\"" + borrowed_tokens["color"]["accent"] + "\",\"source\":\"direction\",\"from_direction\":\"" + borrowed["id"] + "\"}.")
                    entry["from_direction"] = borrowed["id"]
                    if not state["working"]["color"]["source"]:
                        _set_working(state, "color", borrowed, "open")
                        filled = [*filled, *_fill_unset_dimensions(state, borrowed)]
                if source == "described":
                    if path != "color.accent": raise ValueError("described source is only available for color.accent")
                    user_words = args.get("user_words")
                    if not isinstance(user_words, str) or not user_words.strip() or not any(_contains(message, user_words) for message in state["user_messages"]): raise ValueError("described color words must come from the user")
                    if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value): raise ValueError("described accent value must be a #RRGGBB hex color; put the user's words in user_words and pass a matching hex as value")
                    entry["user_words"] = user_words
                    color_source = state["working"]["color"]["source"]
                    if color_source:
                        background = state["working"]["color"].get("palette", {}).get("background") if color_source.startswith("composed:") else archetypes()[color_source]["color"]["background"]
                        adjusted, adjustment = _contrast_safe_accent(value, background)
                        if adjusted is None: raise ValueError("described accent cannot be made readable")
                        if adjusted != value:
                            entry["value"], entry["contrast_adjusted"] = adjusted, adjustment
                if state["adjustments"].get(path) == entry: raise ValueError("nothing changed")
                if source == "agent" and all(_sources(state).values()) and resolve_direction(_working_direction(state), state["rejected"], constraints=state["constraints"], user_messages=state["user_messages"])[path.split(".")[0]][path.split(".")[1]] == value: raise ValueError("adjustment already matches the current token")
                candidate = {**state["adjustments"], path:entry}
                validate_adjustments(candidate, _sources(state), state["rejected"], state["user_messages"])
                state["adjustments"] = candidate
                if borrowed:
                    _record_dimension_change(state, "color")
                    _enforce_working(state)
                    state["conflicts"] = detect_conflicts(_working_direction(state))
                    detail = "Accent borrowed from " + borrowed["label"] + "."
                    if filled: detail += " Filled unset dimensions from " + borrowed["label"] + ": " + ", ".join(filled) + "."
                    return complete({"state":replace_state(state, session_id), "detail":detail})
                if source == "described":
                    _record_dimension_change(state, "color")
                    _enforce_working(state)
                    state["conflicts"] = detect_conflicts(_working_direction(state))
                    next_step = "Tell the user in one plain sentence that the color was " + entry["contrast_adjusted"] + " slightly so it stays readable, then ask if it’s the shade they meant." if entry.get("contrast_adjusted") else _NEXT_DESCRIBED_ACCENT
                    return complete({"state":replace_state(state, session_id), "detail":"Accent matched from the user's description."})
                _record_dimension_change(state, path.split(".", 1)[0])
        elif action == "add_constraint":
            _confirmation(state, args.get("confirmed_by_user"))
            constraint = args.get("constraint")
            if not isinstance(constraint, dict) or set(constraint) - {"id","text","kind","path","value"} or not {"id","text","kind"} <= set(constraint) or constraint["kind"] not in {"require","avoid"}: raise ValueError("constraint requires id, text, and kind")
            if any(item["id"] == constraint["id"] for item in state["constraints"]): raise ValueError("constraint id already exists")
            state["constraints"].append(constraint)
        elif action == "remove_constraint":
            remaining = [item for item in state["constraints"] if item["id"] != args.get("constraint_id")]
            if len(remaining) == len(state["constraints"]): raise ValueError("nothing changed")
            state["constraints"] = remaining
        else: raise ValueError("unknown action")
        _enforce_working(state)
        state["conflicts"] = detect_conflicts(_working_direction(state)) if all(_sources(state).values()) else []
        detail = " Filled unset dimensions from " + direction["label"] + ": " + ", ".join(filled) + "." if action == "lock" and filled else ""
        payload = {"state": replace_state(state, session_id), "detail": detail}
        if 'downgrade_warning' in locals() and downgrade_warning: payload["warnings"] = [downgrade_warning]
        if action == "lock": payload["confirmation"] = {"message_event_id": confirmation_event_id, "scope": [dimension]}
        return complete(payload)
    except _Guidance as exc: return _result(str(exc), changed=False, changes=[])
    except Exception as exc:
        no_ops = {"nothing changed": _NEXT_NO_CHANGE, "no adjustment exists at path": _NEXT_NOTHING_REMOVE, "adjustment already matches the current token": _NEXT_NO_CHANGE, "dimension is already locked": _NEXT_ALREADY_LOCKED, "dimension is already unlocked": _NEXT_ALREADY_UNLOCKED, "working direction is already shown": _NEXT_ALREADY_SHOWN, "directions share this accent": _NEXT_NO_CHANGE}
        if str(exc) in no_ops: return _result(no_ops[str(exc)], changed=False, changes=[])
        return _refusal(exc)

def design_discovery_get_state(args: dict, **kwargs) -> str:
    try:
        _check_arguments(args, set())
        session_id = str(kwargs.get("session_id") or "")
        if session_id and kwargs.get("activate_session", True): _activate(session_id)
        state = get_state(session_id); resolved = []
        for direction in state["directions"]:
            tokens = resolve_direction(direction, state["rejected"], constraints=state["constraints"], user_messages=state["user_messages"])
            resolved.append({"direction_id":direction["id"],"tokens":tokens,"contrast":contrast_report(tokens),"conflicts":_public_conflicts(detect_conflicts(direction))})
        working = None
        if all(_sources(state).values()):
            tokens = resolve_direction(_working_direction(state), state["rejected"], constraints=state["constraints"], user_messages=state["user_messages"])
            working = {"tokens":tokens,"contrast":contrast_report(tokens),"conflicts":_public_conflicts(detect_conflicts(_working_direction(state)))}
        font_library = [{key: item[key] for key in ("id", "family", "category", "class", "roles", "weights")} for item in fonts().values()]
        if state["directions"]:
            next_step = "Use the resolved directions to continue the design discovery conversation."
        elif not state.get("understanding"):
            next_step = _NEXT_GET_STATE
        elif _understanding_reply(state):
            next_step = "Call generate_directions with the user’s reply, word for word, as confirmed_by_user. Do not call record_understanding again."
        else:
            next_step = _NEXT_AWAITING_UNDERSTANDING_REPLY
        next_step += _NO_INTERNALS
        return _result(next_step, state=state, resolved_directions=resolved, resolved_working=working, catalog={"archetypes":catalog(),"fonts":font_library,"vocabulary":VOCABULARY})
    except Exception as exc: return _refusal(exc)

_MESSAGE_LOG_KEYS = ("user_messages", "assistant_messages", "message_events")
def _compact_resolved(item):
    if not isinstance(item, dict): return item
    compact = {key: value for key, value in item.items() if key != "contrast"}
    contrast = item.get("contrast")
    if isinstance(contrast, dict):
        compact["contrast_failures"] = [entry.get("label", name) for name, entry in contrast.items() if isinstance(entry, dict) and not entry.get("passes", True)]
    return compact
def design_discovery_get_state_tool(args: dict, **kwargs) -> str:
    """Agent-facing get_state: the full payload minus message bodies and contrast tables, so Hermes keeps it inline."""
    payload = json.loads(design_discovery_get_state(args, **kwargs))
    if not payload.get("ok") or not isinstance(payload.get("state"), dict): return json.dumps(payload, ensure_ascii=False)
    state = payload["state"]
    state["message_counts"] = {key: len(state.get(key) or []) for key in _MESSAGE_LOG_KEYS}
    for key in _MESSAGE_LOG_KEYS: state.pop(key, None)
    payload["resolved_directions"] = [_compact_resolved(item) for item in payload.get("resolved_directions") or []]
    payload["resolved_working"] = _compact_resolved(payload.get("resolved_working"))
    return json.dumps(payload, ensure_ascii=False)

def export_design_md(args: dict, **kwargs) -> str:
    try:
        _check_arguments(args, {"confirmed_by_user", "folder"})
        session_id = str(kwargs.get("session_id") or "")
        if not session_id: raise ValueError("session_id is required")
        state = _activate(session_id); confirmation_event_id = _export_confirmation_after_last_lock(state, args.get("confirmed_by_user"))
        unlocked = [dimension for dimension in DIMENSIONS if state["working"][dimension]["status"] != "locked"]
        if unlocked: raise ValueError("all five dimensions must be locked; unlocked: " + ", ".join(unlocked))
        tokens = resolve_direction(_working_direction(state), state["rejected"], constraints=state["constraints"], user_messages=state["user_messages"])
        document = _render_design_md(state, tokens)
        state["phase"], state["exported_at"] = "final", datetime.now(timezone.utc).isoformat()
        path = design_md_path(session_id); path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp"); temporary.write_text(document, encoding="utf-8"); os.replace(temporary, path)
        requested = args.get("folder")
        if requested is not None and (not isinstance(requested, str) or not any(_contains(message, requested) for message in state["user_messages"])): raise ValueError("export folder must come from the user")
        candidate = Path(requested or state.get("workspace_cwd") or (Path.home() / "Documents" / "Design Discovery"))
        if requested and (not candidate.is_absolute() or not candidate.is_dir()): raise ValueError("export folder is unavailable")
        if not candidate.is_absolute() or not candidate.is_dir() or (not requested and (candidate == Path.home() or candidate.parent == candidate or str(candidate).casefold().startswith(str(Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))).casefold()))): candidate = Path.home() / "Documents" / "Design Discovery"
        candidate.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", next((item["label"] for item in state["directions"] if item["id"] == state["working"]["color"].get("direction_id")), "design").casefold()).strip("-")
        public = Path(state.get("export_path") or candidate / "DESIGN.md")
        if public.parent != candidate or (public.exists() and state.get("export_path") != str(public)):
            public = candidate / ("DESIGN-" + slug + ".md")
            index = 2
            while public.exists(): public = candidate / ("DESIGN-" + slug + "-" + str(index) + ".md"); index += 1
        public.write_text(document, encoding="utf-8")
        state["export_path"] = str(public.resolve())
        _record_confirmation(state, confirmation_event_id, "export", "export_confirmation")
        return _result("Give the user this saved path in one line and stop.", design_md=document, design_md_path=str(public.resolve()), state=replace_state(state, session_id), confirmation={"message_event_id": confirmation_event_id, "scope": "export"})
    except Exception as exc: return _refusal(exc)

def pre_llm_call(**kwargs):
    try:
        session_id = str(kwargs.get("session_id") or "")
        state = get_state(session_id)
        message = kwargs.get("user_message")
        if session_id and isinstance(message, str) and message:
            _RECENT_USER_MESSAGES[session_id] = [*_RECENT_USER_MESSAGES.get(session_id, []), message][-10:]
            _RECENT_MESSAGE_EVENTS[session_id] = [*_RECENT_MESSAGE_EVENTS.get(session_id, []), {"role":"user","text":message}][-20:]
        if session_id and _is_design_invocation(message):
            state = _activate(session_id)
        if not state.get("active") or not session_id or state.get("session_id") != session_id: return None
        if isinstance(message, str) and message:
            _append_message(state, "user", message)
            state = replace_state(_clean(state), session_id)
        return {"context":"Design Discovery state (authoritative, rev {rev}): {state}".format(rev=state["rev"],state=json.dumps(state,ensure_ascii=False,separators=(",",":")))}
    except Exception: return None

def post_llm_call(**kwargs):
    try:
        session_id, message = str(kwargs.get("session_id") or ""), kwargs.get("assistant_response")
        if not session_id or not isinstance(message, str) or not message: return None
        _RECENT_ASSISTANT_MESSAGES[session_id] = [*_RECENT_ASSISTANT_MESSAGES.get(session_id, []), message][-10:]
        _RECENT_MESSAGE_EVENTS[session_id] = [*_RECENT_MESSAGE_EVENTS.get(session_id, []), {"role":"assistant","text":message}][-20:]
        state = get_state(session_id)
        if not state.get("active") or state.get("session_id") != session_id: return None
        _append_message(state, "assistant", message)
        replace_state(_clean(state), session_id)
    except Exception: return None

def _clarify_answers(result):
    """Return (parsed, answers) from a host clarify result. Never trusts tool arguments."""
    if not isinstance(result, str) or not result.strip(): return False, []
    try: parsed = json.loads(result)
    except ValueError: return True, [result.strip()]
    if isinstance(parsed, str): return (True, [parsed.strip()]) if parsed.strip() else (False, [])
    if not isinstance(parsed, dict) or parsed.get("error"): return False, []
    if isinstance(parsed.get("responses"), list):
        if parsed.get("outcome", "submitted") != "submitted": return True, []
        answers = [item["user_response"].strip() for item in parsed["responses"] if isinstance(item, dict) and item.get("status", "answered") == "answered" and isinstance(item.get("user_response"), str) and item["user_response"].strip()]
        return True, answers
    answer = next((parsed[key] for key in ("user_response", "answer", "response") if isinstance(parsed.get(key), str)), None)
    return (True, [answer.strip()]) if answer and answer.strip() else (False, [])

def post_tool_call(**kwargs):
    """Log the user's answers to the host's clarify tool as interview replies."""
    try:
        session_id = str(kwargs.get("session_id") or "")
        if str(kwargs.get("tool_name") or "") != "clarify" or not session_id: return None
        parsed, answers = _clarify_answers(kwargs.get("result")) if kwargs.get("status") in (None, "ok") else (False, [])
        logged = 0
        try:
            for answer in answers:
                _RECENT_USER_MESSAGES[session_id] = [*_RECENT_USER_MESSAGES.get(session_id, []), answer][-10:]
                _RECENT_MESSAGE_EVENTS[session_id] = [*_RECENT_MESSAGE_EVENTS.get(session_id, []), {"role":"user","text":answer,"source":"clarify"}][-20:]
            state = get_state(session_id)
            if answers and state.get("active") and state.get("session_id") == session_id:
                for answer in answers:
                    state["user_messages"] = [*state.get("user_messages", []), answer][-50:]
                    _append_event(state, {"role":"user","text":answer,"source":"clarify"})
                replace_state(_clean(state), session_id)
                logged = len(answers)
        finally:
            append_tool_event(session_id, {"timestamp": datetime.now(timezone.utc).isoformat(), "tool": "clarify", "action": "post_tool_call", "args": {"parsed": parsed, "answers_logged": logged}, "ok": parsed})
    except Exception: return None

def pre_tool_call(**kwargs):
    """Hold build tools until the active design session has exported DESIGN.md."""
    try:
        tool_name, session_id = str(kwargs.get("tool_name") or ""), str(kwargs.get("session_id") or "")
        allowed = {"generate_directions", "record_understanding", "design_discovery_get_state", "update_choice", "export_design_md", "tool_search", "tool_describe", "skills_list", "clarify"}
        if tool_name.startswith("design_discovery") or tool_name in allowed: return None
        state = get_state(session_id)
        if not state.get("active") or state.get("session_id") != session_id or state.get("phase") == "final":
            return None
        if tool_name == "skill_view":
            args = kwargs.get("args") if isinstance(kwargs.get("args"), dict) else {}
            skill = str(args.get("skill_name") or args.get("name") or args.get("skill") or "")
            if skill in {"design-discovery", "design-discovery:design-discovery"}: return None
            return {"action": "block", "message": "You’re in a design discovery session. Use only the design discovery tools until DESIGN.md is exported."}
        return {"action": "block", "message": "Design discovery is in progress. Use the design discovery tools, tool search, or tool detail until DESIGN.md is exported."}
    except Exception:
        return None

def register(ctx) -> None:
    def logged(name, handler):
        def invoke(args, **kwargs):
            result = handler(args, **kwargs)
            session_id = str(kwargs.get("session_id") or "")
            if session_id:
                payload = json.loads(result)
                structural = {key: args[key] for key in ("dimension", "path", "source", "direction", "direction_id", "from_direction") if key in args}
                if name == "generate_directions" and isinstance(payload.get("generated_directions"), list):
                    structural["directions"] = payload["generated_directions"]
                elif name == "generate_directions" and isinstance(args.get("directions"), list):
                    structural["directions"] = [{"color": {key: direction.get("composed_palette", {}).get(key) for key in ("background", "surface", "text", "muted", "border", "border_strong", "accent")}, "accent_usage": direction.get("accent_usage")} for direction in args["directions"] if isinstance(direction, dict)]
                if name == "generate_directions":
                    sample = args.get("sample")
                    structural["sample_shape"] = {str(key): type(value).__name__ for key, value in sample.items()} if isinstance(sample, dict) else type(sample).__name__
                    structural["voice_shapes"] = [{str(key): type(value).__name__ for key, value in item.get("voice", {}).items()} if isinstance(item.get("voice"), dict) else type(item.get("voice")).__name__ for item in args.get("directions", []) if isinstance(item, dict)]
                try:
                    append_tool_event(session_id, {"timestamp": datetime.now(timezone.utc).isoformat(), "tool": name, "action": args.get("action"), "args": structural, "ok": payload.get("ok", False), "error_code": payload.get("error"), "next_code": payload.get("next"), "rev": payload.get("state", {}).get("rev"), "confirmation": payload.get("confirmation")})
                except Exception:
                    pass
            return result
        return invoke
    ctx.register_tool(name="generate_directions",toolset="design_discovery",schema=GENERATE_SCHEMA,handler=logged("generate_directions", generate_directions))
    ctx.register_tool(name="record_understanding",toolset="design_discovery",schema=UNDERSTANDING_SCHEMA,handler=logged("record_understanding", record_understanding))
    ctx.register_tool(name="design_discovery_get_state",toolset="design_discovery",schema=GET_STATE_SCHEMA,handler=logged("design_discovery_get_state", design_discovery_get_state_tool))
    ctx.register_tool(name="update_choice",toolset="design_discovery",schema=UPDATE_SCHEMA,handler=logged("update_choice", update_choice))
    ctx.register_tool(name="export_design_md",toolset="design_discovery",schema=EXPORT_SCHEMA,handler=logged("export_design_md", export_design_md))
    ctx.register_hook("pre_llm_call",pre_llm_call); ctx.register_hook("post_llm_call",post_llm_call); ctx.register_hook("pre_tool_call",pre_tool_call); ctx.register_hook("post_tool_call",post_tool_call); ctx.register_skill("design-discovery",Path(__file__).parent / "skills" / "design-discovery" / "SKILL.md")
