-- Human input boundary; model replies are never routed here as commands.
require "ArayHumanAgentState"
require "ArayHumanJson"
ArayHuman=ArayHuman or {}
local Q={}; ArayHuman.Conversation=Q
local C,J=ArayHuman.Capabilities,ArayHuman.Json
local active,seenWorld,serial={},nil,0
local function log(event,id,detail) print('[ARAY] event='..event..' uuid='..tostring(id)..' '..tostring(detail or '')) end
function Q.say(id,text)
 local c=C.actor(id)
 if c and ArayHuman.SpeechBubble and ArayHuman.SpeechBubble.show then ArayHuman.SpeechBubble.show(c,text,false) end
 if ArayHuman.setStatus then ArayHuman.setStatus(text) end
end
local function observed(c,p)
 local out={zombies={},nearby_npcs={},doors={},obstacles={},visibility={known=c.CanSee~=nil,complete=false,
  scope='native_CanSee_line_of_sight_no_camera_no_field_of_view_claim'}}
 local examined=0; local budget=128; local complete=true
 local function visible(entry,kind)
  local pos=entry.position or entry
  if not pos or not C.finite(pos.x) or not C.finite(pos.y) or not C.finite(pos.z) or not c.CanSee then complete=false; return false end
  local sq=getCell():getGridSquare(math.floor(pos.x),math.floor(pos.y),math.floor(pos.z))
  if not sq then complete=false; return false end
  local dx,dy=pos.x-c:getX(),pos.y-c:getY()
  if dx*dx+dy*dy>(p.radius or 10)^2 or math.floor(pos.z)~=math.floor(c:getZ()) then complete=false; return false end
  local steps=math.max(1,math.ceil(math.max(math.abs(dx),math.abs(dy))*2))
  for i=0,steps do
   if not getCell():getGridSquare(math.floor(c:getX()+dx*i/steps),math.floor(c:getY()+dy*i/steps),math.floor(pos.z)) then complete=false; return false end
  end
  local objects=kind=='door' and sq:getObjects() or sq:getMovingObjects()
  local count=objects and objects:size()
  if type(count)~='number' or count>32 then complete=false; return false end
  for i=0,count-1 do
   examined=examined+1; if examined>budget then complete=false; return false end
   local object=objects:get(i)
   local match=kind=='npc' and object and object.getModData and object:getModData().ARAY_Uuid==entry.uuid
    or kind=='zombie' and object and instanceof(object,'IsoZombie') and not object:isDead()
     and math.abs(object:getX()-pos.x)<.01 and math.abs(object:getY()-pos.y)<.01
    or kind=='door' and object and (instanceof(object,'IsoDoor') or instanceof(object,'IsoThumpable') and object.isDoor and object:isDoor())
   if match then
    local ok,yes=pcall(function() return c:CanSee(object) end)
    if not ok or type(yes)~='boolean' then complete=false end
    if ok and yes==true then return true end
   end
  end
  return false
 end
 for _,spec in ipairs({{'zombies',p.nearby_zombies,'zombie',12},{'nearby_npcs',p.nearby_npcs,'npc',12},{'doors',p.doors,'door',8}}) do
  for _,entry in ipairs(spec[2] or {}) do
   if #out[spec[1]]>=spec[4] then complete=false; break end
   if visible(entry,spec[3]) then out[spec[1]][#out[spec[1]]+1]=C.copy(entry) end
   if examined>budget then break end
  end
 end
 out.visibility.complete=out.visibility.known and complete and p.scan.complete==true; out.visibility.examined=math.min(examined,budget)
 return out
end
-- Reduce whole fields/entries, never cut serialized JSON. Unknown/partial stays explicit.
function Q.compact(context,message,budget)
 local text=(message or ''):lower()
 local inv=context.inventory
 if inv then
  local items={}
  for index,item in ipairs(inv.items or {}) do
   items[#items+1]={item_id=item.item_id,full_type=item.full_type,quantity=item.quantity,_index=index}
  end
  table.sort(items,function(a,b)
   local function relevant(v)
    local name=type(v.full_type)=='string' and v.full_type:match('[^.]+$')
    return name and #name>=3 and text:find(name:lower(),1,true)~=nil
   end
   local ar,br=relevant(a),relevant(b)
   if ar~=br then return ar==true end
   return a._index<b._index
  end)
  for _,item in ipairs(items) do item._index=nil end
  context.inventory={uuid=inv.uuid,world_id=inv.world_id,complete=inv.complete,reason=inv.reason,
   items=items,weight=inv.weight,capacity=inv.capacity}
 end
 local survival=context.survival or {}
 context.survival={health=survival.health,conditions=survival.conditions,needs=survival.needs,needs_policy=survival.needs_policy}
 context.survival_partial=true
 context.observation=nil; context.scan=nil
 local inventoryRelevant=text:find('invent',1,true) or text:find('itens',1,true) or text:find('carrega',1,true)
 if context.inventory and not inventoryRelevant then
  while #context.inventory.items>8 do
   table.remove(context.inventory.items); context.inventory.complete=false
   context.inventory.reason='question_relevance'; context.context_partial=true
  end
 end
 local keys=inventoryRelevant and {'nearby_npcs','doors','zombies'} or {'nearby_npcs','doors'}
 local function fits() local s=J.encode(context); return s and ArayHuman.Text.bytes(s)<=budget end
 for _,key in ipairs(keys) do
  while not fits() and #(context[key] or {})>0 do table.remove(context[key]); context.context_partial=true end
 end
 while not fits() and context.inventory and #context.inventory.items>0 do
  table.remove(context.inventory.items); context.inventory.complete=false; context.inventory.reason='chat_byte_budget'; context.context_partial=true
 end
 while not fits() and #(context.zombies or {})>0 do table.remove(context.zombies); context.context_partial=true end
 if not fits() then context.survival={health=survival.health}; context.survival_partial=true end
 if context.context_partial and context.visibility then context.visibility.complete=false end
 return fits()
end
function Q.context(id,message)
 local c,why=C.actor(id); if not c then return nil,why end
 local s=ArayHuman.AgentState.getSnapshot(id); local p=ArayHuman.Perception.getSnapshot(id)
 if not s or not s.active or not p or not p.player.known or not p.player.same_floor.value
  or not p.player.distance.known or p.player.distance.value>10 then return nil,"conversation_out_of_range" end
 local inventory=ArayHuman.Inventory.readInventory(id)
 local seen=observed(c,p)
 local context={schema_version=1,uuid=id,world_id=C.world(),captured_at_ms=C.now(),
  perception_captured_at_ms=p.captured_at_ms,observation=p.observation,position=s.position,
  execution=s.runtime and s.runtime.execution,
  player={known=true,distance=p.player.distance},threat={known=#seen.zombies>0,observed_zombies=#seen.zombies},survival=s.survival,inventory=inventory,
  nearby_npcs=seen.nearby_npcs,zombies=seen.zombies,doors=seen.doors,obstacles=seen.obstacles,
  visibility=seen.visibility,scan=p.scan,
  observation_id=s.observation_id}
 local compacted=Q.compact(context,message,12000)
 local encoded=J.encode(context)
 if not compacted or not encoded or ArayHuman.Text.bytes(encoded)>12000 then return nil,"context_budget" end
 log('perception_context',id,'bytes='..ArayHuman.Text.bytes(encoded)..' captured_at_ms='..context.captured_at_ms)
 return context
end
function Q.fingerprint(context)
 local facts={}; local inv=context.inventory or {}
 for _,item in ipairs(inv.items or {}) do
  facts[#facts+1]=tostring(item.item_id)..':'..tostring(item.full_type)..':'..tostring(item.quantity and item.quantity.value)
 end
 table.sort(facts)
 local survival=context.survival or {}; local hp=survival.health or {}; local panic=(survival.needs or {}).panic or {}
 local execution=context.execution or {}
 return table.concat(facts,'|')..'/'..tostring(inv.complete)..'/'..#(context.zombies or {})..'/'..#(context.doors or {})
  ..'/'..tostring(hp.value)..'/'..tostring(panic.value)..'/'..tostring(execution.action)..'/'..tostring(execution.state)
end
function Q.intent(message)
 local t=ArayHuman.Text.compare(message):gsub('[%p]',' '):gsub('%s+',' '):match('^%s*(.-)%s*$')
 if t=='me siga' or t=='siga me' or t=='siga' or t=='venha comigo' or t=='pode me seguir' or t=='me siga por favor' then return 'FOLLOW_PLAYER' end
 if t=='pare' or t=='parar' or t=='fique aqui' or t=='pare por favor' or t=='pode parar' or t=='nao me siga' then return 'STOP' end
 if t=='va ate ali' or t=='va ate ali por favor' or t=='pode ir ate ali' then return 'WALK' end
 return nil
end
function Q.command(id,action,context,target)
 log('chat_intent',id,'action='..action..' source=human_input')
 if C.world()~=seenWorld then active={}; seenWorld=C.world() end
 if ArayHuman.Executor.getControlState(id).emergency_priority then return false,"emergency_priority" end
 local threat=ArayHuman.Perception.observeThreats(id)
 if threat and threat.active and threat.immediate then return false,"emergency_priority" end
 if action=='WALK' then
  if not target then return false,"destination_required: selecione um destino; use o menu Ir até" end
  local ok,why=ArayHuman.AgentState.validateCandidate(id,'WALK',target,context.observation_id)
  if not ok then return false,why end
 elseif target~=nil then return false,"unexpected_target" end
 serial=serial+1; local rid='chat-action:'..serial..':'..C.now()
 log('action_requested',id,'action_id='..rid..' action='..action)
 local ok,result=ArayHuman.Executor.requestLocomotion({uuid=id,world_id=C.world(),action_id=rid,
  action=action=='WALK' and 'MOVE_TO' or action,movement_mode=action=='WALK' and 'WALK' or nil,
  source='manual',target_id=target,expires_at_ms=C.now()+30000})
 if ok then
  if active[id] and ArayHuman.Chat and ArayHuman.Chat.actionResult then
   ArayHuman.Chat.actionResult(id,active[id].action_id,{state='CANCELLED',reason='superseded'})
  end
  active[id]={action_id=rid,world_id=C.world(),character=C.actor(id)}
 else log('action_result',id,'action_id='..rid..' result='..tostring(result)) end
 return ok,ok and rid or result
end
local last=0
function Q.update()
 if C.world()~=seenWorld then active={}; seenWorld=C.world() end
 if C.now()-last<250 then return end; last=C.now()
 for id,r in pairs(active) do
  if C.actor(id)~=r.character then
   if ArayHuman.Chat and ArayHuman.Chat.actionResult then ArayHuman.Chat.actionResult(id,r.action_id,{state='CANCELLED',reason='actor_changed'}) end
   active[id]=nil
  else
   local result=ArayHuman.Locomotion.getResult(id,r.action_id)
   if result then
    if ArayHuman.Chat and ArayHuman.Chat.actionResult then ArayHuman.Chat.actionResult(id,r.action_id,result) end
    log('action_result',id,'action_id='..r.action_id..' state='..result.state..' result='..tostring(result.result))
    Q.say(id,result.state=='COMPLETED' and 'Ação concluída: '..tostring(result.result) or 'Ação encerrada: '..tostring(result.result))
    active[id]=nil
   end
  end
 end
end
Events.OnTick.Add(Q.update)
