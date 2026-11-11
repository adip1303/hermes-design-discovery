"""Stdlib-only dispatch smoke test for Design Discovery plugin handlers."""

from __future__ import annotations

import json
import importlib
import importlib.util
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PACKAGE = "smoke_design_discovery_plugin"


def load_plugin():
    spec = importlib.util.spec_from_file_location(PLUGIN_PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[PLUGIN_PACKAGE] = module
    spec.loader.exec_module(module)
    return module


plugin = load_plugin()
state = importlib.import_module(PLUGIN_PACKAGE + ".state")


class RecordingContext:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}
        self.hooks: dict[str, object] = {}

    def register_tool(self, *, name: str, handler, **_kwargs) -> None:
        self.tools[name] = handler

    def register_hook(self, name: str, handler) -> None:
        self.hooks[name] = handler

    def register_skill(self, *_args) -> None:
        pass

    def dispatch(self, name: str, args: dict, session_id: str = "smoke-session") -> str:
        return self.tools[name](args, session_id=session_id)


def result(value: str) -> dict:
    assert isinstance(value, str), "handler must return a JSON string"
    decoded = json.loads(value)
    assert isinstance(decoded, dict), "handler JSON must be an object"
    return decoded


def main() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        state.data_dir = lambda: Path(directory)  # type: ignore[method-assign]
        context = RecordingContext()
        plugin.register(context)
        assert set(context.tools) == {"design_discovery_generate_directions", "design_discovery_record_understanding", "design_discovery_update_choice", "design_discovery_get_state", "design_discovery_export_design_md"}
        assert set(context.hooks) == {"pre_llm_call", "post_llm_call", "pre_tool_call", "post_tool_call"}

        # Hermes dispatches schema properties as keyword arguments.
        direction = {"id": "smoke", "label": "Smoke", "rationale": "Smoke", "sources": {"typography": "precision-technical", "color": "quiet-warmth", "layout": "precision-technical", "geometry": "precision-technical", "motion": "precision-technical"}, "adjustments": {"color.accent": {"value": "#4E5A3A", "source": "agent"}}}
        directions = [direction, {**direction, "id": "smoke-two", "label": "Smoke Two", "sources": {**direction["sources"], "color": "editorial"}, "adjustments": {"typography.display_font": {"value": "inter", "source": "agent"}}}, {**direction, "id": "smoke-three", "label": "Smoke Three", "sources": {**direction["sources"], "color": "bright-friendly"}, "adjustments": {"typography.display_font": {"value": "fraunces", "source": "agent"}}}]
        context.hooks["pre_llm_call"](session_id="smoke-session", user_message="I need a dashboard")
        context.hooks["pre_llm_call"](session_id="smoke-session", user_message="It should feel clear and calm")
        assert result(context.dispatch("design_discovery_record_understanding", {"summary": "You want a clear dashboard."}))["ok"] is True
        context.hooks["pre_llm_call"](session_id="smoke-session", user_message="yes, that is right")
        written = result(context.dispatch("design_discovery_generate_directions", {"directions": directions, "brief": "smoke", "answers": [{"q": "What is it?", "a": "A dashboard"}], "confirmed_by_user": "yes, that is right"}))
        assert written["ok"] is True
        assert written["state"]["brief"] == "smoke"

        read = result(context.dispatch("design_discovery_get_state", {}))
        assert read["ok"] is True
        assert read["state"]["rev"] == written["state"]["rev"]
        assert read["state"]["build_stamp"] is None
        assert read["state"]["loaded_stamp"] is None
        context.hooks["pre_llm_call"](session_id="smoke-session", user_message="confirmed")
        assert result(context.dispatch("design_discovery_update_choice", {"action": "lock", "dimension": "color", "direction_id": "smoke", "confirmed_by_user": "confirmed"}))["ok"] is True
        assert result(context.dispatch("design_discovery_export_design_md", {}))["ok"] is False

        bom_stamp = Path(directory) / "bom-stamp.json"
        bom_stamp.write_text(json.dumps({"git_sha": "bomsha", "built_at": "2026-11-08T00:00:00Z", "dirty": True}), encoding="utf-8-sig")
        assert state._read_build_stamp(bom_stamp) == {"git_sha": "bomsha", "built_at": "2026-11-08T00:00:00Z", "dirty": True}

        injected = context.hooks["pre_llm_call"](session_id="smoke-session")
        assert injected and "Design Discovery state" in injected["context"]
        assert context.hooks["pre_llm_call"](session_id="other-session") is None

    print("smoke_tools: passed")


if __name__ == "__main__":
    main()
