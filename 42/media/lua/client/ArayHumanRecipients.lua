-- Preparation only. No sends, actions, inference, UI selection or message interpretation.
require "ArayHumanText"
require "ArayHumanCapabilities"
ArayHuman=ArayHuman or {}
local R={}; ArayHuman.Recipients=R
local aliases,world={},nil
local function check()
 local current=ArayHuman.Capabilities.world()
 if current~=world then aliases={}; world=current end
 return current
end
function R.setAliases(uuid,list,expectedWorld)
 local current=check()
 if expectedWorld and expectedWorld~=current then return false,'world_mismatch' end
 if not ArayHuman.Capabilities.actor(uuid) or type(list)~='table' or #list>8 then return false,'aliases_invalid' end
 local copy={}
 for _,name in ipairs(list) do
  if type(name)~='string' or #name==0 or #name>64 or name:find('[,:@&%c]') then return false,'alias_invalid' end
  copy[#copy+1]=name
 end
 aliases[uuid]=copy; return true
end
function R.resolve(message,expectedWorld)
 local current=check()
 local result={schema_version=1,world_id=current,captured_at_ms=ArayHuman.Capabilities.now(),uuids={},status='no_recipient'}
 if expectedWorld and expectedWorld~=current then result.status='world_mismatch'; return result end
 if not current or type(message)~='string' or ArayHuman.Text.bytes(message)>2000 then result.status='invalid_message'; return result end
 local split=message:find(':',1,true) or message:find(',',1,true)
 local address=split and message:sub(1,split-1)
 if not address then return result end
 result.body=message:sub(split+1):match('^%s*(.-)%s*$')
 if result.body=='' then result.status='empty_message'; return result end
 result.collective=false
 address=ArayHuman.Text.compare(address):gsub('@','')
 local map,all={},{}
 local function add(name,id)
  local key=ArayHuman.Text.compare(name)
  if key=='' then return end
  map[key]=map[key] or {}; map[key][id]=true
 end
 local roster=ArayHuman.rosterSnapshot and ArayHuman.rosterSnapshot() or {}
 if #roster>128 then result.status='roster_budget'; return result end
 for _,entry in ipairs(roster) do
  local c=ArayHuman.Capabilities.actor(entry.uuid)
  if c then
   all[entry.uuid]=true
   local md=c:getModData(); add(md.ARAY_Name or '',entry.uuid)
   local ok,desc=pcall(function() return c:getDescriptor() end)
   if ok and desc then
    local valid,first,last=pcall(function() return desc:getForename(),desc:getSurname() end)
    if valid then add(first or '',entry.uuid); add((first or '')..' '..(last or ''),entry.uuid) end
   end
   for _,name in ipairs(aliases[entry.uuid] or {}) do add(name,entry.uuid) end
  end
 end
 local chosen={}
 if address=='voces' or address=='pessoal' or address=='todos' then
  if map[address] then result.status='ambiguous_recipient'; return result end
  chosen=all; result.collective=true
 else
  address=address:gsub(' e ', ','):gsub('%s*&%s*',',')
  for name in (address..','):gmatch('(.-),') do
   local candidates=map[ArayHuman.Text.compare(name)]
   if not candidates then result.status='unknown_recipient'; return result end
   local count,id=0,nil; for candidate in pairs(candidates) do count=count+1; id=candidate end
   if count~=1 then result.status='ambiguous_recipient'; return result end
   chosen[id]=true
  end
 end
 for id in pairs(chosen) do result.uuids[#result.uuids+1]=id end
 table.sort(result.uuids)
 result.status=#result.uuids>0 and 'resolved' or 'no_recipient'
 return result
end
