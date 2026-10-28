"""Real dispatcher, temporary SQLite and simulated Ollama; never starts the game."""
import copy
import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import decision_handler as dh
import ollama_service as svc
from persistence import PersistenceStore

WORLD = "Sandbox/decision-tests"
MODEL = "selected-model:existing"


def identity(name, temperament):
    return {"first_name": name, "last_name": "Teste", "sex": "male", "age": 30,
            "occupation": "mecanico", "description": "Sobrevivente", "lore": f"Historia de {name}",
            "personality": {"temperament": temperament}, "speech": "Direto", "skills": ["reparos"],
            "fears": "Perigo", "motivations": "Sobreviver"}


@pytest.fixture
def context(tmp_path):
    path = tmp_path / "persistence" / "aray.sqlite"
    store = PersistenceStore(path)
    a = store.create_npc(WORLD, identity("Miguel", "calmo"))
    b = store.create_npc(WORLD, identity("Bruno", "ousado"))
    store.close()
    return SimpleNamespace(root=tmp_path, database=path, a=a["npc_id"], b=b["npc_id"])


def request(npc_id, req_id="decision-1", sequence=1):
    now = dh.now_ms()
    yes = {"known": True, "value": True}
    return {"id": req_id, "kind": "decision_request", "world_id": WORLD, "npc_id": npc_id,
            "session_id": "session-1", "session_started_at_ms": now - 1000,
            "sequence": sequence, "issued_at_ms": now, "expires_at_ms": now + 10000,
            "snapshot": {"uuid": npc_id, "world_id": WORLD, "captured_at_ms": now,
                         "active": True, "alive": yes, "position": {"known": True, "x": .5, "y": .5, "z": 0},
                         "radius": 10, "player": {"known": True},
                         "tiles": [{"x": 1, "y": 0, "z": 0, "solid_floor": yes, "free": yes,
                                    "traversable_candidate": yes}]}}


def decision(action="FOLLOW_PLAYER", parameters=None):
    return {"action": action, "parameters": parameters or {}, "reason": "O jogador esta proximo.", "priority": 2}


class FakeClient:
    def __init__(self, content=None, exception=None):
        self.content = json.dumps(decision()) if content is None else content
        self.exception = exception
        self.calls = []

    def chat(self, model, messages, **kwargs):
        self.calls.append((model, copy.deepcopy(messages), copy.deepcopy(kwargs)))
        if self.exception:
            raise self.exception
        return {"message": {"content": self.content}}


def wait_result(dispatcher, count=1):
    deadline = time.monotonic() + 2
    output = []
    while time.monotonic() < deadline:
        output.extend(dispatcher.poll())
        if len(output) >= count:
            return output
        time.sleep(.005)
    pytest.fail("worker did not produce a result")


def test_valid_decision_model_profile_and_identity(context):
    client = FakeClient()
    data = request(context.a)
    result = dh.decide(data, context.database, client, MODEL)
    assert result["ok"] and result["decision"] == decision()
    assert result["npc_id"] == context.a and result["executable"] is False
    model, messages, options = client.calls[0]
    assert model == MODEL
    assert options["profile"]["temperature"] == 0
    assert options["profile"]["num_predict"] >= 256
    assert options["profile"]["format"] == dh.SCHEMA
    assert 0 < options["timeout"] <= dh.HTTP_TIMEOUT_S
    prompt = json.loads(messages[1]["content"])
    assert prompt["identity"]["personality"] == {"temperament": "calmo"}
    assert prompt["snapshot"]["destination_candidates"][0]["candidate_id"] == "tile:1:0:0"


@pytest.mark.parametrize("raw,code", [
    ("not json", "invalid_json"),
    ('```json\n{}\n```', "invalid_json"),
    (json.dumps(decision("EXECUTE_LUA")), "action"),
    (json.dumps(decision("MOVE_TO", {"candidate_id": "invented"})), "destination"),
    (json.dumps(decision("MOVE_TO", {"x": 999, "y": 999, "z": 0})), "destination"),
    (json.dumps(decision("IDLE", {"code": "os.execute('bad')"})), "parameters"),
    (json.dumps({**decision(), "priority": True}), "priority"),
    (json.dumps({**decision(), "reason": "x" * 241}), "reason"),
    (json.dumps(decision("SAY", {"text": "x" * 301})), "say_text"),
    (json.dumps({**decision(), "uuid": "npc_1"}), "decision_fields"),
    ('{"action":"IDLE","action":"STOP","parameters":{},"reason":"x","priority":0}', "invalid_json"),
    (json.dumps(decision()) + " trailing", "invalid_json"),
    ('{"action":"IDLE","parameters":{},"reason":"x","priority":NaN}', "invalid_json"),
])
def test_invalid_model_output(context, raw, code):
    result = dh.decide(request(context.a), context.database, FakeClient(raw), MODEL)
    assert not result["ok"] and result["error"]["code"] == code
    assert result["decision"]["action"] == "IDLE"


@pytest.mark.parametrize("action", ["MOVE_TO", "WANDER_NEARBY"])
def test_only_existing_verified_destinations(context, action):
    data = request(context.a)
    client = FakeClient(json.dumps(decision(action, {"candidate_id": "tile:1:0:0"})))
    assert dh.decide(data, context.database, client, MODEL)["ok"]
    data["snapshot"]["tiles"][0]["free"] = {"known": False}
    assert dh.decide(data, context.database, client, MODEL)["error"]["code"] == "destination"
    data["snapshot"]["tiles"][0]["free"] = {"known": True, "value": True}
    data["snapshot"]["radius"] = .1
    assert dh.decide(data, context.database, client, MODEL)["error"]["code"] == "destination"


def test_two_personalities_no_history_or_caller_override(context):
    client = FakeClient()
    first = request(context.a)
    first["identity"] = {"name": "INJECTED_PERSONA"}
    first["goal"] = "Esperar"
    assert dh.decide(first, context.database, client, MODEL)["ok"]
    assert dh.decide(request(context.b), context.database, client, MODEL)["ok"]
    prompts = [call[1][1]["content"] for call in client.calls]
    assert "Miguel" in prompts[0] and "calmo" in prompts[0] and "Bruno" not in prompts[0]
    assert "Bruno" in prompts[1] and "ousado" in prompts[1] and "Miguel" not in prompts[1]
    assert all("INJECTED_PERSONA" not in prompt for prompt in prompts)
    assert all(len(call[1]) == 2 for call in client.calls)


@pytest.mark.parametrize("change,code", [
    (lambda d: d.update(npc_id="npc_1"), "npc_id"),
    (lambda d: d["snapshot"].update(uuid="wrong"), "snapshot_identity"),
    (lambda d: d["snapshot"].update(world_id="Sandbox/other"), "snapshot_identity"),
    (lambda d: d["snapshot"].update(active=False), "inactive_snapshot"),
    (lambda d: d.update(sequence=True), "sequence"),
    (lambda d: d.update(expires_at_ms=d["issued_at_ms"] - 1), "ttl"),
    (lambda d: d.update(set_model="another"), "unexpected_command"),
    (lambda d: d.update(goal="x" * 501), "goal"),
    (lambda d: d["snapshot"]["position"].update(x=10**400), "position"),
])
def test_request_validation(context, change, code):
    data = request(context.a)
    change(data)
    client = FakeClient()
    result = dh.decide(data, context.database, client, MODEL)
    assert result["error"]["code"] == code and not client.calls


def test_nonexistent_uuid_wrong_world_and_dead(context):
    import uuid
    data = request(str(uuid.uuid4()))
    assert dh.decide(data, context.database, FakeClient(), MODEL)["error"]["code"] == "npc_not_found"
    data = request(context.a)
    data["world_id"] = data["snapshot"]["world_id"] = "Sandbox/other"
    assert dh.decide(data, context.database, FakeClient(), MODEL)["error"]["code"] == "npc_not_found"
    store = PersistenceStore(context.database)
    store.mark_npc_dead(WORLD, context.a)
    store.close()
    assert dh.decide(request(context.a), context.database, FakeClient(), MODEL)["error"]["code"] == "npc_dead"


def test_expired_before_and_after_inference(context):
    data = request(context.a)
    client = FakeClient()
    assert dh.decide(data, context.database, client, MODEL, lambda: data["expires_at_ms"])["error"]["code"] == "expired"
    assert not client.calls

    class Late(FakeClient):
        def chat(self, *args, **kwargs):
            clock[0] = data["expires_at_ms"]
            return super().chat(*args, **kwargs)

    clock = [data["issued_at_ms"]]
    assert dh.decide(data, context.database, Late(), MODEL, lambda: clock[0])["error"]["code"] == "expired"


def test_timeout_and_offline(context):
    result = dh.decide(request(context.a), context.database, FakeClient(exception=TimeoutError()), MODEL)
    assert result["error"]["code"] == "ollama_timeout"
    client = FakeClient()
    assert dh.decide(request(context.a), context.database, client, None)["error"]["code"] == "model_unavailable"
    assert not client.calls
    class Offline:
        def chat(self, *args, **kwargs):
            return None
    assert not dh.decide(request(context.a), context.database, Offline(), MODEL)["ok"]


def test_say_is_inert_data(context, monkeypatch):
    monkeypatch.setattr(os, "system", lambda *a: pytest.fail("code executed"))
    text = "os.execute('bad'); __import__('os').system('bad')"
    result = dh.decide(request(context.a), context.database,
                       FakeClient(json.dumps(decision("SAY", {"text": text}))), MODEL)
    assert result["ok"] and result["decision"]["parameters"]["text"] == text
    assert result["executable"] is False


def test_duplicate_sequence_session_and_mutation(context):
    client = FakeClient()
    dispatcher = dh.DecisionDispatcher(context.database, lambda: client)
    try:
        data = request(context.a)
        assert dispatcher.submit(data, MODEL) is None
        data["snapshot"]["uuid"] = "mutated"
        assert wait_result(dispatcher)[0]["ok"]
        original = request(context.a)
        assert dispatcher.submit(original, MODEL) is None
        assert len(client.calls) == 1
        stale = request(context.a, "stale", 1)
        stale["session_started_at_ms"] = original["session_started_at_ms"]
        assert dispatcher.submit(stale, MODEL)["error"]["code"] == "stale_sequence"
        old_session = request(context.a, "old-session", 5)
        old_session["session_id"] = "old"
        old_session["session_started_at_ms"] = original["session_started_at_ms"] - 100
        assert dispatcher.submit(old_session, MODEL)["error"]["code"] == "stale_session"
    finally:
        dispatcher.close()


class Blocked(FakeClient):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def chat(self, *args, **kwargs):
        self.entered.set()
        assert self.release.wait(2), "test failed to release fake Ollama"
        return super().chat(*args, **kwargs)


def test_queue_bounded_expiry_and_late_completion(context):
    client = Blocked()
    data = request(context.a)
    clock = [data["issued_at_ms"]]
    dispatcher = dh.DecisionDispatcher(context.database, lambda: client, capacity=1, clock=lambda: clock[0])
    try:
        dispatcher.submit(data, MODEL)
        assert client.entered.wait(1)
        assert dispatcher.submit(request(context.b, "full"), MODEL)["error"]["code"] == "queue_full"
        clock[0] = data["expires_at_ms"]
        assert dispatcher.poll()[0]["error"]["code"] == "expired"
        client.release.set()
    finally:
        client.release.set()
        dispatcher.close()
    assert dispatcher.poll() == []


def test_new_sequence_supersedes_pending_result(context):
    client = Blocked()
    dispatcher = dh.DecisionDispatcher(context.database, lambda: client)
    try:
        first = request(context.a)
        dispatcher.submit(first, MODEL)
        assert client.entered.wait(1)
        newer = copy.deepcopy(first)
        newer.update(id="newer", sequence=2)
        dispatcher.submit(newer, MODEL)
        assert dispatcher.poll()[0]["error"]["code"] == "superseded"
        client.release.set()
        result = wait_result(dispatcher)
        assert len(result) == 1 and result[0]["id"] == "newer" and result[0]["ok"]
    finally:
        client.release.set()
        dispatcher.close()


def mailbox(context, monkeypatch, client):
    monkeypatch.setattr(svc, "ROOT", context.root)
    monkeypatch.setattr(svc, "TO_PY", context.root / "to_py")
    monkeypatch.setattr(svc, "TO_LUA", context.root / "to_lua")
    svc.TO_PY.mkdir()
    svc.TO_LUA.mkdir()
    dispatcher = dh.DecisionDispatcher(context.database, lambda: client)
    state = SimpleNamespace(online=True, models=[MODEL], world_models={WORLD: MODEL}, version="test",
                            client=FakeClient(), decision_dispatcher=dispatcher, update=lambda **kw: None)
    def send(data):
        req_id = data["id"]
        (svc.TO_PY / f"{req_id}.json.tmp").write_text(json.dumps(data), encoding="utf-8")
        ok = svc.TO_PY / f"{req_id}.ok"
        ok.write_text(req_id, encoding="utf-8")
        svc.take_request(ok, state)
    return state, send


def test_mailbox_persist_ping_and_chat_during_slow_decision(context, monkeypatch):
    client = Blocked()
    state, send = mailbox(context, monkeypatch, client)
    try:
        send(request(context.a))
        assert client.entered.wait(1)
        start = time.monotonic()
        send({"id": "persist-1", "kind": "persist", "world_id": WORLD, "op": "save_npc_state",
              "npc_id": context.a, "state": {"position_x": 2.5, "position_y": .5, "position_z": 0,
                                               "direction": "N", "state_version": 1}})
        send({"id": "ping-1", "kind": "ping", "world_id": WORLD})
        send({"id": "chat-1", "kind": "chat_request", "world_id": WORLD, "npc_id": context.b,
              "message": "Bruno: Ola", "context": {},
              "routing":{"schema_version":1,"world_id":WORLD,"recipients":[context.b],"event_id":"speech-legacy","captured_at_ms":int(time.time()*1000)}})
        assert time.monotonic() - start < 1
        for req_id, flag in (("persist-1", "ok"), ("ping-1", "ok"), ("chat-1", "success")):
            assert json.loads((svc.TO_LUA / f"{req_id}.json").read_text(encoding="utf-8"))[flag]
        assert not (svc.TO_LUA / "decision-1.json").exists()
        assert state.world_models == {WORLD: MODEL}
        client.release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not (svc.TO_LUA / "decision-1.json").exists():
            svc.poll_decisions(state)
            time.sleep(.005)
        output = svc.TO_LUA / "decision-1.json"
        result = json.loads(output.read_text(encoding="utf-8"))
        assert result["ok"] and client.calls[0][0] == MODEL
        original = output.read_bytes()
        send(request(context.a))
        assert output.read_bytes() == original and len(client.calls) == 1
    finally:
        client.release.set()
        state.decision_dispatcher.close()


def test_mailbox_rejects_set_model_and_id_mismatch(context, monkeypatch):
    state, send = mailbox(context, monkeypatch, FakeClient())
    try:
        data = request(context.a)
        data["set_model"] = "not-allowed"
        send(data)
        result = json.loads((svc.TO_LUA / "decision-1.json").read_text())
        assert result["error"]["code"] == "unexpected_command"
        assert state.world_models == {WORLD: MODEL}
        data = request(context.a, "embedded-id")
        path = svc.TO_PY / "filename-id.json.tmp"
        path.write_text(json.dumps(data), encoding="utf-8")
        ok = svc.TO_PY / "filename-id.ok"
        ok.write_text("filename-id")
        svc.take_request(ok, state)
        result = json.loads((svc.TO_LUA / "filename-id.json").read_text())
        assert result["id"] == "filename-id" and result["error"]["code"] == "request_id_mismatch"
    finally:
        state.decision_dispatcher.close()


def test_database_read_only_and_worker_thread_ownership(context, monkeypatch):
    original = dh.read_identity
    thread_ids = []
    def observed(*args):
        thread_ids.append(threading.get_ident())
        return original(*args)
    monkeypatch.setattr(dh, "read_identity", observed)
    before = context.database.read_bytes()
    factories = []
    def factory():
        factories.append(threading.get_ident())
        return FakeClient()
    dispatcher = dh.DecisionDispatcher(context.database, factory)
    try:
        dispatcher.submit(request(context.a), MODEL)
        assert wait_result(dispatcher)[0]["ok"]
    finally:
        dispatcher.close()
    assert factories and all(item != threading.get_ident() for item in factories + thread_ids)
    assert context.database.read_bytes() == before
    missing = context.root / "missing.sqlite"
    assert dh.decide(request(context.a), missing, FakeClient(), MODEL)["error"]["code"] == "database_unavailable"
    assert not missing.exists()


def test_death_during_inference(context):
    class Dies(FakeClient):
        def chat(self, *args, **kwargs):
            store = PersistenceStore(context.database)
            store.mark_npc_dead(WORLD, context.a)
            store.close()
            return super().chat(*args, **kwargs)
    result = dh.decide(request(context.a), context.database, Dies(), MODEL)
    assert result["error"]["code"] == "npc_dead" and result["decision"]["action"] == "IDLE"


def test_new_session_supersedes_old_and_rejects_its_replay(context):
    dispatcher = dh.DecisionDispatcher(context.database, FakeClient)
    try:
        data = request(context.a)
        dispatcher.submit(data, MODEL)
        assert wait_result(dispatcher)[0]["ok"]
        newer = copy.deepcopy(data)
        newer.update(id="next-session", session_id="session-2",
                     session_started_at_ms=data["session_started_at_ms"] + 1)
        dispatcher.submit(newer, MODEL)
        assert wait_result(dispatcher)[0]["session_id"] == "session-2"
        data.update(id="replayed-session", sequence=10)
        assert dispatcher.submit(data, MODEL)["error"]["code"] == "stale_session"
    finally:
        dispatcher.close()


def test_untrusted_metadata_returns_serializable_errors(context):
    dispatcher = dh.DecisionDispatcher(context.database, FakeClient)
    try:
        data = request(context.a)
        data["id"] = []
        result = dispatcher.submit(data, MODEL)
        assert result["error"]["code"] == "id"
        json.dumps(result, allow_nan=False)
        data = request(context.a)
        data["sequence"] = float("nan")
        result = dispatcher.submit(data, MODEL)
        assert result["error"]["code"] == "sequence"
        json.dumps(result, allow_nan=False)
    finally:
        dispatcher.close()


def test_existing_http_client_payload_and_timeout(monkeypatch):
    recorded = []
    class Session:
        def post(self, url, **kwargs):
            recorded.append((url, kwargs))
            return SimpleNamespace(status_code=200, json=lambda: {"message": {"content": json.dumps(decision())}})
    monkeypatch.setattr(svc, "requests", SimpleNamespace(Session=Session))
    client = svc.OllamaClient("http://localhost:11434")
    client.chat(MODEL, [{"role": "user", "content": "data"}], timeout=3,
                profile={**dh.PROFILE, "format": dh.SCHEMA})
    url, payload = recorded[0]
    assert url.endswith("/api/chat") and payload["timeout"] == 3
    assert payload["json"]["model"] == MODEL and payload["json"]["format"] == dh.SCHEMA
    assert payload["json"]["options"]["num_predict"] == 384
    assert payload["json"]["options"]["temperature"] == 0


def test_batch_priority_preserves_control_and_chat(context, monkeypatch):
    incoming = context.root / "to_py"
    incoming.mkdir()
    monkeypatch.setattr(svc, "TO_PY", incoming)
    calls = []
    for req_id, kind in (("a-decision", "decision_request"), ("b-chat", "chat_request"),
                         ("c-ping", "ping"), ("d-save", "persist")):
        (incoming / f"{req_id}.json.tmp").write_text(json.dumps({"kind": kind}))
        (incoming / f"{req_id}.ok").write_text(req_id)
    monkeypatch.setattr(svc, "take_request", lambda path, state: calls.append(path.stem))
    svc.process_mailbox_once(SimpleNamespace())
    assert calls == ["c-ping", "d-save", "b-chat", "a-decision"]
