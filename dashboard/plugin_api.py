"""Desktop REST bridge for revisioned Design Discovery state."""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import sys
import types
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

_ROOT = Path(__file__).resolve().parent.parent
_PACKAGE = "design_discovery_dashboard"


def _load_plugin_entry():
    entry_path = (_ROOT / "__init__.py").resolve()
    for module in tuple(sys.modules.values()):
        source = getattr(module, "__file__", None)
        if source and Path(source).resolve() == entry_path:
            return module
    package = sys.modules.get(_PACKAGE)
    if package is None:
        package = types.ModuleType(_PACKAGE)
        package.__path__ = [str(_ROOT)]
        package.__package__ = _PACKAGE
        sys.modules[_PACKAGE] = package
    name = _PACKAGE + ".entry"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, _ROOT / "__init__.py", submodule_search_locations=[str(_ROOT)])
        if spec is None or spec.loader is None:
            raise ImportError("could not load Design Discovery plugin entry")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


_plugin = _load_plugin_entry()
_state = importlib.import_module(_plugin.__name__ + ".state")
_design_core = importlib.import_module(_plugin.__name__ + ".design_core")
design_discovery_get_state = _plugin.design_discovery_get_state
fonts = _design_core.fonts
apply_patch = _state.apply_patch
available_session_ids = _state.available_session_ids
has_valid_state = _state.has_valid_state


router = APIRouter()
_LOG = logging.getLogger(__name__)


def resolved_state(session_id: str) -> dict:
    if session_id and not has_valid_state(session_id):
        _LOG.warning("design-discovery state missing for requested session_id=%s; available_session_ids=%s", session_id, available_session_ids())
    payload = json.loads(design_discovery_get_state({}, session_id=session_id, activate_session=False))
    if not payload.get("ok"):
        raise HTTPException(status_code=500, detail=payload.get("error", "could not resolve design state"))
    state = payload["state"]
    direction_copy = {item["id"]: item for item in state["directions"]}
    resolved_directions = [
        {
            **resolved,
            "label": direction_copy[resolved["direction_id"]]["label"],
            "rationale": direction_copy[resolved["direction_id"]]["rationale"],
            "sample": state.get("sample"),
        }
        for resolved in payload["resolved_directions"]
    ]
    resolved_working = payload["resolved_working"]
    if resolved_working:
        direction_copy = {item["id"]: item for item in state["directions"]}
        dimensions = [
            {"dimension": dimension, "label": direction_copy.get(value.get("direction_id"), {}).get("label", "a direction"), "status": value["status"]}
            for dimension, value in state["working"].items()
        ]
        accent = state["adjustments"].get("color.accent")
        if isinstance(accent, dict) and accent.get("source") == "direction":
            dimensions.append({"dimension": "accent", "label": direction_copy.get(accent.get("from_direction"), {}).get("label", "a direction"), "status": state["working"]["color"]["status"]})
        if isinstance(accent, dict) and accent.get("source") == "described":
            dimensions.append({"dimension": "accent", "label": accent.get("user_words", "a described color"), "status": state["working"]["color"]["status"], "described": True, "contrast_adjusted": accent.get("contrast_adjusted")})
        if isinstance(accent, dict) and accent.get("source") in {"agent", "user"}:
            dimensions.append({"dimension": "accent", "label": accent.get("value", "an accent color"), "status": state["working"]["color"]["status"]})
        resolved_working = {
            **resolved_working,
            "dimensions": dimensions,
            "sample": state.get("sample"),
        }
    design_md = None
    if state["phase"] == "final":
        path = _state.design_md_path(session_id)
        if path.is_file(): design_md = path.read_text(encoding="utf-8")
    return {
        "ok": True,
        "phase": state["phase"],
        "conflicts": state["conflicts"],
        "resolved_directions": resolved_directions,
        "resolved_working": resolved_working,
        "font_families": {font_id: item["family"] for font_id, item in fonts().items()},
        "design_md": design_md, "design_md_path": state.get("export_path"),
    }


@router.get("/state")
async def read_state(request: Request) -> dict:
    return resolved_state(str(request.query_params.get("session_id") or ""))


@router.post("/state")
async def patch_state(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="JSON body required") from exc
    if not isinstance(body, dict) or not isinstance(body.get("field_path"), str) or not isinstance(body.get("session_id"), str) or "value" not in body:
        raise HTTPException(status_code=400, detail="session_id, field_path, and value are required")
    expected_rev = body.get("expected_rev")
    if expected_rev is not None and (not isinstance(expected_rev, int) or isinstance(expected_rev, bool)):
        raise HTTPException(status_code=400, detail="expected_rev must be an integer")
    try:
        state = apply_patch(body["field_path"], body["value"], body["session_id"], expected_rev)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="state revision changed; reload and retry") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "state": state}


@router.post("/workspace")
async def record_workspace(request: Request) -> dict:
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("session_id"), str) or not isinstance(body.get("cwd"), str):
        raise HTTPException(status_code=400, detail="session_id and cwd are required")
    path = Path(body["cwd"])
    if not path.is_absolute() or not path.is_dir():
        raise HTTPException(status_code=400, detail="cwd must be an existing absolute directory")
    return {"ok": True, "state": apply_patch("workspace_cwd", str(path), body["session_id"])}
