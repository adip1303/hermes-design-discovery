"""Deterministic Track A data loading, resolution, and constraint checks."""
from __future__ import annotations
import colorsys
import difflib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from .contrast import contrast_ratio, report as contrast_report

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DIMENSIONS = ("typography", "color", "layout", "geometry", "motion")
ADJUSTMENT_PATHS = {"typography.display_font": "display", "typography.body_font": "body", "typography.scale": "type_scale_id", "typography.weight_contrast": "weight_contrast", "layout.density": "density", "geometry.radius": "radius", "geometry.border": "border", "geometry.elevation": "elevation", "motion.preset": "motion_preset", "color.accent": "accent"}

def _read(path: Path) -> Any: return json.loads(path.read_text(encoding="utf-8"))
def archetypes() -> dict[str, dict[str, Any]]: return {item["id"]: item for path in sorted((DATA / "archetypes").glob("*.json")) for item in [_read(path)]}
def fonts() -> dict[str, dict[str, Any]]:
    items = _read(DATA / "fonts.json"); classes = _read(DATA / "vocabulary.json")["font_classes"]
    if any(set(item) - {"id", "family", "category", "class", "roles", "weights", "variable", "license", "fallback", "tags", "source"} or not isinstance(item.get("class"), str) or item["class"] not in classes for item in items): raise ValueError("every font requires one known class")
    counts = {name: sum(item["class"] == name for item in items) for name in classes}
    if any(count < 2 for count in counts.values()): raise ValueError("every font class requires at least two fonts")
    return {item["id"]: item for item in items}
def _enum_data() -> dict[str, Any]: return _read(DATA / "enums.json")
def enums() -> dict[str, Any]: return _enum_data()["$defs"]
def _validate_enum_guidance() -> None:
    data = _enum_data(); values = data.get("token_values", {})
    groups = {"type_scale_id": "type_scales", "weight_contrast": "weight_contrasts", "density": "densities", "radius": "radii", "border": "borders", "elevation": "elevations", "motion_preset": "motion_presets"}
    for enum_name, group in groups.items():
        entries = values.get(group)
        if not isinstance(entries, dict) or any(not isinstance(entries.get(value), dict) or not isinstance(entries[value].get("guidance"), str) or not entries[value]["guidance"] for value in enums()[enum_name]["enum"]):
            raise ValueError("enums.json is missing guidance for " + enum_name)
    for group in ("densities", "motion_presets"):
        if not isinstance(values.get(group, {}).get("always"), list) or not all(isinstance(line, str) and line for line in values[group]["always"]):
            raise ValueError("enums.json is missing always guidance for " + group)
    color = values.get("color")
    if not isinstance(color, dict) or not isinstance(color.get("always"), list) or not isinstance(color.get("fill_only"), str):
        raise ValueError("enums.json is missing color guidance")
def vocabulary() -> dict[str, Any]:
    """Load the word-to-move catalog and reject a bad catalog before a session starts."""
    value = _read(DATA / "vocabulary.json")
    if not isinstance(value, dict) or not isinstance(value.get("words"), list) or not isinstance(value.get("font_classes"), dict):
        raise ValueError("vocabulary.json must contain words and font_classes")
    traits = set(enums()["trait"]["enum"])
    move_enums = {
        "layout.density": "density", "geometry.radius": "radius", "geometry.border": "border",
        "geometry.elevation": "elevation", "motion.preset": "motion_preset",
        "type.scale": "type_scale_id", "type.weight_contrast": "weight_contrast",
    }
    for word in value["words"]:
        if not isinstance(word, dict) or not isinstance(word.get("id"), str) or not isinstance(word.get("aliases"), list) or not isinstance(word.get("traits"), list):
            raise ValueError("vocabulary word requires id, aliases, and traits")
        if any(not isinstance(trait, str) or trait not in traits for trait in word["traits"]):
            raise ValueError("vocabulary has an unknown trait")
        for section, field in (("layout", "density"), ("geometry", "radius"), ("geometry", "border"), ("geometry", "elevation"), ("motion", "preset"), ("type", "scale"), ("type", "weight_contrast")):
            moves = word.get(section, {})
            if moves is not None and not isinstance(moves, dict): raise ValueError("vocabulary move section must be an object")
            if isinstance(moves, dict) and field in moves:
                values = moves[field]
                if not isinstance(values, list) or any(item not in enums()[move_enums[section + "." + field]]["enum"] for item in values):
                    raise ValueError("vocabulary has an invalid " + section + "." + field + " move")
        type_moves = word.get("type", {})
        if isinstance(type_moves, dict) and "classes" in type_moves:
            if not isinstance(type_moves["classes"], list) or any(item not in value["font_classes"] for item in type_moves["classes"]):
                raise ValueError("vocabulary has an unknown font class")
    for phrase in value.get("common_phrases", []):
        if not isinstance(phrase, dict) or not isinstance(phrase.get("phrases"), list) or not isinstance(phrase.get("reading"), str):
            raise ValueError("vocabulary phrase readings require phrases and reading")
    return value
def conflict_rules() -> list[dict[str, Any]]:
    path = DATA / "conflicts.json"
    value = _read(path) if path.exists() else {}
    if not isinstance(value, dict) or not isinstance(value.get("rules"), list):
        raise ValueError("conflicts.json must contain a rules list")
    traits = set(enums()["trait"]["enum"])
    density_values = set(enums()["density"]["enum"])
    for rule in value["rules"]:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or rule.get("a") not in traits or rule.get("b") not in traits or rule.get("severity") not in {"tension", "clash"} or not all(isinstance(rule.get(key), str) and rule[key] for key in ("tradeoff", "resolution")):
            raise ValueError("conflicts.json has an unknown trait")
        for variant in rule.get("variants", []):
            if not isinstance(variant, dict) or set(variant) != {"when", "resolution"} or not isinstance(variant["resolution"], str) or not variant["resolution"] or not isinstance(variant["when"], dict): raise ValueError("conflicts.json has an invalid variant")
            when = variant["when"]
            if not when or set(when) - {"user_accent", "density"}: raise ValueError("conflicts.json has an unknown variant condition")
            if "user_accent" in when and not isinstance(when["user_accent"], bool): raise ValueError("conflicts.json has an invalid user_accent condition")
            if "density" in when and (not isinstance(when["density"], list) or not when["density"] or any(item not in density_values for item in when["density"])): raise ValueError("conflicts.json has an invalid density condition")
    return value["rules"]
def blank_rejected() -> dict[str, Any]: return {"archetypes": {dimension: [] for dimension in DIMENSIONS}, "fonts": [], "accents": []}
def empty_adjustments() -> dict[str, dict[str, Any]]: return {}
def _hex(value: Any) -> bool: return isinstance(value, str) and len(value) == 7 and value.startswith("#") and all(char in "0123456789abcdefABCDEF" for char in value[1:])
_COMPOSED_KEYS = ("background", "surface", "text", "muted", "border", "border_strong", "accent")
def _word_catalog() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for word in vocabulary()["words"]:
        for name in [word["id"], *word["aliases"]]: result[name.casefold()] = word
    return result
def filter_composed_words(words: Any) -> tuple[list[str], list[str]]:
    """Resolve known vocabulary aliases and report only discarded inputs."""
    if not isinstance(words, list): return [], ["words"]
    catalog, resolved, dropped = _word_catalog(), [], []
    for word in words:
        entry = catalog.get(word.casefold()) if isinstance(word, str) else None
        if entry: resolved.append(entry["id"])
        else: dropped.append(str(word))
    return resolved[:4], dropped
def _validate_composed_words(palette: dict[str, Any]) -> list[str]:
    words = palette.get("words")
    if not isinstance(words, list) or not len(words) <= 4 or any(not isinstance(word, str) for word in words):
        raise ValueError("composed_palette words must contain up to 4 vocabulary words")
    catalog = _word_catalog(); resolved = []
    for word in words:
        entry = catalog.get(word.casefold())
        if not entry:
            suggestions = difflib.get_close_matches(word.casefold(), sorted(catalog), n=3, cutoff=.45)
            raise ValueError("unknown composed palette word: " + word + ". Closest valid words: " + ", ".join(suggestions or sorted(catalog)[:3]))
        resolved.append(entry["id"])
    return resolved
def _hls(value: str) -> tuple[float, float, float]:
    rgb = tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))
    return colorsys.rgb_to_hls(*rgb)
def _hex_hls(hue: float, lightness: float, saturation: float) -> str:
    return "#" + "".join(f"{round(part * 255):02X}" for part in colorsys.hls_to_rgb(hue, max(0, min(1, lightness)), saturation))
def _correct_lightness(value: str, backgrounds: list[str], required: float) -> str | None:
    if all(contrast_ratio(value, ground) >= required for ground in backgrounds): return value
    hue, lightness, saturation = _hls(value)
    candidates = [_hex_hls(hue, step / 100, saturation) for step in range(101)]
    candidates.sort(key=lambda candidate: abs(_hls(candidate)[1] - lightness))
    return next((candidate for candidate in candidates if all(contrast_ratio(candidate, ground) >= required for ground in backgrounds)), None)
def auto_correct_composed_palette(palette: dict[str, Any]) -> list[dict[str, str]]:
    """Make a composed palette readable without choosing a different color family."""
    if not isinstance(palette, dict) or any(not _hex(palette.get(key)) for key in _COMPOSED_KEYS):
        return []
    adjusted: list[dict[str, str]] = []
    background = palette["background"]
    hue, surface_lightness, saturation = _hls(palette["surface"])
    _, background_lightness, _ = _hls(background)
    difference = abs(surface_lightness - background_lightness)
    if not .02 <= difference <= .08:
        direction = 1 if surface_lightness >= background_lightness else -1
        target = max(0, min(1, background_lightness + direction * .03))
        if target == background_lightness: target = max(0, min(1, background_lightness - direction * .03))
        replacement = _hex_hls(hue, target, saturation)
        adjusted.append({"role": "surface", "from": palette["surface"], "to": replacement})
        palette["surface"] = replacement
    for role, required in (("text", 7), ("muted", 4.5), ("border_strong", 3), ("accent", 3)):
        grounds = [palette["background"], palette["surface"]]
        replacement = _correct_lightness(palette[role], grounds, required)
        if replacement is None:
            raise ValueError("composed palette " + role + " cannot be made readable")
        if replacement != palette[role]:
            adjusted.append({"role": role, "from": palette[role], "to": replacement})
            palette[role] = replacement
    return adjusted
def _status_color(hue_degrees: int, background: str, surface: str) -> str:
    _, background_lightness, _ = _hls(background)
    direction = -1 if background_lightness >= .5 else 1
    for step in range(101):
        candidate = _hex_hls(hue_degrees / 360, .38 + direction * step / 100, .64)
        if contrast_ratio(candidate, background) >= 4.5 and contrast_ratio(candidate, surface) >= 4.5: return candidate
    raise ValueError("could not derive a readable status color")
def _derived_composed_color(palette: dict[str, str]) -> dict[str, Any]:
    background, surface = palette["background"], palette["surface"]
    contrast = contrast_ratio(palette["accent"], background)
    accent_text = next((candidate for candidate in ("#000000", "#FFFFFF", palette["text"], background) if contrast_ratio(candidate, palette["accent"]) >= 4.5), max(("#000000", "#FFFFFF", palette["text"], background), key=lambda item: contrast_ratio(item, palette["accent"])))
    _, lightness, _ = _hls(background)
    return {**palette, "mode": "light" if lightness >= .5 else "dark", "accent_text": accent_text,
            "accent_alternates": [], "success": _status_color(140, background, surface), "warning": _status_color(42, background, surface), "danger": _status_color(0, background, surface),
            "accent_usage": "text_and_fill" if contrast >= 4.5 else "fill_only"}
def _readable_accent_text(value: str) -> tuple[str, str]:
    if contrast_ratio("#FFFFFF", value) >= 4.5: return value, "#FFFFFF"
    if contrast_ratio("#000000", value) >= 4.5: return value, "#000000"
    hue, lightness, saturation = _hls(value)
    candidates = [_hex_hls(hue, step / 100, saturation) for step in range(101)]
    candidates.sort(key=lambda candidate: abs(_hls(candidate)[1] - lightness))
    for candidate in candidates:
        if contrast_ratio("#FFFFFF", candidate) >= 4.5: return candidate, "#FFFFFF"
        if contrast_ratio("#000000", candidate) >= 4.5: return candidate, "#000000"
    raise ValueError("accent cannot be made readable")
def _validate_composed_palette(palette: Any) -> None:
    if not isinstance(palette, dict) or set(palette) != {*_COMPOSED_KEYS, "words"} or any(not _hex(palette.get(key)) for key in _COMPOSED_KEYS):
        raise ValueError("composed_palette must contain exactly background, surface, text, muted, border, border_strong, accent, and words")
    palette["words"] = _validate_composed_words(palette)
    for foreground, background, required in (("text", "background", 7), ("text", "surface", 7), ("muted", "background", 4.5), ("muted", "surface", 4.5), ("border_strong", "background", 3), ("accent", "background", 3)):
        ratio = contrast_ratio(palette[foreground], palette[background])
        if ratio < required:
            _, bg_lightness, _ = _hls(palette[background])
            move = "darker" if bg_lightness >= .5 else "lighter"
            raise ValueError(f"composed palette {foreground} on {background} is {ratio}:1; it needs {required}:1. Make {foreground} {move}.")
    _, background_lightness, _ = _hls(palette["background"]); _, surface_lightness, _ = _hls(palette["surface"])
    difference = abs(surface_lightness - background_lightness) * 100
    if not 2 <= difference <= 8:
        low, high = max(0, background_lightness * 100 - 8), min(100, background_lightness * 100 + 8)
        inner_low, inner_high = max(0, background_lightness * 100 - 2), min(100, background_lightness * 100 + 2)
        raise ValueError(f"composed palette surface is {difference:.1f} lightness points from background; it needs 2 to 8. Use surface lightness between {low:.1f} and {inner_low:.1f}, or between {inner_high:.1f} and {high:.1f}.")
    derived = {"color": _derived_composed_color(dict(palette))}
    failed = next((item for item in contrast_report(derived).values() if not item["passes"]), None)
    if failed:
        raise ValueError(f"composed palette {failed['label'].casefold()}; it needs {failed['minimum']}:1")
def _message_contains(message: object, value: object) -> bool:
    normalize = lambda item: "".join(char for char in str(item).casefold() if char.isalnum())
    return normalize(value) in normalize(message)

def _path_value(values: dict[str, Any], path: str) -> Any:
    value: Any = values
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value: return None
        value = value[part]
    return value

def _font_alternatives(source_font: str, role: str, rejected: dict[str, Any]) -> str:
    all_fonts = fonts(); category = all_fonts[source_font]["category"]
    candidates = [font_id for font_id, item in all_fonts.items() if item["category"] == category and role in item["roles"] and font_id not in rejected["fonts"]]
    return ", ".join(candidates[:3]) or "none"

def _validate_adjustment(path: str, entry: Any, sources: dict[str, str], rejected: dict[str, Any], user_messages: list[str] | None = None) -> None:
    if path not in ADJUSTMENT_PATHS: raise ValueError(f"unsupported adjustment path: {path}")
    direction_entry = path == "color.accent" and isinstance(entry, dict) and entry.get("source") == "direction" and set(entry) == {"value", "source", "from_direction"}
    described_entry = path == "color.accent" and isinstance(entry, dict) and entry.get("source") == "described" and set(entry) in ({"value", "source", "user_words"}, {"value", "source", "user_words", "contrast_adjusted"})
    if not isinstance(entry, dict) or (set(entry) != {"value", "source"} and not direction_entry and not described_entry) or entry["source"] not in {"agent", "user", "direction", "described"}: raise ValueError(f"adjustment {path} must contain value and source (agent, user, direction, or described)")
    value, kind = entry["value"], ADJUSTMENT_PATHS[path]
    if entry["source"] == "user":
        shown_value = fonts().get(value, {}).get("family", value) if kind in {"display", "body"} else value
        if user_messages is not None and not any(str(shown_value).casefold() in message.casefold() for message in user_messages):
            entry["source"] = "agent"
    if entry["source"] == "described" and not any(_message_contains(message, entry["user_words"]) for message in (user_messages or [])):
        raise ValueError("described color words must come from the user")
    if kind in {"display", "body"}:
        available = fonts()
        if value not in available:
            source_font = archetypes()[sources["typography"]]["typography"]["display_font" if kind == "display" else "body_font"]
            raise ValueError(f"unknown font: {value}. Closest available {kind} fonts in category {available[source_font]['category']}: {_font_alternatives(source_font, kind, rejected)}")
        if kind not in available[value]["roles"]: raise ValueError(f"font does not allow {kind}: {value}")
        if value in rejected["fonts"]: raise ValueError(f"font is rejected: {value}")
    elif kind == "accent":
        if not _hex(value): raise ValueError("color.accent must be a #RRGGBB hex value")
        if value in rejected["accents"]: raise ValueError("accent is rejected")
        if entry["source"] == "agent" and not sources["color"].startswith("composed:"):
            color = archetypes()[sources["color"]]["color"]
            if value not in color["accent_alternates"]: raise ValueError("agent-sourced accent must be from the color source alternates")
    elif value not in enums()[kind]["enum"]: raise ValueError(f"invalid {path}: {value}")

def validate_adjustments(adjustments: Any, sources: dict[str, str], rejected: dict[str, Any] | None = None, user_messages: list[str] | None = None) -> None:
    rejected = rejected or blank_rejected()
    if not isinstance(adjustments, dict): raise ValueError("adjustments is required")
    for path, entry in adjustments.items(): _validate_adjustment(path, entry, sources, rejected, user_messages)

def _enforce_constraints(tokens: dict[str, Any], constraints: list[dict[str, Any]]) -> None:
    for constraint in constraints:
        path, value = constraint.get("path"), constraint.get("value")
        if not path or value is None: continue
        actual = _path_value(tokens, path)
        violates = actual != value if constraint["kind"] == "require" else actual == value
        if violates: raise ValueError(f"constraint violated: {constraint['text']}")

def validate_direction(direction: dict[str, Any], rejected: dict[str, Any] | None = None, constraints: list[dict[str, Any]] | None = None, user_messages: list[str] | None = None) -> None:
    rejected = rejected or blank_rejected(); available = archetypes(); sources, adjustments = direction.get("sources"), direction.get("adjustments")
    if not isinstance(sources, dict) or set(sources) != set(DIMENSIONS): raise ValueError("sources must name all five dimensions")
    for dimension in DIMENSIONS:
        source = sources[dimension]
        if dimension == "color" and source == "composed": raise ValueError('Use sources.color "composed" only when generating; the plugin assigns its composed direction id.')
        if dimension == "color" and isinstance(source, str) and source.startswith("composed:"):
            expected = "composed:" + str(direction.get("id") or "")
            if direction.get("id") != "working" and source != expected: raise ValueError('composed color source must be "composed:" plus this direction id')
            _validate_composed_palette(direction.get("composed_palette"))
            continue
        if dimension == "color" and "composed_palette" in direction: raise ValueError("archetype color directions cannot also include composed_palette")
        if source not in available: raise ValueError(f"unknown {dimension} archetype: {source}")
        if source in rejected["archetypes"][dimension]: raise ValueError(f"rejected {dimension} archetype: {source}")
    validate_adjustments(adjustments, sources, rejected, user_messages)
    if constraints: _enforce_constraints(resolve_direction(direction, rejected, enforce_constraints=False), constraints)

def resolve_direction(direction: dict[str, Any], rejected: dict[str, Any] | None = None, enforce_constraints: bool = True, constraints: list[dict[str, Any]] | None = None, user_messages: list[str] | None = None) -> dict[str, Any]:
    if enforce_constraints: validate_direction(direction, rejected, user_messages=user_messages)
    items, sources = archetypes(), direction["sources"]
    resolved = {dimension: deepcopy(items[sources[dimension]][dimension]) for dimension in DIMENSIONS if dimension != "color"}
    composed = isinstance(sources.get("color"), str) and sources["color"].startswith("composed:")
    resolved["color"] = _derived_composed_color({key: direction["composed_palette"][key] for key in _COMPOSED_KEYS}) if composed else deepcopy(items[sources["color"]]["color"])
    provenance = {dimension: {key: sources[dimension] for key in values} for dimension, values in resolved.items()}
    resolved["voice"] = deepcopy(direction.get("voice") or items[sources["typography"]]["voice"]); provenance["voice"] = {key: "user" if direction.get("voice") else sources["typography"] for key in resolved["voice"]}
    resolved["accent_usage"] = resolved["color"].pop("accent_usage") if composed else items[sources["color"]].get("accent_usage", "text_and_fill"); provenance["accent_usage"] = sources["color"]
    for path, entry in direction["adjustments"].items():
        container, key, value = *path.split("."), entry["value"]
        if path == "color.accent":
            color = resolved["color"]
            background_contrast = contrast_ratio(value, color["background"])
            if background_contrast < 3: raise ValueError(f"accent {value} cannot reach 3:1 against the background")
            candidates = [color["accent_text"], color["background"], color["text"], "#FFFFFF"]
            accent_text = next((candidate for candidate in candidates if contrast_ratio(candidate, value) >= 4.5), max(candidates, key=lambda candidate: contrast_ratio(candidate, value)))
            color["accent_text"] = accent_text; provenance["color"]["accent_text"] = entry["source"]
            resolved["accent_usage"] = "text_and_fill" if background_contrast >= 4.5 else "fill_only"
            provenance["accent_usage"] = entry["source"]
        resolved[container][key] = value; provenance[container][key] = entry["source"]
    corrected_accent, accent_text = _readable_accent_text(resolved["color"]["accent"])
    if corrected_accent != resolved["color"]["accent"]: resolved["color"]["accent"] = corrected_accent
    resolved["color"]["accent_text"] = accent_text
    if resolved["typography"].get("ui_font") is None: resolved["typography"]["ui_font"] = resolved["typography"]["body_font"]; provenance["typography"]["ui_font"] = provenance["typography"]["body_font"]
    resolved["provenance"] = provenance
    if constraints: _enforce_constraints(resolved, constraints)
    return resolved

def _palette_signature(direction: dict[str, Any]) -> tuple[str, dict[str, str]]:
    resolved = resolve_direction(direction, enforce_constraints=False)
    return direction["label"], resolved["color"]

def color_variety_error(directions: list[dict[str, Any]], typography_variety: bool = True) -> str | None:
    """Return a human-meaningful collision; never score a palette's taste."""
    signatures = [_palette_signature(direction) for direction in directions]
    failures = []
    for index, (left_label, left) in enumerate(signatures):
        for right_label, right in signatures[index + 1:]:
            _, left_lightness, left_saturation = _hls(left["background"]); left_hue = _hls(left["background"])[0] * 360
            _, right_lightness, right_saturation = _hls(right["background"]); right_hue = _hls(right["background"])[0] * 360
            background_hue_diff = abs((left_hue - right_hue + 180) % 360 - 180)
            _, _, left_accent_saturation = _hls(left["accent"]); left_accent_hue = _hls(left["accent"])[0] * 360
            _, _, right_accent_saturation = _hls(right["accent"]); right_accent_hue = _hls(right["accent"])[0] * 360
            accent_hue_diff = abs((left_accent_hue - right_accent_hue + 180) % 360 - 180)
            mode_diff = left["mode"] != right["mode"]
            lightness_value = abs(left_lightness - right_lightness) * 100; lightness_diff = lightness_value >= 15
            hue_diff = left_saturation > .05 and right_saturation > .05 and background_hue_diff >= 30
            left_neutral, right_neutral = left_accent_saturation < .10, right_accent_saturation < .10
            accent_diff = left_neutral != right_neutral or (not left_neutral and not right_neutral and accent_hue_diff >= 40)
            if not any((mode_diff, lightness_diff, hue_diff, accent_diff)):
                target = (left_accent_hue + 40) % 360
                failures.append(f"{left_label} and {right_label}: mode differs: {'yes' if mode_diff else 'no'}; background lightness difference {lightness_value:.1f} (need 15+); background hue difference {background_hue_diff:.1f} (need 30+, counted only when both saturations exceed 5%); accent family difference {accent_hue_diff:.1f} (need 40+, or neutral versus chromatic). Move {right_label}'s accent hue at least 40 degrees from {left_label}'s, currently {left_accent_hue:.0f} versus {right_accent_hue:.0f}; try {target:.0f} or higher. Changes to saturation, text, muted, or borders do not count toward variety.")
    used = {}
    for direction in directions:
        font = resolve_direction(direction)["typography"]["display_font"]
        used.setdefault(font, []).append(direction["label"])
    duplicates = [(font, labels) for font, labels in used.items() if len(labels) > 1]
    if typography_variety and duplicates:
        all_fonts = fonts()
        unused = [font_id for font_id, item in all_fonts.items() if "display" in item["roles"] and font_id not in used]
        failures.extend("Display font " + font + " is shared by " + " and ".join(labels) + ". Options: " + ", ".join(unused) + "." for font, labels in duplicates)
    return "directions are too similar in color or typography:\n" + "\n".join(failures) if failures else None

def direction_traits(direction: dict[str, Any]) -> set[str]:
    items, traits = archetypes(), set()
    for source in direction["sources"].values():
        if source in items: traits.update(items[source]["traits"])
    if str(direction["sources"].get("color", "")).startswith("composed:"):
        for word in _validate_composed_words(direction["composed_palette"]): traits.update(_word_catalog()[word]["traits"])
    return traits
def detect_conflicts(direction: dict[str, Any]) -> list[dict[str, Any]]:
    traits = direction_traits(direction)
    density = resolve_direction(direction, enforce_constraints=False)["layout"]["density"]
    accent = direction.get("adjustments", {}).get("color.accent", {})
    context = {"user_accent": accent.get("source") in {"user", "described"}, "density": density}
    results = []
    for rule in conflict_rules():
        if not {rule["a"], rule["b"]} <= traits: continue
        resolution = rule["resolution"]
        for variant in rule.get("variants", []):
            when = variant["when"]
            if all(context[key] == value if key == "user_accent" else context[key] in value for key, value in when.items()):
                resolution = variant["resolution"]; break
        results.append({"rule_id": rule["id"], "severity": rule["severity"], "tradeoff": rule["tradeoff"], "resolution": resolution})
    return results

_validate_enum_guidance()

def catalog() -> list[dict[str, Any]]:
    fields = ("id", "name", "summary", "not", "traits", "use_when", "avoid_when")
    return [{**{field: item[field] for field in fields}, "accent_usage": item.get("accent_usage", "text_and_fill"), "typography": item["typography"], "density": item["layout"]["density"], "radius": item["geometry"]["radius"], "border": item["geometry"]["border"], "elevation": item["geometry"]["elevation"], "motion": item["motion"]["preset"]} for item in archetypes().values()]

# Validate bundled vocabulary on import, before a live tool call can consume it.
VOCABULARY = vocabulary()
_CONFLICT_RULES = conflict_rules()
