"""Mandatory routing and observation-only neural boundaries; no game/network/model."""
import copy
import json

import pytest

from test_real_integration_fixes import integrated, build, agent, inventory, observer, nav, physical, safety, lua, ui
from test_executor import CLIENT
from test_conversation_backend import context, request, wait, Client, MODEL
from conversation_handler import ChatDispatcher, validate
from language_encoder import LanguageEncoder
from neural_state import build_observation
from decision_handler import read_identity
import ollama_service as svc


@pytest.mark.parametrize('message',['Venha aqui','me siga','Olá!','Vi Carlos ontem','Desconhecido: olá'])
def test_no_recipient_no_processing_even_with_f7_selection(integrated,message):
    integrated.globals().inputMessage=message
    integrated.execute('''
        local calls=0; Q.context=function() calls=calls+1; error('must not observe') end
        local ok=H.sendMessage(inputMessage,uuidA)
        assert(not ok and calls==0 and next(files)==nil and E.getState(uuidA)==nil)
        assert(#H.getEvents(uuidA)==0 and #H.getHistory(uuidA)==0)
    ''')


def test_explicit_name_overrides_selection_without_new_command_grammar(integrated):
    integrated.execute('''
        local ok,rid=H.sendMessage('Carlos, venha aqui',uuidB); assert(ok)
        local req=requestFor(rid); assert(req.npc_id==uuidA and req.message=='Carlos, venha aqui')
        assert(req.routing.recipients[1]==uuidA and E.getState(uuidA)==nil)
        assert(not H.isPending(uuidB)) -- no new intent for "venha aqui"
    ''')


def test_explicit_multiple_fanout_sessions_and_cross_reply_guard(integrated):
    integrated.execute('''
        local ok,first,results=H.sendMessage('Carlos e Tania: olá, memória 😀!'); assert(ok and #results==2)
        assert(results[1].uuid~=results[2].uuid)
        local a,b=requestFor(results[1].result),requestFor(results[2].result)
        assert(a.session_id~=b.session_id and a.npc_id~=b.npc_id and a.routing.event_id==b.routing.event_id)
        assert(a.message==b.message and a.context.uuid==a.npc_id and b.context.uuid==b.npc_id)
        respond(results[1].result,'Resposta errada',function(r) r.npc_id=b.npc_id end)
        assert(H.isPending(a.npc_id))
        respond(results[1].result,'Resposta correta ç 😀')
        assert(not H.isPending(a.npc_id) and H.isPending(b.npc_id))
        assert(H.getEvents(a.npc_id)[1].result.state=='REPLIED')
        assert(H.getEvents(b.npc_id)[1].result.state=='CHAT_REQUESTED')
        assert(H.getHistory(a.npc_id)[2].text=='Resposta correta ç 😀' and #H.getHistory(b.npc_id)==1)
    ''')


def test_collective_only_one_verbal_request_and_each_has_memory(integrated):
    integrated.execute('''
        local ok,rid,results=H.sendMessage('Vocês, como estão?'); assert(ok and #results==1)
        local count=0; for path in pairs(files) do if path:find('.json.tmp',1,true) then count=count+1 end end
        assert(count==1)
        local a,b=H.getEvents(uuidA)[1],H.getEvents(uuidB)[1]
        assert(a.event_id==b.event_id and a.text=='Vocês, como estão?' and a.speaker.kind=='player')
        assert(a.result.state=='OBSERVED_SILENT' or b.result.state=='OBSERVED_SILENT')
        assert(not H.sendMessage('Pessoal: outra pergunta'))
    ''')


def test_existing_commands_fanout_and_duplicate_actions_blocked(integrated):
    integrated.execute('''
        assert(H.sendMessage('Carlos e Tania: me siga'))
        assert(E.getState(uuidA).action=='FOLLOW_PLAYER' and E.getState(uuidB).action=='FOLLOW_PLAYER')
        local old=E.getState(uuidA).actionId
        assert(not H.sendMessage('Carlos e Tania: me siga'))
        assert(E.getState(uuidA).actionId==old and next(files)==nil)
        assert(H.sendMessage('Carlos: pare'))
        assert(E.getState(uuidA).action=='STOP' and E.getState(uuidB).action=='FOLLOW_PLAYER')
        assert(H.getEvents(uuidA)[1].result.state=='CANCELLED')
        clock=clock+250; Q.update()
        assert(H.getEvents(uuidA)[2].result.state~='RECEIVED')
    ''')


def test_manual_stop_has_priority_over_pending_inference_and_group_cooldown(integrated):
    integrated.execute('''
        local ok,rid=H.sendMessage('Vocês, como estão?'); assert(ok)
        assert(H.isPending())
        assert(H.sendMessage('Vocês: pare'))
        assert(E.getState(uuidA).action=='STOP' and E.getState(uuidB).action=='STOP')
        assert(not H.isPending())
        local requested=requestFor(rid).npc_id
        assert(H.getEvents(requested)[1].result.state=='DISCARDED')
        assert(H.getEvents(requested)[1].result.reason=='manual_command')
        respond(rid,'Resposta antiga'); assert(#H.getHistory(requested)==3)
    ''')


@pytest.mark.parametrize('condition',['dead','far','wrong_world','ambiguous','invalid_uuid','alias_collision'])
def test_invalid_group_blocks_all_before_actions(integrated,condition):
    integrated.globals().condition=condition
    integrated.execute('''
        local message='Carlos e Tania: me siga'; local expected=C.world()
        if condition=='dead' then roster[uuidB].dead=true
        elseif condition=='far' then roster[uuidB].x=40
        elseif condition=='wrong_world' then expected='other-world'
        elseif condition=='ambiguous' then roster[uuidB].md.ARAY_Name='Carlos'; message='Carlos: me siga'
        elseif condition=='invalid_uuid' then ArayHuman.Recipients.resolve=function() return {status='resolved',world_id=C.world(),body='me siga',uuids={'npc_1'}} end
        else ArayHuman.Recipients.setAliases(uuidA,{'Doc'}); ArayHuman.Recipients.setAliases(uuidB,{'Doc'}); message='Doc: me siga' end
        local ok=H.sendMessage(message,nil,nil,expected)
        assert(not ok and next(files)==nil and E.getState(uuidA)==nil and E.getState(uuidB)==nil)
    ''')


def test_alias_unicode_and_expiration_memory(integrated):
    integrated.execute('''
        assert(ArayHuman.Recipients.setAliases(uuidA,{'Doutor João'}))
        local ok,rid=H.sendMessage('Doutor Joao: minha ação é segura?'); assert(ok)
        local req=requestFor(rid); assert(req.npc_id==uuidA)
        assert(req.agent_input.uuid==uuidA and req.agent_input.world_id==C.world())
        assert(req.agent_input.capabilities.PUSH_ZOMBIE.support=='UNSUPPORTED')
        clock=clock+20001; H.update()
        assert(H.getEvents(uuidA)[1].result.state=='EXPIRED' and not H.isPending())
        worldName='new'; assert(#H.getEvents(uuidA)==0)
    ''')


def test_collective_word_alias_is_ambiguous_not_implicit_broadcast(integrated):
    integrated.execute('''
        assert(ArayHuman.Recipients.setAliases(uuidA,{'Todos'}))
        local ok,why=H.sendMessage('Todos: me siga')
        assert(not ok and why=='ambiguous_recipient' and next(files)==nil)
        assert(E.getState(uuidA)==nil and E.getState(uuidB)==nil)
    ''')


def test_memory_copy_and_registry_bound(integrated):
    integrated.execute('''
        for i=1,12 do
            clock=clock+1100
            local ok,rid=H.sendMessage('Carlos: olá '..i); assert(ok)
            respond(rid,'Olá 😀 '..i)
        end
        local events=H.getEvents(uuidA); assert(#events==8 and #H.getEvents(uuidB)==0)
        assert(events[8].text=='Carlos: olá 12' and events[8].result.text=='Olá 😀 12')
        events[8].text='tamper'; assert(H.getEvents(uuidA)[8].text=='Carlos: olá 12')
        assert(forbiddenCalls==0)
    ''')


def test_talkbar_uses_mandatory_router_not_selected_actor(ui):
    ui.execute('ISPanel=ISCollapsableWindow')
    ui.execute((CLIENT/'ArayHumanTalkBar.lua').read_text(encoding='utf-8'))
    ui.execute('''
        getSpecificPlayer=function() return player end; player.Say=function() end
        local closed=false
        roster[uuidB].dead=true
        ArayTalkBar.prerender({npc=roster[uuidB],world_id=C.world(),close=function() closed=true end})
        assert(not closed) -- selected actor cannot close a bar addressing another NPC
        local function send(text)
            local bar={npc=roster[uuidB],world_id=C.world(),
              inputBox={getInternalText=function() return text end,setText=function() end},close=function() end}
            ArayTalkBar.onSend(bar)
        end
        send('me siga'); assert(E.getState(uuidA)==nil and E.getState(uuidB)==nil)
        send('Carlos: me siga'); assert(E.getState(uuidA).action=='FOLLOW_PLAYER' and E.getState(uuidB)==nil)
    ''')


def test_encoder_unavailable_and_no_synthetic_semantics():
    value=LanguageEncoder().encode('João, venha aqui')
    assert value['status']=='UNAVAILABLE' and value['vector'] is None and value['dimensions'] is None
    assert LanguageEncoder().encode('ç'*2000)['reason']=='message_budget'


@pytest.mark.parametrize('vector',[[float('nan')],[float('inf')],[True],[],[0]*769,'fake'])
def test_encoder_rejects_invalid_trusted_adapter_output(vector):
    result=LanguageEncoder(lambda _:vector,'test-adapter').encode('Olá')
    assert result['status']=='UNAVAILABLE' and result['vector'] is None


def test_neural_observation_known_unknown_unavailable_and_copy(context):
    r=request(context.a); r['context']['threat']={'known':False,'reason':'partial_scan'}
    value=build_observation(r,read_identity(context.database,r['world_id'],context.a),r['issued_at_ms'])
    assert value['language']['status']=='UNAVAILABLE' and value['identity']['value']['npc_id']==context.a
    assert value['threat']['status']=='UNKNOWN' and value['profile']['status']=='UNAVAILABLE'
    assert value['personal_memory']['status']=='UNAVAILABLE'
    value['inventory']['value']['items'].append({'injected':True})
    assert r['context']['inventory']['items']==[]


@pytest.mark.parametrize('change',['missing','wrong_world','wrong_npc','expired_route','duplicate_ids','no_name'])
def test_backend_rejects_unrouted_requests_before_model(context,change):
    r=request(context.a); client=Client(); d=ChatDispatcher(context.database,lambda:client)
    if change=='missing':r.pop('routing')
    elif change=='wrong_world':r['routing']['world_id']='other'
    elif change=='wrong_npc':r['routing']['recipients']=[context.b]
    elif change=='expired_route':r['routing']['captured_at_ms']-=1501
    elif change=='duplicate_ids':r['routing']['recipients']*=2
    else:r['message']='Venha aqui'
    try:
        result=d.submit(r,MODEL)
        assert result and not result['success'] and not client.calls
        assert not d.observations
        assert svc.validate_chat_request(r) is not None
    finally:d.close()


def test_backend_observations_isolated_bounded_and_expired(context):
    client=Client(); d=ChatDispatcher(context.database,lambda:client)
    try:
        a=request(context.a); b=request(context.b,2)
        for r in (a,b):d.submit(r,MODEL); assert wait(d)[0]['success']
        av=d.get_observation(a['world_id'],context.a); bv=d.get_observation(b['world_id'],context.b)
        assert av['uuid']!=bv['uuid'] and av['identity']['value']['name']!=bv['identity']['value']['name']
        assert av['language']['vector'] is None and len(json.dumps(av).encode())<=32768
        d.clock=lambda: a['issued_at_ms']+2000
        assert d.get_observation(a['world_id'],context.a)['status']=='UNAVAILABLE'
    finally:d.close()


@pytest.mark.parametrize('change',['uuid','world','expired'])
def test_invalid_agent_input_never_reaches_model(context,change):
    r=request(context.a)
    r['agent_input']={'schema_version':1,'uuid':context.a,'world_id':r['world_id'],'captured_at_ms':r['issued_at_ms']}
    if change=='uuid':r['agent_input']['uuid']=context.b
    elif change=='world':r['agent_input']['world_id']='other'
    else:r['agent_input']['captured_at_ms']-=1501
    client=Client(); d=ChatDispatcher(context.database,lambda:client)
    try:
        d.submit(r,MODEL); result=wait(d)[0]
        assert not result['success'] and not client.calls and not d.observations
    finally:d.close()
