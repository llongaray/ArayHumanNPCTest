require "ArayHumanPhysical"
-- Bounded local route evaluation. No actions and no inference.
ArayHuman = ArayHuman or {}
ArayHuman.EscapePlanner = {}
local P = ArayHuman.EscapePlanner
local function call(o,name,...)
    if not o then return nil end
    local args={...}
    local ok,value=pcall(function() if o[name] then return o[name](o,unpack(args)) end end)
    if ok then return value end
end
local function id(x,y,z) return "tile:"..math.floor(x)..":"..math.floor(y)..":"..math.floor(z) end
local function distance(ax,ay,bx,by) return math.sqrt((ax-bx)^2+(ay-by)^2) end
local function segmentDistance(x,y,ax,ay,bx,by)
    local dx,dy=bx-ax,by-ay
    local f=(dx*dx+dy*dy)>0 and ((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy) or 0
    f=math.max(0,math.min(1,f))
    return distance(x,y,ax+f*dx,ay+f*dy)
end
-- Supercover of the actual fractional segment, bounded to the emergency radius.
-- At corners require BOTH cardinal passages: no diagonal wall cutting.
function P.segmentPassable(ax,ay,bx,by,z,c)
    if distance(ax,ay,bx,by)>7 then return false,"api=geometry obstacle=segment_budget" end
    local cell=getCell()
    local function square(x,y) return cell:getGridSquare(x,y,z) end
    local function edge(a,b)
        if not a or not b then return false,"api=getGridSquare obstacle=unloaded" end
        local context=" from="..a:getX()..","..a:getY()..","..z.." to="..b:getX()..","..b:getY()..","..z
            .." direction="..(b:getX()-a:getX())..","..(b:getY()-a:getY())
        if not ArayHuman.squareFree(b,c) then return false,"api=squareFree obstacle=occupied_or_solid"..context end
        local ok,detail=ArayHuman.Perception.edgePassable(a,b)
        return ok==true,detail or ("api=edgePassable obstacle=unknown_or_floor"..context)
    end
    local x,y=math.floor(ax),math.floor(ay)
    local tx,ty=math.floor(bx),math.floor(by)
    local dx,dy=bx-ax,by-ay
    local sx,sy=dx>=0 and 1 or -1,dy>=0 and 1 or -1
    local vx=dx==0 and math.huge or ((dx>0 and x+1 or x)-ax)/dx
    local vy=dy==0 and math.huge or ((dy>0 and y+1 or y)-ay)/dy
    for step=1,24 do
        if x==tx and y==ty then return true end
        local a=square(x,y)
        local nx,ny=x,y
        if math.abs(vx-vy)<.000001 then
            nx,ny=x+sx,y+sy
            for _,pair in ipairs({{a,square(nx,y)},{a,square(x,ny)},
                {square(nx,y),square(nx,ny)},{square(x,ny),square(nx,ny)}}) do
                local ok,detail=edge(pair[1],pair[2]); if not ok then return false,detail end
            end
            vx=vx+1/math.abs(dx); vy=vy+1/math.abs(dy)
        elseif vx<vy then nx=x+sx; vx=vx+1/math.abs(dx)
        else ny=y+sy; vy=vy+1/math.abs(dy) end
        local ok,detail=true,nil
        if nx==x or ny==y then ok,detail=edge(a,square(nx,ny)) end
        if not ok then return false,detail end
        x,y=nx,ny
    end
    return false,"api=geometry obstacle=segment_budget"
end
function P.validateLeg(c,t,observation)
    if not observation or not observation.active or observation.scan.truncated or observation.scan.unknown then return false,"threat_scan_incomplete" end
    local sq=getCell():getGridSquare(t.x,t.y,t.z)
    if not sq or not ArayHuman.squareFree(sq,c) then return false,"destination_blocked" end
    local pass,detail=P.segmentPassable(c:getX(),c:getY(),t.x+.5,t.y+.5,t.z,c)
    if not pass then return false,"route_edge_blocked",detail end
    local initial=math.huge
    for _,threat in ipairs(observation.threats) do
        initial=math.min(initial,distance(c:getX(),c:getY(),threat.position.x,threat.position.y))
    end
    for _,threat in ipairs(observation.threats) do
        local p=threat.position
        if segmentDistance(p.x,p.y,c:getX(),c:getY(),t.x+.5,t.y+.5)<math.min(.8,initial)-.03
            or distance(p.x,p.y,t.x+.5,t.y+.5)<initial-.03 then return false,"route_threatened" end
    end
    return true
end
function P.plan(c,observation,cfg,excluded)
    if not observation or not observation.active or not observation.immediate then return nil,"emergency_not_confirmed" end
    if observation.scan.truncated or observation.scan.unknown then return nil,"threat_scan_incomplete" end
    local threats=observation.threats
    if #threats==0 or #threats>24 then return nil,"threat_count_unsupported" end
    local cell=getCell(); local origin=c:getCurrentSquare()
    local x,y,z=c:getX(),c:getY(),math.floor(c:getZ())
    local initial=math.huge
    for _,t in ipairs(threats) do initial=math.min(initial,distance(x,y,t.position.x,t.position.y)) end
    local occupants,examined,unknown=0,0,false
    local function safeSquare(sq)
        if call(sq,"TreatAsSolidFloor")~=true or call(sq,"isFree",false)~=true then return false end
        local movers=call(sq,"getMovingObjects"); local count=call(movers,"size")
        if type(count)~="number" then unknown=true; return false end
        for i=0,count-1 do
            occupants=occupants+1
            if occupants>256 then unknown=true; return false end
            local obj=call(movers,"get",i)
            if obj and obj~=c then
                local md=call(obj,"getModData")
                if instanceof(obj,"IsoZombie") or instanceof(obj,"IsoGameCharacter")
                    or (md and md.ARAY_IsNPC) or (ArayHuman.getLocalPlayer and obj==ArayHuman.getLocalPlayer()) then return false end
            end
        end
        return true
    end
    local function clearance(ax,ay,bx,by)
        local endpoint=math.huge
        for _,t in ipairs(threats) do
            local p=t.position
            -- The first segment starts at the real fractional NPC position.
            if segmentDistance(p.x,p.y,ax,ay,bx,by)<math.min(.8,initial)-.03 then return nil end
            endpoint=math.min(endpoint,distance(p.x,p.y,bx,by))
        end
        if endpoint<initial-.03 then return nil end
        return endpoint
    end
    local root={square=origin,x=math.floor(x),y=math.floor(y),z=z,px=x,py=y,cost=0}
    local todo,visited={root},{[origin]=true}
    local chosen=nil
    local nodeLimit=math.max(1,math.min(128,cfg.maxRouteNodes or 96))
    while #todo>0 and examined<nodeLimit and occupants<=256 do
        table.sort(todo,function(a,b) if (a.rank or a.cost)~=(b.rank or b.cost) then return (a.rank or a.cost)<(b.rank or b.cost) end; return id(a.x,a.y,a.z)<id(b.x,b.y,b.z) end)
        local node=table.remove(todo,1); examined=examined+1
        if node~=root and node.clearance>=cfg.safeThreatDistance and node.clearance>=initial+2
            and not (excluded and excluded[id(node.x,node.y,z)]) then chosen=node; break end
        for _,d in ipairs({{1,0},{-1,0},{0,1},{0,-1}}) do
            local nx,ny=node.x+d[1],node.y+d[2]
            local px,py=nx+.5,ny+.5
            local cost=node.cost+distance(node.px,node.py,px,py)
            if cost<=cfg.emergencyDistance and distance(x,y,px,py)<=cfg.emergencyDistance then
                local sq=call(cell,"getGridSquare",nx,ny,z)
                local transitions=nil
                local pass=sq and ArayHuman.Perception.edgePassable(node.square,sq)==true
                if sq and not pass and cfg.allowInteractions and ArayHuman.Physical then
                    transitions=ArayHuman.Physical.edgeTransitions(c,node.square,sq)
                end
                if sq and not visited[sq] and (pass or transitions) and safeSquare(sq) then
                    local separation=clearance(node.px,node.py,px,py)
                    if transitions then
                        local margin=transitions[1].kind=="OPEN_DOOR" and 1.25 or 2
                        for _,threat in ipairs(threats) do
                            local p=threat.position
                            if distance(node.px,node.py,p.x,p.y)<margin or distance(px,py,p.x,p.y)<2.5 then separation=nil end
                        end
                    end
                    if separation then
                        visited[sq]=true
                        todo[#todo+1]={square=sq,x=nx,y=ny,z=z,px=px,py=py,cost=cost,
                            clearance=separation,parent=node,transitions=transitions,
                            rank=cost+((node.rank or node.cost)-node.cost)+(transitions and 4 or 0)}
                    end
                end
            end
        end
    end
    if not chosen then return nil,unknown and "route_occupancy_unknown"
        or (#todo>0 and examined>=nodeLimit and "route_budget_exhausted" or "safe_escape_unavailable") end
    local route,corridor={}, {[id(x,y,z)]=true}
    local node=chosen
    while node~=root do
        if not node.transitions or node.transitions[1].kind=='OPEN_DOOR' then
            table.insert(route,1,{kind='WALK',x=node.x,y=node.y,z=z,target_id=id(node.x,node.y,z)})
        end
        for j=#(node.transitions or {}),1,-1 do
            local t=node.transitions[j]
            table.insert(route,1,{kind=t.kind,object=t.object,direction=t.direction,
                x=node.x,y=node.y,z=z,fromX=node.parent.x,fromY=node.parent.y,target_id=id(node.x,node.y,z)})
        end
        corridor[id(node.x,node.y,z)]=true; node=node.parent
    end
    -- Keep turning anchors only where a straight native leg is not proven safe.
    local compact={}; local cursor=1; local px,py=x,y
    while cursor<=#route do
        local chosenIndex=cursor
        local last=cursor
        if route[cursor].kind=='WALK' then
            while last<#route and route[last+1].kind=='WALK' do last=last+1 end
        end
        for j=last,cursor,-1 do
            local t=route[j]
            if t.kind=="WALK" and P.segmentPassable(px,py,t.x+.5,t.y+.5,z,c) and clearance(px,py,t.x+.5,t.y+.5) then
                chosenIndex=j; break
            end
        end
        local t=route[chosenIndex]; compact[#compact+1]=t
        px,py=t.x+.5,t.y+.5; cursor=chosenIndex+1
    end
    route=compact
    return {destination={x=chosen.x,y=chosen.y,z=z,target_id=id(chosen.x,chosen.y,z)},route=route,corridor=corridor,
        distance=chosen.cost,nodes=examined,occupants=occupants},nil
end
