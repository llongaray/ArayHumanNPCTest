"""Decisões da restauração da Fase 3B.2, sem o Project Zomboid."""

from __future__ import annotations

from typing import Any


def decide(snapshot: dict[str, Any]) -> dict[str, Any]:
    phase = snapshot.get("phase", "WAITING_WORLD")
    if snapshot.get("world_changed"):
        return {"phase": "WAITING_WORLD", "reset": True}
    if phase == "WAITING_WORLD":
        if snapshot.get("has_world"):
            return {"phase": "WAITING_PLAYER"}
        return {"phase": phase}
    if phase == "WAITING_PLAYER":
        if not snapshot.get("player_alive"):
            return {"phase": phase}
        return {"phase": "WAITING_BRIDGE", "start_delay": True}
    if phase == "WAITING_BRIDGE":
        if not snapshot.get("delay_elapsed"):
            return {"phase": phase}
        if not snapshot.get("bridge_ready"):
            return {"phase": phase}
        if snapshot.get("pending"):
            return {"phase": phase}
        return {"phase": "LOADING_PERSISTENCE", "send": "list_npcs"}
    if phase == "LOADING_PERSISTENCE":
        if snapshot.get("timed_out"):
            if int(snapshot.get("tries") or 0) >= int(snapshot.get("max_tries") or 3):
                return {"phase": "PERSISTENCE_UNAVAILABLE"}
            return {"phase": "RETRY_WAIT"}
        result = snapshot.get("result")
        if not result:
            return {"phase": phase}
        if result.get("duplicate"):
            return {"phase": phase, "ignore": True}
        if not result.get("ok"):
            return {"phase": "RETRY_WAIT"}
        op = result.get("op")
        if op == "list_npcs":
            alive = [item for item in (result.get("npcs") or []) if item.get("alive", True)]
            dead = [item for item in (result.get("npcs") or []) if item.get("alive") is False]
            if not alive:
                return {"phase": "ACTIVE", "spawn": False, "dead": len(dead)}
            return {"phase": "WAITING_SQUARE", "restore": alive, "spawn": False}
        if op == "ensure_npc":
            if result.get("alive") is False:
                return {"phase": "NPC_DEAD", "uuid": result.get("npc_id"), "spawn": False}
            return {"phase": "LOADING_PERSISTENCE", "send": "load_state", "uuid": result.get("npc_id")}
        if op == "load_state":
            if result.get("position_x") is None:
                return {"phase": "RESTORING_NPC", "mode": "create", "uuid": snapshot.get("uuid")}
            return {
                "phase": "VALIDATING_STATE",
                "uuid": snapshot.get("uuid"),
                "revision": result.get("state_version"),
                "x": result.get("position_x"),
                "y": result.get("position_y"),
                "z": result.get("position_z"),
                "direction": result.get("direction"),
            }
        if op == "save_state":
            return {"phase": "ACTIVE", "confirm_revision": result.get("state_version")}
        return {"phase": phase}
    if phase == "RETRY_WAIT":
        if snapshot.get("retry_elapsed"):
            return {"phase": "WAITING_BRIDGE"}
        return {"phase": phase}
    if phase == "VALIDATING_STATE":
        coords = snapshot.get("coords") or {}
        if not _valid_coords(coords):
            return {"phase": "RESTORE_FAILED", "reason": "coordenadas"}
        return {"phase": "WAITING_SQUARE"}
    if phase == "WAITING_SQUARE":
        square = snapshot.get("square")
        if square == "pronto":
            return {"phase": "RESTORING_NPC", "mode": "restore"}
        if square == "adjacente":
            return {"phase": "RESTORING_NPC", "mode": "adjacent"}
        if snapshot.get("square_timeout"):
            return {"phase": "RESTORE_FAILED", "reason": "nao carregado", "keep_saved": True}
        return {"phase": phase}
    if phase == "RESTORING_NPC":
        if snapshot.get("npc_exists"):
            return {"phase": "ACTIVE", "duplicate_blocked": True}
        if snapshot.get("spawned"):
            if snapshot.get("mode") == "create":
                return {"phase": "LOADING_PERSISTENCE", "send": "save_state", "revision": 1}
            return {"phase": "ACTIVE"}
        return {"phase": "RESTORE_FAILED", "reason": "spawn", "keep_saved": True}
    if phase == "ACTIVE":
        if snapshot.get("player_changed"):
            return {"phase": "ACTIVE", "keep_uuid": True}
        if snapshot.get("save_requested") and not snapshot.get("pending"):
            if snapshot.get("position_changed"):
                revision = int(snapshot.get("confirmed_revision") or 0) + 1
                return {"phase": "ACTIVE", "send": "save_state", "revision": revision}
            return {"phase": "ACTIVE", "skip_save": True}
        return {"phase": phase}
    if phase == "RESTORE_FAILED" and snapshot.get("square") == "pronto":
        return {"phase": "WAITING_SQUARE"}
    if phase == "NPC_DEAD":
        return {"phase": "NPC_DEAD", "spawn": False}
    return {"phase": phase}


def _valid_coords(coords: dict[str, Any]) -> bool:
    for key in ("x", "y", "z"):
        value = coords.get(key)
        if not isinstance(value, (int, float)):
            return False
    return abs(float(coords["x"])) < 100000 and abs(float(coords["y"])) < 100000


def manual_spawn_allowed(phase: str, npc_alive: bool) -> str:
    if npc_alive:
        return "existe"
    if phase == "NPC_DEAD":
        return "morto"
    if phase in ("ACTIVE", "RESTORE_FAILED", "PERSISTENCE_UNAVAILABLE"):
        return "recusar_novo"
    return "em_andamento"
