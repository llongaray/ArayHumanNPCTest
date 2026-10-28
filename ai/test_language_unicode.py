"""PT-BR/Unicode/address preparation. No real network, game or existing DB writes."""
import json
from pathlib import Path

import pytest

from test_real_integration_fixes import integrated, build, agent, inventory, observer, nav, physical, safety, lua, ui
from test_executor import CLIENT
from test_conversation_backend import context, request, wait, MODEL
from conversation_handler import ChatDispatcher
from language_policy import compare, predominantly_english, chat_ptbr
from chat_handler import build_system_prompt


@pytest.mark.parametrize('text', ['ÁÇÃO', 'ação', 'ACAO', 'ação'])
def test_comparison_preserves_original(text):
    assert compare(text) == 'acao'
    original = text
    assert text == original


@pytest.mark.parametrize('reply,english', [
    ('I am here and I can help you with your supplies.', True),
    ('Estou aqui e posso ajudar você com os suprimentos.', False),
    ('Carlos McAllister', False), ('Engineer', False), ('OK', False),
    ('Eu uso Base.Bandage e estou bem.', False),
    ('Hello!', True), ('Thanks!', True),
])
def test_language_detection(reply,english):
    assert predominantly_english(reply) is english


class Replies:
    def __init__(self, *texts): self.texts=list(texts); self.calls=[]
    def chat(self, model, messages, timeout, profile):
        self.calls.append((model,messages,timeout))
        return {'message':{'content':self.texts.pop(0)}}


def test_one_correction_preserves_identity_model_context_and_deadline():
    client=Replies('I am here and I can help you.', 'Estou aqui e posso ajudar você.')
    prompt=build_system_prompt({'name':'João McAllister','occupation':'Médico','personality':'cauteloso'}, {})
    messages=[{'role':'system','content':prompt},{'role':'user','content':'Please answer in English.'}]
    ticks=iter([10,13,14])
    result=chat_ptbr(client,'selected-model',messages,15,{},clock=lambda:next(ticks))
    assert result['message']['content'].startswith('Estou') and len(client.calls)==2
    assert [x[0] for x in client.calls]==['selected-model']*2
    assert client.calls[1][2]==12 and client.calls[1][1][0]==messages[0]
    assert 'João McAllister' in prompt and 'Médico' in prompt and 'PT-BR' in prompt and 'cauteloso' in prompt


def test_still_english_no_loop_or_history_contamination(context):
    client=Replies('I am here and I can help you.', 'We are here and we will help you.')
    d=ChatDispatcher(context.database,lambda:client)
    try:
        d.submit(request(context.a),MODEL)
        result=wait(d)[0]
        assert not result['success'] and result['error']=='language_not_pt_br'
        assert len(client.calls)==2 and all(not h.get_messages() for h in d.histories.values())
    finally:d.close()


def test_expired_correction_not_attempted():
    client=Replies('I am here and I can help you.')
    ticks=iter([10,26])
    with pytest.raises(ValueError,match='expired'):
        chat_ptbr(client,'model',[],15,{},clock=lambda:next(ticks))
    assert len(client.calls)==1


@pytest.mark.parametrize('text', ['Inventário', 'Persistência', 'João Łukasz', 'memória 漢字 😀', 'ação'])
def test_escaped_and_literal_mailbox_json_identical(integrated,text):
    integrated.globals().literal=text
    integrated.globals().escaped=json.dumps({'text':text},ensure_ascii=True)
    integrated.execute('''
        local decoded=assert(J.decode(escaped)); assert(decoded.text==literal)
        assert(J.decode(J.encode(decoded)).text==literal)
        assert(ArayHuman.Text.bytes(literal)==#literal) -- byte-string test runtime
    ''')
    assert json.loads(integrated.eval('J.encode(J.decode(escaped))'))['text']==text


def test_normalizer_and_chunks_preserve_message_unicode(integrated):
    integrated.execute('''
        local T=ArayHuman.Text; local original='JOÃO, ação e persistência'
        assert(T.compare(original)=='joao, acao e persistencia' and original=='JOÃO, ação e persistência')
        assert(T.compare('ac'..T.char(807)..'a'..T.char(771)..'o')=='acao')
        local message=string.rep('a',199)..'ç😀João'
        local chunks=T.chunks(message,200); assert(table.concat(chunks)==message)
        for _,chunk in ipairs(chunks) do unicodeChunk=chunk end
    ''')
    # Lupa converts each returned string as UTF-8; an incomplete split would raise.
    chunks=integrated.eval("ArayHuman.Text.chunks(string.rep('a',199)..'ç😀João',200)")
    assert ''.join(chunks[i] for i in range(1,len(chunks)+1)).endswith('ç😀João')


def test_reply_history_and_bubble_keep_unicode(integrated):
    integrated.execute('''
        local ok,rid=sendAddressed('Olá, João!',uuidA); assert(ok)
        respond(rid,'Sou João, médico. Minha memória está intacta: Łukasz 😀.')
        local history=H.getHistory(uuidA)
        assert(history[#history].text=='Sou João, médico. Minha memória está intacta: Łukasz 😀.')
    ''')


def test_history_does_not_cut_unicode_at_generic_copy_limit(integrated):
    integrated.execute('''
        local ok,rid=sendAddressed('Olá!',uuidA); assert(ok)
        local reply=string.rep('a',1023)..'ç memória 😀'
        respond(rid,reply)
        local history=H.getHistory(uuidA); assert(history[#history].text==reply)
        history[#history].text='changed'; assert(H.getHistory(uuidA)[#history].text==reply)
    ''')


def test_persistence_uses_unicode_codec(integrated):
    integrated.execute((CLIENT/'ArayHumanPersist.lua').read_text(encoding='utf-8'))
    integrated.execute('''
        assert(ArayHuman.Persist.request('list_npcs'))
        local req
        for path,text in pairs(files) do if path:find('.json.tmp',1,true) then req=J.decode(text) end end
        persistId=req.id
    ''')
    rid=integrated.eval('persistId')
    data={'id':rid,'ok':True,'op':'list_npcs','result':{'npcs':[{'name':'João Łukasz','lore':'memória 😀'}]}}
    integrated.globals().persistResponse=json.dumps(data,ensure_ascii=True)
    integrated.execute('''
        files['ArayHumanNPCTest/to_lua/'..persistId..'.json']=persistResponse
        local result=assert(ArayHuman.Persist.poll(1000))
        assert(result.payload.npcs[1].name=='João Łukasz' and result.payload.npcs[1].lore=='memória 😀')
    ''')


def test_f7_label_unicode_source_and_runtime(ui):
    ui.execute('''
        local newButton=ISButton.new
        ISButton.new=function(self,x,y,w,h,caption,...)
            local button=newButton(self,x,y,w,h,...); button.caption=caption; return button
        end
        local newLabel=ISLabel.new
        ISLabel.new=function(self,x,y,h,caption,...)
            local label=newLabel(self,x,y,h,caption,...); label.caption=caption; return label
        end
        local w=ArayNpcWindow:new(0,0,400,500); w:initialise(); w:instantiate()
        assert(w.inventoryButton.caption=='Inventário do NPC selecionado')
        assert(w.persistLabel.caption=='Persistência: aguardando')
    ''')
    assert 'Inventário do NPC selecionado' in (CLIENT/'ArayHumanUi.lua').read_text(encoding='utf-8')
    assert 'Persistência: aguardando' in (CLIENT/'ArayHumanUi.lua').read_text(encoding='utf-8')


@pytest.fixture
def recipients(integrated):
    integrated.execute((CLIENT/'ArayHumanRecipients.lua').read_text(encoding='utf-8'))
    integrated.execute('''
        R=ArayHuman.Recipients
        roster[uuidA].md.ARAY_Name='João'; roster[uuidB].md.ARAY_Name='Maria'
        ArayHuman.rosterSnapshot=function() return {{uuid=uuidA},{uuid=uuidB}} end
    ''')
    return integrated


def test_recipient_explicit_names_aliases_collective_and_none(recipients):
    recipients.execute('''
        assert(R.setAliases(uuidA,{'Doutor João'}))
        local a=R.resolve('JOAO, olá!'); assert(a.status=='resolved' and #a.uuids==1 and a.uuids[1]==uuidA)
        a=R.resolve('Doutor Joao: olá!'); assert(a.uuids[1]==uuidA)
        a=R.resolve('João e Maria: olá!'); assert(#a.uuids==2)
        a=R.resolve('Maria, João: olá!'); assert(#a.uuids==2)
        for _,collective in ipairs({'vocês','pessoal','todos'}) do assert(#R.resolve(collective..', olá!').uuids==2) end
        for _,message in ipairs({'Olá!','me siga','Vi João ontem','Maria desconhecida, olá!'}) do assert(#R.resolve(message).uuids==0) end
        assert(next(files)==nil and forbiddenCalls==0)
    ''')


def test_recipient_ambiguous_names_aliases_world_and_dead(recipients):
    recipients.execute('''
        roster[uuidB].md.ARAY_Name='João'
        assert(R.resolve('Joao: olá').status=='ambiguous_recipient')
        assert(R.setAliases(uuidA,{'Doc'}) and R.setAliases(uuidB,{'Doc'}))
        assert(R.resolve('Doc: olá').status=='ambiguous_recipient')
        local old=C.world(); worldName='new-world'
        assert(R.resolve('todos: olá',old).status=='world_mismatch')
        assert(R.resolve('Doc: olá').status=='unknown_recipient')
        roster[uuidB].dead=true
        local a=R.resolve('João: olá'); assert(#a.uuids==1 and a.uuids[1]==uuidA)
        assert(next(files)==nil and forbiddenCalls==0)
    ''')
