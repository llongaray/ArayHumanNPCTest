-- Initial visuals, immutable per world/UUID. Uses the native LastStand round-trip.
require "ArayHumanJson"
require "ArayHumanCapabilities"
ArayHuman=ArayHuman or {}
local V={}; ArayHuman.Appearance=V
local J,C=ArayHuman.Json,ArayHuman.Capabilities
local jobs,seenWorld,serial={},nil,0
local function check()
 local w=C.world(); if w~=seenWorld then jobs={}; seenWorld=w end; return w
end
local function call(o,m,...) local a={...}; local ok,v=pcall(function() return o[m](o,unpack(a)) end); if ok then return v end end
local function log(id,event,reason) print("[ARAY-VISUAL] uuid="..tostring(id).." event="..event.." reason="..tostring(reason)) end
local function clothingString(item)
 local visual=call(item,"getVisual")
 if not visual then return nil,"clothing_visual_unavailable" end
 local available,owner=pcall(function() return visual:getInventoryItem() end)
 if not available then return nil,"clothing_owner_api" end
 if owner and owner~=item then return nil,"clothing_owner_mismatch" end
 if not owner then
  local linked=pcall(function() visual:setInventoryItem(item) end)
  if not linked then return nil,"clothing_owner_api" end
 end
 if call(visual,"getInventoryItem")~=item then return nil,"clothing_owner_unavailable" end
 local text=call(visual,"getLastStandString")
 if type(text)~="string" or #text>4096 then return nil,"UNSUPPORTED_clothing_visual" end
 return text
end
local function send(id,op,visual)
 local w=check(); if not w or not C.validId(id,36) then return false,"appearance_identity" end
 local count=0; for _ in pairs(jobs) do count=count+1 end
 if not jobs[id] and count>=128 then return false,"appearance_registry_full" end
 serial=serial+1; local rid=C.now().."-visual-"..serial
 local payload=J.encode({id=rid,kind="appearance_request",world_id=w,npc_id=id,op=op,visual=visual})
 if not payload then return false,"appearance_budget" end
 local ok=pcall(function()
  local f=getFileWriter("ArayHumanNPCTest/to_py/"..rid..".json.tmp",true,false); assert(f); f:write(payload); f:close()
  f=getFileWriter("ArayHumanNPCTest/to_py/"..rid..".ok",true,false); assert(f); f:write(rid); f:close()
 end)
 if not ok then return false,"appearance_mailbox_unavailable" end
 jobs[id]={id=rid,state="PENDING",sent=C.now(),world_id=w,op=op,visual=visual}
 return true
end
function V.get(id)
 check(); local r=jobs[id]
 if not r then local ok,why=send(id,"get"); if not ok then return nil,why end; return nil,"appearance_pending" end
 if r.state=="PENDING" then return nil,"appearance_pending" end
 if r.state=="FAILED" then return nil,r.reason end
 if not r.visual then return nil,"missing" end
 local copy=J.decode(J.encode(r.visual)); return copy,"found"
end
function V.capture(c,id)
 if c~=ArayHuman.getNpcByUuid(id) or c==ArayHuman.getLocalPlayer() or (call(c,"getModData") or {}).ARAY_Uuid~=id then return nil,"appearance_owner" end
 local human=call(c,"getHumanVisual"); local body=call(human,"getBodyVisuals")
 if call(body,"size")~=0 then return nil,"UNSUPPORTED_body_visuals_migration_required" end
 local text=call(human,"getLastStandString"); local female=call(c,"isFemale")
 local worn=call(c,"getWornItems"); local count=call(worn,"size")
 if type(text)~="string" or #text>8192 or type(female)~="boolean" or type(count)~="number" or count>32 then return nil,"UNSUPPORTED_visual_api" end
 local visual={schema_version=1,female=female,human=text,clothes={}}
 for i=0,count-1 do
  local item=call(worn,"getItemByIndex",i); local s,why=clothingString(item)
  if not s then return nil,why end
  visual.clothes[#visual.clothes+1]=s
 end
 return visual
end
function V.saveInitial(c,id)
 local data,why=V.capture(c,id); if not data then log(id,"capture_failed",why); return false,why end
 local r=jobs[id]
 if r and r.state=="READY" and r.visual then return true,"already_stored" end
 return send(id,"create",data)
end
-- Descriptor/actor must be new private spawn objects, never registered live actors.
function V.prepare(desc,data)
 if not isClient or not isServer or isClient() or isServer() then return false,"UNSUPPORTED_visual_authority" end
 local ok=pcall(function()
  assert(data.schema_version==1 and type(data.female)=="boolean")
  assert(desc~=(ArayHuman.getLocalPlayer() and ArayHuman.getLocalPlayer():getDescriptor()))
  desc:setFemale(data.female); assert(desc:getHumanVisual():loadLastStandString(data.human))
 end)
 return ok,ok and nil or "appearance_descriptor_failed"
end
function V.applyNew(c,data)
 if not isClient or not isServer or isClient() or isServer() then return false,"UNSUPPORTED_visual_authority" end
 if c==ArayHuman.getLocalPlayer() or call(c,"isNPC")~=false then return false,"appearance_not_new_actor" end
 local ok=pcall(function()
  assert(c:getHumanVisual():loadLastStandString(data.human))
  assert(c:getWornItems():size()==0,"new_actor_has_clothes")
  for _,s in ipairs(data.clothes) do
   local item=ItemVisual.createLastStandItem(s); assert(item,"clothing_asset_missing")
   local text,why=clothingString(item); assert(text==s,why or "clothing_roundtrip_mismatch")
   c:getInventory():AddItem(item); c:setWornItem(item:getBodyLocation(),item)
  end
  assert(c:getHumanVisual():getLastStandString()==data.human,"human_roundtrip_mismatch")
 end)
 return ok,ok and nil or "appearance_restore_failed"
end
local last=0
function V.update()
 check(); if C.now()-last<100 then return end; last=C.now(); local budget=2
 for id,r in pairs(jobs) do if r.state=="PENDING" and budget>0 then
  budget=budget-1
  local ok,text=pcall(function()
   local f=getFileReader("ArayHumanNPCTest/to_lua/"..r.id..".json",false); if not f then return nil end
   local chunks={}; local n=0; local line=f:readLine()
   while line do n=n+#line; if n>65536 then f:close(); return nil end; chunks[#chunks+1]=line; line=f:readLine() end
   f:close(); return table.concat(chunks)
  end)
  local data=ok and text and J.decode(text)
  if data and data.id==r.id and data.kind=="appearance_response" and data.npc_id==id and data.world_id==seenWorld then
   if data.ok then r.state="READY"; r.visual=data.found and data.visual or nil; log(id,"appearance_ready",r.op)
   else r.state="FAILED"; r.reason=data.error or "appearance_service_failed"; log(id,"appearance_failed",r.reason) end
  elseif C.now()-r.sent>=15000 then r.state="FAILED"; r.reason="appearance_timeout"; log(id,"appearance_failed",r.reason) end
 end end
end
Events.OnTick.Add(V.update)
