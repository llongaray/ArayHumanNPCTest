"""Native build rules and creation adapter: real Lua 5.1/5.4, simulated Java."""
import pytest
from test_agent_catalog import agent, inventory, observer, nav, physical, safety, lua
from test_executor import CLIENT


@pytest.fixture
def build(agent):
    agent.execute((CLIENT / "ArayHumanCharacterBuild.lua").read_text(encoding="utf-8"))
    agent.execute('''
        B=ArayHuman.CharacterBuild; calls={}; SandboxVars={CharacterFreePoints=0}; penalty=1
        getSandboxOptions=function() return {getOptionByName=function(_,key)
            assert(key=="NegativeTraitsPenalty"); return {getValue=function() return penalty end} end} end
        function javaList(values)
            local r=list(values); r.add=function(_,v) values[#values+1]=v end; return r
        end
        ArrayList={new=function() return javaList({}) end}
        function nativeId(name) return {getName=function() return name end} end
        skills={}; skillOrder={}
        for _,key in ipairs({"Fitness","Strength","Woodwork","Aiming"}) do
            local k=key; local o={getId=function() return k end,getTotalXpForLevel=function(_,n) return n*100 end}
            skills[k]=o; skillOrder[#skillOrder+1]=o
        end
        PerkFactory={PerkList=javaList(skillOrder)}
        function map(data) local n=0; for _ in pairs(data) do n=n+1 end; return {data=data,size=function() return n end} end
        transformIntoKahluaTable=function(m) return m.data end
        function definition(key,cost,free,grants,excludes,xp)
            local o={type=nativeId(key),cost=cost,free=free,grants=grants or {},excludes=excludes or {},xp=xp or {}}
            function o:getType() return self.type end
            function o:getCost() return self.cost end
            function o:isFree() return self.free end
            function o:getGrantedTraits() local r={}; for _,k in ipairs(self.grants) do r[#r+1]=nativeId(k) end; return javaList(r) end
            function o:getMutuallyExclusiveTraits() local r={}; for _,k in ipairs(self.excludes) do r[#r+1]=nativeId(k) end; return javaList(r) end
            function o:getXpBoosts() local r={}; for k,v in pairs(self.xp) do r[skills[k]]=v end; return map(r) end
            return o
        end
        professions={definition("unemployed",8,false),definition("carpenter",-2,false,{"craft"},nil,{Woodwork=3}),
            definition("veteran",-8,false,{"fearless"},nil,{Aiming=2})}
        traitRows={definition("strong",8,false,nil,{"weak"},{Strength=4}),
            definition("weak",-10,false,nil,{"strong"},{Strength=-5}),
            definition("brave",4,false,nil,{"coward"}),definition("coward",-2,false,nil,{"brave","fearless"}),
            definition("smoker",-4,false),definition("clumsy",-2,false),
            definition("craft",0,true,nil,nil,{Woodwork=1}),definition("fearless",0,true,nil,{"coward"}),
            definition("freetrait",0,true),definition("zero",0,false)}
        traits={}; for _,v in ipairs(traitRows) do traits[v.type:getName()]=v end
        CharacterProfessionDefinition={getProfessions=function() return javaList(professions) end}
        CharacterTraitDefinition={getTraits=function() return javaList(traitRows) end}
        function proposal(prof,selected) return {schema_version=1,profession_id=prof or "unemployed",trait_ids=selected or {}} end
        function descriptor()
            local d={boosts={}}
            function d:setProfessionSkills(p) calls[#calls+1]="descriptor_skills"; self.boosts={}; for k,v in pairs(p.xp) do self.boosts[k]=v end end
            function d:setCharacterProfession(p) calls[#calls+1]="descriptor_profession"; self.profession=p end
            function d:getCharacterProfession() return self.profession end
            return d
        end
        function fresh(d)
            local c=character(nil,.5,.5,0,"IsoPlayer"); c.md={}; c.levels={}; c.xps={}; c.selected={}; c.npcFlag=false
            function c:getDescriptor() return d end
            function c:isNPC() return self.npcFlag end
            function c:setNPC(v) self.npcFlag=v; calls[#calls+1]="npc_flag" end
            function c:getPerkLevel(p) return self.levels[p:getId()] or 0 end
            c.traits={get=function(_,t) return c.selected[t:getName()]==true end,
                getKnownTraits=function() local r={}; for k in pairs(c.selected) do r[#r+1]=nativeId(k) end; return javaList(r) end}
            function c:getCharacterTraits() return self.traits end
            c.xp={getXP=function(_,p) return c.xps[p:getId()] or 0 end,
                getPerkBoost=function(_,p) return d.boosts[p:getId()] or 0 end,
                getTotalXp=function() local n=0; for _,v in pairs(c.xps) do n=n+v end; return n end,
                getLevel=function() return 0 end,setXPToLevel=forbidden,AddXP=forbidden}
            function c:getXp() return self.xp end
            function c:applyTraits(selected)
                assert(self~=player and not self.npcFlag); calls[#calls+1]="applyTraits"
                local levels={Fitness=5,Strength=5}
                for k,v in pairs(d.boosts) do levels[k]=(levels[k] or 0)+v end
                for i=0,selected:size()-1 do
                    local key=selected:get(i):getName(); self.selected[key]=true
                    for k,v in pairs(traits[key].xp) do levels[k]=(levels[k] or 0)+v end
                end
                for k,v in pairs(levels) do
                    self.levels[k]=math.max(0,math.min(10,v)); self.xps[k]=self.levels[k]*100; d.boosts[k]=math.min(3,self.levels[k])
                end
            end
            function c:applyProfessionRecipes() assert(self~=player); self.profRecipes=true end
            function c:applyCharacterTraitsRecipes() assert(self~=player); self.traitRecipes=true end
            c.LevelPerk=forbidden; c.setPerkLevelDebug=forbidden
            return c
        end
        function prepare(p,uuid)
            local d=descriptor(); local token,why=B.prepareDescriptor(d,uuid or "33333333-3333-4333-8333-333333333333",C.world(),p)
            return token,why,d
        end
        player.getDescriptor=function() return {getCharacterProfession=function() return nativeId("unemployed") end} end
        player.getCharacterTraits=function() return {getKnownTraits=function() return javaList({nativeId("strong")}) end,get=function() return true end} end
        player.isNPC=function() return false end
        player.getPerkLevel=function(_,p) return p==skills.Strength and 9 or 0 end
        player.getXp=function() return {getXP=function(_,p) return p==skills.Strength and 900 or 0 end,
            getPerkBoost=function() return 0 end,getTotalXp=function() return 900 end,getLevel=function() return 0 end} end
        player.applyTraits=forbidden; player.applyProfessionRecipes=forbidden; player.applyCharacterTraitsRecipes=forbidden
    ''')
    return agent


@pytest.mark.parametrize("prof,traits,balance,valid", [
    ("unemployed", "{}", 8, True), ("unemployed", '{"strong"}', 0, True),
    ("carpenter", "{}", -2, False), ("carpenter", '{"clumsy"}', 0, True),
    ("unemployed", '{"strong","brave"}', -4, False),
    ("unemployed", '{"smoker","brave"}', 8, True),
])
def test_native_budget_rules(build, prof, traits, balance, valid):
    build.globals().prof=prof
    build.globals().expectedBalance=balance
    build.globals().expectedValid=valid
    build.execute(f'local r=B.validateProposal(proposal(prof,{traits})); assert(r.balance==expectedBalance and r.valid==expectedValid); assert(r.strategic_quality.known==false)')


@pytest.mark.parametrize("invalid", [
    'proposal("invented")', 'proposal("unemployed",{"strong","weak"})',
    'proposal("unemployed",{"strong","strong"})', 'proposal("unemployed",{"invented"})',
    'proposal("unemployed",{"freetrait"})', 'proposal("unemployed",{"zero"})',
    'proposal("veteran",{"coward","weak"})', '{schema_version=1,profession_id="unemployed",trait_ids={},cost=-100}',
    '{schema_version=1,profession_id="unemployed",trait_ids={},skills={Strength=10}}',
    '{schema_version=1,profession_id="unemployed",trait_ids={[2]="smoker"}}',
])
def test_invalid_builds_are_refused(build, invalid):
    build.execute('local p='+invalid+'; local r=B.validateProposal(p); assert(not r.valid); assert(not prepare(p)); assert(#calls==0)')


@pytest.mark.parametrize("mode,offset", [(1,0),(2,1),(3,1),(4,2)])
def test_negative_trait_penalty_and_free_sandbox_points(build, mode, offset):
    build.globals().penalty=mode
    build.globals().expectedOffset=offset
    build.execute('''
        SandboxVars.CharacterFreePoints=2
        local r=B.validateProposal(proposal("unemployed",{"weak","smoker","clumsy"}))
        assert(r.valid and r.negative_offset==expectedOffset and r.balance==26-expectedOffset)
    ''')


def test_native_application_verifies_levels_traits_xp_and_is_one_shot(build):
    build.execute('''
        local token,r,d=prepare(proposal("carpenter",{"clumsy"})); assert(token)
        local c=fresh(d); assert(B.applyCreated(c,token)); c:setNPC(true)
        assert(c:getPerkLevel(skills.Woodwork)==4 and c:getXp():getXP(skills.Woodwork)==400)
        assert(c:getXp():getPerkBoost(skills.Woodwork)==3 and c:getPerkLevel(skills.Fitness)==5)
        assert(c.selected.craft and c.selected.clumsy and c.profRecipes and c.traitRecipes)
        assert(c.md.ARAY_CharacterBuild.status=="APPLIED_VERIFIED")
        assert(calls[1]=="descriptor_skills" and calls[2]=="descriptor_profession" and calls[3]=="applyTraits" and calls[4]=="npc_flag")
        assert(not B.applyCreated(c,token) and c:getPerkLevel(skills.Woodwork)==4)
    ''')


def test_reload_and_two_npcs_preserve_progression_and_identity(build):
    build.execute('''
        local id1="33333333-3333-4333-8333-333333333333"; local id2="44444444-4444-4444-8444-444444444444"
        for _,id in ipairs({id1,id2}) do
            local token,_,d=prepare(proposal("unemployed",{"strong"}),id); local c=fresh(d)
            assert(B.applyCreated(c,token)); c:setNPC(true); c.md.ARAY_IsNPC=true; roster[id]=c
        end
        local a=roster[id1]; a.levels.Woodwork=6; a.xps.Woodwork=600
        local before=#calls
        assert(not prepare(proposal(),id1))
        local p=B.getProfile(id1); local b=B.getProfile(id2)
        assert(p.uuid==id1 and b.uuid==id2 and p.points.value==0 and p.initial_build.uuid==id1)
        local exported=B.exportRecord(id1)
        assert(exported.initial_build.initial.proposal.profession_id=="unemployed")
        assert(a.levels.Woodwork==6 and #calls==before)
        A.clearAll(); assert(observation(id1).profile.available)
        assert(a.levels.Woodwork==6 and #calls==before)
    ''')


def test_player_read_only_and_context_contains_only_game_profile(build):
    build.execute('''
        local count=#calls; local p=B.getPlayerProfile()
        assert(p.profession.value=="unemployed" and p.traits.items[1]=="strong")
        assert(p.xp.total.value==900 and p.points.known==false and #calls==count)
        local ctx=B.getProposalContext("Carpinteiro de apoio")
        assert(ctx.catalog.complete and ctx.player_profile.skills.known and not ctx.executable)
        assert(ctx.player_profile.name==nil and ctx.player_profile.position==nil)
        assert(player:getPerkLevel(skills.Strength)==9 and forbiddenCalls==0)
        local token=assert(prepare(proposal())); assert(not B.applyCreated(player,token))
    ''')


@pytest.mark.parametrize("failure", ["expired", "world", "wrong_descriptor", "levels", "native_api", "native_failure", "wrong_result", "rules_changed"])
def test_apply_failures_never_replay_or_fallback_to_setters(build, failure):
    build.globals().failure=failure
    build.execute('''
        local token,_,d=prepare(proposal()); assert(token); local c=fresh(d)
        if failure=="expired" then clock=clock+30000
        elseif failure=="world" then worldName="changed"
        elseif failure=="wrong_descriptor" then c=fresh(descriptor())
        elseif failure=="levels" then c.levels.Woodwork=2
        elseif failure=="native_api" then c.applyTraits=nil
        elseif failure=="native_failure" then c.applyTraits=function() error("native") end
        elseif failure=="wrong_result" then c.applyTraits=function() end end
        if failure=="rules_changed" then SandboxVars.CharacterFreePoints=1 end
        assert(not B.applyCreated(c,token)); assert(not B.applyCreated(c,token))
        assert(forbiddenCalls==0)
    ''')


def test_partial_apis_catalog_cycle_and_multiplayer_fail_closed(build):
    build.execute('''
        traits.craft.grants={"craft"}
        assert(not B.validateProposal(proposal("carpenter",{"clumsy"})).valid)
        traits.craft.grants={}; isClient=function() return true end
        assert(not prepare(proposal()))
        CharacterTraitDefinition=nil
        assert(not B.getCatalog().complete and not B.validateProposal(proposal()).valid)
    ''')


def test_agent_profile_replaces_reserved_fields_without_touching_player(build):
    build.execute('''
        local s=observation(); assert(s.profile.schema_version==1 and s.profile.available)
        assert(s.profile.profession.known==false and s.profile.skills.known)
        assert(s.profile.points.known==false and s.profile.reason~="3C.4D.1_not_implemented")
        assert(C.getCatalog(uuidA).actions.PUSH_ZOMBIE.support=="UNSUPPORTED")
    ''')


@pytest.mark.parametrize("mode", [1,2,3,4])
def test_point_balance_matches_actual_vanilla_lua(build, mode):
    from test_executor import NATIVE
    source = (NATIVE.parents[1] / "OptionScreens/CharacterCreationProfession.lua").read_text(encoding="utf-8")
    build.execute("CharacterCreationProfession={}")
    import re
    for method in ("PointToSpend", "negativeTraitOffset"):
        function = re.search(r"function CharacterCreationProfession:" + method + r"\(\).*?^end", source, re.M | re.S)
        assert function
        build.execute(function.group())
    build.globals().penalty=mode
    build.execute('''
        SandboxVars.CharacterFreePoints=3
        local p=proposal("unemployed",{"weak","smoker","clumsy"}); local native=CharacterCreationProfession
        local ui=setmetatable({pointToSpend=16,cost=8,listboxTraitSelected={items={}}},{__index=native})
        for _,key in ipairs(p.trait_ids) do ui.listboxTraitSelected.items[#ui.listboxTraitSelected.items+1]={item=traits[key]} end
        assert(ui:PointToSpend()==B.validateProposal(p).balance)
    ''')


def test_real_installation_costs_are_not_assumed_from_older_builds(build):
    from test_executor import NATIVE
    import re
    game = NATIVE.parents[4]
    trait_text=(game / "media/scripts/generated/characters/character_traits.txt").read_text(encoding="utf-8")
    profession_text=(game / "media/scripts/generated/characters/character_professions.txt").read_text(encoding="utf-8")
    def cost(text, kind, name):
        block=re.search(kind+r" base:"+name+r"\s*\{([^}]+)\}",text)
        return int(re.search(r"Cost\s*=\s*(-?\d+)",block[1])[1])
    build.globals().actualStrong=cost(trait_text,"character_trait_definition","strong")
    build.globals().actualCarpenter=cost(profession_text,"character_profession_definition","carpenter")
    build.execute('''
        traits.strong.cost=actualStrong; professions[2].cost=actualCarpenter
        assert(B.validateProposal(proposal("unemployed",{"strong"})).balance==8-actualStrong)
        assert(B.validateProposal(proposal("carpenter")).balance==actualCarpenter)
    ''')


@pytest.mark.parametrize("case", ["valid", "invalid", "restore", "native_failed"])
def test_production_spawn_hook_before_npc_flag_and_failure_cleanup(build, case):
    source=(CLIENT / "ArayHumanTest.lua").read_text(encoding="utf-8")
    body=source[source.index("local function spawnNpc("):source.index("function ArayHuman.getNpc()")]
    build.execute('''
        ctorCalls=0; restoredPlayer=false
        SurvivorFactory={CreateSurvivor=function()
            local d=descriptor(); d.setForename=function() end; d.setSurname=function() end; return d end}
        IsoPlayer.new=function(cell,d,x,y,z)
            ctorCalls=ctorCalls+1; calls[#calls+1]="constructor"; constructed=fresh(d)
            constructed.getBodyDamage=function() return {} end
            constructed.removeFromWorld=function(c) c.removedWorld=true end
            constructed.removeFromSquare=function(c) c.removedSquare=true end
            if spawnCase=="native_failed" then constructed.applyTraits=function() error("native failure") end end
            return constructed
        end
        InventoryItemFactory=nil; instanceItem=nil
        configureNpc=function(c) c:setNPC(true); c.md.ARAY_IsNPC=true end
        restoreLocalPlayer=function() restoredPlayer=true end
        trackNpc=function(c) roster[c.md.ARAY_Uuid]=c end
        rememberBorn=function() end; applyDirection=function() end; xy=function() return "test" end
    ''')
    build.execute(body + "\nspawnUnderTest=spawnNpc")
    build.globals().spawnCase=case
    build.execute('''
        local config={uuid="33333333-3333-4333-8333-333333333333",square=squares["0:0:0"],characterBuild=proposal("unemployed",{"strong"})}
        if spawnCase=="invalid" then config.characterBuild=proposal("veteran") end
        if spawnCase=="restore" then config.restoring=true end
        local ok=spawnUnderTest(player,cell,config)
        if spawnCase=="valid" then
            assert(ok and ctorCalls==1 and constructed:isNPC())
            assert(calls[1]=="descriptor_skills" and calls[2]=="descriptor_profession" and calls[3]=="constructor" and calls[4]=="applyTraits" and calls[5]=="npc_flag")
            assert(roster[config.uuid]==constructed and constructed.md.ARAY_CharacterBuild.initial.balance==0)
        elseif spawnCase=="native_failed" then
            assert(not ok and constructed.removedWorld and constructed.removedSquare and restoredPlayer)
            assert(not constructed:isNPC() and roster[config.uuid]==nil)
        else assert(not ok and ctorCalls==0) end
        assert(player:getPerkLevel(skills.Strength)==9 and forbiddenCalls==0)
    ''')


def test_prepare_cannot_mutate_player_or_existing_npc_descriptor(build):
    build.execute('''
        local d=descriptor(); player.getDescriptor=function() return d end
        local before=#calls
        assert(not B.prepareDescriptor(d,"33333333-3333-4333-8333-333333333333",C.world(),proposal()))
        roster[uuidA].getDescriptor=function() return d end
        player.getDescriptor=function() return nil end
        assert(not B.prepareDescriptor(d,"33333333-3333-4333-8333-333333333333",C.world(),proposal()))
        assert(#calls==before and forbiddenCalls==0)
    ''')
