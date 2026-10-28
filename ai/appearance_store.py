"""Immutable native visual sidecars. No writes to saves or SQLite."""
import hashlib
import json
import os
import uuid
from pathlib import Path

from persistence import validate_world_id


def handle(root: Path, data: dict) -> dict:
    response = {"kind": "appearance_response", "id": data.get("id"), "world_id": data.get("world_id"),
                "npc_id": data.get("npc_id"), "ok": False}
    try:
        if validate_world_id(data.get("world_id")) or str(uuid.UUID(data["npc_id"])) != data["npc_id"]:
            raise ValueError("appearance_identity")
        path = root / "appearance" / hashlib.sha256(data["world_id"].encode()).hexdigest() / (data["npc_id"] + ".json")
        if data.get("op") not in ("get", "create"):
            raise ValueError("appearance_op")
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if existing and (existing.get("world_id") != data["world_id"] or existing.get("npc_id") != data["npc_id"] or existing.get("schema_version") != 1):
            raise ValueError("appearance_existing_invalid_migration_required")
        if data["op"] == "create":
            visual = data.get("visual")
            if not isinstance(visual, dict) or set(visual) != {"schema_version", "female", "human", "clothes"} or visual["schema_version"] != 1:
                raise ValueError("appearance_schema")
            clothes = visual["clothes"]
            if clothes == {}:  # Empty Lua array on the existing JSON boundary.
                clothes = visual["clothes"] = []
            if type(visual["female"]) is not bool or not isinstance(visual["human"], str) or not visual["human"].startswith("version=") or len(visual["human"]) > 8192:
                raise ValueError("appearance_human")
            if not isinstance(clothes, list) or len(clothes) > 32:
                raise ValueError("appearance_clothes")
            for garment in clothes:
                if not isinstance(garment, str) or not garment.startswith("version=") or len(garment) > 4096:
                    raise ValueError("appearance_garment")
            if len(json.dumps(visual).encode())>60000:
                raise ValueError("appearance_budget")
            proposed = {"schema_version": 1, "world_id": data["world_id"], "npc_id": data["npc_id"], "visual": visual}
            if existing and existing != proposed:
                raise ValueError("appearance_conflict_migration_required")
            if not existing:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix("." + uuid.uuid4().hex + ".part")
                try:
                    with tmp.open("x", encoding="utf-8") as f:
                        json.dump(proposed, f, ensure_ascii=True); f.flush(); os.fsync(f.fileno())
                    os.link(tmp, path)  # Atomic create-if-absent, never replace an existing record.
                except FileExistsError:
                    if json.loads(path.read_text(encoding="utf-8")) != proposed:
                        raise ValueError("appearance_conflict_migration_required")
                finally:
                    tmp.unlink(missing_ok=True)
                existing = proposed
        response.update(ok=True, found=existing is not None, visual=existing["visual"] if existing else None)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        response["error"] = str(exc)[:120]
    return response
