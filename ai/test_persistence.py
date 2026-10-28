#!/usr/bin/env python3
"""Fase 3B.1: banco temporario, sem o SQLite do jogador."""

import tempfile
import unittest
from pathlib import Path

from persistence import PersistenceStore, handle_persist, validate_world_id


WORLD_A = "Sandbox/2026-10-27_20-00-09"
WORLD_B = "Apocalypse/outro-mundo"


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.store = PersistenceStore(Path(self.directory.name) / "aray.sqlite")

    def tearDown(self) -> None:
        self.store.close()
        self.directory.cleanup()

    def test_schema_and_world(self) -> None:
        self.assertEqual(self.store.schema_version(), 2)
        first = self.store.ensure_world(WORLD_A)
        again = self.store.ensure_world(WORLD_A)
        self.assertEqual(first["created_at"], again["created_at"])
        self.assertIsNone(validate_world_id(WORLD_A))

    def test_carlos_uuid_is_stable_and_isolated(self) -> None:
        carlos_a = self.store.ensure_npc(WORLD_A)
        again = self.store.ensure_npc(WORLD_A)
        carlos_b = self.store.ensure_npc(WORLD_B)
        self.assertEqual(carlos_a["npc_id"], again["npc_id"])
        self.assertNotEqual(carlos_a["npc_id"], carlos_b["npc_id"])
        self.assertEqual(carlos_a["name"], "Carlos")
        self.assertEqual(carlos_a["surname"], "Aray")
        self.assertEqual(carlos_a["age"], 35)
        self.assertEqual(carlos_a["sex"], "male")
        self.assertTrue(carlos_a["alive"])

    def test_state_revision_and_restore(self) -> None:
        npc = self.store.ensure_npc(WORLD_A)
        saved = self.store.save_state(WORLD_A, npc["npc_id"], {
            "position_x": 10.5, "position_y": 20.5, "position_z": 0,
            "direction": "N", "health": 1, "current_action": "parado",
            "state_version": 2,
        })
        loaded = self.store.load_state(WORLD_A, npc["npc_id"])
        self.assertEqual(loaded["position_x"], 10.5)
        self.assertEqual(saved["state_version"], 2)
        with self.assertRaises(ValueError):
            self.store.save_state(WORLD_A, npc["npc_id"], {
                "position_x": 1, "position_y": 1, "position_z": 0, "state_version": 1,
            })
        kept = self.store.load_state(WORLD_A, npc["npc_id"])
        self.assertEqual(kept["position_x"], 10.5)

    def test_dead_npc_is_not_replaced(self) -> None:
        original = self.store.ensure_npc(WORLD_A)
        dead = self.store.mark_dead(WORLD_A)
        assert dead is not None
        self.assertFalse(dead["alive"])
        again = self.store.ensure_npc(WORLD_A)
        self.assertEqual(again["npc_id"], original["npc_id"])
        self.assertFalse(again["alive"])

    def test_duplicate_message_and_bad_world(self) -> None:
        npc = self.store.ensure_npc(WORLD_A)
        message = {"message_id": "m1", "role": "user", "content": "Olá", "player_character_id": "survivor-31"}
        self.assertTrue(self.store.add_message(WORLD_A, npc["npc_id"], message))
        self.assertFalse(self.store.add_message(WORLD_A, npc["npc_id"], message))
        self.assertEqual(validate_world_id("../segredo"), "world_id")
        rejected = handle_persist(self.store, {"op": "ensure_npc", "world_id": "../segredo"})
        self.assertFalse(rejected["ok"])
        malformed = handle_persist(self.store, {"op": "salvar", "world_id": WORLD_A})
        self.assertEqual(malformed["error"], "op")

    def test_reopen_keeps_schema(self) -> None:
        path = self.store.path
        self.store.ensure_npc(WORLD_A)
        self.store.close()
        reopened = PersistenceStore(path)
        try:
            self.assertEqual(reopened.schema_version(), 2)
            self.assertEqual(reopened.get_npc(WORLD_A)["name"], "Carlos")
        finally:
            reopened.close()

    def test_v1_carlos_survives_and_names_stay_unique(self) -> None:
        import sqlite3
        from persistence import _apply_v1

        path = Path(self.directory.name) / "legacy.sqlite"
        conn = sqlite3.connect(path)
        _apply_v1(conn)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (1, 't')")
        conn.execute(
            "INSERT INTO worlds(world_id, created_at, last_loaded_at, schema_version) VALUES (?, 't', 't', 1)",
            (WORLD_A,),
        )
        carlos_id = "11111111-1111-1111-1111-111111111111"
        conn.execute(
            """
            INSERT INTO npcs(
                npc_id, world_id, name, surname, age, sex, occupation,
                persona_id, alive, created_at, updated_at
            ) VALUES (?, ?, 'Carlos', 'Aray', 35, 'male', 'mecanico', 'persona_default', 1, 't', 't')
            """,
            (carlos_id, WORLD_A),
        )
        conn.commit()
        conn.close()
        store = PersistenceStore(path)
        try:
            self.assertEqual(store.schema_version(), 2)
            self.assertEqual(store.get_npc(WORLD_A)["npc_id"], carlos_id)
            created = store.create_npc(WORLD_A, {
                "first_name": "Miguel", "last_name": "Ferreira", "sex": "male", "age": 42,
                "occupation": "Carpinteiro", "description": "Barba curta.",
                "lore": "Trabalhava com madeira antes do surto.",
                "personality": {"temperament": "calmo", "sociability": "reservado", "courage": "moderada"},
                "speech": "Fala baixo.", "skills": ["marceneiro"], "fears": "Perder a familia.",
                "motivations": "Achar sobreviventes.",
            })
            self.assertNotEqual(created["npc_id"], carlos_id)
            with self.assertRaises(ValueError):
                store.create_npc(WORLD_A, {
                    "first_name": "carlos", "last_name": " Aray", "sex": "male", "age": 30,
                    "occupation": "Outra", "description": "x", "lore": "y",
                    "personality": {}, "speech": "z", "skills": [], "fears": "a", "motivations": "b",
                })
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
