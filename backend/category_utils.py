from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Set

from fastapi import HTTPException

_CATEGORIES_CACHE: Optional[List[dict]] = None
_CATEGORIES_PATH = Path(__file__).resolve().parent / "类目.json"


def _ensure_categories_loaded() -> List[dict]:
    """Lazy load categories JSON into memory."""
    global _CATEGORIES_CACHE
    if _CATEGORIES_CACHE is None:
        if not _CATEGORIES_PATH.exists():
            raise HTTPException(status_code=500, detail="categories file not found")
        try:
            raw = _CATEGORIES_PATH.read_text(encoding="utf-8")
            _CATEGORIES_CACHE = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"failed to load categories: {exc}") from exc
    return _CATEGORIES_CACHE


def get_all_categories() -> List[dict]:
    """Return full category tree."""
    return _ensure_categories_loaded()


def get_top_level_cat_ids() -> List[str]:
    """Return all level-1 category IDs as strings (keep file order)."""
    categories = _ensure_categories_loaded()
    ids: List[str] = []
    for item in categories:
        cid = item.get("catId")
        if cid is not None:
            ids.append(str(cid))
    return ids


def get_all_valid_cat_ids() -> Set[str]:
    """Return all catIds (level-1 + children) for validation."""
    categories = _ensure_categories_loaded()
    valid: Set[str] = set()
    for item in categories:
        cid = item.get("catId")
        if cid is not None:
            valid.add(str(cid))
        for child in item.get("children") or []:
            cid2 = child.get("catId")
            if cid2 is not None:
                valid.add(str(cid2))
    return valid


def get_secondary_categories(cat_id: str) -> list:
    """Return child categories of given top-level cat."""
    if not (cat_id or "").strip():
        return []
    categories = _ensure_categories_loaded()
    for item in categories:
        if str(item.get("catId")) == str(cat_id):
            children = item.get("children")
            return list(children) if isinstance(children, list) else []
    return []
