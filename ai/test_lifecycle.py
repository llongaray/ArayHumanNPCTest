#!/usr/bin/env python3
"""Fase 3B.2 sem o jogo e sem o banco real."""

import tempfile
import unittest
from pathlib import Path

from lifecycle import decide, manual_spawn_allowed
from persistence import PersistenceStore


WORLD = "Sandbox/2026-10-27_20-00-09"


class LifecycleTests(unittest.TestCase):
    def test_first_world_creates_once(self) -> None:
        step = decide({"phase": "WAITING_WORLD", "has_world": True})
        self.assertEqual(step["phase"], "WAITING_PLAYER")
        step = decide({"phase": "WAITING_PLAYER", "player_alive": True})
        self.assertEqual(step["phase"], "WAITING_BRIDGE")
        step = decide({"phase": "WAITING_BRIDGE", "delay_elapsed": True, "bridge_ready": True})
        self.assertEqual(step["send"], "list_npcs")
        step = decide({
            "phase": "LOADING_PERSISTENCE",
            "result": {"ok": True, "op": "list_npcs", "npcs": []},
        })
        self.assertEqual(step["phase"], "ACTIVE")
        self.assertFalse(step["spawn"])

    def test_second_load_restores_same_uuid_and_revision(self) -> None:
        step = decide({
            "phase": "LOADING_PERSISTENCE",
            "uuid": "uuid-1",
            "result": {
                "ok": True, "op": "load_state", "position_x": 3397.5,
                "position_y": 10978.25, "position_z": 0, "direction": "S",
                "state_version": 4,
            },
        })
        self.assertEqual(step["phase"], "VALIDATING_STATE")
        self.assertEqual(step["revision"], 4)
        self.assertEqual(step["direction"], "S")
        step = decide({"phase": "VALIDATING_STATE", "coords": {"x": 3397.5, "y": 10978.25, "z": 0}})
        self.assertEqual(step["phase"], "WAITING_SQUARE")
        step = decide({"phase": "WAITING_SQUARE", "square": "pronto"})
        self.assertEqual(step["mode"], "restore")

    def test_unloaded_square_keeps_saved_position(self) -> None:
        waiting = decide({"phase": "WAITING_SQUARE", "square": "nao carregado"})
        self.assertEqual(waiting["phase"], "WAITING_SQUARE")
        failed = decide({"phase": "WAITING_SQUARE", "square": "nao carregado", "square_timeout": True})
        self.assertTrue(failed["keep_saved"])
        later = decide({"phase": "RESTORE_FAILED", "square": "pronto"})
        self.assertEqual(later["phase"], "WAITING_SQUARE")

    def test_duplicate_response_player_swap_and_dead(self) -> None:
        duplicate = decide({
            "phase": "LOADING_PERSISTENCE",
            "result": {"ok": True, "op": "ensure_npc", "duplicate": True},
        })
        self.assertTrue(duplicate["ignore"])
        swapped = decide({"phase": "ACTIVE", "player_changed": True, "uuid": "uuid-1"})
        self.assertTrue(swapped["keep_uuid"])
        dead = decide({
            "phase": "LOADING_PERSISTENCE",
            "result": {"ok": True, "op": "ensure_npc", "alive": False, "npc_id": "uuid-1"},
        })
        self.assertEqual(dead["phase"], "NPC_DEAD")
        self.assertEqual(manual_spawn_allowed("NPC_DEAD", False), "morto")
        self.assertEqual(manual_spawn_allowed("ACTIVE", True), "existe")
        self.assertEqual(manual_spawn_allowed("LOADING_PERSISTENCE", False), "em_andamento")

    def test_save_skips_unchanged_and_orders_revision(self) -> None:
        same = decide({"phase": "ACTIVE", "save_requested": True, "position_changed": False, "confirmed_revision": 4})
        self.assertTrue(same["skip_save"])
        changed = decide({"phase": "ACTIVE", "save_requested": True, "position_changed": True, "confirmed_revision": 4})
        self.assertEqual(changed["revision"], 5)
        unavailable = decide({"phase": "LOADING_PERSISTENCE", "timed_out": True, "tries": 3, "max_tries": 3})
        self.assertEqual(unavailable["phase"], "PERSISTENCE_UNAVAILABLE")

    def test_database_revision_survives_reopen(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "aray.sqlite"
        store = PersistenceStore(path)
        npc = store.ensure_npc(WORLD)
        store.save_state(WORLD, npc["npc_id"], {
            "position_x": 12.25, "position_y": 8.5, "position_z": 0,
            "direction": "E", "state_version": 3,
        })
        again = store.save_state(WORLD, npc["npc_id"], {
            "position_x": 12.25, "position_y": 8.5, "position_z": 0,
            "direction": "E", "state_version": 3,
        })
        self.assertEqual(again["position_x"], 12.25)
        store.close()
        reopened = PersistenceStore(path)
        self.addCleanup(reopened.close)
        loaded = reopened.load_state(WORLD, npc["npc_id"])
        assert loaded is not None
        self.assertEqual(loaded["state_version"], 3)
        self.assertEqual(loaded["direction"], "E")
        other = reopened.ensure_npc("Apocalypse/outro")
        self.assertNotEqual(other["npc_id"], npc["npc_id"])
        with self.assertRaises(ValueError):
            reopened.save_state(WORLD, npc["npc_id"], {
                "position_x": 1, "position_y": 2, "position_z": 0,
                "direction": "N", "state_version": 3,
            })


if __name__ == "__main__":
    unittest.main()
