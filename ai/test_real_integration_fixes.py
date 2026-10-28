"""Production Lua paths, simulated native APIs and in-memory mailbox. No game/services."""
import pytest
from test_character_build import build, agent, inventory, observer, nav, physical, safety, lua
from test_executor import CLIENT


@pytest.fixture
def integrated(build):
    for file in ("ArayHumanText.lua", "ArayHumanJson.lua", "ArayHumanAppearance.lua", "ArayHumanConversation.lua", "ArayHumanRecipients.lua", "ArayHumanNeuralInput.lua", "ArayHumanChat.lua"):
        build.execute((CLIENT / file).read_text(encoding="utf-8"))
    build.execute('''
        roster[uuidA].md.ARAY_Name='Carlos'; roster[uuidB].md.ARAY_Name='Tania'
        ArayHuman.rosterSnapshot=function() return {{uuid=uuidA,character=roster[uuidA],dead=roster[uuidA].dead},{uuid=uuidB,character=roster[uuidB],dead=roster[uuidB].dead}} end
        function sendAddressed(message,id,target)
            return ArayHuman.Chat.sendMessage(roster[id].md.ARAY_Name..': '..message,nil,target)
        end
        H=ArayHuman.Chat; Q=ArayHuman.Conversation; V=ArayHuman.Appearance; J=ArayHuman.Json
        files={}
        getFileWriter=function(path)
            files[path]=''
            return {write=function(_,text) files[path]=files[path]..text end,close=function() end}
        end
        getFileReader=function(path)
            if not files[path] then return nil end
            local read=false
            return {readLine=function() if not read then read=true; return files[path] end end,close=function() end}
        end
        function requestFor(rid) return assert(J.decode(files['ArayHumanNPCTest/to_py/'..rid..'.json.tmp'])) end
        function respond(rid,text,mutate)
            local r=requestFor(rid)
            local response={id=rid,kind='chat_response',protocol_version=2,npc_id=r.npc_id,world_id=r.world_id,
                session_id=r.session_id,session_started_at_ms=r.session_started_at_ms,sequence=r.sequence,
                expires_at_ms=r.expires_at_ms,verbal_only=true,executable=false,success=true,reply=text}
            if mutate then mutate(response) end
            files['ArayHumanNPCTest/to_lua/'..rid..'.json']=assert(J.encode(response))
            clock=clock+75; H.update()
        end
        function human(text)
            local h={text=text or 'version=2;hairModel=Short;beardModel=Full;skinTexture=1;'}
            function h:getLastStandString() return self.text end
            function h:loadLastStandString(value) self.text=value; return true end
            function h:getBodyVisuals() return list({}) end
            return h
        end
        for _,c in pairs(roster) do
            c.visual=human(); c.wornData={}
            c.getHumanVisual=function(self) return self.visual end
            c.isFemale=function() return false end
            c.getWornItems=function(self) return {size=function() return #self.wornData end,getItemByIndex=function(_,i) return self.wornData[i+1] end} end
        end
        function garment(text)
            local item=newItem('Tshirt',nil); local visual={getLastStandString=function() return text end}
            visual.getInventoryItem=function(self) return self.owner end
            visual.setInventoryItem=function(self,owner) self.owner=owner end
            item.getVisual=function() return visual end; item.getBodyLocation=function() return 'Tshirt' end
            return item
        end
        ItemVisual={createLastStandItem=function(text) return garment(text) end}
    ''')
    return build


@pytest.mark.parametrize("text", ['hello', 'quote: " and slash \\', 'linha\nseguinte', 'ação'])
def test_bounded_json_roundtrip(integrated, text):
    integrated.globals().message=text
    integrated.execute('local decoded=assert(J.decode(assert(J.encode({text=message,zero=0,no=false})))); assert(decoded.text==message and decoded.zero==0 and decoded.no==false)')


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":1} trailing', '{"a":NaN}', '[1,]', 'os.execute("anything")'])
def test_json_rejects_untrusted_syntax(integrated, text):
    integrated.globals().message=text
    integrated.execute('assert(J.decode(message)==nil)')


def test_manual_chat_commands_two_npcs_and_cancel_old_callback(integrated):
    integrated.execute('''
        assert(sendAddressed('me siga',uuidA)); local old=queued(uuidA)
        assert(E.getState(uuidA).action=='FOLLOW_PLAYER')
        assert(sendAddressed('me siga',uuidB)); local other=queued(uuidB)
        assert(sendAddressed('pare',uuidA)); if old then old:perform() end
        assert(E.getState(uuidA).action=='STOP' and queued(uuidB)==other)
        assert(next(files)==nil) -- no Ollama request for human commands
        clock=clock+250; Q.update()
        assert(logContains('event=action_result') and forbiddenCalls==0)
    ''')


def test_ambiguous_destination_refused_and_valid_token_executes(integrated):
    integrated.execute('''
        local ok,reason=sendAddressed('vá até ali',uuidA)
        assert(not ok and reason:find('destination_required') and not queued(uuidA),tostring(reason)..' intent='..tostring(Q.intent('vá até ali')))
        ok,reason=sendAddressed('vá até ali',uuidA,'tile:999:999:0')
        assert(not ok and reason=='candidate_not_in_observation')
        assert(sendAddressed('vá até ali',uuidA,'tile:1:0:0'))
        assert(E.getState(uuidA).action=='MOVE_TO' and queued(uuidA))
        complete(uuidA); clock=clock+250; Q.update()
        assert(logContains('event=action_result') and L.getState(uuidA).state=='COMPLETED')
    ''')


def test_emergency_has_priority_over_chat(integrated):
    integrated.execute('''
        character(nil,-.5,.5,0,'IsoZombie'); fireTick(250)
        local ok,reason=sendAddressed('me siga',uuidA)
        assert(not ok and reason=='emergency_priority')
    ''')


def test_real_uuid_context_and_reply_survive_focus_switch(integrated):
    integrated.execute('''
        local item=newItem('Nails',roster[uuidA].inv); item.getCount=function() return 3 end
        local ok,rid=sendAddressed('Olá, como vai?',uuidA); assert(ok)
        local req=requestFor(rid)
        assert(req.npc_id==uuidA and req.context.uuid==uuidA and req.context.inventory.items[1].full_type=='Base.Nails')
        assert(req.context.inventory.items[1].quantity.value==3 and req.context.world_id==C.world())
        focus=roster[uuidB]
        respond(rid,'Resposta verbal. me siga')
        assert(not H.isPending() and #H.getHistory(uuidA)==2 and #H.getHistory(uuidB)==0)
        assert(bubbles[#bubbles].character==roster[uuidA] and E.getState(uuidA)==nil)
        H.update(); assert(#H.getHistory(uuidA)==2)
    ''')


@pytest.mark.parametrize("mutation", ["world", "uuid", "session", "sequence", "code"])
def test_reply_identity_and_no_executable_payload(integrated, mutation):
    integrated.globals().mutation=mutation
    integrated.execute('''
        local ok,rid=sendAddressed('Olá',uuidA); assert(ok)
        respond(rid,'Não deve aparecer',function(r)
            if mutation=='world' then r.world_id='other'
            elseif mutation=='uuid' then r.npc_id=uuidB
            elseif mutation=='session' then r.session_id='other'
            elseif mutation=='sequence' then r.sequence=r.sequence+1
            else r.action='FOLLOW_PLAYER' end
        end)
        assert(H.isPending(uuidA) and #H.getHistory(uuidA)==1 and E.getState(uuidA)==nil)
        clock=clock+20000; H.update(); assert(not H.isPending())
    ''')


def test_inventory_changed_or_world_changed_discards_old_reply(integrated):
    integrated.execute('''
        local ok,rid=sendAddressed('Olá',uuidA); assert(ok)
        newItem('Nails',roster[uuidA].inv)
        respond(rid,'Inventário antigo')
        assert(#H.getHistory(uuidA)==1 and not H.isPending())
        ok,rid=sendAddressed('Olá',uuidA); assert(ok)
        worldName='another'; respond(rid,'Mundo antigo')
        assert(#H.getHistory(uuidA)==0 and not H.isPending())
    ''')


def test_native_inventory_empty_partial_quantities_player_untouched(integrated):
    integrated.execute('''
        local s=I.readInventory(uuidA); assert(s.complete and #s.items==0 and s.weight.value==0)
        local a=newItem('Nails',roster[uuidA].inv); a.getCount=function() return 5 end
        newItem('Bandage',roster[uuidB].inv)
        s=I.readInventory(uuidA); assert(s.items[1].quantity.value==5 and #s.items==1)
        assert(I.readInventory(uuidB).items[1].full_type=='Base.Bandage')
        a.getCount=nil; assert(not I.readInventory(uuidA).items[1].quantity.known)
        I.config.maxItems=0; s=I.readInventory(uuidA); assert(not s.complete and s.reason)
        assert(not I.readInventory('npc_1') and forbiddenCalls==0)
    ''')


def test_native_visual_roundtrip_and_inventory_clothes(integrated):
    integrated.execute('''
        local c=roster[uuidA]; local shirt=garment('version=1;type=Base.Tshirt;tint=0.5,0.4,0.3;')
        c.inv:AddItem(shirt); c.wornData={shirt}
        local snapshot=assert(V.capture(c,uuidA))
        local d=descriptor(); d.setFemale=function(self,v) self.female=v end
        d.getHumanVisual=function(self) self.h=self.h or human(); return self.h end
        assert(V.prepare(d,snapshot))
        local restored=fresh(d); restored.visual=human('version=2;hairModel=Different;')
        restored.getHumanVisual=function(self) return self.visual end
        restored.inv={items={},AddItem=function(self,item) self.items[#self.items+1]=item end}; restored.getInventory=function(self) return self.inv end
        restored.wornData={}; restored.getWornItems=c.getWornItems
        restored.setWornItem=function(self,location,item) self.wornData[#self.wornData+1]=item end
        assert(V.applyNew(restored,snapshot))
        assert(restored.visual.text==c.visual.text and #restored.wornData==1 and #restored.inv.items==1)
        assert(not V.applyNew(player,snapshot) and not V.capture(player,uuidA))
    ''')


def test_appearance_mailbox_is_uuid_world_bound_and_exact_copy(integrated):
    integrated.execute('''
        local data,why=V.get(uuidA); assert(not data and why=='appearance_pending')
        local rid
        for path,text in pairs(files) do if path:find('.json.tmp',1,true) then rid=J.decode(text).id end end
        local visual={schema_version=1,female=false,human='version=2;'..string.rep('x',1400),clothes={}}
        files['ArayHumanNPCTest/to_lua/'..rid..'.json']=J.encode({kind='appearance_response',id=rid,npc_id=uuidB,world_id=C.world(),ok=true,found=true,visual=visual})
        clock=clock+100; V.update(); assert(select(2,V.get(uuidA))=='appearance_pending')
        files['ArayHumanNPCTest/to_lua/'..rid..'.json']=J.encode({kind='appearance_response',id=rid,npc_id=uuidA,world_id=C.world(),ok=true,found=true,visual=visual})
        clock=clock+100; V.update(); data=assert(V.get(uuidA)); assert(#data.human==#visual.human)
        data.human='mutated'; assert(V.get(uuidA).human~=data.human)
        worldName='other'; assert(select(2,V.get(uuidA))=='appearance_pending')
    ''')


def test_unsupported_body_visuals_and_missing_assets_fail_closed(integrated):
    integrated.execute('''
        roster[uuidA].visual.getBodyVisuals=function() return list({{}}) end
        local data,why=V.capture(roster[uuidA],uuidA); assert(not data and why:find('UNSUPPORTED'))
        local c=fresh(descriptor()); c.getHumanVisual=function() return human() end
        c.getWornItems=function() return {size=function() return 0 end} end
        ItemVisual.createLastStandItem=function() return nil end
        assert(not V.applyNew(c,{human='version=2;',clothes={'version=1;type=missing;'}}))
    ''')


def test_chat_perception_never_reveals_entities_without_native_los(integrated):
    integrated.execute('''
        local c=roster[uuidA]; local zombie=character(nil,3.5,.5,0,'IsoZombie'); zombie.hidden=true
        c.CanSee=function(_,object) return not object.hidden end
        ArayHuman.Perception.updateSnapshot(uuidA); A.invalidate(uuidA)
        local ctx=assert(Q.context(uuidA)); assert(#ctx.zombies==0 and ctx.visibility.known)
        zombie.hidden=false; ctx=assert(Q.context(uuidA)); assert(#ctx.zombies==1)
        assert(ctx.zombies[1].position.x==3.5 and ctx.inventory.uuid==uuidA)
        c.CanSee=nil; ctx=assert(Q.context(uuidA)); assert(#ctx.zombies==0 and not ctx.visibility.known)
        assert(forbiddenCalls==0)
    ''')


@pytest.fixture
def ui(integrated):
    integrated.execute('''
        UIFont={Small='small'}; windows={}
        local W={}
        function W:new(x,y,width,height)
            return setmetatable({x=x,y=y,width=width,height=height,items={},options={},selected=1,visible=false},{__index=self})
        end
        function W:derive() return setmetatable({},{__index=self}) end
        function W:initialise() end
        function W:instantiate() if self.createChildren and not self.created then self.created=true; self:createChildren() end end
        function W:createChildren() end
        function W:addChild(child) end
        function W:titleBarHeight() return 20 end
        function W:addOption(text) self.options[#self.options+1]=text end
        function W:addItem(text,item) self.items[#self.items+1]={text=text,item=item} end
        function W:clear() self.items={}; self.options={} end
        function W:setEnabled() end
        function W:setHeight(h) self.height=h end
        function W:setName(name) self.name=name end
        function W:setVisible(v) self.visible=v end
        function W:getIsVisible() return self.visible end
        function W:addToUIManager() windows[#windows+1]=self end
        function W:removeFromUIManager() self.removed=true end
        function W:update() end
        function W:render() end
        function W:prerender() end
        ISCollapsableWindow=W
        for _,key in ipairs({'ISComboBox','ISButton','ISLabel','ISScrollingListBox'}) do
            _G[key]={new=function(_,x,y,w,h) return W:new(x,y,w,h) end}
        end
        Events.OnKeyPressed={Add=function() end}
    ''')
    integrated.execute((CLIENT / "ArayHumanInventoryWindow.lua").read_text(encoding="utf-8"))
    integrated.execute((CLIENT / "ArayHumanUi.lua").read_text(encoding="utf-8"))
    return integrated


def test_f7_inventory_selection_refresh_and_read_only_ui(ui):
    ui.execute('''
        local a=newItem('Nails',roster[uuidA].inv); a.getCount=function() return 2 end
        local b=newItem('Bandage',roster[uuidB].inv); b.getCount=function() return 1 end
        local w=ArayNpcWindow:new(0,0,400,500); w:initialise(); w:instantiate()
        w:updateNpcCombo()
        for index,id in ipairs(w.npcIds) do if id==uuidB then w.npcCombo.selected=index end end
        w:onNpcSelect(w.npcCombo); assert(w.selectedUuid==uuidB)
        w:onInventory(); local panel=windows[#windows]
        assert(panel.uuid==uuidB and panel.list.items[1].text:find('Base.Bandage',1,true))
        assert(not panel.list.items[1].text:find('Nails') and #roster[uuidA].inv.items==1 and #roster[uuidB].inv.items==1)
        panel:refresh(); assert(#roster[uuidB].inv.items==1)
        roster[uuidB].dead=true; w:updateNpcCombo(); assert(w.selectedUuid~=uuidB)
        worldName='different'; panel:update(); assert(not panel.visible and panel.removed)
        assert(forbiddenCalls==0)
    ''')


def test_legacy_appearance_missing_blocks_restore_without_randomization(integrated):
    source=(CLIENT / "ArayHumanLifecycle.lua").read_text(encoding="utf-8")
    function=source[source.index('local function spawnRecord('):source.index('local function restoreNext(')]
    integrated.execute(function+'\nspawnRecordUnderTest=spawnRecord')
    integrated.execute('''
        local calls=0; ArayHuman.spawnCarlos=function() calls=calls+1; return true end
        V.get=function() return nil,'missing' end
        local saved={uuid='33333333-3333-4333-8333-333333333333',saved={x=0,y=0,z=0}}
        assert(not spawnRecordUnderTest(saved,squares['0:0:0'],'pronto') and calls==0)
        saved.saved=nil
        assert(spawnRecordUnderTest(saved,squares['0:0:0'],'criar') and calls==1)
    ''')


def test_visual_pending_and_legacy_migration_do_not_fail_other_restores(integrated):
    source = (CLIENT / "ArayHumanLifecycle.lua").read_text(encoding="utf-8")
    functions = source[source.index('local function spawnRecord('):source.index('local function onResult(')]
    integrated.execute('''
        local phase='ACTIVE'
        local records={pending={uuid='pending'},legacy={uuid='legacy',saved={x=0,y=0,z=0}},ready={uuid='ready'}}
        local queue={{uuid='pending'},{uuid='legacy'},{uuid='ready'}}
        local markedDead={}
        local function setPhase(value) phase=value end
        local function nowMs() return 1000 end
        local SQUARE_WAIT_MS=10000
    ''' + functions + '''
        local spawned={}
        ArayHuman.spawnCarlos=function(config) spawned[config.uuid]=true; return true end
        ArayHuman.findRestoreSquare=function() return squares['0:0:0'],'pronto' end
        ArayHuman.getNpcByUuid=function() return nil end
        V.get=function(id)
            if id=='pending' then return nil,'appearance_pending' end
            return nil,'missing'
        end
        restoreNext()
        assert(phase=='WAITING_SQUARE' and not queue[1].done)
        assert(queue[2].done and records.legacy.visualMigrationRequired and not spawned.legacy)
        assert(queue[3].done and spawned.ready)
        V.get=function() return nil,'missing' end
        restoreNext()
        assert(phase=='ACTIVE' and queue[1].done and spawned.pending)
    ''')
