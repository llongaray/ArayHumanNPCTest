"""3C.4E.3 regressions: production Lua, native APIs/mailbox simulated only."""
import json

import pytest

from test_real_integration_fixes import integrated, build, agent, inventory, observer, nav, physical, safety, lua
from test_executor import CLIENT
from test_conversation_backend import request, context, Client, wait, MODEL
from conversation_handler import validate, wire_bytes, ChatDispatcher
from chat_handler import ChatHistory


def test_utf8_context_23800_bytes_uses_same_wire_budget():
    r = request("11111111-1111-4111-8111-111111111111")
    r["context"]["observed_text"] = "ç" * 11600
    assert 23000 < wire_bytes(r["context"]) < 24000
    assert len(json.dumps(r["context"]).encode()) > 24000  # Previous mismatch.
    validate(r, r["issued_at_ms"])


def test_protocol_overhead_still_rejected():
    r = request("11111111-1111-4111-8111-111111111111")
    r["context"]["observed_text"] = "x" * 23000
    r["untrusted_extra"] = "x" * 10000
    with pytest.raises(ValueError, match="context_budget"):
        validate(r, r["issued_at_ms"])


def test_history_byte_budget_keeps_latest_turn_and_question(context):
    client = Client()
    d = ChatDispatcher(context.database, lambda: client)
    r = request(context.a)
    history = ChatHistory()
    for label in ("older", "middle", "newest"):
        history.add_user(label + "ç" * 4500)
        history.add_assistant(label + " resposta " + "ç" * 4500)
    d.histories[(r["world_id"], r["npc_id"], r["session_id"])] = history
    try:
        d.submit(r, MODEL)
        assert wait(d)[0]["success"]
        messages = client.calls[0][1]
        assert wire_bytes(messages) <= 32768
        assert messages[-1] == {"role": "user", "content": r["message"]}
        assert any(m["content"].startswith("newest") for m in messages)
        assert not any(m["content"].startswith("older") for m in messages)
        assert messages[1]["role"] == "user" and messages[2]["role"] == "assistant"
    finally:
        d.close()


def test_extensive_perception_and_inventory_simple_question(integrated):
    integrated.execute('''
        for i=1,128 do
            local item=newItem('Item'..i..string.rep('ç',120),roster[uuidA].inv)
            item.getCount=function() return 1 end
        end
        local ok,rid=sendAddressed('Olá, quem é você?',uuidA)
        assert(ok,rid)
        local req=requestFor(rid)
        assert(req.npc_id==uuidA and req.world_id==C.world())
        assert(#J.encode(req.context)<=12000 and #files['ArayHumanNPCTest/to_py/'..rid..'.json.tmp']<=32768)
        assert(not req.context.inventory.complete and #req.context.inventory.items<=8)
        assert(req.context.inventory.uuid==uuidA)
        capturedWire=files['ArayHumanNPCTest/to_py/'..rid..'.json.tmp']
        respond(rid,'Sou Carlos.'); assert(not H.isPending(uuidA))
    ''')
    actual_request = json.loads(integrated.eval("capturedWire"))
    validate(actual_request, actual_request["issued_at_ms"])


def test_relevant_inventory_preserved_before_large_spatial_fields(integrated):
    integrated.execute('''
        local ctx={uuid=uuidA,world_id=C.world(),captured_at_ms=clock,
          inventory={uuid=uuidA,world_id=C.world(),complete=true,items={
           {item_id='one',full_type='Base.Bandage',quantity={known=true,value=2}}}},
          zombies={{position={x=1,y=0,z=0},extra=string.rep('x',20000)}},
          doors={{extra=string.rep('x',20000)}},nearby_npcs={},visibility={known=true,complete=true}}
        assert(Q.compact(ctx,'quais itens no inventário?',3000))
        assert(ctx.inventory.complete and ctx.inventory.items[1].full_type=='Base.Bandage')
        assert(ctx.context_partial and not ctx.visibility.complete and #J.encode(ctx)<=3000)
        assert(J.decode(J.encode(ctx)).uuid==uuidA)
    ''')


def test_named_item_prioritized_without_inventing_quantity(integrated):
    integrated.execute('''
        local ctx={inventory={uuid=uuidA,world_id=C.world(),complete=true,items={}},visibility={complete=true}}
        for i=1,40 do ctx.inventory.items[i]={item_id=tostring(i),full_type='Base.Other'..i,quantity={known=true,value=1}} end
        ctx.inventory.items[41]={item_id='last',full_type='Base.Bandage',quantity={known=false,reason='missing_api'}}
        assert(Q.compact(ctx,'tem Bandage no inventário?',1500))
        assert(ctx.inventory.items[1].full_type=='Base.Bandage')
        assert(ctx.inventory.items[1].quantity.known==false and ctx.inventory.items[1].quantity.value==nil)
        assert(ctx.inventory.uuid==uuidA and not ctx.inventory.complete and ctx.context_partial)
    ''')


def test_visual_null_owner_repaired_before_native_serialization(integrated):
    integrated.execute('''
        local c=roster[uuidA]; local item=garment('version=1;type=Base.Tshirt;')
        local visual=item:getVisual(); local count=0
        visual.getLastStandString=function(self)
            assert(self.owner==item,'native inventoryItem null'); count=count+1
            return 'version=1;type=Base.Tshirt;'
        end
        c.inv:AddItem(item); c.wornData={item}
        local before=#c.inv.items
        local a=assert(V.capture(c,uuidA)); local b=assert(V.capture(c,uuidA))
        assert(count==2 and a.clothes[1]==b.clothes[1] and #c.inv.items==before)
        assert(visual:getInventoryItem()==item)
    ''')


def test_visual_foreign_owner_or_missing_api_never_serialized(integrated):
    integrated.execute('''
        local c=roster[uuidA]; local item=garment('version=1;type=Base.Tshirt;')
        c.wornData={item}; local visual=item:getVisual(); local calls=0
        visual.getLastStandString=function() calls=calls+1; error('must not serialize') end
        visual.owner=garment('other')
        local data,why=V.capture(c,uuidA); assert(not data and why=='clothing_owner_mismatch' and calls==0)
        visual.owner=nil; visual.setInventoryItem=nil
        data,why=V.capture(c,uuidA); assert(not data and why=='clothing_owner_api' and calls==0)
        visual.setInventoryItem=function() end
        data,why=V.capture(c,uuidA); assert(not data and why=='clothing_owner_unavailable' and calls==0)
        assert(not V.saveInitial(c,uuidA) and #c.inv.items==0)
    ''')


@pytest.fixture
def bridge(integrated):
    integrated.execute('''
        bridgeTicks={}; Events.OnTick.Add=function(fn) bridgeTicks[#bridgeTicks+1]=fn end
        getSpecificPlayer=function() return player end
        getWorld=function() return {getWorld=function() return 'world' end} end
        getCore=function() return {getGameMode=function() return 'Sandbox' end} end
        bridgeUpdates=0; ArayHuman.Ollama={update=function() bridgeUpdates=bridgeUpdates+1 end}
        function bridgeRequest()
            local last
            for path,text in pairs(files) do
                if path:find('.json.tmp',1,true) then
                    local req=J.decode(text)
                    if req and req.kind=='ping' and (not last or req.id>last.id) then last=req end
                end
            end
            return assert(last)
        end
    ''')
    integrated.execute((CLIENT / "ArayHumanBridge.lua").read_text(encoding="utf-8"))
    return integrated


def test_bridge_absent_partial_wrong_id_then_valid_response(bridge):
    bridge.execute('''
        local tick=bridgeTicks[1]; tick(); local req=bridgeRequest()
        local path='ArayHumanNPCTest/to_lua/'..req.id..'.json'
        local originalError=error; local raised=0
        error=function(...) raised=raised+1; return originalError(...) end
        for i=1,3 do clock=clock+1000; tick() end
        assert(raised==0 and bridgeUpdates==0)
        for _,bad in ipairs({'','{','{"id":"wrong","kind":"pong","ok":true}',
          '{"id":"'..req.id..'","kind":"pong","ok":true,"ok":false}'}) do
            files[path]=bad; clock=clock+1000; tick(); assert(bridgeUpdates==0)
        end
        files[path]=J.encode({id=req.id,kind='pong',ok=true})
        clock=clock+1000; tick(); assert(bridgeUpdates==1 and raised==0)
    ''')


def test_bridge_read_failure_closes_handle_and_retries_same_request(bridge):
    bridge.execute('''
        local tick=bridgeTicks[1]; tick(); local req=bridgeRequest(); local closes=0
        getFileReader=function() return {readLine=function() error('temporary I/O') end,
          close=function() closes=closes+1 end} end
        clock=clock+1000; assert(pcall(tick)); assert(closes==1 and bridgeUpdates==0)
        getFileReader=function() local read=false; return {
          readLine=function() if not read then read=true; return J.encode({id=req.id,kind='pong',ok=true}) end end,
          close=function() closes=closes+1 end} end
        clock=clock+1000; tick(); assert(closes==2 and bridgeUpdates==1)
    ''')


def test_bridge_read_budget_timeout_and_bounded_attempts(bridge):
    bridge.execute('''
        local tick=bridgeTicks[1]; tick(); local closes=0
        getFileReader=function() return {readLine=function() return string.rep('x',65537) end,
         close=function() closes=closes+1 end} end
        clock=clock+1000; assert(pcall(tick)); assert(closes==1 and bridgeUpdates==0)
        getFileReader=function() return nil end
        for i=1,8 do clock=clock+11000; tick() end
        local count=0; for path in pairs(files) do if path:find('.json.tmp',1,true) then count=count+1 end end
        assert(count==3 and bridgeUpdates==0)
    ''')
