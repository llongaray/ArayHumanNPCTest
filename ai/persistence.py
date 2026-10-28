"""Banco SQLite da Fase 3B.1. Um arquivo, mundos isolados por coluna."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
CARLOS_PERSONA = "persona_default"
CARLOS = {
    "name": "Carlos",
    "surname": "Aray",
    "age": 35,
    "sex": "male",
    "occupation": "mecanico",
    "persona_id": CARLOS_PERSONA,
}

_WORLD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,159}$")
_OPS = {
    "status",
    "ensure_world",
    "ensure_npc",
    "get_npc",
    "list_npcs",
    "create_npc",
    "restore_npc",
    "save_state",
    "save_npc_state",
    "load_state",
    "mark_npc_dead",
}

_NAME = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' ._-]{0,39}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_or(text: object, fallback: Any) -> Any:
    if not isinstance(text, str) or not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def normalize_full_name(name: str, surname: str) -> str:
    text = re.sub(r"\s+", " ", f"{name} {surname}").strip()
    return text.casefold()


def validate_world_id(world_id: object) -> str | None:
    if not isinstance(world_id, str) or not world_id:
        return "world_id"
    if ".." in world_id or "\\" in world_id or "//" in world_id:
        return "world_id"
    if world_id.startswith("/") or world_id.endswith("/"):
        return "world_id"
    if not _WORLD_ID.match(world_id):
        return "world_id"
    return None


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _apply_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS worlds (
            world_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            last_loaded_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS npcs (
            npc_id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL REFERENCES worlds(world_id),
            name TEXT NOT NULL,
            surname TEXT NOT NULL,
            age INTEGER NOT NULL,
            sex TEXT NOT NULL,
            occupation TEXT NOT NULL,
            persona_id TEXT NOT NULL,
            alive INTEGER NOT NULL CHECK (alive IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (world_id, persona_id)
        );
        CREATE TABLE IF NOT EXISTS npc_state (
            npc_id TEXT PRIMARY KEY REFERENCES npcs(npc_id),
            world_id TEXT NOT NULL,
            position_x REAL NOT NULL,
            position_y REAL NOT NULL,
            position_z REAL NOT NULL,
            direction TEXT,
            health REAL,
            current_action TEXT,
            last_saved_at TEXT NOT NULL,
            state_version INTEGER NOT NULL,
            UNIQUE (npc_id, world_id)
        );
        CREATE TABLE IF NOT EXISTS npc_appearance (
            npc_id TEXT PRIMARY KEY REFERENCES npcs(npc_id),
            hair TEXT,
            beard TEXT,
            skin_tone TEXT,
            clothing_json TEXT,
            visual_json TEXT
        );
        CREATE TABLE IF NOT EXISTS npc_inventory (
            npc_id TEXT NOT NULL REFERENCES npcs(npc_id),
            slot TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_data_json TEXT,
            quantity INTEGER NOT NULL,
            equipped INTEGER NOT NULL CHECK (equipped IN (0, 1)),
            body_location TEXT,
            PRIMARY KEY (npc_id, slot)
        );
        CREATE TABLE IF NOT EXISTS conversations (
            message_id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL,
            npc_id TEXT NOT NULL REFERENCES npcs(npc_id),
            player_character_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS npc_memories (
            memory_id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL,
            npc_id TEXT NOT NULL REFERENCES npcs(npc_id),
            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,
            importance INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL,
            confidence TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_npcs_world ON npcs(world_id);
        CREATE INDEX IF NOT EXISTS idx_conversations_npc ON conversations(world_id, npc_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_memories_npc ON npc_memories(world_id, npc_id);
        """
    )


class PersistenceStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.conn = _connect(self.path)
        self.migrate()

    def close(self) -> None:
        if self.conn is None:
            return
        self.conn.close()
        self.conn = None

    def schema_version(self) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        ).fetchone()
        return int(row["version"])

    def migrate(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        current = self.schema_version()
        if current > SCHEMA_VERSION:
            raise RuntimeError(f"schema futuro {current}")
        if current < 1:
            if current == 0 and self._has_user_tables():
                self._backup(current)
            _apply_v1(self.conn)
            self.conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (1, ?)",
                (utc_now(),),
            )
            current = 1
            self.conn.commit()
        if current < 2:
            self.conn.commit()
            if self.path.is_file() and self._has_user_tables():
                self._backup(1)
            self.conn.execute("PRAGMA foreign_keys = OFF")
            try:
                self._migrate_v2()
                self.conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (2, ?)",
                    (utc_now(),),
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

    def _migrate_v2(self) -> None:
        self.conn.execute(
                """
                CREATE TABLE npcs_v2 (
                    npc_id TEXT PRIMARY KEY,
                    world_id TEXT NOT NULL REFERENCES worlds(world_id),
                    name TEXT NOT NULL,
                    surname TEXT NOT NULL,
                    age INTEGER NOT NULL,
                    sex TEXT NOT NULL,
                    occupation TEXT NOT NULL,
                    persona_id TEXT NOT NULL,
                    alive INTEGER NOT NULL CHECK (alive IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    description TEXT,
                    lore TEXT,
                    personality_json TEXT,
                    speech_style TEXT,
                    fears TEXT,
                    motivations TEXT,
                    skills_json TEXT,
                    name_key TEXT NOT NULL
                )
                """
            )
        rows = self.conn.execute("SELECT * FROM npcs").fetchall()
        for row in rows:
            item = dict(row)
            self.conn.execute(
                """
                INSERT INTO npcs_v2(
                    npc_id, world_id, name, surname, age, sex, occupation,
                    persona_id, alive, created_at, updated_at, name_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["npc_id"], item["world_id"], item["name"], item["surname"],
                    item["age"], item["sex"], item["occupation"], item["persona_id"],
                    item["alive"], item["created_at"], item["updated_at"],
                    normalize_full_name(item["name"], item["surname"]),
                ),
            )
        self.conn.execute("DROP TABLE npcs")
        self.conn.execute("ALTER TABLE npcs_v2 RENAME TO npcs")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_npcs_world ON npcs(world_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_npcs_alive ON npcs(world_id, alive)")
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_npcs_name ON npcs(world_id, name_key)"
        )

    def _has_user_tables(self) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'worlds'"
        ).fetchone()
        return row is not None

    def _backup(self, version: int) -> None:
        if not self.path.is_file():
            return
        dest = self.path.with_name(self.path.name + f".bak-v{version}")
        self.conn.commit()
        shutil.copy2(self.path, dest)

    def ensure_world(self, world_id: str) -> dict[str, Any]:
        reason = validate_world_id(world_id)
        if reason:
            raise ValueError(reason)
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO worlds(world_id, created_at, last_loaded_at, schema_version)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(world_id) DO UPDATE SET last_loaded_at = excluded.last_loaded_at
            """,
            (world_id, now, now, SCHEMA_VERSION),
        )
        self.conn.commit()
        return self._world_row(world_id)

    def _world_row(self, world_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT world_id, created_at, last_loaded_at, schema_version FROM worlds WHERE world_id = ?",
            (world_id,),
        ).fetchone()
        return dict(row) if row else {}

    def ensure_npc(self, world_id: str) -> dict[str, Any]:
        self.ensure_world(world_id)
        existing = self.get_npc(world_id)
        if existing:
            return existing
        now = utc_now()
        npc_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO npcs(
                npc_id, world_id, name, surname, age, sex, occupation,
                persona_id, alive, created_at, updated_at, name_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                npc_id,
                world_id,
                CARLOS["name"],
                CARLOS["surname"],
                CARLOS["age"],
                CARLOS["sex"],
                CARLOS["occupation"],
                CARLOS["persona_id"],
                now,
                now,
                normalize_full_name(CARLOS["name"], CARLOS["surname"]),
            ),
        )
        self.conn.commit()
        return self.get_npc(world_id) or {}

    def _as_npc(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        data = dict(row)
        data["alive"] = bool(data["alive"])
        raw_personality = data.get("personality_json")
        raw_skills = data.get("skills_json")
        data["personality"] = _json_or(raw_personality, None)
        data["skills"] = _json_or(raw_skills, [])
        return data

    def get_npc(self, world_id: str) -> dict[str, Any] | None:
        reason = validate_world_id(world_id)
        if reason:
            raise ValueError(reason)
        row = self.conn.execute(
            "SELECT * FROM npcs WHERE world_id = ? AND persona_id = ?",
            (world_id, CARLOS_PERSONA),
        ).fetchone()
        return self._as_npc(row)

    def get_by_id(self, world_id: str, npc_id: str) -> dict[str, Any] | None:
        reason = validate_world_id(world_id)
        if reason:
            raise ValueError(reason)
        row = self.conn.execute(
            "SELECT * FROM npcs WHERE world_id = ? AND npc_id = ?",
            (world_id, npc_id),
        ).fetchone()
        return self._as_npc(row)

    def list_npcs(self, world_id: str) -> list[dict[str, Any]]:
        self.ensure_world(world_id)
        rows = self.conn.execute(
            """
            SELECT n.npc_id, n.world_id, n.name, n.surname, n.age, n.sex, n.occupation,
                   n.alive, n.name_key,
                   s.position_x, s.position_y, s.position_z, s.direction, s.state_version
            FROM npcs n
            LEFT JOIN npc_state s ON s.npc_id = n.npc_id AND s.world_id = n.world_id
            WHERE n.world_id = ?
            ORDER BY n.created_at
            """,
            (world_id,),
        ).fetchall()
        found = []
        for row in rows:
            item = dict(row)
            item["alive"] = bool(item["alive"])
            found.append(item)
        return found

    def name_keys(self, world_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT name_key FROM npcs WHERE world_id = ?",
            (world_id,),
        ).fetchall()
        return [str(row["name_key"]) for row in rows]

    def create_npc(self, world_id: str, identity: dict[str, Any]) -> dict[str, Any]:
        self.ensure_world(world_id)
        name = str(identity.get("first_name") or "").strip()
        surname = str(identity.get("last_name") or "").strip()
        sex = identity.get("sex")
        age = identity.get("age")
        occupation = str(identity.get("occupation") or "").strip()
        if not _NAME.match(name) or not _NAME.match(surname):
            raise ValueError("nome")
        if sex not in ("male", "female"):
            raise ValueError("sex")
        if isinstance(age, float) and age.is_integer():
            age = int(age)
        if not isinstance(age, int) or age < 18 or age > 80:
            raise ValueError("age")
        if not occupation or len(occupation) > 60:
            raise ValueError("occupation")
        key = normalize_full_name(name, surname)
        if key in self.name_keys(world_id):
            raise ValueError("nome repetido")
        npc_id = str(uuid.uuid4())
        now = utc_now()
        personality = identity.get("personality") if isinstance(identity.get("personality"), dict) else {}
        skills = identity.get("skills") if isinstance(identity.get("skills"), list) else []
        self.conn.execute(
            """
            INSERT INTO npcs(
                npc_id, world_id, name, surname, age, sex, occupation, persona_id,
                alive, created_at, updated_at, description, lore, personality_json,
                speech_style, fears, motivations, skills_json, name_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                npc_id, world_id, name, surname, age, sex, occupation, "generated",
                now, now,
                str(identity.get("description") or "")[:500],
                str(identity.get("lore") or "")[:2000],
                json.dumps(personality, ensure_ascii=False),
                str(identity.get("speech") or "")[:300],
                str(identity.get("fears") or "")[:300],
                str(identity.get("motivations") or "")[:300],
                json.dumps([str(item)[:40] for item in skills[:8]], ensure_ascii=False),
                key,
            ),
        )
        self.conn.commit()
        created = self.get_by_id(world_id, npc_id)
        if not created:
            raise RuntimeError("npc nao gravado")
        return created

    def mark_dead(self, world_id: str) -> dict[str, Any] | None:
        npc = self.get_npc(world_id)
        if not npc:
            return None
        return self.mark_npc_dead(world_id, npc["npc_id"])

    def mark_npc_dead(self, world_id: str, npc_id: str) -> dict[str, Any] | None:
        npc = self.get_by_id(world_id, npc_id)
        if not npc:
            return None
        self.conn.execute(
            "UPDATE npcs SET alive = 0, updated_at = ? WHERE npc_id = ? AND world_id = ?",
            (utc_now(), npc_id, world_id),
        )
        self.conn.commit()
        return self.get_by_id(world_id, npc_id)

    def save_state(self, world_id: str, npc_id: str, state: dict[str, Any]) -> dict[str, Any]:
        npc = self.get_by_id(world_id, npc_id)
        if not npc:
            raise ValueError("npc")
        version = state.get("state_version")
        if isinstance(version, float) and version.is_integer():
            version = int(version)
        if not isinstance(version, int) or version < 1:
            raise ValueError("state_version")
        for key in ("position_x", "position_y", "position_z"):
            if not isinstance(state.get(key), (int, float)):
                raise ValueError(key)
        current = self.load_state(world_id, npc_id)
        if current and version < int(current["state_version"]):
            raise ValueError("revisao antiga")
        if current and version == int(current["state_version"]):
            same = (
                abs(float(current["position_x"]) - float(state["position_x"])) < 0.05
                and abs(float(current["position_y"]) - float(state["position_y"])) < 0.05
                and abs(float(current["position_z"]) - float(state["position_z"])) < 0.01
                and (current.get("direction") or "") == (state.get("direction") or "")
            )
            if same:
                return current
            raise ValueError("revisao divergente")
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO npc_state(
                npc_id, world_id, position_x, position_y, position_z, direction,
                health, current_action, last_saved_at, state_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(npc_id) DO UPDATE SET
                position_x = excluded.position_x,
                position_y = excluded.position_y,
                position_z = excluded.position_z,
                direction = excluded.direction,
                health = excluded.health,
                current_action = excluded.current_action,
                last_saved_at = excluded.last_saved_at,
                state_version = excluded.state_version
            """,
            (
                npc_id,
                world_id,
                float(state["position_x"]),
                float(state["position_y"]),
                float(state["position_z"]),
                state.get("direction"),
                state.get("health"),
                state.get("current_action"),
                now,
                version,
            ),
        )
        self.conn.commit()
        saved = self.load_state(world_id, npc_id)
        if not saved:
            raise RuntimeError("estado nao gravado")
        return saved

    def load_state(self, world_id: str, npc_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT npc_id, world_id, position_x, position_y, position_z, direction,
                   health, current_action, last_saved_at, state_version
            FROM npc_state WHERE npc_id = ? AND world_id = ?
            """,
            (npc_id, world_id),
        ).fetchone()
        return dict(row) if row else None

    def add_message(self, world_id: str, npc_id: str, message: dict[str, Any]) -> bool:
        message_id = message.get("message_id")
        role = message.get("role")
        content = message.get("content")
        if not isinstance(message_id, str) or not message_id:
            raise ValueError("message_id")
        if role not in ("user", "assistant"):
            raise ValueError("role")
        if not isinstance(content, str):
            raise ValueError("content")
        try:
            self.conn.execute(
                """
                INSERT INTO conversations(
                    message_id, world_id, npc_id, player_character_id, role, content, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    world_id,
                    npc_id,
                    message.get("player_character_id"),
                    role,
                    content,
                    utc_now(),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def status(self, world_id: str) -> dict[str, Any]:
        self.ensure_world(world_id)
        npc = self.get_npc(world_id)
        messages = 0
        if npc:
            row = self.conn.execute(
                "SELECT COUNT(*) AS total FROM conversations WHERE world_id = ? AND npc_id = ?",
                (world_id, npc["npc_id"]),
            ).fetchone()
            messages = int(row["total"])
        return {
            "world_id": world_id,
            "schema_version": self.schema_version(),
            "npc_id": npc["npc_id"] if npc else None,
            "alive": npc["alive"] if npc else None,
            "messages": messages,
        }


def handle_persist(store: PersistenceStore, data: dict[str, Any]) -> dict[str, Any]:
    op = data.get("op")
    world_id = data.get("world_id")
    if op not in _OPS:
        return {"ok": False, "error": "op"}
    if validate_world_id(world_id):
        return {"ok": False, "error": "world_id"}
    if data.get("action") is not None:
        return {"ok": False, "error": "action"}
    try:
        if op == "ensure_world":
            result = store.ensure_world(str(world_id))
        elif op == "ensure_npc":
            result = store.ensure_npc(str(world_id))
        elif op == "list_npcs":
            result = {"npcs": store.list_npcs(str(world_id))}
        elif op == "get_npc":
            npc_id = data.get("npc_id")
            if isinstance(npc_id, str) and npc_id:
                result = store.get_by_id(str(world_id), npc_id)
            else:
                result = store.get_npc(str(world_id))
        elif op == "restore_npc":
            npc_id = data.get("npc_id")
            if not isinstance(npc_id, str):
                return {"ok": False, "op": op, "error": "npc_id", "message": "npc_id"}
            npc = store.get_by_id(str(world_id), npc_id)
            result = {"npc": npc, "state": store.load_state(str(world_id), npc_id) if npc else None}
        elif op == "create_npc":
            identity = data.get("identity")
            if not isinstance(identity, dict):
                return {"ok": False, "op": op, "error": "identity", "message": "identity"}
            result = store.create_npc(str(world_id), identity)
        elif op == "mark_npc_dead":
            npc_id = data.get("npc_id")
            if not isinstance(npc_id, str):
                return {"ok": False, "op": op, "error": "npc_id", "message": "npc_id"}
            result = store.mark_npc_dead(str(world_id), npc_id)
        elif op == "status":
            result = store.status(str(world_id))
        elif op in ("save_state", "save_npc_state"):
            state = data.get("state")
            npc_id = data.get("npc_id")
            if not isinstance(state, dict) or not isinstance(npc_id, str):
                return {"ok": False, "op": op, "error": "state", "message": "state"}
            result = store.save_state(str(world_id), npc_id, state)
        elif op == "load_state":
            npc_id = data.get("npc_id")
            if not isinstance(npc_id, str):
                return {"ok": False, "op": op, "error": "npc_id", "message": "npc_id"}
            result = store.load_state(str(world_id), npc_id)
        else:
            return {"ok": False, "error": "op", "message": "op"}
        return {"ok": True, "op": op, "world_id": world_id, "result": result}
    except ValueError as exc:
        return {"ok": False, "op": op, "error": str(exc), "message": str(exc)}
    except sqlite3.Error:
        return {"ok": False, "op": op, "error": "sqlite", "message": "sqlite"}


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
    os.replace(tmp, path)
