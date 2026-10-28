#!/usr/bin/env python3
"""Fase 1: ping/pong por arquivo. Sem Ollama."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
SLEEP_S = 0.25

ROOT = Path(os.environ.get(
    "ARAY_BRIDGE_DIR",
    str(Path.home() / "Zomboid" / "Lua" / "ArayHumanNPCTest"),
))
TO_PY = ROOT / "to_py"
TO_LUA = ROOT / "to_lua"


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def validate_ping(data: object) -> str | None:
    if not isinstance(data, dict):
        return "nao objeto"
    kind = data.get("kind")
    req_id = data.get("id")
    world_id = data.get("world_id")
    if kind != "ping":
        return "kind"
    if not isinstance(req_id, str) or not SAFE_ID.match(req_id):
        return "id"
    if not isinstance(world_id, str) or not world_id or ".." in world_id:
        return "world_id"
    if data.get("action") is not None:
        return "action"
    return None


def seen_path() -> Path:
    return ROOT / "seen_ids.txt"


def already_seen(req_id: str) -> bool:
    path = seen_path()
    if not path.is_file():
        return False
    return req_id in path.read_text(encoding="utf-8").splitlines()


def remember(req_id: str) -> None:
    path = seen_path()
    lines = []
    if path.is_file():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    lines.append(req_id)
    atomic_write(path, "\n".join(lines[-32:]) + "\n")


def reply(req_id: str) -> None:
    payload = {
        "id": req_id,
        "kind": "pong",
        "ok": True,
        "service": "aray-bridge",
    }
    atomic_write(TO_LUA / f"{req_id}.json", json.dumps(payload, separators=(",", ":")))
    print(f"[ARAY] ponte pong id={req_id}", flush=True)


def take_request(ok_path: Path) -> None:
    req_id = ok_path.stem
    tmp_path = TO_PY / f"{req_id}.json.tmp"
    if not SAFE_ID.match(req_id):
        print(f"[ARAY] ponte pedido recusado id", flush=True)
        ok_path.unlink(missing_ok=True)
        return
    if not tmp_path.is_file():
        print(f"[ARAY] ponte pedido recusado tmp id={req_id}", flush=True)
        ok_path.unlink(missing_ok=True)
        return
    try:
        data = json.loads(tmp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"[ARAY] ponte pedido recusado json id={req_id}", flush=True)
        tmp_path.unlink(missing_ok=True)
        ok_path.unlink(missing_ok=True)
        return
    reason = validate_ping(data)
    tmp_path.unlink(missing_ok=True)
    ok_path.unlink(missing_ok=True)
    if reason:
        print(f"[ARAY] ponte pedido recusado {reason} id={req_id}", flush=True)
        return
    if already_seen(req_id):
        print(f"[ARAY] ponte pedido antigo id={req_id}", flush=True)
        return
    remember(req_id)
    world_id = data.get("world_id")
    print(f"[ARAY] ponte ping id={req_id} world_id={world_id}", flush=True)
    reply(req_id)


def main() -> None:
    TO_PY.mkdir(parents=True, exist_ok=True)
    TO_LUA.mkdir(parents=True, exist_ok=True)
    print(f"[ARAY] ponte servico iniciado dir={ROOT}", flush=True)
    while True:
        for ok_path in sorted(TO_PY.glob("*.ok")):
            take_request(ok_path)
        time.sleep(SLEEP_S)


if __name__ == "__main__":
    main()
