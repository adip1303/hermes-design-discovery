import ast
import importlib
import re
import json
import tempfile
import sys
import types
from unittest.mock import patch
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PACKAGE = "test_design_discovery_plugin"


def _load_plugin():
    module = sys.modules.get(PLUGIN_PACKAGE)
    if module is None:
        spec = importlib.util.spec_from_file_location(PLUGIN_PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[PLUGIN_PACKAGE] = module
        spec.loader.exec_module(module)
    return module


plugin = _load_plugin()
design_core = importlib.import_module(PLUGIN_PACKAGE + ".design_core")
state = importlib.import_module(PLUGIN_PACKAGE + ".state")
contrast = importlib.import_module(PLUGIN_PACKAGE + ".contrast")
contrast_ratio, report = contrast.contrast_ratio, contrast.report


def direction(color="quiet-warmth", accent="#4E5A3A"):
    adjustments = {} if accent is None else {"color.accent": {"value": accent, "source": "agent"}}
    return {"id": "one", "label": "One", "rationale": "Test", "sources": {"typography": "precision-technical", "color": color, "layout": "precision-technical", "geometry": "precision-technical", "motion": "precision-technical"}, "adjustments": adjustments}


COMPOSED = {"background": "#FCF7F0", "surface": "#F4EDE4", "text": "#2B2018", "muted": "#67594E", "border": "#D9C8B6", "border_strong": "#8D715B", "accent": "#B84A22", "words": ["warm"]}


def composed_direction(label="Clay Morning", palette=None):
    item = direction(accent=None)
    item.update({"label": label, "sources": {**item["sources"], "color": "composed"}, "composed_palette": dict(palette or COMPOSED)})
    return item


def composed_triplet(first=None):
    return [first or composed_direction(), composed_direction("Olive Sand", {**COMPOSED, "background": "#EEE2C7", "surface": "#E6D8BA", "text": "#282216", "muted": "#625B45", "border_strong": "#867650", "accent": "#617333"}), composed_direction("Amber Espresso", {**COMPOSED, "background": "#241710", "surface": "#2D1D14", "text": "#FFF3E8", "muted": "#D6BEB0", "border_strong": "#8A684F", "accent": "#DE932F"})]


def varied_directions():
    first = direction()
    second = direction(color="precision-technical", accent=None); second["id"], second["label"] = "two", "Two"; second["adjustments"] = {"typography.display_font": {"value": "inter", "source": "agent"}}
    third = direction(color="editorial", accent=None); third["id"], third["label"] = "three", "Three"; third["adjustments"] = {"typography.display_font": {"value": "fraunces", "source": "agent"}}
    return [first, second, third]


ANSWERS = [{"q": "What is it?", "a": "A dashboard"}]


def confirmed_understanding(plugin, session_id="one", summary=None, reply="yes, that is right"):
    summary = summary or "You want a calm dashboard for people who need clarity."
    plugin.pre_llm_call(session_id=session_id, user_message="I need a dashboard")
    plugin.post_llm_call(session_id=session_id, assistant_response="What should this help people do, and how should it feel?")
    plugin.pre_llm_call(session_id=session_id, user_message="It should feel clear and calm.")
    recorded = json.loads(plugin.design_discovery_record_understanding({"summary": summary}, session_id=session_id))
    assert recorded["ok"] is True, recorded.get("error", recorded)
    plugin.pre_llm_call(session_id=session_id, user_message=reply)
    return reply


def generate(plugin, directions, session_id="one", expect_ok=True, **extra):
    if len(directions) < 3:
        directions = [*directions, *[dict(directions[0], id=f"{directions[0]['id']}-extra-{index}") for index in range(3 - len(directions))]]
    directions = [dict(item, sources=dict(item["sources"]), adjustments=dict(item["adjustments"])) for item in directions]
    for index, item in enumerate(directions):
        if index and item["sources"]["color"] == directions[0]["sources"]["color"] and item["sources"]["color"] != "composed":
            used = {prior["sources"]["color"] for prior in directions[:index]}
            item["sources"] = {**item["sources"], "color": next(color for color in ("precision-technical", "editorial", "bright-friendly") if color not in used)}
            item["adjustments"] = {path: value for path, value in item["adjustments"].items() if not path.startswith("color.")}
    confirmation = confirmed_understanding(
        plugin,
        session_id=session_id,
        summary=extra.pop("summary", None),
        reply=extra.pop("confirmed_by_user", "yes, that is right"),
    )
    result = plugin.design_discovery_generate_directions({"directions": directions, "answers": ANSWERS, "confirmed_by_user": confirmation, **extra}, session_id=session_id)
    parsed = json.loads(result)
    if expect_ok:
        assert parsed["ok"] is True, parsed.get("error", parsed)
    return result


def update_success(plugin, args, session_id="one"):
    result = json.loads(plugin.design_discovery_update_choice(args, session_id=session_id))
    assert result["ok"] is True, result.get("error", result)
    return result


def confirm(plugin, words="confirmed"):
    plugin.pre_llm_call(session_id="one", user_message=words)

def interview_reply(plugin, session_id="one"):
    plugin.pre_llm_call(session_id=session_id, user_message="I need a dashboard.")
    plugin.post_llm_call(session_id=session_id, assistant_response="What should it help people do?")
    plugin.pre_llm_call(session_id=session_id, user_message="Help people see the daily status.")


def lock_all(plugin):
    for dimension in design_core.DIMENSIONS:
        words = "lock " + dimension
        confirm(plugin, words)
        update_success(plugin, {"action": "lock", "dimension": dimension, "direction_id": "one", "confirmed_by_user": words})


@contextmanager
def isolated_plugin():
    original = state.data_dir
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
        state.data_dir = lambda: Path(directory)
        plugin = _load_plugin()
        previous_typography_variety = plugin.TYPOGRAPHY_VARIETY_ENABLED
        plugin.TYPOGRAPHY_VARIETY_ENABLED = False
        plugin._RECENT_USER_MESSAGES.clear()
        plugin._RECENT_ASSISTANT_MESSAGES.clear()
        plugin._RECENT_MESSAGE_EVENTS.clear()
        try:
            with patch.object(Path, "home", return_value=Path(directory)):
                yield plugin
        finally:
            plugin.TYPOGRAPHY_VARIETY_ENABLED = previous_typography_variety
            plugin._RECENT_USER_MESSAGES.clear()
            plugin._RECENT_ASSISTANT_MESSAGES.clear()
            plugin._RECENT_MESSAGE_EVENTS.clear()
            state.data_dir = original


def dashboard_api():
    if "fastapi" not in sys.modules:
        fastapi = types.ModuleType("fastapi")
        class Router:
            def get(self, _path): return lambda function: function
            def post(self, _path): return lambda function: function
        class HttpError(Exception):
            def __init__(self, **kwargs): self.kwargs = kwargs
        fastapi.APIRouter, fastapi.HTTPException, fastapi.Request = Router, HttpError, object
        sys.modules["fastapi"] = fastapi
    name = "test_design_discovery_dashboard_api"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, ROOT / "dashboard" / "plugin_api.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


def test_direction_resolves_full_tokens():
    assert set(design_core.resolve_direction(direction())) == {*design_core.DIMENSIONS, "voice", "accent_usage", "provenance"}


def test_composed_palette_validates_and_derives_light_and_dark_tokens():
    light = composed_direction(); light["id"] = "dir-a"; light["sources"]["color"] = "composed:dir-a"
    tokens = design_core.resolve_direction(light)
    assert tokens["color"]["mode"] == "light" and tokens["accent_usage"] in {"text_and_fill", "fill_only"}
    assert all(contrast_ratio(tokens["color"][name], tokens["color"]["background"]) >= 4.5 for name in ("success", "warning", "danger"))
    dark = composed_direction(palette={**COMPOSED, "background": "#21140F", "surface": "#2A1A14", "text": "#FFF4EA", "muted": "#D4BEB0", "border_strong": "#8D715B", "accent": "#E07A42"}); dark["id"] = "dir-b"; dark["sources"]["color"] = "composed:dir-b"
    assert design_core.resolve_direction(dark)["color"]["mode"] == "dark"


def test_vocabulary_is_validated_at_load_and_returned_in_catalog():
    assert len(design_core.VOCABULARY["words"]) == 62
    invalid = {**design_core.VOCABULARY, "words": [{**design_core.VOCABULARY["words"][0], "traits": ["not-a-trait"]}]}
    original_read = design_core._read
    with patch.object(design_core, "_read", side_effect=lambda path: invalid if path.name == "vocabulary.json" else original_read(path)):
        try:
            design_core.vocabulary(); assert False
        except ValueError as exc:
            assert "unknown trait" in str(exc)
    with isolated_plugin() as plugin:
        catalog = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["catalog"]
        assert catalog["vocabulary"]["words"][0]["id"] == design_core.VOCABULARY["words"][0]["id"]


def test_composed_palette_legibility_errors_name_pair_ratio_and_move():
    for key, value, pair in (("text", "#C9BFB6", "text on background"), ("muted", "#C9BFB6", "muted on background"), ("border_strong", "#EDE4DA", "border_strong on background"), ("accent", "#EDE4DA", "accent on background")):
        item = composed_direction(palette={**COMPOSED, key: value}); item["id"] = "dir-a"; item["sources"]["color"] = "composed:dir-a"
        try:
            design_core.validate_direction(item)
            assert False
        except ValueError as exc:
            assert pair in str(exc) and ":1" in str(exc) and "darker" in str(exc), str(exc)
    item = composed_direction(palette={**COMPOSED, "surface": "#E1D9D0"}); item["id"] = "dir-a"; item["sources"]["color"] = "composed:dir-a"
    try:
        design_core.validate_direction(item); assert False
    except ValueError as exc:
        assert "surface" in str(exc) and "lightness points" in str(exc) and "between" in str(exc)


def test_unreadable_composed_text_refusal_names_pairs_and_offers_resendable_grounds():
    moss = {"background":"#77754A","surface":"#868357","text":"#F7F4E9","muted":"#E3DEC7","border":"#96936A","border_strong":"#BBB78D","accent":"#D99A38","words":["warm","natural"]}
    choices = composed_triplet()
    choices[2] = composed_direction("Moss Watch", moss)
    with isolated_plugin() as plugin:
        refused = json.loads(generate(plugin, choices, expect_ok=False))
        assert refused["ok"] is False and refused["error"] == "composed palette text cannot be made readable"
        assert "Moss Watch: text #F7F4E9 on background #77754A is 4.31:1, needs 7:1" in refused["next"]
        assert "text #F7F4E9 on surface #868357 is 3.53:1, needs 7:1" in refused["next"]
        recovery = design_core.composed_text_recovery(moss)
        assert recovery is not None
        darker = recovery["darker"]
        assert darker["background"] in refused["next"] and darker["surface"] in refused["next"]
        assert contrast_ratio(moss["text"], darker["background"]) >= 7
        retried = composed_triplet()
        retried[2] = composed_direction("Moss Watch", {**moss, **darker})
        accepted = json.loads(generate(plugin, retried))
        assert accepted["ok"] is True


def test_archetype_colors_remain_unchecked_and_composed_variety_is_noticeable():
    item = direction(accent=None); design_core.validate_direction(item)
    warm_white = composed_direction("Terracotta", COMPOSED)
    sand_olive = composed_direction("Olive Sand", {**COMPOSED, "background": "#EEE2C7", "surface": "#E6D8BA", "text": "#282216", "muted": "#625B45", "border_strong": "#867650", "accent": "#617333"})
    espresso_amber = composed_direction("Amber Espresso", {**COMPOSED, "background": "#241710", "surface": "#2D1D14", "text": "#FFF3E8", "muted": "#D6BEB0", "border_strong": "#8A684F", "accent": "#DE932F"})
    directions = [warm_white, sand_olive, espresso_amber]
    for index, entry in enumerate(directions): entry["id"] = f"dir-{chr(97 + index)}"; entry["sources"]["color"] = "composed:" + entry["id"]
    assert design_core.color_variety_error(directions, typography_variety=False) is None
    near = [directions[0], dict(directions[0], id="dir-z", label="Almost Clay", sources={**directions[0]["sources"], "color":"composed:dir-z"})]
    error = design_core.color_variety_error(near, typography_variety=False)
    assert "Terracotta" in error and "Almost Clay" in error
    neutral = dict(directions[0], id="dir-n", label="Neutral Accent", sources={**directions[0]["sources"], "color":"composed:dir-n"}, composed_palette={**directions[0]["composed_palette"], "accent":"#77716B"})
    assert design_core.color_variety_error([directions[0], neutral], typography_variety=False) is None


def test_legacy_direction_overrides_migrate_to_agent_adjustments():
    legacy = direction()
    legacy["overrides"] = {"accent": "#4E5A3A", "display_font": None, "body_font": None}
    legacy.pop("adjustments")
    assert state._normalise({"directions": [legacy]})["directions"][0]["adjustments"] == {"color.accent": {"value": "#4E5A3A", "source": "agent"}}


def test_voice_follows_typography_source_and_ui_font_defaults_to_body():
    choice = direction()
    choice["sources"]["typography"] = "editorial"
    tokens = design_core.resolve_direction(choice)
    assert tokens["voice"]["tone"] == "Considered, literary, precise"
    assert tokens["typography"]["ui_font"] == "libre-franklin"
    choice["sources"]["typography"] = "bright-friendly"
    tokens = design_core.resolve_direction(choice)
    assert tokens["typography"]["ui_font"] == "figtree"


def test_default_accent_usage_allows_text_and_fill():
    tokens = design_core.resolve_direction(direction())
    assert tokens["accent_usage"] == "text_and_fill"


def test_fill_only_accent_usage_allows_non_text_contrast_and_exports_rule():
    choice = direction(color="bright-friendly", accent=None)
    choice["sources"] = {dimension: "bright-friendly" for dimension in design_core.DIMENSIONS}
    tokens = design_core.resolve_direction(choice)
    assert tokens["accent_usage"] == "fill_only"
    assert report(tokens)["accent_on_background"]["aa_large"]
    with isolated_plugin() as plugin:
        generate(plugin, [choice])
        lock_all(plugin)
        confirm(plugin, "export it")
        exported = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))
        assert "Never use the accent color for text" in exported["design_md"]


def test_black_on_white_has_21_to_1_contrast():
    assert contrast_ratio("#000000", "#FFFFFF") == 21.0


def test_contrast_report_has_wcag_thresholds():
    tokens = design_core.resolve_direction(direction())
    result = report(tokens)["text_on_background"]
    assert set(result) == {"ratio", "aa_normal", "aaa_normal", "aa_large", "aaa_large", "minimum", "passes", "label"}
    assert "border_strong_on_background" in report(tokens)


def test_get_state_includes_resolved_contrast():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        response = json.loads(plugin.design_discovery_get_state({}, session_id="one"))
        assert "contrast" in response["resolved_directions"][0]


def test_resolved_working_reflects_mixed_locks():
    cool = direction(color="precision-technical", accent=None); cool["label"] = "Cool"
    warm_type = direction(); warm_type["id"], warm_type["label"] = "warm-type", "Warm Type"; warm_type["sources"]["typography"] = "quiet-warmth"
    warm_type["sources"]["color"] = "quiet-warmth"
    third = direction(color="editorial", accent=None); third["id"], third["label"] = "third", "Reading Brief"
    with isolated_plugin() as plugin:
        generated = json.loads(generate(plugin, [cool, warm_type, third]))
        assert generated["ok"] is True, generated
        for dimension in design_core.DIMENSIONS:
            selected = "Warm Type" if dimension == "typography" else "Cool"
            words = "lock " + dimension
            confirm(plugin, words)
            update_success(plugin, {"action": "lock", "dimension": dimension, "direction_id": selected, "confirmed_by_user": words})
        response = json.loads(plugin.design_discovery_get_state({}, session_id="one"))
        working = response["resolved_working"]
        assert working is not None
        assert working["tokens"]["typography"]["display_font"] == "cormorant-garamond"
        assert working["tokens"]["color"]["mode"] == "dark"
        assert "accent_text_on_accent" in working["contrast"]


def test_locked_dimensions_survive_regeneration():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        confirm(plugin)
        update_success(plugin, {"action": "lock", "dimension": "color", "direction_id": "one", "confirmed_by_user": "confirmed"})
        regenerated = json.loads(generate(plugin, [direction()]))["state"]
        assert regenerated["working"]["color"]["status"] == "locked"


def test_composed_color_is_snapshotted_when_tried_or_locked_and_survives_regeneration():
    with isolated_plugin() as plugin:
        first = composed_direction(); generate(plugin, composed_triplet(first))
        update_success(plugin, {"action": "try", "directions": {"color": "Clay Morning"}})
        confirm(plugin, "keep the clay color")
        update_success(plugin, {"action": "lock", "dimension": "color", "direction_id": "Clay Morning", "confirmed_by_user": "keep the clay color"})
        snapshot = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["state"]["working"]["color"]["palette"]
        replacement = composed_direction("Different", {**COMPOSED, "background": "#20150F", "surface": "#281A13", "text": "#FFF4EA", "muted": "#D6BEB0", "border_strong": "#8A684F", "accent": "#49AAA1"})
        generate(plugin, composed_triplet(replacement))
        state_value = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["state"]
        assert state_value["working"]["color"]["palette"] == snapshot and state_value["working"]["color"]["status"] == "locked"


def test_composed_source_is_rewritten_and_other_composed_ids_are_refused():
    with isolated_plugin() as plugin:
        generated = json.loads(generate(plugin, composed_triplet()))
        stored = generated["state"]["directions"][0]
        assert stored["sources"]["color"] == "composed:dir-a"
    with isolated_plugin() as plugin:
        bad = composed_direction(); bad["sources"]["color"] = "composed:dir-other"
        refused = json.loads(generate(plugin, composed_triplet(bad), expect_ok=False))
        assert refused["ok"] is False and 'sources.color "composed"' in refused["next"]


def test_composed_adjustment_rederives_usage_and_pane_and_export_mark_composed():
    with isolated_plugin() as plugin:
        generate(plugin, composed_triplet())
        update_success(plugin, {"action": "try", "directions": {"color": "Clay Morning"}})
        plugin.pre_llm_call(session_id="one", user_message="Make the button orange like a tangerine")
        adjusted = update_success(plugin, {"action": "adjust", "path": "color.accent", "value": "#D4783C", "source": "described", "user_words": "orange like a tangerine"})
        assert adjusted["state"]["adjustments"]["color.accent"]["source"] == "described"
        api = dashboard_api()
        pane = api.resolved_state("one")
        assert pane["resolved_working"]["tokens"]["accent_usage"] in {"text_and_fill", "fill_only"}
        assert next(item for item in pane["resolved_working"]["dimensions"] if item["dimension"] == "color")["label"] == "Clay Morning"
        for dimension in design_core.DIMENSIONS:
            words = "lock " + dimension
            confirm(plugin, words)
            update_success(plugin, {"action": "lock", "dimension": dimension, "direction_id": "Clay Morning", "confirmed_by_user": words})
        confirm(plugin, "export it")
        exported = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))
        assert "## Tokens" in exported["design_md"] and "composed:" not in exported["design_md"]


def test_rejected_archetype_is_refused():
    rejected = design_core.blank_rejected(); rejected["archetypes"]["color"].append("quiet-warmth")
    try: design_core.validate_direction(direction(), rejected); assert False
    except ValueError: pass


def test_rejected_font_is_refused():
    rejected = design_core.blank_rejected(); rejected["fonts"].append("inter")
    choice = direction(); choice["adjustments"]["typography.display_font"] = {"value": "inter", "source": "agent"}
    try: design_core.validate_direction(choice, rejected); assert False
    except ValueError: pass


def test_rejected_accent_is_refused():
    rejected = design_core.blank_rejected(); rejected["accents"].append("#4E5A3A")
    try: design_core.validate_direction(direction(), rejected); assert False
    except ValueError: pass


def test_accent_outside_alternates_is_refused():
    try: design_core.validate_direction(direction(accent="#FFFFFF")); assert False
    except ValueError: pass


def test_export_fails_until_all_dimensions_locked():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        assert json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "confirmed"}, session_id="one"))["ok"] is False


def test_successful_export_sets_exported_at():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        lock_all(plugin)
        confirm(plugin, "export it")
        exported = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))
        assert exported["ok"] is True
        assert exported["state"]["exported_at"] is not None
        assert "## Voice" in exported["design_md"]


def test_conflict_detection_fires_for_cold_plus_warm():
    assert design_core.detect_conflicts(direction())


def test_conflict_loader_rejects_bad_traits_and_variant_conditions():
    original_read = design_core._read
    bad_trait = {"rules": [{"id": "bad", "a": "not-a-trait", "b": "warm", "severity": "tension", "tradeoff": "x", "resolution": "y"}]}
    with patch.object(design_core, "_read", side_effect=lambda path: bad_trait if path.name == "conflicts.json" else original_read(path)):
        try: design_core.conflict_rules(); assert False
        except ValueError as exc: assert "unknown trait" in str(exc)
    bad_when = {"rules": [{"id": "bad", "a": "cold", "b": "warm", "severity": "tension", "tradeoff": "x", "resolution": "y", "variants": [{"when": {"unknown": True}, "resolution": "z"}]}]}
    with patch.object(design_core, "_read", side_effect=lambda path: bad_when if path.name == "conflicts.json" else original_read(path)):
        try: design_core.conflict_rules(); assert False
        except ValueError as exc: assert "unknown variant condition" in str(exc)


def test_composed_words_validate_aliases_and_supply_conflict_traits():
    item = composed_direction(); item["id"] = "dir-a"; item["sources"]["color"] = "composed:dir-a"; item["composed_palette"]["words"] = ["bold", "simple"]
    assert design_core._validate_composed_words(item["composed_palette"]) == ["bold", "minimal"]
    design_core.validate_direction(item)
    assert item["composed_palette"]["words"] == ["bold", "minimal"]
    assert any(conflict["rule_id"] == "expressive-vs-minimal" for conflict in design_core.detect_conflicts(item))
    item["composed_palette"]["words"] = ["warme"]
    try: design_core.validate_direction(item); assert False
    except ValueError as exc: assert "Closest valid words" in str(exc) and "warm" in str(exc)


def test_conflict_variants_use_accent_provenance_and_resolved_density():
    expressive = composed_direction(); expressive["id"] = "dir-a"; expressive["sources"]["color"] = "composed:dir-a"; expressive["composed_palette"]["words"] = ["bold", "minimal"]
    default = next(item for item in design_core.detect_conflicts(expressive) if item["rule_id"] == "expressive-vs-minimal")
    expressive["adjustments"]["color.accent"] = {"value": "#B84A22", "source": "described", "user_words": "orange"}
    accented = next(item for item in design_core.detect_conflicts(expressive) if item["rule_id"] == "expressive-vs-minimal")
    assert accented["resolution"] != default["resolution"] and "user's choice" in accented["resolution"]
    dense_calm = composed_direction(); dense_calm["id"] = "dir-b"; dense_calm["sources"]["color"] = "composed:dir-b"; dense_calm["composed_palette"]["words"] = ["dense", "calm"]
    dense_calm["adjustments"]["layout.density"] = {"value": "comfortable", "source": "agent"}
    comfortable = next(item for item in design_core.detect_conflicts(dense_calm) if item["rule_id"] == "dense-vs-calm")
    dense_calm["adjustments"]["layout.density"] = {"value": "compact", "source": "agent"}
    compact = next(item for item in design_core.detect_conflicts(dense_calm) if item["rule_id"] == "dense-vs-calm")
    assert "roomy layout" in comfortable["resolution"] and comfortable["resolution"] != compact["resolution"]


def test_enum_guidance_is_complete_and_validated_at_load():
    design_core._validate_enum_guidance()
    original_read = design_core._read; invalid = original_read(design_core.DATA / "enums.json")
    invalid["token_values"]["densities"]["compact"].pop("guidance")
    with patch.object(design_core, "_read", side_effect=lambda path: invalid if path.name == "enums.json" else original_read(path)):
        try: design_core._validate_enum_guidance(); assert False
        except ValueError as exc: assert "missing guidance" in str(exc)


def test_get_state_limits_conflicts_to_two_and_puts_clashes_first():
    with isolated_plugin() as plugin:
        generate(plugin, varied_directions())
        conflicts = [
            {"rule_id": "tension-one", "severity": "tension", "tradeoff": "tension one", "resolution": "one"},
            {"rule_id": "clash", "severity": "clash", "tradeoff": "clash", "resolution": "two"},
            {"rule_id": "tension-two", "severity": "tension", "tradeoff": "tension two", "resolution": "three"},
        ]
        with patch.object(plugin, "detect_conflicts", return_value=conflicts):
            payload = json.loads(plugin.design_discovery_get_state({}, session_id="one"))
        shown = payload["resolved_directions"][0]["conflicts"]
        assert shown == [{"tradeoff": "clash", "resolution": "two"}, {"tradeoff": "tension one", "resolution": "one"}]
        assert "rule_id" not in shown[0]


def test_latest_generic_yes_after_summary_is_used_for_export():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()], confirmed_by_user="Yes")
        lock_all(plugin)
        plugin.post_llm_call(session_id="one", assistant_response="This is the final direction. Export it when you are ready.")
        plugin.pre_llm_call(session_id="one", user_message="Yes")
        exported = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "Yes"}, session_id="one"))
        assert exported["ok"] is True


def test_all_archetypes_meet_required_contrast_thresholds():
    for archetype_id in design_core.archetypes():
        choice = direction(color=archetype_id, accent=None)
        choice["sources"] = {dimension: archetype_id for dimension in design_core.DIMENSIONS}
        tokens = design_core.resolve_direction(choice)
        result = report(tokens)
        assert result["border_strong_on_background"]["aa_large"]
        required = ["text_on_background", "text_on_surface", "muted_on_background", "accent_text_on_accent", "success_on_surface", "warning_on_surface", "danger_on_surface"]
        if tokens["accent_usage"] == "text_and_fill":
            required.append("accent_on_background")
        else:
            assert result["accent_on_background"]["aa_large"]
        for name in required:
            assert result[name]["aa_normal"], f"{archetype_id}: {name}"
        for name, values in result.items():
            if name.startswith("accent_text_on_alternate_"):
                assert values["aa_normal"], f"{archetype_id}: {name}"


def test_hook_skips_nonmatching_session_id():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        assert plugin.pre_llm_call(session_id="other") is None


def test_generate_from_new_session_resets_state():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()], brief="first")
        confirm(plugin)
        update_success(plugin, {"action": "lock", "dimension": "color", "direction_id": "one", "confirmed_by_user": "confirmed"})
        reset = json.loads(generate(plugin, [direction()], session_id="two", brief="second"))["state"]
        assert reset["brief"] == "second"
        assert reset["working"]["color"]["status"] == "open"


def test_agent_accent_outside_alternates_is_refused():
    choice = direction(accent="#FFFFFF")
    try:
        design_core.validate_direction(choice)
        assert False
    except ValueError as exc:
        assert "agent-sourced accent" in str(exc)


def test_user_accent_is_accepted_and_chooses_readable_text():
    choice = direction(accent=None)
    choice["adjustments"]["color.accent"] = {"value": "#000000", "source": "user"}
    tokens = design_core.resolve_direction(choice, user_messages=["Use #000000"])
    assert tokens["color"]["accent_text"] == "#FFFFFF"
    assert tokens["provenance"]["color"]["accent"] == "user"


def test_user_accent_failing_contrast_is_refused():
    choice = direction(accent=None)
    choice["adjustments"]["color.accent"] = {"value": "#E4DFD5", "source": "user"}
    try:
        design_core.resolve_direction(choice, user_messages=["Use #E4DFD5"])
        assert False
    except ValueError as exc:
        assert "cannot reach" in str(exc)


def test_accent_text_uses_a_later_candidate_when_the_authored_one_fails():
    choice = direction(color="bright-friendly", accent=None)
    choice["adjustments"]["color.accent"] = {"value": "#000000", "source": "user"}
    tokens = design_core.resolve_direction(choice, user_messages=["Use #000000"])
    assert tokens["color"]["accent_text"] == "#FFFFFF"


def test_unknown_font_is_leniently_dropped_with_source_value_and_valid_values():
    choice = direction()
    choice["adjustments"]["typography.display_font"] = {"value": "missing-serif", "source": "agent"}
    with isolated_plugin() as plugin:
        accepted = json.loads(generate(plugin, [choice]))
        warning = next(item for item in accepted["warnings"] if "typography.display_font" in item)
        assert accepted["ok"] is True and "error" not in accepted and "missing-serif" in warning and "kept" in warning
        assert all(font_id in warning for font_id in design_core.fonts())


def test_enforced_avoid_constraint_blocks_direction():
    constraint = {"id": "no-dark", "text": "Do not use dark mode", "kind": "avoid", "path": "color.mode", "value": "dark"}
    choice = direction(color="precision-technical", accent=None)
    try:
        design_core.validate_direction(choice, constraints=[constraint])
        assert False
    except ValueError as exc:
        assert "Do not use dark mode" in str(exc)


def test_adjust_works_on_locked_dimension():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        confirm(plugin, "round")
        update_success(plugin, {"action": "lock", "dimension": "geometry", "direction_id": "one", "confirmed_by_user": "round"})
        adjusted = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "geometry.radius", "value": "round", "source": "user"}, session_id="one"))
        assert adjusted["ok"] is True, adjusted
        assert adjusted["state"]["working"]["geometry"]["status"] == "locked"


def test_regeneration_keeps_user_adjustments():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        confirm(plugin, "none")
        update_success(plugin, {"action": "adjust", "path": "motion.preset", "value": "none", "source": "user"})
        regenerated = json.loads(generate(plugin, [direction()]))
        assert regenerated["state"]["adjustments"]["motion.preset"] == {"value": "none", "source": "user"}


def test_catalog_excludes_internal_refs():
    with isolated_plugin() as plugin:
        response = json.loads(plugin.design_discovery_get_state({}, session_id="one"))
        assert all("internal_refs" not in entry for entry in response["catalog"]["archetypes"])
        assert all(set(font) == {"id", "family", "category", "roles", "class", "weights"} for font in response["catalog"]["fonts"])


def test_design_md_lists_user_decisions_and_constraints():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        confirm(plugin, "none Keep the writing direct confirmed")
        update_success(plugin, {"action": "adjust", "path": "motion.preset", "value": "none", "source": "user"})
        update_success(plugin, {"action": "add_constraint", "constraint": {"id": "voice", "text": "Keep the writing direct", "kind": "require"}, "confirmed_by_user": "Keep the writing direct"})
        lock_all(plugin)
        confirm(plugin, "export it")
        exported = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))
        assert "Micro changes: 0ms" in exported["design_md"]
        assert "Keep the writing direct" in exported["design_md"]


def test_design_md_dont_items_read_correctly_after_dont():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        lock_all(plugin)
        confirm(plugin, "export it")
        original = plugin.resolve_direction
        def with_voice(*args, **kwargs):
            tokens = original(*args, **kwargs)
            tokens["voice"] = {**tokens["voice"], "dont": ["Avoid empty jargon", "Don't sound robotic", "Avoid sounding robotic", "Use alarmist language"]}
            return tokens
        with patch.object(plugin, "resolve_direction", with_voice):
            exported = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))
        assert exported["ok"] is True, exported.get("error", exported)
        section = exported["design_md"].split("Don't:\n", 1)[1].split("\n\n", 1)[0]
        items = [line[2:] for line in section.splitlines() if line.startswith("- ")]
        assert items == ["Use empty jargon", "Sound robotic", "Sounding robotic", "Use alarmist language"]
        assert not any(item.casefold().startswith(prefix) for item in items for prefix in ("avoid", "don't", "do not", "never"))


def test_generate_refuses_empty_interview_answers():
    with isolated_plugin() as plugin:
        interview_reply(plugin)
        response = json.loads(plugin.design_discovery_generate_directions({"directions": [direction()], "answers": []}, session_id="one"))
        assert response["ok"] is True and response["generated"] is False and "error" not in response and response["next"] == plugin._NEXT_INTERVIEW


def test_record_understanding_requires_a_reply_after_the_brief():
    with isolated_plugin() as plugin:
        plugin.pre_llm_call(session_id="one", user_message="A bakery dashboard")
        result = json.loads(plugin.design_discovery_record_understanding({"summary": "A warm bakery."}, session_id="one"))
        assert result["ok"] is True and result["recorded"] is False and "error" not in result and result["next"] == plugin._NEXT_INTERVIEW
        assert result["state"]["understanding"] is None
        plugin.pre_llm_call(session_id="one", user_message="It should feel warm.")
        assert json.loads(plugin.design_discovery_record_understanding({"summary": "A warm bakery."}, session_id="one"))["recorded"] is not False


def test_generation_recovers_recorded_interview_answers_when_answers_are_omitted():
    with isolated_plugin() as plugin:
        plugin._activate("one")
        plugin.post_llm_call(session_id="one", assistant_response="What are you making, and how should it feel?")
        plugin.pre_llm_call(session_id="one", user_message="A neighborhood bakery that feels warm and unhurried.")
        plugin.post_llm_call(session_id="one", assistant_response="Who is it for?")
        plugin.pre_llm_call(session_id="one", user_message="People ordering bread for pickup.")
        plugin.design_discovery_record_understanding({"summary": "A warm neighborhood bakery for bread pickup."}, session_id="one")
        plugin.pre_llm_call(session_id="one", user_message="Yes, that is right")
        result = json.loads(plugin.design_discovery_generate_directions({"directions": varied_directions(), "confirmed_by_user": "Yes, that is right"}, session_id="one"))
        assert result["ok"] is True
        assert result["state"]["answers"] == [
            {"q": "What are you making, and how should it feel?", "a": "A neighborhood bakery that feels warm and unhurried."},
            {"q": "Who is it for?", "a": "People ordering bread for pickup."},
        ]


def test_run_8b_recovery_uses_the_pre_summary_user_brief_without_a_question_pair():
    with isolated_plugin() as plugin:
        plugin._activate("one")
        plugin.pre_llm_call(session_id="one", user_message="A morning dashboard for checking agents that feels warm, not generic SaaS.")
        plugin.post_llm_call(session_id="one", assistant_response="What should people notice first?")
        plugin.pre_llm_call(session_id="one", user_message="The morning status at a glance.")
        plugin.design_discovery_record_understanding({"summary": "A warm morning dashboard for checking agents."}, session_id="one")
        plugin.pre_llm_call(session_id="one", user_message="Yes, that is right")
        result = json.loads(plugin.design_discovery_generate_directions({"directions": varied_directions(), "confirmed_by_user": "Yes, that is right"}, session_id="one"))
        assert result["ok"] is True
        assert result["state"]["answers"] == [{"q": "What should people notice first?", "a": "The morning status at a glance."}]


def test_generation_leniently_drops_bad_sample_voice_and_words_with_warnings():
    choices = composed_triplet()
    choices[0]["voice"] = {"tone": "bad", "do": ["one"], "dont": [], "example": "bad"}
    choices[0]["composed_palette"]["words"] = ["not-a-word"]
    with isolated_plugin() as plugin:
        result = json.loads(generate(plugin, choices, sample={"title": "Incomplete"}))
        assert result["ok"] is True
        assert result["state"]["sample"] is None
        assert len(result["state"]["directions"][0]["voice"]["do"]) == len(result["state"]["directions"][0]["voice"]["dont"]) == 3
        assert result["state"]["directions"][0]["composed_palette"]["words"] == []
        assert len(result["warnings"]) >= 3
        assert "continue" in result["next"].casefold()


def test_generate_schema_exposes_lenient_sample_and_voice_shapes_without_hard_limits():
    schema = plugin.GENERATE_SCHEMA
    sample = schema["parameters"]["properties"]["sample"]
    assert set(sample["properties"]) == {"title", "body", "items", "primary", "secondary"}
    assert set(sample["properties"]["items"]["items"]["properties"]) == {"label", "status", "status_label"}
    voice = schema["parameters"]["properties"]["directions"]["items"]["properties"]["voice"]
    assert set(voice["properties"]) == {"tone", "do", "dont", "example"}
    assert "Example sample:" in schema["description"]
    assert not any(key in json.dumps({"sample": sample, "voice": voice}) for key in ("maxLength", "minItems", "maxItems", '"required"'))


def test_no_interview_refusal_stays_specific_after_understanding_confirmation():
    with isolated_plugin() as plugin:
        plugin.pre_llm_call(session_id="one", user_message="A warm bakery for pickup orders.")
        plugin.design_discovery_record_understanding({"summary": "A warm bakery for pickup orders."}, session_id="one")
        plugin.pre_llm_call(session_id="one", user_message="Yes, that is right")
        refused = json.loads(plugin.design_discovery_generate_directions({"directions": varied_directions(), "confirmed_by_user": "Yes, that is right"}, session_id="one"))
        assert refused["ok"] is True and refused["generated"] is False and "error" not in refused and refused["next"] == plugin._NEXT_INTERVIEW


def test_generate_requires_exactly_three_directions():
    with isolated_plugin() as plugin:
        refused = json.loads(plugin.design_discovery_generate_directions({"directions": [direction()], "answers": ANSWERS}, session_id="one"))
        assert refused["ok"] is False
        assert refused["error"] == "Provide exactly three directions, each with a distinct user-noticeable approach."
        directions = varied_directions()
        for index, item in enumerate(directions):
            item["id"] = f"direction-{index}"
        assert json.loads(generate(plugin, directions))["ok"] is True


def test_user_adjustment_requires_matching_user_message():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        adjusted = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "motion.preset", "value": "none", "source": "user"}, session_id="one"))
        assert adjusted["ok"] is True and "error" not in adjusted and adjusted["warnings"]
        assert adjusted["state"]["adjustments"]["motion.preset"]["source"] == "agent"
        assert "motion.preset" not in {item["path"] for item in plugin._user_decisions(adjusted["state"])}
        lock_all(plugin); confirm(plugin, "export it")
        document = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))["design_md"]
        assert "Motion: none (your choice)" not in document
        confirm(plugin, "none")
        assert json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "motion.preset", "value": "none", "source": "user"}, session_id="one"))["ok"] is True


def test_confirmation_required_for_lock_reject_constraint_and_export():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        lock = json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "color", "direction_id": "one"}, session_id="one"))
        reject = json.loads(plugin.design_discovery_update_choice({"action": "reject", "dimension": "color", "archetype_id": "quiet-warmth"}, session_id="one"))
        constrained = json.loads(plugin.design_discovery_update_choice({"action": "add_constraint", "constraint": {"id": "x", "text": "Use light", "kind": "require"}}, session_id="one"))
        exported = json.loads(plugin.design_discovery_export_design_md({}, session_id="one"))
        assert all(item["error"] == "Ask the user to approve this in their own words, then pass their exact words as confirmed_by_user." for item in (lock, reject, constrained, exported))
        confirm(plugin, "yes, confirm it")
        assert json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "color", "direction_id": "one", "confirmed_by_user": "confirm"}, session_id="one"))["ok"] is True
        assert json.loads(plugin.design_discovery_update_choice({"action": "reject", "dimension": "color", "archetype_id": "bright-friendly", "confirmed_by_user": "confirm"}, session_id="one"))["ok"] is True
        assert json.loads(plugin.design_discovery_update_choice({"action": "add_constraint", "constraint": {"id": "y", "text": "Keep it simple", "kind": "require"}, "confirmed_by_user": "confirm"}, session_id="one"))["ok"] is True


def test_hook_records_only_matching_session_messages_and_keeps_last_50():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        for index in range(51):
            plugin.pre_llm_call(session_id="one", user_message=f"message {index}")
        state_value = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["state"]
        assert state_value["user_messages"] == [f"message {index}" for index in range(1, 51)]
        plugin.pre_llm_call(session_id="other", user_message="do not record")
        assert "do not record" not in json.loads(plugin.design_discovery_get_state({}, session_id="one"))["state"]["user_messages"]


def test_pre_activation_brand_hex_is_available_after_session_activates():
    with isolated_plugin() as plugin:
        plugin.pre_llm_call(session_id="brand-session", user_message="Use our brand color #EDEDED")
        choice = direction(color="precision-technical", accent=None)
        choice["adjustments"]["color.accent"] = {"value": "#EDEDED", "source": "user"}
        activated = json.loads(generate(plugin, [choice], session_id="brand-session"))
        assert activated["ok"] is True
        assert any("#EDEDED" in message for message in activated["state"]["user_messages"])


def test_pre_tool_hook_blocks_building_until_export_and_allows_design_tools():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        blocked = plugin.pre_tool_call(tool_name="write_file", session_id="one")
        assert blocked == {"action": "block", "message": "Design discovery is in progress. Use the design discovery tools, tool search, or tool detail until DESIGN.md is exported. If the user wants to stop designing or do something else, call design_discovery_update_choice with action end."}
        assert plugin.pre_tool_call(tool_name="design_discovery_get_state", session_id="one") is None
        state_value = state.get_state("one"); state_value["phase"] = "final"; state.replace_state(state_value, "one")
        assert plugin.pre_tool_call(tool_name="terminal", session_id="one") is None


def test_sessions_keep_independent_state():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()], session_id="one", brief="first")
        generate(plugin, [direction()], session_id="two", brief="second")
        one = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["state"]
        two = json.loads(plugin.design_discovery_get_state({}, session_id="two"))["state"]
        assert one["brief"] == "first"
        assert two["brief"] == "second"
        assert state.state_path("one").is_file()
        assert state.state_path("two").is_file()


def test_dashboard_route_returns_requested_session_or_empty_state():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()], session_id="one", brief="first")
        if "fastapi" not in sys.modules:
            fastapi = types.ModuleType("fastapi")
            class Router:
                def get(self, _path): return lambda function: function
                def post(self, _path): return lambda function: function
            class HttpError(Exception):
                def __init__(self, **kwargs): self.kwargs = kwargs
            fastapi.APIRouter = Router
            fastapi.HTTPException = HttpError
            fastapi.Request = object
            sys.modules["fastapi"] = fastapi
        api = dashboard_api()
        def read(session_id):
            coroutine = api.read_state(SimpleNamespace(query_params={"session_id": session_id}))
            try:
                coroutine.send(None)
            except StopIteration as result:
                return result.value
            raise AssertionError("read_state unexpectedly awaited")
        selected = read("one")
        missing = read("missing")
        assert selected["resolved_directions"][0]["label"] == "One"
        assert missing["resolved_directions"] == []
        assert missing["resolved_working"] is None


def test_invalid_or_old_schema_state_is_ignored():
    with isolated_plugin() as plugin:
        path = state.state_path("old")
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"schema_version": 0, "session_id": "old", "active": True}), encoding="utf-8")
        assert json.loads(plugin.design_discovery_get_state({}, session_id="old", activate_session=False))["state"]["active"] is False
        path.write_text(json.dumps({"schema_version": 1, "session_id": "old", "directions": [{"invalid": True}]}), encoding="utf-8")
        assert json.loads(plugin.design_discovery_get_state({}, session_id="old", activate_session=False))["state"]["directions"] == []


def test_pre_tool_hook_does_not_block_without_current_session_state():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()], session_id="active")
        assert plugin.pre_tool_call(tool_name="write_file", session_id="other") is None


def test_skill_invocation_activates_the_session_before_any_tool_call():
    with isolated_plugin() as plugin:
        plugin.pre_llm_call(session_id="one", user_message='[IMPORTANT: The user has invoked the "design-discovery" skill, indicating they want help.]')
        state_value = state.get_state("one")
        assert state_value["active"] is True
        assert state_value["phase"] == "discovering"
        assert plugin.pre_tool_call(tool_name="write_file", session_id="one")["action"] == "block"


def test_other_skill_load_is_blocked_only_for_active_session():
    with isolated_plugin() as plugin:
        assert plugin.pre_tool_call(tool_name="skill_view", args={"skill_name": "claude-design"}, session_id="one") is None
        generate(plugin, [direction()], session_id="one")
        assert plugin.pre_tool_call(tool_name="skill_view", args={"skill_name": "claude-design"}, session_id="one") == {"action": "block", "message": "You’re in a design discovery session. Use only the design discovery tools until DESIGN.md is exported. If the user wants to stop designing or do something else, call design_discovery_update_choice with action end."}
        assert plugin.pre_tool_call(tool_name="skill_view", args={"skill_name": "design-discovery:design-discovery"}, session_id="one") is None


def test_design_tool_results_include_prescriptive_next_steps():
    with isolated_plugin() as plugin:
        empty = json.loads(plugin.design_discovery_get_state({}, session_id="one"))
        no_internals = " Keep the reply focused on the selected direction and its design, using plain language rather than implementation terms."
        assert empty["next"] == "Ask the user what they’re making, who it’s for, how it should feel, and what they don’t want. Then call design_discovery_record_understanding with what you understood, show it to the user, and wait for them to confirm before generating directions." + no_internals
        generated = json.loads(generate(plugin, [direction()]))
        assert json.loads(plugin.design_discovery_get_state({}, session_id="one"))["next"] == "Use the resolved directions to continue the design discovery conversation." + no_internals
        assert generated["next"] == "Describe each direction in one plain sentence and tell the user the pane shows them. Ask which is closest and what they would change, then stop. Do not recommend one. Do not offer to build, mock up, or render anything outside the pane. Do not lock anything until the user says so. Never name archetypes or design systems; describe what each direction does. When the user likes a direction but wants a change, use try for that whole direction, then adjust only what they asked for. Never lock until they approve what the pane shows. Use these direction ids for try and lock: dir-a (One), dir-b (One), dir-c (One)."
        confirm(plugin)
        updated = json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "color", "direction_id": "one", "confirmed_by_user": "confirmed"}, session_id="one"))
        assert updated["next"] == plugin._NEXT_CHANGED
        refused = json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "layout", "direction_id": "one"}, session_id="one"))
        assert refused["next"] == "Ask the user in plain words whether they want this. Do not suggest wording for their reply."
        for dimension in ("typography", "layout", "geometry", "motion"):
            words = "lock " + dimension
            confirm(plugin, words)
            update_success(plugin, {"action": "lock", "dimension": dimension, "direction_id": "one", "confirmed_by_user": words})
        confirm(plugin, "export it")
        exported = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))
    assert exported["next"] == "Give the user this saved path in one line and stop."


def test_generate_refuses_starting_point_names_in_labels():
    named = direction()
    named["label"] = "Quiet Warmth, booted up"
    with isolated_plugin() as plugin:
        refused = json.loads(generate(plugin, [named], expect_ok=False))
        assert refused["ok"] is False
        assert refused["next"] == "Rename the direction to describe what it does. Never use starting point names."


def test_unknown_action_has_a_specific_recovery_step():
    with isolated_plugin() as plugin:
        refused = json.loads(plugin.design_discovery_update_choice({"action": "unknown"}, session_id="one"))
        assert refused["next"] == "Use one of these actions: try, approve_direction, lock, unlock, reject, clear_reject, adjust, add_constraint, or remove_constraint."


def test_post_llm_hook_records_assistant_messages_with_same_limit_as_user_messages():
    with isolated_plugin() as plugin:
        plugin.pre_llm_call(session_id="one", user_message='[IMPORTANT: The user has invoked the "design-discovery" skill, indicating they want help.]')
        for index in range(51):
            plugin.post_llm_call(session_id="one", assistant_response=f"assistant {index}")
        saved = state.get_state("one")
        assert saved["assistant_messages"] == [f"assistant {index}" for index in range(1, 51)]


def test_suggested_quoted_confirmation_is_refused():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        plugin.post_llm_call(session_id="one", assistant_response='Reply “YES, CONFIRM IT!” when you agree.')
        plugin.pre_llm_call(session_id="one", user_message="yes, confirm it!")
        refused = json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "color", "direction_id": "one", "confirmed_by_user": "yes, confirm it!"}, session_id="one"))
        assert refused["ok"] is False
        assert refused["next"] == "Ask the user in your own words whether they approve. Do not suggest how to reply, then wait."


SKILL_INVOCATION = '[IMPORTANT: The user has invoked the "design-discovery:design-discovery" skill, indicating they want you to follow its instructions.]'


def test_clarify_answer_from_host_counts_as_interview_reply():
    with isolated_plugin() as plugin:
        plugin.pre_llm_call(session_id="one", user_message=SKILL_INVOCATION)
        blocked = plugin.design_discovery_record_understanding({"summary": "You want a calm dashboard."}, session_id="one")
        assert json.loads(blocked)["recorded"] is False
        answer = "A morning check of which agents failed overnight. Warm, not generic SaaS."
        plugin.post_tool_call(tool_name="clarify", session_id="one", status="ok", args={"question": "What is it and how should it feel?"}, result=json.dumps({"question": "What is it and how should it feel?", "choices_offered": None, "user_response": answer}))
        saved = state.get_state("one")
        assert {"role": "user", "text": answer, "source": "clarify"} in [{key: event[key] for key in ("role", "text", "source") if key in event} for event in saved["message_events"]]
        recorded = json.loads(plugin.design_discovery_record_understanding({"summary": "You want a warm morning dashboard that shows failed agents."}, session_id="one"))
        assert recorded["ok"] is True and recorded["recorded"] is True


def test_agent_supplied_answers_alone_do_not_satisfy_the_interview_gate():
    with isolated_plugin() as plugin:
        plugin.pre_llm_call(session_id="one", user_message=SKILL_INVOCATION)
        assert json.loads(plugin.design_discovery_record_understanding({"summary": "You want a warm dashboard."}, session_id="one"))["recorded"] is False
        saved = state.get_state("one")
        saved["answers"] = [{"question": "How should it feel?", "answer": "Warm and inviting"}]
        state.replace_state(saved, "one")
        plugin.post_tool_call(tool_name="clarify", session_id="one", status="error", result=json.dumps({"error": "cancelled"}))
        plugin.post_tool_call(tool_name="design_discovery_get_state", session_id="one", status="ok", result=json.dumps({"user_response": "Warm and inviting"}))
        plugin.design_discovery_generate_directions({"directions": varied_directions(), "answers": ANSWERS, "confirmed_by_user": "yes"}, session_id="one")
        recorded = json.loads(plugin.design_discovery_record_understanding({"summary": "You want a warm dashboard."}, session_id="one"))
        assert recorded["recorded"] is False
        assert recorded["next"] == plugin._NEXT_INTERVIEW


def clarify_result(*answers, outcome="submitted"):
    # Shape copied from a live Hermes clarify result (run 10), with the text shortened.
    return json.dumps({"responses": [{"question": f"Question {index}?", "choices_offered": ["Warm and human", "Bold and unconventional"], "status": "answered" if answer else "unanswered", "user_response": answer} for index, answer in enumerate(answers, 1)], "outcome": outcome})


def clarify_log_lines():
    return [event for event in map(json.loads, state.tool_events_path("one").read_text(encoding="utf-8").splitlines()) if event.get("tool") == "clarify"]


def test_real_clarify_responses_count_as_interview_replies_and_are_logged_without_text():
    with isolated_plugin() as plugin:
        plugin.pre_llm_call(session_id="one", user_message=SKILL_INVOCATION)
        assert json.loads(plugin.design_discovery_record_understanding({"summary": "You want a calm dashboard."}, session_id="one"))["recorded"] is False
        answers = ["It'll be just me. I'll be using it to track which agents broke or failed overnight", "Warm and human"]
        plugin.post_tool_call(tool_name="clarify", session_id="one", status="ok", args={"questions": ["agent supplied"]}, result=clarify_result(*answers))
        saved = state.get_state("one")
        assert [event["text"] for event in saved["message_events"] if event.get("source") == "clarify"] == answers
        recorded = json.loads(plugin.design_discovery_record_understanding({"summary": "You want a warm morning dashboard that shows failed agents."}, session_id="one"))
        assert recorded["ok"] is True and recorded["recorded"] is True
        plugin.post_tool_call(tool_name="clarify", session_id="one", status="ok", result=clarify_result(None, outcome="cancelled"))
        lines = clarify_log_lines()
        assert [line["args"] for line in lines] == [{"parsed": True, "answers_logged": 2}, {"parsed": True, "answers_logged": 0}]
        assert not any(answer in json.dumps(lines) for answer in answers)


def test_understanding_confirmed_through_clarify_lets_generate_directions_succeed():
    with isolated_plugin() as plugin:
        plugin.pre_llm_call(session_id="one", user_message=SKILL_INVOCATION)
        assert json.loads(plugin.design_discovery_record_understanding({"summary": "You want a calm dashboard."}, session_id="one"))["recorded"] is False
        plugin.post_tool_call(tool_name="clarify", session_id="one", status="ok", result=clarify_result("It'll be just me, tracking which agents failed overnight", "Warm and human"))
        recorded = json.loads(plugin.design_discovery_record_understanding({"summary": "You want a personal morning dashboard that shows failed agents. It should feel warm, not generic SaaS."}, session_id="one"))
        assert recorded["recorded"] is True and recorded["next"] == plugin._NEXT_UNDERSTANDING
        reply = "Thats correct. Generate the directions please"
        plugin.post_tool_call(tool_name="clarify", session_id="one", status="ok", result=clarify_result(reply))
        accepted = json.loads(plugin.design_discovery_generate_directions({"directions": varied_directions(), "answers": ANSWERS, "confirmed_by_user": reply}, session_id="one"))
        assert accepted["ok"] is True, accepted.get("error", accepted)
        assert accepted["generated"] is not False
        assert reply not in json.dumps(clarify_log_lines())


def test_generate_without_recorded_understanding_points_to_record_understanding():
    with isolated_plugin() as plugin:
        interview_reply(plugin)
        refused = json.loads(plugin.design_discovery_generate_directions({"directions": varied_directions(), "answers": ANSWERS, "confirmed_by_user": "yes"}, session_id="one"))
        assert refused["ok"] is False
        assert refused["error"] == "understanding confirmation is required"
        assert refused["next"].startswith("Nothing was generated. Call design_discovery_record_understanding with what you understood, show it to the user")


def test_generate_with_unconfirmed_recorded_understanding_points_to_recording_the_confirmation():
    with isolated_plugin() as plugin:
        summary = "You want a calm dashboard for people who need clarity each morning."
        interview_reply(plugin)
        recorded = json.loads(plugin.design_discovery_record_understanding({"summary": summary}, session_id="one"))
        assert recorded["ok"] is True and recorded["recorded"] is True
        saved = state.get_state("one")
        saved["message_events"] = [event for event in saved["message_events"] if event.get("role") != "understanding"]
        state.replace_state(saved, "one")
        plugin.post_llm_call(session_id="one", assistant_response="Here is what I understood: " + summary + " Is that right?")
        reply = "Yes thats correct. Generate the directions please"
        plugin.pre_llm_call(session_id="one", user_message=reply)
        request = {"directions": varied_directions(), "answers": ANSWERS, "confirmed_by_user": reply}
        refused = json.loads(plugin.design_discovery_generate_directions(request, session_id="one"))
        assert refused["ok"] is False
        assert refused["error"] == "understanding confirmation is required"
        assert "If the user has already confirmed it, call design_discovery_record_understanding with the summary you showed them, then call design_discovery_generate_directions with their reply, word for word, as confirmed_by_user." in refused["next"]
        assert "If they have not replied yet, show them the summary and wait for their reply." in refused["next"]
        assert "—" not in refused["next"] and "–" not in refused["next"]
        json.loads(plugin.design_discovery_record_understanding({"summary": summary}, session_id="one"))
        accepted = json.loads(plugin.design_discovery_generate_directions(request, session_id="one"))
        assert accepted["ok"] is True, accepted.get("error", accepted)


def test_generate_requires_recorded_understanding_and_later_user_confirmation():
    with isolated_plugin() as plugin:
        request = {"directions": varied_directions(), "answers": ANSWERS, "confirmed_by_user": "yes"}
        interview_reply(plugin)
        refused = json.loads(plugin.design_discovery_generate_directions(request, session_id="one"))
        assert refused["ok"] is False
        assert refused["next"] == "Nothing was generated. Call design_discovery_record_understanding with what you understood, show it to the user, and wait for their reply. Never describe directions that haven’t been generated."
        plugin.pre_llm_call(session_id="one", user_message="yes")
        recorded = json.loads(plugin.design_discovery_record_understanding({"summary": "You want a calm dashboard with a clear morning ritual."}, session_id="one"))
        assert recorded["next"] == "Show the user this summary in your own words and ask if it’s right. Then stop and wait for their reply."
        refused = json.loads(plugin.design_discovery_generate_directions(request, session_id="one"))
        assert refused["ok"] is False
        assert refused["next"] == "The user hasn’t replied yet. Show them your understanding and wait for their reply."
        plugin.pre_llm_call(session_id="one", user_message="yes")
        accepted = json.loads(plugin.design_discovery_generate_directions(request, session_id="one"))
        assert accepted["ok"] is True


def test_replacing_understanding_requires_a_fresh_confirmation():
    with isolated_plugin() as plugin:
        request = {"directions": varied_directions(), "answers": ANSWERS, "confirmed_by_user": "yes"}
        interview_reply(plugin)
        plugin.design_discovery_record_understanding({"summary": "First understanding in two plain sentences."}, session_id="one")
        plugin.pre_llm_call(session_id="one", user_message="yes")
        recorded = json.loads(plugin.design_discovery_record_understanding({"summary": "Second understanding in two plain sentences."}, session_id="one"))
        assert recorded["next"] == "The understanding is already confirmed. Call design_discovery_generate_directions with the user’s reply as confirmed_by_user. Do not call design_discovery_record_understanding again."
        assert state.get_state("one")["understanding"] == {"summary": "Second understanding in two plain sentences."}
        assert json.loads(plugin.design_discovery_generate_directions(request, session_id="one"))["ok"] is True


def test_understanding_confirmation_refusals_and_state_guidance_follow_the_latest_reply():
    request = {"directions": varied_directions(), "answers": ANSWERS}
    with isolated_plugin() as plugin:
        interview_reply(plugin)
        plugin.design_discovery_record_understanding({"summary": "You want a calm dashboard with a clear morning ritual."}, session_id="one")
        waiting = json.loads(plugin.design_discovery_get_state({}, session_id="one"))
        assert waiting["next"] == "The user hasn’t replied yet. Show them your understanding and wait for their reply. Keep the reply focused on the selected direction and its design, using plain language rather than implementation terms."
        plugin.pre_llm_call(session_id="one", user_message="Yes thats correct. Generate the options please")
        omitted = json.loads(plugin.design_discovery_generate_directions(request, session_id="one"))
        assert omitted["error"] == "understanding confirmation is missing"
        assert omitted["next"] == "The user has replied to the summary. Call design_discovery_generate_directions with that reply, word for word, as confirmed_by_user. Do not call design_discovery_record_understanding again."
        state_after_reply = json.loads(plugin.design_discovery_get_state({}, session_id="one"))
        assert state_after_reply["next"] == "Call design_discovery_generate_directions with the user’s reply, word for word, as confirmed_by_user. Do not call design_discovery_record_understanding again. Keep the reply focused on the selected direction and its design, using plain language rather than implementation terms."
        mismatched = json.loads(plugin.design_discovery_generate_directions({**request, "confirmed_by_user": "totally unrelated"}, session_id="one"))
        assert mismatched["error"] == "understanding confirmation did not match the latest user reply"
        assert mismatched["next"] == "Pass the user’s reply exactly as they wrote it as confirmed_by_user."
        recorded_again = json.loads(plugin.design_discovery_record_understanding({"summary": "You want a calm dashboard with a clear morning ritual."}, session_id="one"))
        assert recorded_again["next"] == "The understanding is already confirmed. Call design_discovery_generate_directions with the user’s reply as confirmed_by_user. Do not call design_discovery_record_understanding again."
        accepted = json.loads(plugin.design_discovery_generate_directions({**request, "confirmed_by_user": "Yes thats correct. Generate the options please"}, session_id="one"))
        assert accepted["ok"] is True


def test_try_sets_sources_without_confirmation_or_locks():
    second = direction(color="precision-technical", accent=None)
    second["id"], second["label"] = "two", "Two"
    with isolated_plugin() as plugin:
        generate(plugin, [direction(), second])
        tried = json.loads(plugin.design_discovery_update_choice({"action": "try", "directions": {"typography": "one", "color": "two"}}, session_id="one"))
        assert tried["ok"] is True
        assert tried["next"] == plugin._NEXT_CHANGED
        assert tried["state"]["working"]["typography"]["source"] == direction()["sources"]["typography"]
        assert tried["state"]["working"]["color"]["source"] == second["sources"]["color"]
        assert all(value["status"] == "open" for value in tried["state"]["working"].values())


def test_try_refuses_locked_dimension_and_partial_try_fills_the_mix():
    second = direction(color="precision-technical", accent=None)
    second["id"], second["label"] = "two", "Two"
    with isolated_plugin() as plugin:
        generate(plugin, [direction(), second])
        partial = json.loads(plugin.design_discovery_update_choice({"action": "try", "directions": {"color": "two"}}, session_id="one"))
        assert "Filled unset dimensions from Two" in partial["detail"]
        assert all(value["source"] for value in partial["state"]["working"].values())
        confirm(plugin)
        assert json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "color", "confirmed_by_user": "confirmed"}, session_id="one"))["ok"] is True
        refused = json.loads(plugin.design_discovery_update_choice({"action": "try", "directions": {"color": "one"}}, session_id="one"))
        assert refused["ok"] is False
        assert refused["error"] == "Cannot try color because it is locked."


def test_route_returns_working_mix_and_lock_after_try_needs_confirmation():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        update_success(plugin, {"action": "try", "directions": {"typography": "one"}})
        api = dashboard_api()
        working = api.resolved_state("one")["resolved_working"]
        assert working["dimensions"] and all(entry["status"] == "open" for entry in working["dimensions"])
        assert not any(entry["status"] == "locked" for entry in working["dimensions"])
        refused = json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "typography"}, session_id="one"))
        assert refused["error"] == "Ask the user to approve this in their own words, then pass their exact words as confirmed_by_user."


def test_borrowed_accent_accepts_a_current_direction_and_records_provenance():
    base = direction(color="editorial", accent=None)
    base["id"], base["label"] = "base", "Base"
    borrowed = direction(color="bright-friendly", accent=None)
    borrowed["id"], borrowed["label"] = "borrowed", "Daylight Almanac"
    third = direction(color="precision-technical", accent=None)
    third["id"], third["label"] = "third", "Third"
    with isolated_plugin() as plugin:
        generate(plugin, [base, borrowed, third])
        update_success(plugin, {"action": "try", "directions": {"color": "base"}})
        result = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": "#F26B1D", "source": "direction", "from_direction": "Daylight Almanac"}, session_id="one"))
        assert result["ok"] is True
        assert result["state"]["adjustments"]["color.accent"] == {"value": "#F26B1D", "source": "direction", "from_direction": "dir-b"}
        assert result["next"] == plugin._NEXT_CHANGED


def test_borrowed_accent_survives_approval_and_is_credited_in_export():
    first = composed_direction("Warm Briefing", {**COMPOSED, "accent": "#8A4B2A"})
    second = composed_direction("Field Notes", {**COMPOSED, "background": "#F4F7F0", "surface": "#EAF0E2", "text": "#24301F", "muted": "#596650", "border": "#C8D2BD", "border_strong": "#718064", "accent": "#4E6B2F"})
    choices = composed_triplet(first=first); choices[1] = second
    with isolated_plugin() as plugin:
        generate(plugin, choices); update_success(plugin, {"action": "try", "directions": {"color": "Warm Briefing"}})
        borrowed = update_success(plugin, {"action": "adjust", "path": "color.accent", "value": "#4E6B2F", "source": "direction", "from_direction": "Field Notes"})
        confirm(plugin, "approve warm briefing"); approved = update_success(plugin, {"action": "approve_direction", "direction": "Warm Briefing", "confirmed_by_user": "approve warm briefing"})
        assert approved["state"]["adjustments"]["color.accent"] == borrowed["state"]["adjustments"]["color.accent"]
        confirm(plugin, "export it"); document = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user":"export it"}, session_id="one"))["design_md"]
        pane = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["resolved_working"]
        assert pane["tokens"]["color"]["accent"] == "#4E6B2F"
        assert "Primary action color: from Field Notes, your choice." in document and "dir-b" not in document


def test_borrowed_accent_refuses_values_outside_current_directions():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        update_success(plugin, {"action": "try", "directions": {"color": "one"}})
        refused = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": "#FFFFFF", "source": "direction", "from_direction": "one"}, session_id="one"))
        assert refused["ok"] is True and "error" not in refused and refused["changes"] == []
        assert refused["next"].startswith("Nothing changed. '#FFFFFF' is not one of One's accent colors. Its accent is #")


HERMES_SPILLOVER_CHARS = 100_000  # live agent.log: 100,187 chars stayed inline, 101,070 was saved to a file


def test_get_state_tool_result_is_compact_and_keeps_what_the_agent_reads():
    with isolated_plugin() as plugin:
        skill = (Path(__file__).resolve().parents[1] / "skills" / "design-discovery" / "SKILL.md").read_text(encoding="utf-8")
        activation = SKILL_INVOCATION + "\n\n" + skill + "\n\nUNIQUE-ACTIVATION-MARKER A dashboard for checking my agents every morning."
        plugin.pre_llm_call(session_id="one", user_message=activation)
        generate(plugin, varied_directions())
        update_success(plugin, {"action": "try", "directions": {"color": "1"}})
        full = plugin.design_discovery_get_state({}, session_id="one")
        result = plugin.design_discovery_get_state_tool({}, session_id="one")
        assert len(result) < HERMES_SPILLOVER_CHARS * 0.75, len(result)
        assert len(result) < len(full)
        assert "UNIQUE-ACTIVATION-MARKER" in full and "UNIQUE-ACTIVATION-MARKER" not in result
        assert "I need a dashboard" not in result and "What should this help people do" not in result
        payload = json.loads(result)
        compact_state = payload["state"]
        assert not {"user_messages", "assistant_messages", "message_events"} & set(compact_state)
        assert compact_state["message_counts"]["user_messages"] >= 1 and compact_state["message_counts"]["message_events"] >= 1
        for key in ("rev", "phase", "active", "session_id", "understanding", "brief", "answers", "directions", "working", "adjustments", "constraints", "sample", "rejected", "conflicts", "build_stamp", "exported_at", "export_path"):
            assert key in compact_state, key
        assert [item["label"] for item in compact_state["directions"]] == ["One", "Two", "Three"]
        assert all({"direction_id", "tokens", "conflicts", "contrast_failures"} <= set(item) and "contrast" not in item for item in payload["resolved_directions"])
        assert {"tokens", "conflicts", "contrast_failures"} <= set(payload["resolved_working"]) and "contrast" not in payload["resolved_working"]
        assert {"archetypes", "fonts", "vocabulary"} == set(payload["catalog"]) and payload["catalog"]["vocabulary"]
        assert payload["next"] == json.loads(full)["next"]
        api = dashboard_api()
        pane = api.resolved_state("one")
        full_payload = json.loads(full)
        assert [item["contrast"] for item in pane["resolved_directions"]] == [item["contrast"] for item in full_payload["resolved_directions"]]
        assert pane["resolved_working"]["contrast"] == full_payload["resolved_working"]["contrast"]


def test_registered_get_state_tool_is_the_compact_result():
    with isolated_plugin() as plugin:
        class Context:
            def register_tool(self, name, toolset, schema, handler): setattr(self, name, handler)
            def register_hook(self, *args): pass
            def register_skill(self, *args): pass
        context = Context(); plugin.register(context)
        plugin.pre_llm_call(session_id="one", user_message=SKILL_INVOCATION + " UNIQUE-ACTIVATION-MARKER")
        result = context.design_discovery_get_state({}, session_id="one")
        assert json.loads(result)["ok"] is True and "UNIQUE-ACTIVATION-MARKER" not in result and "message_counts" in json.loads(result)["state"]


def test_approve_direction_locks_the_tried_color_as_shown():
    # Live run 11: try color from direction 2, then approve_direction 1 with the user's words.
    with isolated_plugin() as plugin:
        generate(plugin, varied_directions())
        tried = update_success(plugin, {"action": "try", "directions": {"typography": "dir-a", "color": "dir-b"}})
        shown = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["resolved_working"]["tokens"]
        adjustments_before = tried["state"]["adjustments"]
        reply = "This is correct. Lets lock in the direction"
        confirm(plugin, reply)
        approved = update_success(plugin, {"action": "approve_direction", "confirmed_by_user": reply, "direction": "dir-a"})
        working = approved["state"]["working"]
        assert working["color"]["direction_id"] == "dir-b" and working["typography"]["direction_id"] == "dir-a"
        assert all(working[dimension]["status"] == "locked" for dimension in design_core.DIMENSIONS)
        assert approved["changes"] == [] and approved["changed"] is False
        assert approved["state"]["adjustments"] == adjustments_before
        assert "Kept color as shown from Two." in approved["warnings"]
        after = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["resolved_working"]["tokens"]
        assert after["color"] == shown["color"]


def test_loose_direction_reference_resolves_to_its_one_ordinal_with_a_warning():
    with isolated_plugin() as plugin:
        generate(plugin, varied_directions())
        tried = update_success(plugin, {"action": "try", "directions": {"color": "color from option 2"}})
        assert tried["state"]["working"]["color"]["direction_id"] == "dir-b"
        assert "Read direction reference 'color from option 2' as 2 (Two, dir-b)." in tried["warnings"]


def test_unresolvable_direction_reference_gives_guidance_and_changes_nothing():
    with isolated_plugin() as plugin:
        generate(plugin, varied_directions())
        update_success(plugin, {"action": "try", "directions": {"color": "1"}})
        before = state.get_state("one")
        result = json.loads(plugin.design_discovery_update_choice({"action": "try", "directions": {"color": "something cozy"}}, session_id="one"))
        assert result["ok"] is True and "error" not in result
        assert result["changes"] == [] and result["changed"] is False
        assert "1 (One, dir-a), 2 (Two, dir-b), 3 (Three, dir-c)" in result["next"] and 'Example call: {"action":"try"' in result["next"]
        assert "—" not in result["next"] and "–" not in result["next"]
        assert state.get_state("one") == before


def test_wrong_borrowed_accent_names_the_right_hex_and_following_it_borrows():
    with isolated_plugin() as plugin:
        generate(plugin, varied_directions())
        update_success(plugin, {"action": "try", "directions": {"color": "1"}})
        saved = state.get_state("one")
        source = next(item for item in saved["directions"] if item["id"] == "dir-c")
        accent = design_core.resolve_direction(source)["color"]["accent"]
        result = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": "#123456", "source": "direction", "from_direction": "color from option 3"}, session_id="one"))
        assert result["ok"] is True and "error" not in result and result["changes"] == []
        assert "Its accent is " + accent in result["next"]
        assert state.get_state("one") == saved
        call = json.loads(result["next"].split("call design_discovery_update_choice with ", 1)[1].rstrip("."))
        assert call == {"action": "adjust", "path": "color.accent", "value": accent, "source": "direction", "from_direction": "dir-c"}
        borrowed = update_success(plugin, call)
        assert borrowed["state"]["adjustments"]["color.accent"]["value"] == accent
        assert borrowed["changes"]


def test_borrowed_accent_recomputes_text_and_usage_for_all_contrast_cases():
    base = direction(color="editorial", accent=None)
    text_fill = {**base, "adjustments": {"color.accent": {"value": "#2F4656", "source": "direction", "from_direction": "editorial"}}}
    fill_only = {**base, "adjustments": {"color.accent": {"value": "#F26B1D", "source": "direction", "from_direction": "bright"}}}
    too_low = {**base, "adjustments": {"color.accent": {"value": "#EDEDED", "source": "direction", "from_direction": "technical"}}}
    text_tokens = design_core.resolve_direction(text_fill)
    fill_tokens = design_core.resolve_direction(fill_only)
    assert text_tokens["color"]["accent_text"] == "#FFFFFF"
    assert text_tokens["accent_usage"] == "text_and_fill"
    assert fill_tokens["accent_usage"] == "fill_only"
    try:
        design_core.resolve_direction(too_low)
        assert False
    except ValueError as exc:
        assert "cannot reach 3:1" in str(exc)


def test_skill_manage_is_blocked_during_an_active_design_session():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        assert plugin.pre_tool_call(tool_name="skill_manage", session_id="one") == {"action": "block", "message": "Design discovery is in progress. Use the design discovery tools, tool search, or tool detail until DESIGN.md is exported. If the user wants to stop designing or do something else, call design_discovery_update_choice with action end."}


def test_lock_fills_unset_dimensions_from_its_direction():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        confirm(plugin, "I approve this direction")
        locked = json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "color", "direction_id": "one", "confirmed_by_user": "I approve this direction"}, session_id="one"))
        assert locked["ok"] is True
        assert locked["state"]["working"]["color"]["status"] == "locked"
        assert all(item["source"] for item in locked["state"]["working"].values())
        assert "Filled unset dimensions from One" in locked["detail"]


def test_borrowed_accent_fills_an_unset_working_mix():
    borrowed = direction(color="quiet-warmth", accent=None)
    borrowed["id"], borrowed["label"] = "borrowed", "Borrowed"
    with isolated_plugin() as plugin:
        generated = json.loads(generate(plugin, [direction(), borrowed]))
        borrowed_stored = next(item for item in generated["state"]["directions"] if item["label"] == "Borrowed")
        accent = design_core.resolve_direction(borrowed_stored)["color"]["accent"]
        adjusted = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": accent, "source": "direction", "from_direction": "Borrowed"}, session_id="one"))
        assert adjusted["ok"] is True
        assert adjusted["state"]["working"]["color"]["direction_id"] == "dir-b"
        assert all(item["source"] for item in adjusted["state"]["working"].values())
        assert "Filled unset dimensions from Borrowed" in adjusted["detail"]


def test_lock_requires_confirmation_after_the_dimension_was_last_changed():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        confirm(plugin, "yes")
        update_success(plugin, {"action": "try", "directions": {"color": "one"}})
        refused = json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "color", "confirmed_by_user": "yes"}, session_id="one"))
        assert refused["ok"] is False
        assert refused["next"] == "The user hasn’t seen this yet. Use try to show it, tell them the pane shows it, and wait for their reply."
        confirm(plugin, "yes, I have seen it")
        assert json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "color", "confirmed_by_user": "yes, I have seen it"}, session_id="one"))["ok"] is True


def test_file_reads_and_searches_are_blocked_during_an_active_design_session():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        expected = {"action": "block", "message": "Design discovery is in progress. Use the design discovery tools, tool search, or tool detail until DESIGN.md is exported. If the user wants to stop designing or do something else, call design_discovery_update_choice with action end."}
        assert plugin.pre_tool_call(tool_name="read_file", session_id="one") == expected
        assert plugin.pre_tool_call(tool_name="search_files", session_id="one") == expected


def test_design_tools_refuse_unknown_arguments():
    with isolated_plugin() as plugin:
        calls = [
            (plugin.design_discovery_record_understanding, {"summary": "A summary.", "unexpected": True}),
            (plugin.design_discovery_generate_directions, {"directions": [], "answers": ANSWERS, "confirmed_by_user": "yes", "unexpected": True}),
            (plugin.design_discovery_get_state, {"unexpected": True}),
            (plugin.design_discovery_export_design_md, {"confirmed_by_user": "yes", "unexpected": True}),
        ]
        for tool, args in calls:
            refused = json.loads(tool(args, session_id="one"))
            assert refused["error"] == "unexpected argument: unexpected"
            assert refused["next"] != plugin._NEXT_GENERIC_REFUSAL
            assert "Valid fields include action" in refused["next"]


def test_each_update_choice_action_refuses_unknown_arguments():
    with isolated_plugin() as plugin:
        for action in ("try", "lock", "unlock", "reject", "clear_reject", "adjust", "add_constraint", "remove_constraint"):
            args = {"action": action, "unexpected": True}
            if action == "lock":
                args = {"action": action, "dimension": "color", "accent": "orange"}
            refused = json.loads(plugin.design_discovery_update_choice(args, session_id="one"))
            expected = "accent" if action == "lock" else "unexpected"
            assert refused["error"] == f"unexpected argument: {expected}"
            assert refused["next"] != plugin._NEXT_GENERIC_REFUSAL
            assert "Valid fields include action" in refused["next"]


def test_update_choice_schema_lists_only_arguments_an_action_accepts():
    with isolated_plugin() as plugin:
        properties = set(plugin.UPDATE_SCHEMA["parameters"]["properties"])
        accepted = set().union(*plugin._UPDATE_ARGUMENTS.values())
        assert properties == accepted
        assert all("description" in item for item in plugin.UPDATE_SCHEMA["parameters"]["properties"].values())


def test_described_accent_uses_recorded_user_words_and_pane_provenance():
    base = direction(color="editorial", accent=None)
    base["id"] = "base"
    with isolated_plugin() as plugin:
        generate(plugin, [base])
        update_success(plugin, {"action": "try", "directions": {"color": "One"}})
        plugin.pre_llm_call(session_id="one", user_message="Make it bright orange, like a tangerine!")
        adjusted = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": "#2F4656", "source": "described", "user_words": "bright orange like a tangerine"}, session_id="one"))
        assert adjusted["ok"] is True
        assert adjusted["next"]
        assert adjusted["state"]["adjustments"]["color.accent"] == {"value": "#2F4656", "source": "described", "user_words": "bright orange like a tangerine"}, adjusted
        api = dashboard_api()
        accent = api.resolved_state("one")["resolved_working"]["dimensions"][-1]
        assert accent == {"dimension": "accent", "label": "bright orange like a tangerine", "status": "open", "described": True, "contrast_adjusted": None}


def test_described_accent_refuses_words_not_recorded_from_the_user():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        update_success(plugin, {"action": "try", "directions": {"color": "one"}})
        refused = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": "#F26B1D", "source": "described", "user_words": "bright orange like a tangerine"}, session_id="one"))
        assert refused["ok"] is False
        assert refused["error"] == "described color words must come from the user"


def test_confirmation_matches_normalized_contiguous_user_text():
    with isolated_plugin() as plugin:
        directions = varied_directions()
        plugin.pre_llm_call(session_id="one", user_message="I need a calm dashboard.")
        plugin.post_llm_call(session_id="one", assistant_response="What should it help people do?")
        plugin.pre_llm_call(session_id="one", user_message="Help people see the morning status.")
        plugin.design_discovery_record_understanding({"summary": "You want a calm dashboard in two plain sentences."}, session_id="one")
        plugin.pre_llm_call(session_id="one", user_message="Yes — that is right, please generate them.")
        accepted = json.loads(plugin.design_discovery_generate_directions({"directions": directions, "answers": ANSWERS, "confirmed_by_user": "that is right"}, session_id="one"))
        assert accepted["ok"] is True


def test_understanding_confirmation_mismatch_names_the_user_reply_requirement():
    with isolated_plugin() as plugin:
        directions = [direction() for _ in range(3)]
        interview_reply(plugin)
        plugin.design_discovery_record_understanding({"summary": "You want a calm dashboard in two plain sentences."}, session_id="one")
        plugin.pre_llm_call(session_id="one", user_message="No, make it brighter.")
        refused = json.loads(plugin.design_discovery_generate_directions({"directions": directions, "answers": ANSWERS, "confirmed_by_user": "yes"}, session_id="one"))
        assert refused["next"] == "Pass the user’s reply exactly as they wrote it as confirmed_by_user."


def test_adjust_before_try_fills_working_state_and_persists_accent_in_pane():
    with isolated_plugin() as plugin:
        generate(plugin, [direction(accent=None)])
        adjusted = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": "#4E5A3A", "source": "agent"}, session_id="one"))
        assert adjusted["next"] == plugin._NEXT_CHANGED
        assert adjusted["state"]["adjustments"]["color.accent"] == {"value": "#4E5A3A", "source": "agent"}
        assert all(item["source"] for item in adjusted["state"]["working"].values())
        if "fastapi" not in sys.modules:
            fastapi = types.ModuleType("fastapi")
            class Router:
                def get(self, _path): return lambda function: function
                def post(self, _path): return lambda function: function
            class HttpError(Exception): pass
            fastapi.APIRouter, fastapi.HTTPException, fastapi.Request = Router, HttpError, object
            sys.modules["fastapi"] = fastapi
        api = dashboard_api()
        working = api.resolved_state("one")["resolved_working"]
        assert working["tokens"]["color"]["accent"] == "#4E5A3A"
        assert working["tokens"]["color"]["accent_text"] != ""
        assert {"dimension": "accent", "label": "#4E5A3A", "status": "open"} in working["dimensions"]


def test_adjust_refuses_invalid_accent_variants_without_saving_or_success_next():
    variants = [
        {"path": "color.accent", "value": "#123456", "source": "agent"},
        {"path": "color.accent", "value": "#F26B1D", "source": "described"},
        {"path": "color.accent", "value": "tangerine", "source": "described", "user_words": "bright orange"},
    ]
    for args in variants:
        with isolated_plugin() as plugin:
            generate(plugin, [direction(accent=None)])
            plugin.pre_llm_call(session_id="one", user_message="Make it bright orange")
            refused = json.loads(plugin.design_discovery_update_choice({"action": "adjust", **args}, session_id="one"))
            assert refused["ok"] is False
            assert refused["next"]
            assert state.get_state("one")["adjustments"] == {}


def test_try_keeps_adjustments_for_dimensions_it_does_not_change():
    second = direction(accent=None); second["id"], second["label"] = "two", "Second choice"
    with isolated_plugin() as plugin:
        generate(plugin, [direction(accent=None), second])
        update_success(plugin, {"action": "adjust", "path": "color.accent", "value": "#4E5A3A", "source": "agent"})
        tried = json.loads(plugin.design_discovery_update_choice({"action": "try", "directions": {"typography": "Second choice"}}, session_id="one"))
        assert tried["state"]["adjustments"]["color.accent"] == {"value": "#4E5A3A", "source": "agent"}


def test_record_understanding_uses_visible_summary_before_latest_user_reply_only():
    summary = "A warm morning dashboard that shows which agents failed overnight, without a generic SaaS feel."
    request = {"directions": varied_directions(), "answers": ANSWERS, "confirmed_by_user": "Thats correct. Generate the directions please"}
    with isolated_plugin() as plugin:
        interview_reply(plugin)
        plugin.post_llm_call(session_id="one", assistant_response="You want a warm morning dashboard that shows which agents failed overnight, without a generic SaaS feel. Is that right?")
        plugin.pre_llm_call(session_id="one", user_message="Thats correct. Generate the directions please")
        recorded = json.loads(plugin.design_discovery_record_understanding({"summary": summary}, session_id="one"))
        assert recorded["next"] == "The understanding is already confirmed. Call design_discovery_generate_directions with the user’s reply as confirmed_by_user. Do not call design_discovery_record_understanding again."
        assert json.loads(plugin.design_discovery_generate_directions(request, session_id="one"))["next"].startswith("Describe each direction")
    with isolated_plugin() as plugin:
        interview_reply(plugin)
        plugin.pre_llm_call(session_id="one", user_message="Thats correct. Generate the directions please")
        recorded = json.loads(plugin.design_discovery_record_understanding({"summary": summary}, session_id="one"))
        assert recorded["next"] == "Show the user this summary in your own words and ask if it’s right. Then stop and wait for their reply."
        waiting = json.loads(plugin.design_discovery_generate_directions(request, session_id="one"))
        assert waiting["next"] == "The user hasn’t replied yet. Show them your understanding and wait for their reply."


def test_generic_quoted_yes_generates_but_scripted_specific_phrase_is_refused():
    request = {"directions": varied_directions(), "answers": ANSWERS, "confirmed_by_user": "Yes"}
    with isolated_plugin() as plugin:
        interview_reply(plugin)
        plugin.design_discovery_record_understanding({"summary": "You want a calm dashboard in two plain sentences."}, session_id="one")
        plugin.post_llm_call(session_id="one", assistant_response='A quick "yes" and I will generate the directions.')
        plugin.pre_llm_call(session_id="one", user_message="Yes")
        accepted = json.loads(plugin.design_discovery_generate_directions(request, session_id="one"))
        assert accepted["next"].startswith("Describe each direction")
    with isolated_plugin() as plugin:
        interview_reply(plugin)
        plugin.design_discovery_record_understanding({"summary": "You want a calm dashboard in two plain sentences."}, session_id="one")
        plugin.post_llm_call(session_id="one", assistant_response='Say "lock the warm palette" to approve it.')
        plugin.pre_llm_call(session_id="one", user_message="lock the warm palette")
        refused = json.loads(plugin.design_discovery_generate_directions({**request, "confirmed_by_user": "lock the warm palette"}, session_id="one"))
        assert refused["next"] == "Ask the user in your own words whether they approve. Do not suggest how to reply, then wait."


def test_generate_refuses_direction_labels_over_four_words():
    named = direction(); named["label"] = "Warm morning agent check dashboard"
    with isolated_plugin() as plugin:
        refused = json.loads(generate(plugin, [named], expect_ok=False))
        assert refused["ok"] is False
        assert refused["next"] == "Give this direction a short name of 2 to 4 words that describes what it does."


def test_generate_assigns_stable_direction_ids_and_accepts_labels_for_selection():
    variants = [None, "", "same"]
    for supplied_id in variants:
        choices = [direction(accent=None) for _ in range(3)]
        for index, choice in enumerate(choices):
            if supplied_id is None: choice.pop("id")
            else: choice["id"] = supplied_id
            choice["label"] = ("Morning Ritual", "Warm Signal", "Playful Dispatch")[index]
        with isolated_plugin() as plugin:
            generated = json.loads(generate(plugin, choices))
            assert [item["id"] for item in generated["state"]["directions"]] == ["dir-a", "dir-b", "dir-c"]
            assert generated["next"].endswith("Use these direction ids for try and lock: dir-a (Morning Ritual), dir-b (Warm Signal), dir-c (Playful Dispatch).")
            tried = json.loads(plugin.design_discovery_update_choice({"action": "try", "directions": {"color": "Warm Signal"}}, session_id="one"))
            assert tried["state"]["working"]["color"]["direction_id"] == "dir-b"
            unknown = json.loads(plugin.design_discovery_update_choice({"action": "try", "directions": {"color": "unknown"}}, session_id="one"))
            assert unknown["next"] == "Nothing changed. The direction reference 'unknown' did not match one direction. Use a number, label or id from this list: 1 (Morning Ritual, dir-a), 2 (Warm Signal, dir-b), 3 (Playful Dispatch, dir-c). Example call: {\"action\":\"try\",\"directions\":{\"color\":\"2\"}}"
            confirm(plugin, "lock warm signal")
            locked = json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "color", "direction_id": "Warm Signal", "confirmed_by_user": "lock warm signal"}, session_id="one"))
            assert locked["state"]["working"]["color"]["direction_id"] == "dir-b"
            api = dashboard_api()
            assert len(api.resolved_state("one")["resolved_directions"]) == 3


def test_generate_refuses_directions_that_are_too_similar_in_color():
    choices = [direction(accent=None) for _ in range(3)]
    for label, choice in zip(("Morning Clay", "Afternoon Clay", "Evening Clay"), choices): choice["label"] = label
    with isolated_plugin() as plugin:
        plugin.pre_llm_call(session_id="one", user_message="A dashboard")
        plugin.post_llm_call(session_id="one", assistant_response="What should this dashboard help people do?")
        plugin.pre_llm_call(session_id="one", user_message="Help people compare the daily status.")
        plugin.design_discovery_record_understanding({"summary": "You want a dashboard with a clear design direction."}, session_id="one")
        plugin.pre_llm_call(session_id="one", user_message="yes")
        refused = json.loads(plugin.design_discovery_generate_directions({"directions": choices, "answers": ANSWERS, "confirmed_by_user": "yes"}, session_id="one"))
        assert refused["ok"] is True and refused["generated"] is False and refused["status"] == "needs_changes"
        assert refused["next"].startswith("Nothing was generated and the pane is unchanged.")
        assert "Morning Clay" in refused["guidance"] and "Afternoon Clay" in refused["guidance"]
        assert "background lightness difference" in refused["guidance"] and "accent family difference" in refused["guidance"]
        assert "Move Afternoon Clay's accent hue" in refused["guidance"]
        assert state.get_state("one")["directions"] == []


def test_described_accent_enforces_contrast_before_persisting_and_shared_accent_is_specific():
    first = direction(accent=None)
    second = direction(accent=None); second["label"] = "Second"
    second["adjustments"] = {"color.accent": {"value": "#4E5A3A", "source": "agent"}}
    with isolated_plugin() as plugin:
        generate(plugin, [first, second])
        update_success(plugin, {"action": "try", "directions": {"color": "One"}})
        plugin.pre_llm_call(session_id="one", user_message="Make it orange")
        shared = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": "#7A4A1E", "source": "direction", "from_direction": "Second"}, session_id="one"))
        assert shared["ok"] is True and shared["changed"] is False and shared["changes"] == [] and "error" not in shared
        assert shared["next"] == plugin._NEXT_NO_CHANGE
        vague = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": "orange", "source": "agent"}, session_id="one"))
        assert vague["next"] == "Use source described, put the user's color words in user_words, and pass a matching #RRGGBB hex as value."


def test_described_accent_is_deepened_for_quiet_warmth_contrast():
    with isolated_plugin() as plugin:
        generate(plugin, [direction(accent=None)])
        for number in range(100): plugin.post_llm_call(session_id="one", assistant_response="old update " + str(number))
        update_success(plugin, {"action": "try", "directions": {"color": "One"}})
        plugin.pre_llm_call(session_id="one", user_message="Make it orange")
        adjusted = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": "#D4783C", "source": "described", "user_words": "orange"}, session_id="one"))
        assert adjusted["ok"] is True
        accent = adjusted["state"]["adjustments"]["color.accent"]
        assert accent["value"] != "#D4783C" and accent["contrast_adjusted"] == "deepened"
        assert adjusted["next"] == plugin._NEXT_CHANGED


def test_no_op_mutations_give_actionable_next_steps():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        update_success(plugin, {"action": "try", "directions": {"color": "one"}})
        repeated_try = json.loads(plugin.design_discovery_update_choice({"action": "try", "directions": {"color": "one"}}, session_id="one"))
        assert repeated_try["ok"] is True and repeated_try["changed"] is False
        assert repeated_try["next"] == plugin._NEXT_ALREADY_SHOWN
        confirm(plugin, "lock it")
        update_success(plugin, {"action": "lock", "dimension": "color", "direction_id": "one", "confirmed_by_user": "lock it"})
        before_events = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["state"]["message_events"]
        repeated_lock = json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "color", "direction_id": "one", "confirmed_by_user": "lock it"}, session_id="one"))
        assert repeated_lock["next"] == plugin._NEXT_ALREADY_LOCKED
        after_events = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["state"]["message_events"]
        assert after_events == before_events
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        update_success(plugin, {"action": "try", "directions": {"color": "one"}})
        repeated_unlock = json.loads(plugin.design_discovery_update_choice({"action": "unlock", "dimension": "color", "direction_id": "one"}, session_id="one"))
        assert repeated_unlock["next"] == plugin._NEXT_ALREADY_UNLOCKED
        missing_adjustment = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "motion.preset", "value": None}, session_id="one"))
        assert missing_adjustment["ok"] is True and missing_adjustment["changed"] is False and "error" not in missing_adjustment
        assert missing_adjustment["next"] == "Nothing to remove; the pane is unchanged."


def test_approve_direction_locks_an_untried_label_and_exports():
    with isolated_plugin() as plugin:
        generate(plugin, [direction(accent=None)])
        confirm(plugin, "I am happy with One, finish it")
        approved = json.loads(plugin.design_discovery_update_choice({"action": "approve_direction", "direction": "One", "confirmed_by_user": "I am happy with One, finish it"}, session_id="one"))
        assert approved["ok"] is True
        assert all(item["status"] == "locked" for item in approved["state"]["working"].values())
        confirm(plugin, "export the final direction")
        exported = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export the final direction"}, session_id="one"))
        assert exported["ok"] is True


def test_direction_ordinals_are_accepted_and_bad_try_entries_are_specific():
    with isolated_plugin() as plugin:
        generated = json.loads(generate(plugin, [direction(accent=None)]))
        tried = json.loads(plugin.design_discovery_update_choice({"action": "try", "directions": {"color": "option 1"}}, session_id="one"))
        assert tried["ok"] is True and tried["state"]["working"]["color"]["direction_id"] == "dir-a"
        malformed = json.loads(plugin.design_discovery_update_choice({"action": "try", "directions": {"colour": 1}}, session_id="one"))
        assert "'colour'=1" in malformed["error"] and "typography" in malformed["error"]


def test_approve_direction_preserves_a_locked_described_color():
    with isolated_plugin() as plugin:
        generate(plugin, [direction(accent=None)])
        update_success(plugin, {"action": "try", "directions": {"color": "One"}})
        plugin.pre_llm_call(session_id="one", user_message="Make it orange like a tangerine")
        update_success(plugin, {"action": "adjust", "path": "color.accent", "value": "#7A4A1E", "source": "described", "user_words": "orange like a tangerine"})
        confirm(plugin, "keep this orange")
        update_success(plugin, {"action": "lock", "dimension": "color", "direction_id": "One", "confirmed_by_user": "keep this orange"})
        confirm(plugin, "approve the rest")
        approved = update_success(plugin, {"action": "approve_direction", "direction": "1", "confirmed_by_user": "approve the rest"})
        assert approved["state"]["working"]["color"]["status"] == "locked"
        assert approved["state"]["adjustments"]["color.accent"]["source"] == "described"


def test_approve_direction_preserves_unlocked_described_accent_and_export_run_seven_flow():
    with isolated_plugin() as plugin:
        generate(plugin, [direction(accent=None)])
        plugin.pre_llm_call(session_id="one", user_message="bright orange")
        update_success(plugin, {"action": "adjust", "path": "color.accent", "value": "#C05A16", "source": "described", "user_words": "bright orange"})
        confirm(plugin, "approve it")
        approved = update_success(plugin, {"action": "approve_direction", "direction": "One", "confirmed_by_user": "approve it"})
        assert approved["state"]["adjustments"]["color.accent"]["value"] == "#C05A16"
        pane = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["resolved_working"]
        assert pane["tokens"]["color"]["accent"] == "#C05A16"
        confirm(plugin, "export it")
        document = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))["design_md"]
        assert "Primary action color: bright orange, your choice." in document and "#C05A16" in document


def test_color_value_refusals_are_specific_and_unknown_sources_are_lenient():
    with isolated_plugin() as plugin:
        generate(plugin, [direction(accent=None)])
        plugin.pre_llm_call(session_id="one", user_message="bright orange")
        for value in ("bright orange", "#123", "#bright orange"):
            refused = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": value, "source": "described", "user_words": "bright orange"}, session_id="one"))
            assert refused["next"] != plugin._NEXT_GENERIC_REFUSAL and "user_words" in refused["next"]
        for source in ("agent", "user"):
            refused = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "color.accent", "value": "bright orange", "source": source}, session_id="one"))
            assert refused["next"] == "Use source described, put the user's color words in user_words, and pass a matching #RRGGBB hex as value."
        for dimension in design_core.DIMENSIONS:
            invalid = direction(); invalid["sources"][dimension] = "structured"
            accepted = json.loads(generate(plugin, [invalid]))
            assert accepted["ok"] is True and "error" not in accepted
            assert any("sources." + dimension in warning and "structured" in warning and "Valid values:" in warning for warning in accepted["warnings"])


def test_design_md_brief_uses_skill_command_remainder_or_next_user_message():
    plugin = _load_plugin()
    state_value = state.fresh_state(); state_value["brief"] = "summary fallback"
    state_value["user_messages"] = ['[IMPORTANT: The user has invoked the "design-discovery" skill]\nThe user has provided the following instruction alongside the skill invocation: A garden planner for mornings.']
    assert plugin._brief_from_user_messages(state_value) == "A garden planner for mornings."
    state_value["user_messages"] = ['[IMPORTANT: The user has invoked the "design-discovery" skill]', "A garden planner for mornings."]
    assert plugin._brief_from_user_messages(state_value) == "A garden planner for mornings."


def test_active_session_allowlist_and_post_export_release():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        blocked = {"action": "block", "message": "Design discovery is in progress. Use the design discovery tools, tool search, or tool detail until DESIGN.md is exported. If the user wants to stop designing or do something else, call design_discovery_update_choice with action end."}
        assert plugin.pre_tool_call(tool_name="computer_use", session_id="one") == blocked
        assert plugin.pre_tool_call(tool_name="terminal", session_id="one") == blocked
        assert plugin.pre_tool_call(tool_name="tool_search", session_id="one") is None
        assert plugin.pre_tool_call(tool_name="tool_describe", session_id="one") is None
        assert plugin.pre_tool_call(tool_name="skill_view", args={"skill_name": "other"}, session_id="one")["action"] == "block"
        assert plugin.pre_tool_call(tool_name="computer_use", session_id="missing") is None
        lock_all(plugin)
        confirm(plugin, "export it")
        json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))
        assert plugin.pre_tool_call(tool_name="computer_use", session_id="one") is None


def test_get_state_does_not_activate_a_fresh_session_or_block_terminal():
    with isolated_plugin() as plugin:
        state_value = json.loads(plugin.design_discovery_get_state_tool({}, session_id="one"))["state"]
        assert state_value["active"] is False
        assert plugin.pre_tool_call(tool_name="terminal", session_id="one") is None


def test_end_releases_an_active_session_and_is_a_successful_inactive_no_op():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        assert plugin.pre_tool_call(tool_name="terminal", session_id="one")["action"] == "block"
        ended = json.loads(plugin.design_discovery_update_choice({"action": "end"}, session_id="one"))
        assert ended["ok"] is True and ended["state"]["active"] is False
        assert plugin.pre_tool_call(tool_name="terminal", session_id="one") is None
        inactive = json.loads(plugin.design_discovery_update_choice({"action": "end"}, session_id="one"))
        assert inactive["ok"] is True and inactive["changed"] is False and inactive["changes"] == []


def test_every_refusal_message_has_specific_recovery_text():
    with isolated_plugin() as plugin:
        messages = []
        for path in (Path("__init__.py"), Path("design_core.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not isinstance(node.exc.func, ast.Name) or node.exc.func.id != "ValueError" or not node.exc.args:
                    continue
                value = node.exc.args[0]
                if isinstance(value, ast.Constant) and isinstance(value.value, str): messages.append(value.value)
        messages += ["unknown action", "unsupported adjustment path: typography.ui_font", "all five dimensions must be locked; unlocked: color", "That value wasn't given by the user. Use source agent, or ask the user.", "invalid directions entry 'colour'=1; use dimensions typography", "unknown layout archetype: structured", "unknown font: missing", "constraint violated: Keep it calm", "accent #FFFFFF cannot reach 3:1 against the background"]
        for message in messages:
            next_text = json.loads(plugin._refusal(ValueError(message)))["next"]
            assert next_text != plugin._NEXT_GENERIC_REFUSAL
            assert next_text != "Correct the invalid input named in the error, then continue the design conversation."
            if next_text.startswith("Correct this input before continuing:"):
                assert message in next_text


def test_tool_event_log_is_redacted_and_session_scoped():
    with isolated_plugin() as plugin:
        class Context:
            def __init__(self): self.handlers = {}
            def register_tool(self, name, toolset, schema, handler): self.handlers[name] = handler
            def register_hook(self, *args): pass
            def register_skill(self, *args): pass
        context = Context(); plugin.register(context)
        result = context.handlers["design_discovery_record_understanding"]({"summary": "private summary"}, session_id="one")
        assert json.loads(result)["ok"] is True
        event = json.loads(state.tool_events_path("one").read_text(encoding="utf-8").splitlines()[-1])
        assert event["tool"] == "design_discovery_record_understanding" and "private summary" not in json.dumps(event)
        assert not state.tool_events_path("two").exists()


def test_generate_event_logs_composed_hex_values_without_user_prose():
    with isolated_plugin() as plugin:
        class Context:
            def register_tool(self, name, toolset, schema, handler): setattr(self, name, handler)
            def register_hook(self, *args): pass
            def register_skill(self, *args): pass
        context = Context(); plugin.register(context)
        confirmation = confirmed_understanding(plugin)
        result = json.loads(context.design_discovery_generate_directions({"directions": composed_triplet(), "answers": ANSWERS, "confirmed_by_user": confirmation}, session_id="one"))
        assert result["ok"] is True
        event = json.loads(state.tool_events_path("one").read_text(encoding="utf-8").splitlines()[-1])
        palette = event["args"]["directions"][0]["composed_palette"]
        assert set(palette) == set(COMPOSED) and all(palette[key].startswith("#") for key in ("background", "surface", "text", "muted", "border", "border_strong", "accent"))
        assert "I need a dashboard" not in json.dumps(event)


def test_export_writes_design_md_with_path_families_and_described_decision():
    with isolated_plugin() as plugin:
        generate(plugin, [direction(accent=None)])
        update_success(plugin, {"action": "try", "directions": {"color": "One"}})
        plugin.pre_llm_call(session_id="one", user_message="Make it orange, like a tangerine")
        update_success(plugin, {"action": "adjust", "path": "color.accent", "value": "#D4783C", "source": "described", "user_words": "orange, like a tangerine"})
        lock_all(plugin)
        confirm(plugin, "export it")
        exported = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))
        path = Path(exported["design_md_path"])
        assert path.read_text(encoding="utf-8") == exported["design_md"] and state.design_md_path("one").read_text(encoding="utf-8") == exported["design_md"]
        assert "Primary action color: orange, like a tangerine, your choice. Deepened slightly so it stays readable." in exported["design_md"]
        assert "--font-display:" in exported["design_md"] and "--font-body:" in exported["design_md"] and "figtree" not in exported["design_md"]
        assert "https://fonts.googleapis.com/css2?family=" in exported["design_md"]
        confirm(plugin, "export again")
        again = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export again"}, session_id="one"))
        assert again["design_md_path"] == exported["design_md_path"] and path.read_text(encoding="utf-8") == again["design_md"]


def test_design_md_leak_guard_and_resolved_values_for_archetypes_composed_and_mixed():
    forbidden = {"composed:", "dir-a", "dir-b", "dir-c", "described", "provenance", "\u2013", "\u2014"}
    for archetype_id, archetype in design_core.archetypes().items():
        forbidden.update({archetype_id, archetype["name"], *archetype["internal_refs"]})
    forbidden.update(font_id for font_id, font in design_core.fonts().items() if font_id != font["family"])
    directions = []
    for archetype_id in design_core.archetypes():
        item = direction(color=archetype_id, accent=None); item["id"] = "safe"; item["label"] = "Direction"; item["sources"] = {dimension: archetype_id for dimension in design_core.DIMENSIONS}
        directions.append(item)
    composed = composed_direction("Garden Watch"); composed["id"] = "safe"; composed["sources"]["color"] = "composed:safe"; directions.append(composed)
    mixed = direction(accent=None); mixed["id"] = "safe"; mixed["label"] = "Direction"; mixed["adjustments"] = {"color.accent": {"value": "#C05A16", "source": "described", "user_words": "bright orange", "contrast_adjusted": "deepened"}}
    directions.append(mixed)
    for item in directions:
        state_value = state.fresh_state(); state_value["brief"] = "A useful product."; state_value["directions"] = [item]
        for dimension in design_core.DIMENSIONS: state_value["working"][dimension] = {"source": item["sources"][dimension], "status": "locked", "direction_id": "safe"}
        if item["sources"]["color"].startswith("composed:"): state_value["working"]["color"]["palette"] = dict(item["composed_palette"])
        state_value["adjustments"] = dict(item["adjustments"]); state_value["user_messages"] = ["bright orange"]
        tokens = design_core.resolve_direction(plugin_direction := plugin._working_direction(state_value), user_messages=state_value["user_messages"])
        document = plugin._render_design_md(state_value, tokens)
        assert len(document.splitlines()) < 300
        assert all("--text-" + name + ":" in document for name in ("caption", "body", "h4", "h3", "h2", "h1", "display"))
        assert all("--space-" + str(index) + ":" in document for index in range(1, 9))
        assert ") (" not in document
        assert all("## " + heading in document for heading in ("Brief", "How it was assembled", "Tokens", "Typography", "Color", "Layout and spacing", "Geometry", "Motion", "Voice", "Instructions for the implementing agent"))
        assert document.count("```") % 2 == 0
        leaked = [value for value in forbidden if (re.search(r"\\b" + re.escape(value) + r"\\b", document, re.I) if value.isalnum() else value in document)]
        assert not leaked, leaked
        values = plugin._token_values(); density = values["densities"][tokens["layout"]["density"]]; motion = values["motion_presets"][tokens["motion"]["preset"]]
        assert str(density["unit_px"]) + "px" in document and str(motion["micro_ms"]) + "ms" in document


def test_fill_only_described_accent_uses_three_to_one_in_pane_and_design_md():
    item = composed_direction("Garden Watch", {**COMPOSED, "background": "#EEF2E8", "surface": "#E5EADD", "text": "#24301F", "muted": "#53604D", "border_strong": "#7B8B70", "accent": "#C05A16", "words": ["calm", "natural"]})
    with isolated_plugin() as plugin:
        generate(plugin, composed_triplet(item))
        update_success(plugin, {"action": "try", "directions": {"color": "Garden Watch"}})
        plugin.pre_llm_call(session_id="one", user_message="bright orange")
        update_success(plugin, {"action": "adjust", "path": "color.accent", "value": "#C05A16", "source": "described", "user_words": "bright orange"})
        pane = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["resolved_working"]
        assert pane["tokens"]["accent_usage"] == "fill_only"
        assert pane["contrast"]["accent_on_background"]["minimum"] == 3 and pane["contrast"]["accent_on_background"]["passes"]
        for dimension in design_core.DIMENSIONS:
            confirm(plugin, "lock " + dimension)
            update_success(plugin, {"action": "lock", "dimension": dimension, "direction_id": "Garden Watch", "confirmed_by_user": "lock " + dimension})
        confirm(plugin, "export it")
        document = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))["design_md"]
        assert "| accent on background | 3.9:1 | 3.0:1 | Pass |" in document


def test_final_pane_payload_carries_exported_content():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()]); lock_all(plugin); confirm(plugin, "export it")
        exported = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))
        api = dashboard_api()
        payload = api.resolved_state("one")
        assert payload["phase"] == "final" and payload["design_md"] == exported["design_md"]


def test_lock_scope_and_export_confirmation_are_recorded_without_user_text():
    with isolated_plugin() as plugin:
        class Context:
            def __init__(self): self.handlers = {}
            def register_tool(self, name, toolset, schema, handler): self.handlers[name] = handler
            def register_hook(self, *args): pass
            def register_skill(self, *args): pass
        context = Context(); plugin.register(context); generate(plugin, [direction(accent=None)])
        assert json.loads(context.handlers["design_discovery_update_choice"]({"action": "try", "directions": {"color": "One"}}, session_id="one"))["ok"]
        plugin.pre_llm_call(session_id="one", user_message="Make it orange, like a tangerine")
        assert json.loads(context.handlers["design_discovery_update_choice"]({"action": "adjust", "path": "color.accent", "value": "#D4783C", "source": "described", "user_words": "orange, like a tangerine"}, session_id="one"))["ok"]
        approval = "Yes I like that. Lets lock it in"
        confirm(plugin, approval)
        assert json.loads(context.handlers["design_discovery_update_choice"]({"action": "lock", "dimension": "color", "direction_id": "one", "confirmed_by_user": approval}, session_id="one"))["ok"]
        refused = json.loads(context.handlers["design_discovery_update_choice"]({"action": "lock", "dimension": "typography", "direction_id": "one", "confirmed_by_user": approval}, session_id="one"))
        assert refused["ok"] is False and "remaining dimensions" in refused["next"]
        confirm(plugin, "approve the rest")
        assert json.loads(context.handlers["design_discovery_update_choice"]({"action": "approve_direction", "direction": "One", "confirmed_by_user": "approve the rest"}, session_id="one"))["ok"]
        stale = json.loads(context.handlers["design_discovery_export_design_md"]({"confirmed_by_user": "approve the rest"}, session_id="one"))
        assert stale["ok"] is True and stale["exported"] is False and "error" not in stale
        assert stale["next"] == "Summarize the final direction in plain words and ask what they think, then wait."
        confirm(plugin, "export it")
        assert json.loads(context.handlers["design_discovery_export_design_md"]({"confirmed_by_user": "export it"}, session_id="one"))["ok"]
        events = state.tool_events_path("one").read_text(encoding="utf-8")
        assert '"message_event_id":' in events and '"scope":["color"]' in events and '"scope":"export"' in events and approval not in events and "export it" not in events


def test_normalise_round_trips_every_persisted_event_role():
    raw = {
        "message_events": [
            {"role": "user", "id": 1, "text": "private user text"},
            {"role": "assistant", "id": 2, "text": "private assistant text"},
            {"role": "understanding", "id": 3, "text": "private summary", "confirmed_reply": "yes"},
            {"role": "dimension_change", "id": 4, "text": "color", "dimension": "color"},
            {"role": "lock_confirmation", "id": 5, "message_event_id": 1, "scope": ["color"], "text": "must not persist"},
            {"role": "approve_confirmation", "id": 6, "message_event_id": 1, "scope": ["typography", "layout"]},
            {"role": "export_confirmation", "id": 7, "message_event_id": 1, "scope": "export"},
        ]
    }
    events = state._normalise(raw)["message_events"]
    assert [event["role"] for event in events] == ["user", "assistant", "understanding", "dimension_change", "lock_confirmation", "approve_confirmation", "export_confirmation"]
    assert events == [
        {"role": "user", "id": 1, "text": "private user text"},
        {"role": "assistant", "id": 2, "text": "private assistant text"},
        {"role": "understanding", "id": 3, "text": "private summary", "confirmed_reply": "yes"},
        {"role": "dimension_change", "id": 4, "text": "color", "dimension": "color"},
        {"role": "lock_confirmation", "id": 5, "message_event_id": 1, "scope": ["color"]},
        {"role": "approve_confirmation", "id": 6, "message_event_id": 1, "scope": ["typography", "layout"]},
        {"role": "export_confirmation", "id": 7, "message_event_id": 1, "scope": "export"},
    ]


def test_summary_detection_skips_confirmation_events_between_visible_messages():
    with isolated_plugin() as plugin:
        plugin._activate("one")
        interview_reply(plugin)
        plugin.post_llm_call(session_id="one", assistant_response="You want a calm dashboard for people who need clarity. Is that right?")
        plugin.pre_llm_call(session_id="one", user_message="Yes, that is right")
        state_value = state.get_state("one")
        plugin._record_confirmation(state_value, plugin._confirmation(state_value, "Yes, that is right"), ["color"], "lock_confirmation")
        state.replace_state(state_value, "one")
        recorded = json.loads(plugin.design_discovery_record_understanding({"summary": "You want a calm dashboard for people who need clarity."}, session_id="one"))
        assert recorded["next"] == "The understanding is already confirmed. Call design_discovery_generate_directions with the user’s reply as confirmed_by_user. Do not call design_discovery_record_understanding again."


def test_confirmation_ids_survive_event_trimming_for_scope_and_export_freshness():
    with isolated_plugin() as plugin:
        generate(plugin, [direction(accent=None)])
        update_success(plugin, {"action": "try", "directions": {"color": "One"}})
        plugin.pre_llm_call(session_id="one", user_message="Make it orange")
        update_success(plugin, {"action": "adjust", "path": "color.accent", "value": "#D4783C", "source": "described", "user_words": "orange"})
        confirm(plugin, "lock it")
        update_success(plugin, {"action": "lock", "dimension": "color", "confirmed_by_user": "lock it"})
        refused = json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "typography", "confirmed_by_user": "lock it"}, session_id="one"))
        assert refused["error"] == "this approval already locked another dimension"
        confirm(plugin, "approve the rest")
        update_success(plugin, {"action": "approve_direction", "direction": "One", "confirmed_by_user": "approve the rest"})
        stale = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "approve the rest"}, session_id="one"))
        assert stale["ok"] is True and stale["exported"] is False and "error" not in stale
        assert stale["next"] == "Summarize the final direction in plain words and ask what they think, then wait."
        confirm(plugin, "export it")
        assert json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))["ok"] is True


def test_loading_idless_events_assigns_ids_in_order():
    with isolated_plugin():
        path = state.state_path("legacy-events"); path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"schema_version": 1, "session_id": "legacy-events", "message_events": [{"role": "assistant", "text": "shown"}, {"role": "user", "text": "yes"}]}), encoding="utf-8")
        loaded = state.get_state("legacy-events")
        assert [event["id"] for event in loaded["message_events"]] == [1, 2]
        assert loaded["next_event_id"] == 3


def test_state_write_retries_then_reports_persistent_storage_failure_without_partial_state():
    with isolated_plugin() as plugin:
        plugin._activate("one")
        interview_reply(plugin)
        calls = {"count": 0}; real_replace = state.os.replace
        destination_path = state.state_path("one").resolve()
        def flaky(source, destination):
            if Path(destination).resolve() != destination_path: return real_replace(source, destination)
            calls["count"] += 1
            if calls["count"] <= 3: raise PermissionError("locked")
            return real_replace(source, destination)
        with patch.object(state.os, "replace", flaky):
            assert json.loads(plugin.design_discovery_record_understanding({"summary": "A clear morning dashboard."}, session_id="one"))["ok"] is True
        assert calls["count"] == 4 and state.get_state("one")["understanding"]["summary"] == "A clear morning dashboard."
        before = state.state_path("one").read_text(encoding="utf-8")
        with patch.object(state.os, "replace", side_effect=PermissionError("locked")):
            refused = json.loads(plugin.design_discovery_record_understanding({"summary": "This must not save."}, session_id="one"))
        assert refused["ok"] is False and "temporary save error" in refused["next"]
        assert state.state_path("one").read_text(encoding="utf-8") == before
        assert not list(state.state_path("one").parent.glob("state.json.*.tmp"))


def test_clarify_is_allowed_during_an_active_design_session():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        assert plugin.pre_tool_call(tool_name="clarify", session_id="one") is None


def test_every_invalid_enum_adjustment_is_lenient_and_names_all_accepted_values():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        update_success(plugin, {"action": "try", "directions": {"typography": "one"}})
        for path, kind in design_core.ADJUSTMENT_PATHS.items():
            if kind in design_core.enums():
                result = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": path, "value": "invalid-value", "source": "agent"}, session_id="one"))
                warning = result["warnings"][0]
                assert result["ok"] is True and result["changed"] is False and "error" not in result
                assert path in warning and "invalid-value" in warning and "kept" in warning
                assert all(str(value) in warning for value in design_core.enums()[kind]["enum"])


def test_defined_refusal_errors_never_use_generic_fallback():
    with isolated_plugin() as plugin:
        messages = ["unknown action", "unknown dimension", "directions must map one or more dimensions to direction ids", "try a direction before changing an individual value", "directions are too similar in color: One and Two share a light ground. Give them a difference the user would notice.", "No directions have been generated yet. Call design_discovery_generate_directions first before referring to a direction.", "unsupported adjustment path", "no adjustment exists at path", "dimension is already locked", "dimension is already unlocked", "working direction is already shown", "described color words must come from the user", "agent-sourced accent must be from the color source alternates", "dimension has not been seen since its last change", "unexpected argument: bad", "composed palette text on background is 2:1; it needs 7:1. Make text darker.", "composed_palette must contain exactly background, surface, text, muted, border, border_strong, and accent as #RRGGBB values", 'Use sources.color "composed" for a composed palette. The plugin assigns the direction id.', "archetype color directions cannot also include composed_palette"]
        for message in messages:
            assert json.loads(plugin._refusal(ValueError(message)))["next"] != plugin._NEXT_GENERIC_REFUSAL


def test_pane_uses_the_validator_contrast_contract_for_every_pair():
    direction_value = composed_direction(); direction_value["id"] = "dir-a"; direction_value["sources"]["color"] = "composed:dir-a"
    tokens = design_core.resolve_direction(direction_value)
    contract = report(tokens)
    assert all({"label", "minimum", "passes"} <= set(item) for item in contract.values())
    pane = Path("desktop/plugin.js").read_text(encoding="utf-8")
    assert "!result.passes" in pane and "aa_normal" not in pane[pane.index("const failures"):pane.index("function StatePane")]


def test_export_confirmation_refusal_keeps_the_direction_in_focus():
    with isolated_plugin() as plugin:
        refused = json.loads(plugin._refusal(ValueError("export confirmation must come after the final lock")))
        assert refused["next"] == "Summarize the final direction in plain words and ask what they think, then wait."


def _export_ready(plugin, words="export it"):
    generate(plugin, [direction(accent=None)])
    lock_all(plugin)
    confirm(plugin, words)
    return json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": words}, session_id="one"))


def test_export_falls_back_for_home_root_and_hermes_cwd():
    with isolated_plugin() as plugin:
        plugin._activate("one")
        for index, value in enumerate((str(Path.home()), Path.home().anchor, str(Path.home() / ".hermes" / "project"))):
            state.apply_patch("workspace_cwd", value, "one")
            exported = _export_ready(plugin, "export " + str(len(value))) if index == 0 else (confirm(plugin, "export " + str(len(value))), json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user":"export " + str(len(value))}, session_id="one")))[1]
            assert "Documents" in exported["design_md_path"] and "Design Discovery" in exported["design_md_path"]


def test_export_folder_provenance_naming_and_same_session_overwrite():
    with isolated_plugin() as plugin:
        folder = state.data_dir() / "chosen"; folder.mkdir()
        plugin.pre_llm_call(session_id="one", user_message="Save it in " + str(folder))
        generate(plugin, [direction(accent=None)]); lock_all(plugin); confirm(plugin, "export it")
        first = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user":"export it", "folder":str(folder)}, session_id="one"))
        assert Path(first["design_md_path"]).parent == folder
        confirm(plugin, "export again")
        again = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user":"export again", "folder":str(folder)}, session_id="one"))
        assert again["design_md_path"] == first["design_md_path"]
        other = folder / "DESIGN.md"; other.write_text("other", encoding="utf-8")
        assert json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user":"export again", "folder":str(folder)}, session_id="one"))["ok"]


def test_export_refuses_untyped_folder():
    with isolated_plugin() as plugin:
        folder = state.data_dir() / "untyped"; folder.mkdir()
        generate(plugin, [direction(accent=None)]); lock_all(plugin); confirm(plugin, "export it")
        refused = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user":"export it", "folder":str(folder)}, session_id="one"))
        assert refused["ok"] is False


def test_inverted_google_font_url_requests_300():
    tokens = design_core.resolve_direction(direction())
    tokens["typography"]["weight_contrast"] = "inverted"
    assert "Cormorant" not in plugin._google_font_url(tokens) or "wght@300" in plugin._google_font_url(tokens)


def test_font_classes_validate_catalog_and_urls_cover_the_full_library():
    raw_fonts = design_core._read(design_core.DATA / "fonts.json")
    vocabulary = design_core._read(design_core.DATA / "vocabulary.json")
    for broken in ({key: value for key, value in raw_fonts[0].items() if key != "class"}, {**raw_fonts[0], "class": "unknown"}):
        with patch.object(design_core, "_read", side_effect=lambda path, broken=broken: [broken, *raw_fonts[1:]] if path.name == "fonts.json" else vocabulary):
            try: design_core.fonts(); assert False
            except ValueError: pass
    with isolated_plugin() as plugin:
        catalog_fonts = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["catalog"]["fonts"]
        assert all({"class", "roles", "weights"} <= set(font) for font in catalog_fonts)
    module = plugin
    for font in raw_fonts:
        tokens = design_core.resolve_direction(direction())
        tokens["typography"].update({"display_font": font["id"], "body_font": font["id"], "ui_font": font["id"]})
        assert font["family"].replace(" ", "+") in module._google_font_url(tokens)
    tokens = design_core.resolve_direction(direction()); tokens["typography"].update({"display_font": "alegreya-sans", "body_font": "young-serif", "ui_font": "young-serif"})
    url = module._google_font_url(tokens)
    assert "Alegreya+Sans:wght@500" in url and "Young+Serif:wght@400" in url


def test_failed_generation_log_redacts_to_palette_fields():
    with isolated_plugin() as plugin:
        class Context:
            def register_tool(self, name, toolset, schema, handler): setattr(self, name, handler)
            def register_hook(self, *args): pass
            def register_skill(self, *args): pass
        context = Context(); plugin.register(context); confirmation = confirmed_understanding(plugin)
        context.design_discovery_generate_directions({"directions":[{"label":"One","rationale":"secret","sources":{},"composed_palette":{"accent":"#ABCDEF"}}],"answers":ANSWERS,"confirmed_by_user":confirmation}, session_id="one")
        event = json.loads(state.tool_events_path("one").read_text(encoding="utf-8").splitlines()[-1])
        assert "secret" not in json.dumps(event) and event["args"]["directions"][0]["color"]["accent"] == "#ABCDEF"


def test_sample_is_stored_exposed_to_the_route_and_has_fixed_pane_fallback():
    sample = {"title": "Fresh bread today", "body": "Reserve a loaf before noon.", "items": [{"label": "Country loaf", "status": "success", "status_label": "Ready"}, {"label": "Cardamom bun", "status": "warning", "status_label": "Limited"}], "primary": "Order bakes", "secondary": "View menu"}
    with isolated_plugin() as plugin:
        generate(plugin, varied_directions(), sample=sample)
        api = dashboard_api()
        payload = api.resolved_state("one")
        assert payload["resolved_directions"][0]["sample"] == sample
        update_success(plugin, {"action": "try", "directions": {"typography": "one"}})
        assert api.resolved_state("one")["resolved_working"]["sample"] == sample
    with isolated_plugin() as plugin:
        generate(plugin, varied_directions())
        assert dashboard_api().resolved_state("one")["resolved_directions"][0]["sample"] is None
    pane = Path("desktop/plugin.js").read_text(encoding="utf-8")
    assert "Second item" in pane and "Needs attention" in pane and "Primary action" in pane and "Secondary action" in pane
    assert "sample.items[1].label" in pane and "sample.primary" in pane and "sample.secondary" in pane and "Your direction" in pane


def test_sample_and_voice_overlength_and_dashes_are_normalized_with_warnings():
    valid = {"title": "Bread", "body": "Fresh loaves.", "items": [{"label": "Loaf", "status": "success", "status_label": "Ready"}, {"label": "Bun", "status": "neutral", "status_label": "Later"}], "primary": "Order", "secondary": "Menu"}
    with isolated_plugin() as plugin:
        overlong = {**valid, "title": "Fresh bread and pastries available today for pickup"}
        accepted = json.loads(generate(plugin, varied_directions(), sample=overlong))
        assert accepted["ok"] is True and accepted["state"]["sample"]["title"] == "Fresh bread and pastries available today" and any("Trimmed sample" in warning for warning in accepted["warnings"])
    with isolated_plugin() as plugin:
        dashed = {**valid, "primary": "Order\u2014now"}
        choices = varied_directions(); choices[0]["voice"] = {"tone": "Warm\u2014practical " + "voice " * 20, "do": ["Name\u2014each bake", "Use simple verbs", "Keep it welcoming"], "dont": ["Use hype", "Sound clinical", "Overpromise"], "example": "Your sourdough is ready."}
        accepted = json.loads(generate(plugin, choices, sample=dashed))
        voice = accepted["state"]["directions"][0]["voice"]
        assert accepted["ok"] is True and accepted["state"]["sample"]["primary"] == "Order, now"
        assert "—" not in voice["tone"] and "—" not in voice["do"][0] and len(voice["tone"]) <= 60
        assert any("Replaced dashes" in warning for warning in accepted["warnings"]) and any("Trimmed voice" in warning for warning in accepted["warnings"])


def test_direction_voice_overrides_state_pane_and_design_md():
    voice = {"tone": "Warm and practical", "do": ["Name each bake", "Use simple verbs", "Keep it welcoming"], "dont": ["Use hype", "Sound clinical", "Overpromise"], "example": "Your sourdough is ready for pickup."}
    choices = varied_directions(); choices[0]["voice"] = voice
    with isolated_plugin() as plugin:
        generate(plugin, choices)
        state_value = state.get_state("one")
        assert state_value["directions"][0]["voice"] == voice
        api = dashboard_api()
        assert api.resolved_state("one")["resolved_directions"][0]["tokens"]["voice"] == voice
        lock_all(plugin); confirm(plugin, "export it")
        document = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))["design_md"]
        assert "Tone: Warm and practical" in document and "Your sourdough is ready for pickup." in document


def test_voice_validation_leniently_pads_and_normalizes_supported_voice_with_a_warning():
    bad_voice = {"tone": "Warm", "do": ["One", "Two"], "dont": ["One", "Two", "Three"], "example": "Example"}
    with isolated_plugin() as plugin:
        choices = varied_directions(); choices[0]["voice"] = bad_voice
        accepted = json.loads(generate(plugin, choices))
        assert accepted["ok"] is True and len(accepted["state"]["directions"][0]["voice"]["do"]) == 3 and accepted["warnings"]
    with isolated_plugin() as plugin:
        choices = varied_directions(); choices[0]["voice"] = {"tone": "Warm\u2014practical", "do": ["One", "Two", "Three"], "dont": ["One", "Two", "Three"], "example": "Example"}
        accepted = json.loads(generate(plugin, choices))
        assert accepted["ok"] is True and accepted["state"]["directions"][0]["voice"]["tone"] == "Warm, practical" and accepted["warnings"]
    with isolated_plugin() as plugin:
        choices = varied_directions(); choices[0]["voice"] = {"tone": "Warm-practical", "do": ["One", "Two", "Three"], "dont": ["One", "Two", "Three"], "example": "Example"}
        accepted = json.loads(generate(plugin, choices))
        assert accepted["ok"] is True and "voice" not in accepted["state"]["directions"][0] and accepted["warnings"]


def test_generation_auto_corrects_legibility_failures_from_multiple_directions():
    choices = composed_triplet()
    choices[0]["composed_palette"] = {**choices[0]["composed_palette"], "text": "#C9BFB6"}
    choices[1]["composed_palette"] = {**choices[1]["composed_palette"], "border_strong": "#EDE4DA"}
    with isolated_plugin() as plugin:
        accepted = json.loads(generate(plugin, choices))
        assert accepted["ok"] is True
        assert accepted["state"]["directions"][0]["auto_adjusted"]
        assert accepted["state"]["directions"][1]["auto_adjusted"]


def test_variety_guidance_names_axes_thresholds_and_a_move_then_resubmission_passes():
    choices = composed_triplet()
    choices[1]["composed_palette"] = dict(COMPOSED)
    with isolated_plugin() as plugin:
        refused = json.loads(generate(plugin, choices, expect_ok=False))
        text = refused["guidance"]
        assert refused["ok"] is True and refused["generated"] is False and refused["status"] == "needs_changes"
        assert refused["next"].startswith("Nothing was generated and the pane is unchanged.")
        assert "background lightness difference" in text and "need 15+" in text
        assert "background hue difference" in text and "need 30+" in text
        assert "accent family difference" in text and "need 40+" in text
        assert "mode differs" in text and "Move Olive Sand's accent hue" in text
        assert state.get_state("one")["directions"] == []
        choices[1] = composed_triplet()[1]
        accepted = json.loads(generate(plugin, choices))
        assert accepted["ok"] is True and accepted["generated"] is True


def test_composed_legibility_auto_correction_preserves_hue_and_saturation_and_records_changes():
    for role, value in (("text", "#C9BFB6"), ("muted", "#C9BFB6"), ("border_strong", "#EDE4DA"), ("accent", "#EDE4DA")):
        choices = composed_triplet()
        before = value
        choices[0]["composed_palette"][role] = before
        with isolated_plugin() as plugin:
            accepted = json.loads(generate(plugin, choices))
            direction_value = accepted["state"]["directions"][0]
            change = next(item for item in direction_value["auto_adjusted"] if item["role"] == role)
            assert change["from"] == before and change["to"] == direction_value["composed_palette"][role]
            before_hls, after_hls = design_core._hls(before), design_core._hls(change["to"])
            assert abs(before_hls[0] - after_hls[0]) < .01 and abs(before_hls[2] - after_hls[2]) < .01
            tokens = design_core.resolve_direction(direction_value)
            assert all(item["passes"] for item in report(tokens).values())


def test_impossible_composed_legibility_still_refuses():
    impossible = composed_direction("Impossible", {"background": "#777777", "surface": "#888888", "text": "#777777", "muted": "#777777", "border": "#777777", "border_strong": "#777777", "accent": "#777777", "words": ["warm"]})
    with isolated_plugin() as plugin:
        refused = json.loads(generate(plugin, [impossible], expect_ok=False))
        assert refused["ok"] is False and "cannot be made readable" in refused["error"]


def test_skill_keeps_replies_focused_on_the_design():
    skill = Path("skills/design-discovery/SKILL.md").read_text(encoding="utf-8")
    assert "Keep replies about the design itself: what each direction does and how it feels." in skill
    assert "Only describe changes listed in the tool result's `changes`. If it is empty, ask the user what they meant." in skill


def test_try_and_approve_copy_direction_adjustments_into_the_working_direction():
    choices = varied_directions()
    choices[0]["adjustments"] = {"typography.display_font": {"value": "inter", "source": "agent"}, "layout.density": {"value": "compact", "source": "agent"}}
    expected = design_core.resolve_direction(choices[0])
    with isolated_plugin() as plugin:
        generate(plugin, choices)
        tried = update_success(plugin, {"action": "try", "directions": {"typography": "one", "layout": "one"}})
        actual = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["resolved_working"]["tokens"]
        assert actual["typography"] == expected["typography"] and actual["layout"] == expected["layout"]
        confirm(plugin, "approve it")
        approved = update_success(plugin, {"action": "approve_direction", "direction": "one", "confirmed_by_user": "approve it"})
        actual = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["resolved_working"]["tokens"]
        assert approved["ok"] is True and actual["typography"] == expected["typography"] and actual["layout"] == expected["layout"]


def test_no_op_updates_return_success_without_error():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        update_success(plugin, {"action": "try", "directions": {"typography": "one"}})
        repeated_try = json.loads(plugin.design_discovery_update_choice({"action": "try", "directions": {"typography": "one"}}, session_id="one"))
        assert repeated_try["ok"] is True and repeated_try["changed"] is False and repeated_try["changes"] == [] and "error" not in repeated_try
        confirm(plugin, "lock it")
        update_success(plugin, {"action": "lock", "dimension": "typography", "confirmed_by_user": "lock it"})
        repeated_lock = json.loads(plugin.design_discovery_update_choice({"action": "lock", "dimension": "typography", "confirmed_by_user": "lock it"}, session_id="one"))
        assert repeated_lock["ok"] is True and repeated_lock["changed"] is False and repeated_lock["changes"] == [] and "error" not in repeated_lock


def test_removing_a_missing_adjustment_is_a_successful_no_op():
    with isolated_plugin() as plugin:
        generate(plugin, [direction()])
        result = json.loads(plugin.design_discovery_update_choice({"action": "adjust", "path": "motion.preset", "value": None}, session_id="one"))
        assert result["ok"] is True and result["changed"] is False and result["changes"] == [] and "error" not in result
        assert result["next"] == "Nothing to remove; the pane is unchanged."


def test_update_results_report_resolved_token_changes_and_adjust_is_scoped():
    with isolated_plugin() as plugin:
        generate(plugin, varied_directions())
        tried = update_success(plugin, {"action": "try", "directions": {"color": "one"}})
        assert tried["changed"] is True and tried["changes"] and tried["next"] == plugin._NEXT_CHANGED
        before = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["resolved_working"]["tokens"]
        plugin.pre_llm_call(session_id="one", user_message="orange")
        adjusted = update_success(plugin, {"action": "adjust", "path": "color.accent", "value": "#C7680C", "source": "described", "user_words": "orange"})
        after = json.loads(plugin.design_discovery_get_state({}, session_id="one"))["resolved_working"]["tokens"]
        assert all(before[key] == after[key] for key in ("typography", "layout", "geometry", "motion", "voice"))
        assert all(item["path"].startswith(("color.accent", "accent_usage")) for item in adjusted["changes"])
        repeated = update_success(plugin, {"action": "adjust", "path": "color.accent", "value": "#C7680C", "source": "described", "user_words": "orange"})
        assert repeated["changed"] is False and repeated["changes"] == [] and repeated["next"] == plugin._NEXT_NO_CHANGE


def test_accent_text_uses_black_when_white_does_not_pass_and_export_has_no_failure():
    choice = composed_direction()
    choice["adjustments"]["color.accent"] = {"value": "#C7680C", "source": "agent"}
    resolved_choice = {**choice, "id": "dir-a", "sources": {**choice["sources"], "color": "composed:dir-a"}}
    tokens = design_core.resolve_direction(resolved_choice)
    assert tokens["color"]["accent_text"] == "#000000" and contrast_ratio("#000000", "#C7680C") >= 4.5
    with isolated_plugin() as plugin:
        generate(plugin, composed_triplet(first=choice)); confirm(plugin, "approve it")
        update_success(plugin, {"action": "approve_direction", "direction": "Clay Morning", "confirmed_by_user": "approve it"})
        confirm(plugin, "export it")
        document = json.loads(plugin.design_discovery_export_design_md({"confirmed_by_user": "export it"}, session_id="one"))["design_md"]
        assert "Accent Text" in document and next(line for line in document.splitlines() if "accent text on accent" in line).endswith("| Pass |")


def test_brief_extraction_uses_only_the_instruction_after_the_skill_wrapper():
    plugin = _load_plugin()
    wrapper = '[IMPORTANT: skill]\n[Bundle context: full skill]\n# Design discovery\n[Skill directory: C:\\skill]\nThe user has provided the following instruction alongside the skill invocation: A calm bakery dashboard.'
    assert plugin._brief_from_user_messages({"user_messages": [wrapper], "brief": "fallback"}) == "A calm bakery dashboard."
    assert all(value not in plugin._brief_from_user_messages({"user_messages": [wrapper], "brief": "fallback"}) for value in ("IMPORTANT:", "[Skill directory", "Bundle context", "# Design discovery"))


def test_generate_leniently_drops_invalid_adjustments_unknown_fonts_and_sources():
    choices = varied_directions()
    choices[0]["adjustments"] = {"typography.scale": {"value": "comfortable", "source": "agent"}, "typography.display_font": {"value": "missing-font", "source": "agent"}}
    choices[1]["sources"]["layout"] = "missing-layout"
    with isolated_plugin() as plugin:
        accepted = json.loads(generate(plugin, choices))
        first, second = accepted["state"]["directions"][:2]
        assert accepted["ok"] is True and "error" not in accepted
        assert first["adjustments"] == {} and second["sources"]["layout"] == "precision-technical"
        warnings = " ".join(accepted["warnings"])
        assert "typography.scale" in warnings and "comfortable" in warnings and "Valid values:" in warnings
        assert "typography.display_font" in warnings and "missing-font" in warnings
        assert "sources.layout" in warnings and "missing-layout" in warnings


def test_adjust_leniently_drops_invalid_enum_and_unknown_font_with_warning():
    with isolated_plugin() as plugin:
        generate(plugin, varied_directions())
        update_success(plugin, {"action": "try", "directions": {"typography": "one"}})
        for path, value in (("typography.scale", "comfortable"), ("typography.display_font", "missing-font")):
            result = update_success(plugin, {"action": "adjust", "path": path, "value": value, "source": "agent"})
            assert "error" not in result and result["warnings"]
            warning = result["warnings"][0]
            assert path in warning and value in warning and "kept" in warning and "Valid values:" in warning
