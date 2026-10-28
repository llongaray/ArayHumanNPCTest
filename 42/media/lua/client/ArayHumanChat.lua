-- Conversation protocol 2: UUID/world/session ownership, verbal-only remote replies.
require "ArayHumanConversation"
require "ArayHumanJson"
require "ArayHumanRecipients"
require "ArayHumanNeuralInput"
ArayHuman=ArayHuman or {}
local H={}; ArayHuman.Chat=H
local C,J,Q=ArayHuman.Capabilities,ArayHuman.Json,ArayHuman.Conversation
local pending,sessions,histories={},{},{}
local memories,seen,lastGroup={},{},-100000
local playerSession=nil
local worldSeen,playerSeen,serial=nil,nil,0
local function log(event,id,detail) print('[ARAY] event='..event..' uuid='..tostring(id)..' '..tostring(detail or '')) end
local function selected(id)
 if id then return id end
 local c=ArayHuman.getNpc and ArayHuman.getNpc(); return c and c:getModData().ARAY_Uuid
end
local function check()
 local w=C.world(); local player=ArayHuman.getLocalPlayer and ArayHuman.getLocalPlayer()
 if w~=worldSeen or player~=playerSeen then
  if w~=worldSeen then memories={} else
   for _,events in pairs(memories) do for _,event in ipairs(events) do
    if event.result.state=='CHAT_REQUESTED' then event.result={state='DISCARDED',reason='speaker_session_changed'} end
   end end
  end
  pending={}; sessions={}; histories={}; seen={}; lastGroup=-100000; worldSeen=w; playerSeen=player
  serial=serial+1; playerSession='player-session:'..C.now()..':'..serial
 end
end
local function add(id,role,text)
 local list=histories[id] or {}; histories[id]=list
 list[#list+1]={role=role,text=text}; while #list>20 do table.remove(list,1) end
end
local function notify(id,success,text,error)
 if ArayHuman.ChatWindow and ArayHuman.ChatWindow.onChatResponse then
  ArayHuman.ChatWindow.onChatResponse(success,text,error,id)
 end
end
local function speak(id,text)
 -- Same bubble implementation and chunk size; no renderer/style/position changes.
 for _,chunk in ipairs(ArayHuman.Text.chunks(text,200)) do Q.say(id,chunk) end
end
local function sendOne(message,uuid,targetId,route)
 check()
 if type(message)~='string' or not message:match('%S') or #message>2000 then return false,'message_invalid' end
 local context,why=Q.context(uuid,message); if not context then return false,why end
 local action=Q.intent(route.body)
 if action then
  local ok,result=Q.command(uuid,action,context,targetId)
  local text=ok and 'Comando aceito; o resultado será confirmado pelo executor.' or 'Não executei: '..tostring(result)
  speak(uuid,text); add(uuid,'user',message); add(uuid,'assistant',text); notify(uuid,ok,text,ok and nil or result)
  return ok,result
 end
 for _,r in pairs(pending) do if r.uuid==uuid then return false,'chat_pending' end end
 local n=0; for _ in pairs(pending) do n=n+1 end; if n>=4 then return false,'chat_queue_full' end
 local session=sessions[uuid]
 if not session then
  local count=0; for _ in pairs(sessions) do count=count+1 end; if count>=128 then return false,'session_budget' end
  serial=serial+1; session={id='chat-'..C.now()..'-'..serial,started=C.now(),sequence=0}; sessions[uuid]=session
 end
 session.sequence=session.sequence+1; serial=serial+1
 local rid=C.now()..'-chat-'..serial
 local request={protocol_version=2,id=rid,kind='chat_request',world_id=worldSeen,npc_id=uuid,
  session_id=session.id,session_started_at_ms=session.started,sequence=session.sequence,
  issued_at_ms=C.now(),expires_at_ms=C.now()+20000,message=message,context=context,
  routing={schema_version=1,world_id=worldSeen,recipients=route.uuids,event_id=route.event_id,
   captured_at_ms=route.captured_at_ms,collective=route.collective},agent_input=ArayHuman.NeuralInput.observe(uuid)}
 if request.agent_input then
  local events=H.getEvents(uuid); local recent={}
  for i=math.max(1,#events-1),#events do recent[#recent+1]=events[i] end
  while #recent>0 and (not J.encode(recent) or ArayHuman.Text.bytes(J.encode(recent))>6000) do table.remove(recent,1) end
  request.agent_input.conversation_memory=recent
 end
 local payload=J.encode(request)
 -- Include the actual encoded envelope and question in the wire budget.
 if payload and ArayHuman.Text.bytes(payload)>32768 then
  local overhead=ArayHuman.Text.bytes(payload)-ArayHuman.Text.bytes(assert(J.encode(context)))
  if not Q.compact(context,message,math.max(512,32768-overhead-128)) then return false,'context_budget' end
  payload=J.encode(request)
 end
 if not payload or ArayHuman.Text.bytes(payload)>32768 then return false,'context_budget' end
 local ok=pcall(function()
  local f=getFileWriter('ArayHumanNPCTest/to_py/'..rid..'.json.tmp',true,false); assert(f); f:write(payload); f:close()
  f=getFileWriter('ArayHumanNPCTest/to_py/'..rid..'.ok',true,false); assert(f); f:write(rid); f:close()
 end)
 if not ok then return false,'chat_mailbox_unavailable' end
 pending[rid]={uuid=uuid,character=C.actor(uuid),request=request}; add(uuid,'user',message)
 log('chat_intent',uuid,'action=VERBAL_ONLY request_id='..rid)
 return true,rid
end
local function finish(uuid,id,result)
 for _,event in ipairs(memories[uuid] or {}) do
  if event.request_id==id then event.result=result; event.result_at_ms=C.now() end
 end
end
function H.getEvents(uuid)
 check(); return J.decode(J.encode(memories[uuid] or {}))
end
function H.actionResult(uuid,action_id,result) check(); finish(uuid,action_id,result) end
function H.sendMessage(message,ignoredSelection,targetId,expectedWorld)
 check()
 local route=ArayHuman.Recipients.resolve(message,expectedWorld or worldSeen)
 if route.status~='resolved' then return false,route.status end
 if #route.uuids>8 then return false,'recipient_budget' end
 if targetId and #route.uuids~=1 then return false,'target_requires_single_recipient' end
 local action=Q.intent(route.body)
 local required=action and 0 or (route.collective and 1 or #route.uuids)
 local count=0; for _ in pairs(pending) do count=count+1 end
 if count+required>4 then return false,'chat_queue_full' end
 if action~='STOP' and #route.uuids>1 and C.now()-lastGroup<2000 then return false,'group_cooldown' end
 local actors,contexts={},{}
 for _,id in ipairs(route.uuids) do
  local actor=C.actor(id); if not actor then return false,'recipient_unavailable' end
  local ctx,why=Q.context(id,message); if not ctx then return false,why end
  if not action and H.isPending(id) then return false,'chat_pending' end
  if action then
   local threat=ArayHuman.Perception.observeThreats(id)
   if ArayHuman.Executor.getControlState(id).emergency_priority or threat and threat.active and threat.immediate then return false,'emergency_priority' end
  end
  actors[id]=actor; contexts[id]=ctx
 end
 local memoryCount=0; for _ in pairs(memories) do memoryCount=memoryCount+1 end
 for _,id in ipairs(route.uuids) do if not memories[id] then memoryCount=memoryCount+1 end end
 if memoryCount>128 then return false,'memory_registry_full' end
 local key=worldSeen..'/'..message..'/'..tostring(targetId)
 if action and seen[key] and C.now()-seen[key]<1000 then return false,'duplicate_message' end
 seen[key]=C.now()
 local size=0; for k,at in pairs(seen) do if C.now()-at>2000 then seen[k]=nil else size=size+1 end end
 if size>128 then seen={} end
 serial=serial+1; route.event_id='speech:'..C.now()..':'..serial
 local response,results=nil,{}
 for index,id in ipairs(route.uuids) do
  if C.world()~=route.world_id or C.actor(id)~=actors[id] then return false,'recipient_changed',results end
  local list=memories[id] or {}; memories[id]=list
  local event={schema_version=1,event_id=route.event_id,uuid=id,world_id=worldSeen,
   speaker={kind='player',session=playerSession},recipients=route.uuids,text=message,
   timestamp_ms=C.now(),context={observation_id=contexts[id].observation_id,threat=contexts[id].threat},result={state='RECEIVED'}}
  list[#list+1]=event; while #list>8 do table.remove(list,1) end
  if route.collective and not action and index>1 then
   event.result={state='OBSERVED_SILENT',reason='collective_verbal_budget'}
   add(id,'user',message)
  else
   local ok,value=sendOne(message,id,targetId,route)
   if ok and action then
    for rid,r in pairs(pending) do if r.uuid==id then
     finish(id,rid,{state='DISCARDED',reason='manual_command'}); pending[rid]=nil
    end end
   end
   event.request_id=ok and value or nil
   event.result={state=ok and (action and 'ACTION_REQUESTED' or 'CHAT_REQUESTED') or 'REJECTED',reason=ok and nil or value}
   results[#results+1]={uuid=id,ok=ok,result=value}
   if not ok then return false,value,results end
   response=response or value
  end
 end
 if #route.uuids>1 then lastGroup=C.now() end
 return true,response,results
end
function H.isPending(uuid)
 check(); for _,r in pairs(pending) do if not uuid or r.uuid==uuid then return true end end; return false
end
function H.getHistory(uuid)
 check(); local result={}
 for _,entry in ipairs(histories[selected(uuid)] or {}) do
  result[#result+1]={role=entry.role,text=entry.text}
 end
 return result -- bounded original strings; generic byte truncation could split UTF-8.
end
function H.clearHistory(uuid) check(); uuid=selected(uuid); if uuid then histories[uuid]={}; sessions[uuid]=nil end end
local last,cursor=0,1
function H.update()
 check(); if C.now()-last<75 then return end; last=C.now()
 local ids={}; for id in pairs(pending) do ids[#ids+1]=id end; table.sort(ids)
 for _=1,math.min(#ids,2) do
  if cursor>#ids then cursor=1 end
  local rid=ids[cursor]; cursor=cursor+1; local r=pending[rid]
  if r then
   local req=r.request; local session=sessions[r.uuid]
   if C.actor(r.uuid)~=r.character or not session or session.id~=req.session_id then finish(r.uuid,rid,{state='CANCELLED',reason='actor_or_session_changed'}); pending[rid]=nil
   elseif C.now()>=req.expires_at_ms then
    pending[rid]=nil; finish(r.uuid,rid,{state='EXPIRED'}); speak(r.uuid,'Conversa não concluída: chat_timeout'); notify(r.uuid,false,nil,'chat_timeout')
   else
    local ok,text=pcall(function()
     local f=getFileReader('ArayHumanNPCTest/to_lua/'..rid..'.json',false); if not f then return nil end
     local out={}; local count=0; local line=f:readLine()
     while line do count=count+ArayHuman.Text.bytes(line); if count>65536 then f:close(); return nil end; out[#out+1]=line; line=f:readLine() end
     f:close(); return table.concat(out)
    end)
    local data=ok and text and J.decode(text)
    if data and data.id==rid and data.kind=='chat_response' and data.protocol_version==2
     and data.npc_id==r.uuid and data.world_id==worldSeen and data.session_id==req.session_id
     and data.session_started_at_ms==req.session_started_at_ms and data.sequence==req.sequence
     and data.expires_at_ms==req.expires_at_ms and data.verbal_only==true and data.executable==false
     and data.action==nil and data.decision==nil then
     pending[rid]=nil
     local current=Q.context(r.uuid,req.message)
     if not current or Q.fingerprint(current)~=Q.fingerprint(req.context) then
      finish(r.uuid,rid,{state='DISCARDED',reason='perception_changed_retry'}); notify(r.uuid,false,nil,'perception_changed_retry'); Q.say(r.uuid,'Meu contexto mudou. Pergunte novamente.')
     elseif data.success==true and type(data.reply)=='string' and #data.reply<=4800 then
      local reply=data.reply
      finish(r.uuid,rid,{state='REPLIED',speaker='npc',text=reply})
      add(r.uuid,'assistant',reply); speak(r.uuid,reply); notify(r.uuid,true,reply)
      log('chat_reply',r.uuid,'request_id='..rid..' verbal_only=true')
     else
      local reason=type(data.error)=='string' and data.error:gsub('[%c]',' '):sub(1,160) or 'chat_backend_failed'
      finish(r.uuid,rid,{state='FAILED',reason=reason}); speak(r.uuid,'Conversa não concluída: '..reason); notify(r.uuid,false,nil,reason)
      log('chat_reply',r.uuid,'request_id='..rid..' success=false reason='..reason)
     end
    end
   end
  end
 end
end
Events.OnTick.Add(H.update)
