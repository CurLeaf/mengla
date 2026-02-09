"""
Panel config for the industry dashboard: modules (enable/disable, order) and layout.
Stored as JSON file; abstracted for future DB storage.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("mengla-backend")

# Default module IDs matching frontend MODES + internal sections
DEFAULT_MODULES: List[Dict[str, Any]] = [
    {"id": "overview", "name": "行业总览", "enabled": True, "order": 0, "props": {}},
    {"id": "high", "name": "蓝海Top行业", "enabled": True, "order": 1, "props": {}},
    {"id": "hot", "name": "热销Top行业", "enabled": True, "order": 2, "props": {}},
    {"id": "chance", "name": "潜力Top行业", "enabled": True, "order": 3, "props": {}},
]

DEFAULT_LAYOUT: Dict[str, Any] = {
    "defaultPeriod": "month",
    "showRankPeriodSelector": True,
}

# panel_config.json 在 backend/ 根目录下（与 category.json 同级）
CONFIG_DIR = Path(__file__).resolve().parent.parent
PANEL_CONFIG_PATH = CONFIG_DIR / "panel_config.json"


def _load_raw() -> Dict[str, Any]:
    if not PANEL_CONFIG_PATH.exists():
        return {
            "modules": list(DEFAULT_MODULES),
            "layout": dict(DEFAULT_LAYOUT),
        }
    try:
        raw = PANEL_CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"modules": list(DEFAULT_MODULES), "layout": dict(DEFAULT_LAYOUT)}
        modules = data.get("modules")
        if not isinstance(modules, list):
            data["modules"] = list(DEFAULT_MODULES)
        layout = data.get("layout")
        if not isinstance(layout, dict):
            data["layout"] = dict(DEFAULT_LAYOUT)
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load panel_config.json: %s, using defaults", exc)
        return {
            "modules": list(DEFAULT_MODULES),
            "layout": dict(DEFAULT_LAYOUT),
        }


def _save_raw(data: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PANEL_CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_panel_config() -> Dict[str, Any]:
    """Return current panel config (modules + layout)."""
    return _load_raw()


def update_panel_config(modules: List[Dict[str, Any]] | None = None, layout: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Update and persist panel config. Pass only the keys you want to update.
    Returns the full config after update.
    """
    data = _load_raw()
    if modules is not None:
        data["modules"] = modules
    if layout is not None:
        data["layout"] = {**data.get("layout", {}), **layout}
    _save_raw(data)
    return data
