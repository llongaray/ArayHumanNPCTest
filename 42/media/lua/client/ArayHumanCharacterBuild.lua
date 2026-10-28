-- Native character creation, explicit proposals only. No progression setters or policy loop.
require "ArayHumanCapabilities"
ArayHuman=ArayHuman or {}
local B={schema_version=1,config={maxProfessions=64,maxTraits=256,maxSkills=128,maxSelected=32,maxPrepared=64,ttlMs=30000,profileIntervalMs=1000,maxProfiles=128}}
ArayHuman.CharacterBuild=B
local C=ArayHuman.Capabilities
local prepared,seenWorld,serial={},nil,0
local profileCache={}
local function call(o,name,...)
 local args={...}; local ok,v=pcall(function() if o and o[name] then return o[name](o,unpack(args)) end end)
 if ok then return v end
end
local function integer(v) return C.finite(v) and v%1==0 end
local function id(v) local n=call(v,"getName"); return type(n)=="string" and #n<=128 and n or nil end
local function list(o,limit)
 local n=call(o,"size"); if not integer(n) or n<0 or n>limit then return nil end
 local r={}; for i=0,n-1 do local v=call(o,"get",i); if v==nil then return nil end; r[#r+1]=v end
 return r
end
local function ids(o)
 local items=list(o,B.config.maxTraits); if not items then return nil end
 local r={}; for _,v in ipairs(items) do local name=id(v); if not name then return nil end; r[#r+1]=name end
 return r
end
local function world()
 local w=C.world(); if w~=seenWorld then prepared={}; profileCache={}; seenWorld=w end
 return w
end
local function dataCopy(v,depth)
 depth=depth or 0
 if depth>12 then error("build_data_depth") end
 if type(v)~="table" then return v end
 local r={}; for k,x in pairs(v) do r[k]=dataCopy(x,depth+1) end
 return r
end
local function same(a,b)
 if type(a)~=type(b) then return false end
 if type(a)~="table" then return a==b end
 for k,v in pairs(a) do if not same(v,b[k]) then return false end end
 for k in pairs(b) do if a[k]==nil then return false end end
 return true
end
local function boosts(o)
 if not o or not transformIntoKahluaTable then return nil end
 local n=call(o,"size"); if not integer(n) or n<0 or n>B.config.maxSkills then return nil end
 local ok,t=pcall(transformIntoKahluaTable,o); if not ok or type(t)~="table" then return nil end
 local r={}; local count=0
 for perk,level in pairs(t) do
  count=count+1; local key=call(perk,"getId")
  if count>B.config.maxSkills or type(key)~="string" or not integer(level) then return nil end
  r[key]=level
 end
 if count~=n then return nil end
 return r
end
local function nativeCatalog()
 if not world() then return nil,"world_unavailable" end
 local ok,ps,ts=pcall(function() return CharacterProfessionDefinition.getProfessions(),CharacterTraitDefinition.getTraits() end)
 if not ok then return nil,"native_definitions_unavailable" end
 ps=list(ps,B.config.maxProfessions); ts=list(ts,B.config.maxTraits)
 if not ps or not ts then return nil,"catalog_budget_or_api" end
 local cat={schema_version=1,world_id=world(),captured_at_ms=C.now(),professions={},traits={},complete=true,
  source="B42_native_definitions",application="experimental_native_singleplayer"}
 local native={professions={},traits={}}
 for _,set in ipairs({{ps,cat.professions,native.professions,false},{ts,cat.traits,native.traits,true}}) do
  for _,d in ipairs(set[1]) do
   local key=id(call(d,"getType")); local cost=call(d,"getCost"); local grants=ids(call(d,"getGrantedTraits"))
   local xp=boosts(call(d,"getXpBoosts"))
   if not key or set[2][key] or not integer(cost) or not grants or not xp then return nil,"definition_incomplete" end
   local row={id=key,cost=cost,grants=grants,xp_boosts=xp}
   if set[4] then
    row.free=call(d,"isFree"); row.excludes=ids(call(d,"getMutuallyExclusiveTraits"))
    if type(row.free)~="boolean" or not row.excludes then return nil,"trait_restrictions_unknown" end
    row.selectable=not row.free and cost~=0
    row.polarity=cost>0 and "positive_cost" or cost<0 and "negative_cost" or "free"
   end
   set[2][key]=row; set[3][key]=d
  end
 end
 local penalty=call(call(getSandboxOptions and getSandboxOptions(),"getOptionByName","NegativeTraitsPenalty"),"getValue")
 local free=SandboxVars and SandboxVars.CharacterFreePoints
 if not integer(penalty) or penalty<1 or penalty>4 or not integer(free) then return nil,"sandbox_budget_unknown" end
 cat.rules={free_points=free,negative_traits_penalty=penalty,
  formula="profession_cost + CharacterFreePoints - selected_trait_costs - negative_offset"}
 return cat,native
end
function B.getCatalog()
 local cat,reason=nativeCatalog()
 return cat and dataCopy(cat) or {schema_version=1,world_id=world(),complete=false,reason=reason}
end
local function proposalShape(p)
 if type(p)~="table" or getmetatable(p) then return false end
 for k in pairs(p) do if k~="schema_version" and k~="profession_id" and k~="trait_ids" then return false end end
 if p.schema_version~=1 or type(p.profession_id)~="string" or #p.profession_id>128
  or type(p.trait_ids)~="table" or getmetatable(p.trait_ids) or #p.trait_ids>B.config.maxSelected then return false end
 for k,v in pairs(p.trait_ids) do
  if not integer(k) or k<1 or k>#p.trait_ids or type(v)~="string" or #v>128 then return false end
 end
 return true
end
local function validate(p,cat)
 local r={schema_version=1,valid=false,proposal=proposalShape(p) and C.copy(p) or nil,rewards={implemented=false},
  learning={schema_version=1,reward={available=false},penalty={available=false}}}
 if not proposalShape(p) then r.reason="proposal_schema"; return r end
 local prof=cat.professions[p.profession_id]
 if not prof then r.reason="profession_unavailable"; return r end
 local effective,order,visiting={},{},{}
 local function include(key)
  if visiting[key] then return false end
  if effective[key] then return true end
  local t=cat.traits[key]; if not t or #order>=128 then return false end
  visiting[key]=true
  for _,g in ipairs(t.grants) do if not include(g) then return false end end
  visiting[key]=nil; effective[key]=true; order[#order+1]=key; return true
 end
 for _,key in ipairs(prof.grants) do if not include(key) then r.reason="invalid_granted_trait"; return r end end
 local balance=prof.cost+cat.rules.free_points; local selected={}
 for _,key in ipairs(p.trait_ids) do
  local t=cat.traits[key]
  if not t or not t.selectable or selected[key] or effective[key] then r.reason="trait_unavailable_or_duplicate"; return r end
  selected[key]=true; balance=balance-t.cost
  if not include(key) then r.reason="invalid_granted_trait"; return r end
 end
 local negative=0
 for _,key in ipairs(order) do
  local t=cat.traits[key]; if t.cost<0 then negative=negative+1 end
  for _,other in ipairs(t.excludes) do if not cat.traits[other] then r.reason="unknown_exclusion"; return r end
   if effective[other] then r.reason="incompatible_traits"; return r end end
 end
 local penalty=cat.rules.negative_traits_penalty; local offset=0
 if penalty==2 then offset=math.floor(negative/3) elseif penalty==3 then offset=math.floor(negative/2)
 elseif penalty==4 and negative>0 then offset=negative-1 end
 r.balance=balance-offset; r.negative_offset=offset; r.effective_traits=order
 r.valid=r.balance>=0; r.budget_status=r.balance==0 and "fully_used" or r.balance>0 and "unspent_suboptimal" or "invalid_negative"
 r.reason=not r.valid and "negative_balance" or nil; r.strategic_quality={known=false,reason="not_evaluated"}
 local expected={Fitness=5,Strength=5}
 for skill,n in pairs(prof.xp_boosts) do expected[skill]=(expected[skill] or 0)+n end
 for _,key in ipairs(order) do for skill,n in pairs(cat.traits[key].xp_boosts) do expected[skill]=(expected[skill] or 0)+n end end
 for skill,n in pairs(expected) do expected[skill]=math.max(0,math.min(10,n)) end
 r.expected_initial_levels=expected; r.rules=C.copy(cat.rules)
 return r
end
function B.validateProposal(proposal)
 local cat,reason=nativeCatalog()
 if not cat then return {schema_version=1,valid=false,reason=reason} end
 return validate(proposal,cat)
end
-- Trusted spawn hook: descriptor never comes from JSON. All native handles remain private.
function B.prepareDescriptor(desc,uuid,worldId,proposal)
 local w=world(); if not w or worldId~=w then return nil,"world_mismatch" end
 local _,why=C.actor(uuid,true); if why=="uuid_invalid" then return nil,why end
 if ArayHuman.getNpcByUuid and ArayHuman.getNpcByUuid(uuid) then return nil,"uuid_already_exists" end
 if not isClient or not isServer or isClient() or isServer() then return nil,"UNSUPPORTED_multiplayer_or_authority" end
 local cat,native=nativeCatalog(); if not cat then return nil,native end
 local validation=validate(proposal,cat); if not validation.valid then return nil,validation.reason,validation end
 local count=0
 for key,v in pairs(prepared) do if v.expires<=C.now() then prepared[key]=nil else count=count+1 end end
 if count>=B.config.maxPrepared then return nil,"prepared_budget" end
 if not desc or not desc.setProfessionSkills or not desc.setCharacterProfession then return nil,"descriptor_api_unavailable" end
 if desc==call(ArayHuman.getLocalPlayer and ArayHuman.getLocalPlayer(),"getDescriptor") then return nil,"player_descriptor_forbidden" end
 local roster=ArayHuman.rosterSnapshot and ArayHuman.rosterSnapshot() or {}
 if #roster>128 then return nil,"descriptor_owner_budget" end
 for _,entry in ipairs(roster) do
  if desc==call(entry.character,"getDescriptor") then return nil,"existing_descriptor_forbidden" end
 end
 local ok=pcall(function()
  desc:setProfessionSkills(native.professions[proposal.profession_id])
  desc:setCharacterProfession(native.professions[proposal.profession_id]:getType())
 end)
 if not ok then return nil,"descriptor_failed_discard" end
 serial=serial+1; local token="build:"..serial
 prepared[token]={uuid=uuid,world_id=w,descriptor=desc,validation=validation,native=native,expires=C.now()+B.config.ttlMs}
 return token,C.copy(validation)
end
function B.applyCreated(c,token)
 world(); local r=prepared[token]; prepared[token]=nil -- one-shot, including failures
 if not r or r.expires<=C.now() or r.world_id~=seenWorld then return false,"prepared_token_invalid" end
 local catalog,why=nativeCatalog(); if not catalog then return false,why end
 local latest=validate(r.validation.proposal,catalog)
 if not latest.valid or latest.balance~=r.validation.balance
  or not same(latest.rules,r.validation.rules) or not same(latest.effective_traits,r.validation.effective_traits)
  or not same(latest.expected_initial_levels,r.validation.expected_initial_levels) then return false,"build_rules_changed" end
 if c==ArayHuman.getLocalPlayer() or call(c,"getDescriptor")~=r.descriptor or call(c,"isNPC")~=false
  or call(c,"isDead")~=false then return false,"not_fresh_owned_character" end
 if r.descriptor==call(ArayHuman.getLocalPlayer(),"getDescriptor") then return false,"player_descriptor_forbidden" end
 local md=call(c,"getModData")
 if not md or md.ARAY_CharacterBuild or md.ARAY_IsNPC or md.ARAY_Uuid and md.ARAY_Uuid~=r.uuid then return false,"already_initialized" end
 local perks=list(PerkFactory and PerkFactory.PerkList,B.config.maxSkills)
 if not perks then return false,"perk_api_unavailable" end
 local map={}; for _,perk in ipairs(perks) do
  local key=call(perk,"getId"); if type(key)~="string" then return false,"perk_id_unavailable" end
  map[key]=perk
  if call(c,"getPerkLevel",perk)~=0 then return false,"not_pristine_levels" end
 end
 for key in pairs(r.validation.expected_initial_levels) do if not map[key] then return false,"expected_perk_unavailable" end end
 if not ArrayList or not ArrayList.new or not c.applyTraits or not c.applyProfessionRecipes or not c.applyCharacterTraitsRecipes then return false,"native_application_unavailable" end
 md.ARAY_Uuid=r.uuid
 md.ARAY_CharacterBuild={schema_version=1,world_id=seenWorld,uuid=r.uuid,status="APPLYING",initial=C.copy(r.validation),applied_at_ms=C.now()}
 local ok=pcall(function()
  local traits=ArrayList.new()
  for _,key in ipairs(r.validation.effective_traits) do traits:add(r.native.traits[key]:getType()) end
  c:applyTraits(traits)
  c:applyProfessionRecipes(); c:applyCharacterTraitsRecipes()
 end)
 if not ok then md.ARAY_CharacterBuild.status="FAILED_DO_NOT_REAPPLY"; return false,"native_application_failed_discard" end
 for _,key in ipairs(r.validation.effective_traits) do
  if call(call(c,"getCharacterTraits"),"get",call(r.native.traits[key],"getType"))~=true then
   md.ARAY_CharacterBuild.status="VERIFICATION_FAILED"; return false,"trait_verification_failed" end
 end
 local xp=call(c,"getXp")
 for key,perk in pairs(map) do
  local expected=r.validation.expected_initial_levels[key] or 0
  local level=call(c,"getPerkLevel",perk)
  local actualXP=call(xp,"getXP",perk)
  local expectedXP=call(perk,"getTotalXpForLevel",expected)
  if level~=expected or not C.finite(actualXP) or not C.finite(expectedXP) or math.abs(actualXP-expectedXP)>.001
   or call(xp,"getPerkBoost",perk)~=math.min(3,expected) then
   md.ARAY_CharacterBuild.status="VERIFICATION_FAILED"; return false,"level_or_xp_verification_failed" end
 end
 md.ARAY_CharacterBuild.status="APPLIED_VERIFIED"
 return true,C.copy(md.ARAY_CharacterBuild)
end
local function profile(c)
 local p={schema_version=1,available=c~=nil,captured_at_ms=C.now(),world_id=world(),
  profession=C.value(id(call(call(c,"getDescriptor"),"getCharacterProfession"))),
  traits={known=false,items={}},skills={known=false,items={}},xp={available=false},
  points={known=false,status="unavailable",reason="no_unspent_creation_points_on_live_character"}}
 if not c then p.reason="instance_unavailable"; return p end
 local traits=call(c,"getCharacterTraits"); local known=list(call(traits,"getKnownTraits"),B.config.maxTraits)
 if known then
  p.traits.known=true
  for _,t in ipairs(known) do
   local has=call(traits,"get",t); local key=id(t)
   if type(has)~="boolean" or not key then p.traits.known=false
   elseif has then p.traits.items[#p.traits.items+1]=key end
  end
 end
 local perks=list(PerkFactory and PerkFactory.PerkList,B.config.maxSkills); local xp=call(c,"getXp")
 if perks then
  p.skills.known=true
  for _,perk in ipairs(perks) do
   local key=call(perk,"getId")
   if not key then p.skills.known=false else p.skills.items[#p.skills.items+1]={id=key,
    level=C.value(call(c,"getPerkLevel",perk)),xp=C.value(call(xp,"getXP",perk)),xp_boost=C.value(call(xp,"getPerkBoost",perk))} end
  end
 end
 p.xp={total=C.value(call(xp,"getTotalXp")),level=C.value(call(xp,"getLevel"))}
 local marker=call(c,"getModData"); marker=marker and marker.ARAY_CharacterBuild
 if type(marker)=="table" and type(marker.initial)=="table" and integer(marker.initial.balance)
  and marker.uuid==(call(c,"getModData") or {}).ARAY_Uuid and marker.world_id==seenWorld then
  p.initial_build=C.copy(marker)
  p.points={known=true,value=marker.initial.balance,scope="initial_build_balance_not_spendable_progression"}
 end
 return p
end
local function cachedProfile(key,c)
 world(); local at=C.now(); local cached=profileCache[key]; local dead=call(c,"isDead")
 if not cached or cached.character~=c or cached.dead~=dead or at<cached.snapshot.captured_at_ms
  or at-cached.snapshot.captured_at_ms>=B.config.profileIntervalMs then
  local count=0; for _ in pairs(profileCache) do count=count+1 end
  if not cached and count>=B.config.maxProfiles then return {schema_version=1,available=false,reason="profile_budget"} end
  cached={character=c,dead=dead,snapshot=profile(c)}; profileCache[key]=cached
 end
 return dataCopy(cached.snapshot)
end
function B.getPlayerProfile()
 local c=ArayHuman.getLocalPlayer and ArayHuman.getLocalPlayer()
 if c and (call(c,"isDead")~=false or call(c,"isNPC")~=false) then c=nil end
 return cachedProfile("controlled_player",c)
end
function B.getProfile(uuid)
 local c,reason=C.actor(uuid,true); local p=c and cachedProfile(uuid,c) or profile(nil); p.uuid=uuid
 if not c then p.reason=reason end
 return p
end
function B.getProposalContext(role)
 if type(role)~="string" or not role:match("%S") or #role>500 then return nil,"role_invalid" end
 local cat=B.getCatalog(); if not cat.complete then return nil,cat.reason end
 return {schema_version=1,world_id=world(),captured_at_ms=C.now(),role=role,
  player_profile=B.getPlayerProfile(),catalog=cat,response_schema={schema_version=1,profession_id="native_id",trait_ids={}},executable=false}
end
-- Export only: do not write an existing SQLite or replay bonuses on loaded actors.
function B.exportRecord(uuid)
 local p=B.getProfile(uuid)
 return {schema_version=1,uuid=uuid,world_id=p.world_id,captured_at_ms=p.captured_at_ms,
  initial_build=p.initial_build,progression={profession=p.profession,traits=p.traits,skills=p.skills,xp=p.xp},
  persistence_status="export_only_existing_database_unchanged",restore_policy="observe_loaded_actor_never_reapply"}
end
