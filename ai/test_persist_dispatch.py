#!/usr/bin/env python3
"""O despachante real da ponte, com banco temporario."""

import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import npc_generator
import ollama_service as svc
from npc_generator import generate_identity


WORLD = "Sandbox/2026-10-27_20-00-09"
OLD_LUA_BOOL = re.compile(r'"ok"\s*:\s*(true\|false)')


def _sample() -> dict:
    return {
        "first_name": "Miguel",
        "last_name": "Ferreira",
        "sex": "male",
        "age": 42,
        "occupation": "Carpinteiro",
        "description": "Homem de barba curta.",
        "lore": "Trabalhava com madeira antes do surto e procura sobreviventes.",
        "personality": {"temperament": "calmo", "sociability": "reservado", "courage": "moderada"},
        "speech": "Fala baixo e direto.",
        "skills": ["marceneiro"],
        "fears": "Perder o rasto da familia.",
        "motivations": "Achar um abrigo seguro.",
    }


class DispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / "to_py").mkdir()
        (self.root / "to_lua").mkdir()
        self.old = (svc.ROOT, svc.TO_PY, svc.TO_LUA)
        svc.ROOT = self.root
        svc.TO_PY = self.root / "to_py"
        svc.TO_LUA = self.root / "to_lua"

    def tearDown(self) -> None:
        svc.ROOT, svc.TO_PY, svc.TO_LUA = self.old
        self.directory.cleanup()

    def _dispatch(self, req_id: str, payload: dict, state: object = None) -> dict:
        tmp = svc.TO_PY / f"{req_id}.json.tmp"
        ok = svc.TO_PY / f"{req_id}.ok"
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        ok.write_text(req_id, encoding="utf-8")
        svc.take_request(ok, state)  # type: ignore[arg-type]
        body = (svc.TO_LUA / f"{req_id}.json").read_text(encoding="utf-8")
        self.assertIsNone(OLD_LUA_BOOL.search(body))
        data = json.loads(body)
        self.assertEqual(data["id"], req_id)
        self.assertEqual(data["kind"], "persist_result")
        return data

    def test_ensure_npc_reaches_lua_as_real_boolean(self) -> None:
        data = self._dispatch("persist-ensure-1", {
            "id": "persist-ensure-1",
            "kind": "persist",
            "op": "ensure_npc",
            "world_id": WORLD,
        })
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["name"], "Carlos")
        self.assertTrue(data["result"]["npc_id"])
        again = self._dispatch("persist-list-1", {
            "id": "persist-list-1",
            "kind": "persist",
            "op": "list_npcs",
            "world_id": WORLD,
        })
        self.assertEqual(len(again["result"]["npcs"]), 1)
        self.assertEqual(again["result"]["npcs"][0]["npc_id"], data["result"]["npc_id"])

    def test_create_npc_uses_generator_and_rejects_duplicate_name(self) -> None:
        self._dispatch("persist-ensure-2", {
            "id": "persist-ensure-2",
            "kind": "persist",
            "op": "ensure_npc",
            "world_id": WORLD,
        })
        state = SimpleNamespace(
            online=True,
            client=object(),
            models=["hf.co/PatrickPat/remnants-llm-v5-GGUF:Q4_K_M"],
            world_models={},
        )
        original = npc_generator.generate_identity

        def fake(_excluded: list[str], _complete: object) -> dict:
            return _sample()

        npc_generator.generate_identity = fake
        try:
            created = self._dispatch("persist-create-1", {
                "id": "persist-create-1",
                "kind": "persist",
                "op": "create_npc",
                "world_id": WORLD,
            }, state)
        finally:
            npc_generator.generate_identity = original
        self.assertTrue(created["ok"])
        self.assertNotEqual(created["result"]["name"], "Carlos")
        self.assertNotIn("npc_id", _sample())

        def duplicate(_excluded: list[str], _complete: object) -> dict:
            copied = _sample()
            copied["first_name"] = "Carlos"
            copied["last_name"] = "Aray"
            return copied

        npc_generator.generate_identity = duplicate
        try:
            rejected = self._dispatch("persist-create-2", {
                "id": "persist-create-2",
                "kind": "persist",
                "op": "create_npc",
                "world_id": WORLD,
            }, state)
        finally:
            npc_generator.generate_identity = original
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"], "nome repetido")

    def test_generator_rejects_invalid_model_text(self) -> None:
        with self.assertRaises(ValueError):
            generate_identity([], lambda _prompt, _schema: "nao e json")
        identity = generate_identity(["Carlos Aray"], lambda _prompt, _schema: json.dumps(_sample()))
        self.assertNotIn("npc_id", identity)
        with self.assertRaises(ValueError):
            generate_identity(["miguel ferreira"], lambda _prompt, _schema: json.dumps(_sample()))


if __name__ == "__main__":
    unittest.main()
