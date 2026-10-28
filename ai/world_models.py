"""Gerenciamento de seleção de modelo por mundo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def load_world_models(root: Path) -> dict[str, str]:
    """Load world-specific model selections."""
    path = root / "world_models.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_world_models(root: Path, data: dict[str, str]) -> None:
    """Save world-specific model selections atomically."""
    path = root / "world_models.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    import os
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def get_model_for_world(world_models: dict[str, str], world_id: str, available_models: list[str]) -> str | None:
    """Get the saved model for a world, if it's still available."""
    saved = world_models.get(world_id)
    if saved and saved in available_models:
        return saved
    return None


def set_model_for_world(root: Path, world_models: dict[str, str], world_id: str, model: str) -> None:
    """Save a model selection for a specific world."""
    world_models[world_id] = model
    save_world_models(root, world_models)
