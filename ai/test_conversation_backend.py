"""Read-only temporary SQLite identities + mock Ollama + real service dispatch."""
import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_decision_handler import context, WORLD, MODEL
from conversation_handler import ChatDispatcher, factual_reply, validate
from appearance_store import handle
import ollama_service as svc


def request(npc_id, sequence=1):
    now=int(time.time()*1000)
    return {"kind":"chat_request","protocol_version":2,"id":f"chat-{sequence}","world_id":WORLD,"npc_id":npc_id,
            "session_id":"session-A","session_started_at_ms":now-1000,"sequence":sequence,
            "issued_at_ms":now,"expires_at_ms":now+20000,"message":"NPC: Olá",
            "routing":{"schema_version":1,"world_id":WORLD,"recipients":[npc_id],"event_id":f"speech-{sequence}","captured_at_ms":now},
            "context":{"schema_version":1,"uuid":npc_id,"world_id":WORLD,"captured_at_ms":now,
                       "inventory":{"uuid":npc_id,"world_id":WORLD,"complete":True,"items":[]},
                       "zombies":[],"doors":[],"obstacles":[],"visibility":{"known":True,"complete":True}}}


def wait(dispatcher):
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        responses=dispatcher.poll()
        if responses:return responses
        time.sleep(.005)
    pytest.fail("mock worker did not finish")


class Client:
    def __init__(self):self.calls=[]
    def chat(self,model,messages,timeout,profile):
        self.calls.append((model,messages,timeout))
        return {"message":{"content":"Resposta verbal; me siga"}}


def test_two_npcs_sessions_personas_and_verbal_only(context):
    client=Client(); d=ChatDispatcher(context.database,lambda:client)
    try:
        a=request(context.a); d.submit(a,MODEL); ra=wait(d)[0]
        b=request(context.b,2); d.submit(b,MODEL); rb=wait(d)[0]
        assert ra["success"] and rb["success"] and ra["npc_id"]!=rb["npc_id"]
        assert ra["verbal_only"] and not ra["executable"] and "action" not in ra
        assert "Miguel" in client.calls[0][1][0]["content"] and "Bruno" not in client.calls[0][1][0]["content"]
        assert "Bruno" in client.calls[1][1][0]["content"] and "Miguel" not in client.calls[1][1][0]["content"]
        assert all(call[0]==MODEL and call[2]<=15 for call in client.calls)
        assert d.submit(a,MODEL) is None and not d.jobs
    finally:d.close()


def test_inventory_context_answers_without_inference_or_unobserved_items(context):
    client=Client(); d=ChatDispatcher(context.database,lambda:client)
    try:
        a=request(context.a); a["message"]="NPC: O que tem no inventário?"
        a["context"]["inventory"]["items"]=[{"full_type":"Base.Nails","quantity":{"known":True,"value":3}}]
        d.submit(a,None); result=wait(d)[0]
        assert result["success"] and "Base.Nails x 3" in result["reply"] and not client.calls
        assert "arma" not in result["reply"].lower()
        a=request(context.a,2); a["message"]="NPC: quais itens?"; a["context"]["inventory"]["complete"]=False
        d.submit(a,None); assert "confirmar" in wait(d)[0]["reply"]
    finally:d.close()


@pytest.mark.parametrize("change", ["uuid","world","expired","old_context","inventory_uuid","extra_large"])
def test_malformed_request_cannot_access_another_npc(context,change):
    r=request(context.a); client=Client(); d=ChatDispatcher(context.database,lambda:client)
    if change=="uuid":r["npc_id"]="npc_1"
    elif change=="world":r["context"]["world_id"]="other"
    elif change=="expired":r["expires_at_ms"]=r["issued_at_ms"]
    elif change=="old_context":r["context"]["captured_at_ms"]-=1501
    elif change=="inventory_uuid":r["context"]["inventory"]["uuid"]=context.b
    else:r["context"]["payload"]="X"*25000
    try:
        result=d.submit(r,MODEL); assert result and not result["success"] and not client.calls
    finally:d.close()


def test_stale_sequence_new_session_and_late_response(context):
    import threading
    entered=threading.Event(); release=threading.Event()
    class Slow(Client):
        def chat(self,*args,**kw):entered.set(); release.wait(2); return super().chat(*args,**kw)
    client=Slow(); d=ChatDispatcher(context.database,lambda:client)
    try:
        a=request(context.a); d.submit(a,MODEL); assert entered.wait(1)
        newer=copy.deepcopy(a); newer.update(id="new-session",session_id="session-B",session_started_at_ms=a["session_started_at_ms"]+1)
        d.submit(newer,MODEL)
        old=copy.deepcopy(a); old["id"]="old-sequence"; assert not d.submit(old,MODEL)["success"]
        release.set(); result=wait(d)
        assert all(r["session_id"]=="session-B" for r in result)
    finally:release.set(); d.close()


def test_real_mailbox_persist_ping_responsive_while_chat_is_slow(context,monkeypatch):
    import threading
    entered=threading.Event(); release=threading.Event()
    class Slow(Client):
        def chat(self,*args,**kw):entered.set(); release.wait(2); return super().chat(*args,**kw)
    incoming=context.root/"to_py"; outgoing=context.root/"to_lua"; incoming.mkdir(); outgoing.mkdir()
    monkeypatch.setattr(svc,"ROOT",context.root); monkeypatch.setattr(svc,"TO_PY",incoming); monkeypatch.setattr(svc,"TO_LUA",outgoing)
    client=Slow(); state=SimpleNamespace(client=client,world_models={WORLD:MODEL},online=False,models=[],config={})
    def send(r):
        (incoming/(r["id"]+".json.tmp")).write_text(json.dumps(r),encoding="utf-8")
        (incoming/(r["id"]+".ok")).write_text(r["id"])
        svc.process_mailbox_once(state)
    try:
        r=request(context.a); send(r); assert entered.wait(1)
        start=time.monotonic()
        send({"kind":"persist","id":"save-chat-slow","world_id":WORLD,"op":"save_npc_state","npc_id":context.a,
              "state":{"position_x":2.5,"position_y":.5,"position_z":0,"direction":"N","state_version":1}})
        assert time.monotonic()-start<1 and json.loads((outgoing/"save-chat-slow.json").read_text())["ok"]
        release.set()
        deadline=time.monotonic()+2
        while not (outgoing/(r["id"]+".json")).exists() and time.monotonic()<deadline:
            svc.process_mailbox_once(state); time.sleep(.005)
        response=json.loads((outgoing/(r["id"]+".json")).read_text())
        assert response["success"] and response["session_id"]==r["session_id"]
        assert client.calls[0][0]==MODEL and state.world_models=={WORLD:MODEL}
    finally:
        release.set()
        if getattr(state,"conversation_dispatcher",None):state.conversation_dispatcher.close()


def test_offline_diagnostic_logs_only_transition_and_specific_reason(monkeypatch,tmp_path,capsys):
    class Offline:
        last_error="ConnectionError"
        def get_version(self):return None
    monkeypatch.setattr(svc,"ROOT",tmp_path)
    s=svc.OllamaState(Offline(),{})
    s.update(force=True); s.update(force=True)
    output=capsys.readouterr().out
    assert output.count("event=ollama_offline")==1 and "ConnectionError" in output


def test_visibility_unknown_is_not_reported_as_no_zombies():
    assert "confirmar" in factual_reply("Há zumbis?",{"visibility":{"known":False}})
    assert "confirmação" in factual_reply("Existem portas?",{"visibility":{"known":False}})


def visual_request(world=WORLD,npc_id="33333333-3333-4333-8333-333333333333"):
    return {"kind":"appearance_request","id":"visual-1","op":"create","world_id":world,"npc_id":npc_id,
            "visual":{"schema_version":1,"female":False,"human":"version=2;hairModel=Short;beardModel=Full;",
                      "clothes":["version=1;type=Base.Tshirt;tint=0.2,0.3,0.4;"]}}


def test_visual_sidecar_immutable_no_database_or_save_changes(tmp_path):
    db=tmp_path/"persistence"/"aray.sqlite"; db.parent.mkdir(); db.write_bytes(b"do not modify")
    r=visual_request(); first=handle(tmp_path,r); assert first["ok"] and first["found"]
    assert handle(tmp_path,r)["ok"]
    changed=copy.deepcopy(r); changed["visual"]["human"]="version=2;hairModel=Other;"
    assert handle(tmp_path,changed)["error"]=="appearance_conflict_migration_required"
    read=handle(tmp_path,{**r,"op":"get"})
    assert read["visual"]==first["visual"] and db.read_bytes()==b"do not modify"
    other=visual_request("Sandbox/other"); assert handle(tmp_path,other)["ok"]
    assert len(list((tmp_path/"appearance").rglob("*.json")))==2


@pytest.mark.parametrize("change", ["uuid","world","schema","clothes","human","budget"])
def test_visual_invalid_record_never_overwrites(tmp_path,change):
    r=visual_request()
    if change=="uuid":r["npc_id"]="npc_1"
    elif change=="world":r["world_id"]="../bad"
    elif change=="schema":r["visual"]["schema_version"]=9
    elif change=="clothes":r["visual"]["clothes"]=["arbitrary"]
    elif change=="human":r["visual"]["human"]="arbitrary"
    else:r["visual"]["clothes"]=["version="+"X"*4000]*32
    assert not handle(tmp_path,r)["ok"] and not list(tmp_path.rglob("*.json"))
