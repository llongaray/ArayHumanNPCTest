-- Manual orders are scoped to UUID; omitted UUID retains focused-NPC compatibility.
require "ArayHumanWalking"
ArayHuman = ArayHuman or {}
local orders = {}
local LABELS = { FOLLOW_PLAYER="Seguindo", STAY="Parado", MOVE_TO="Indo ao destino",
    FACE_TARGET="Olhando", STOP="Parado" }
local NEAR = { {1,0}, {-1,0}, {0,1}, {0,-1}, {1,1}, {1,-1}, {-1,1}, {-1,-1},
    {2,0}, {-2,0}, {0,2}, {0,-2} }
local function now() return getTimestampMs() end
local function world()
    local w=getWorld and getWorld(); local core=getCore and getCore()
    return w and core and tostring(core:getGameMode()).."/"..tostring(w:getWorld()) or nil
end
local function resolve(uuid)
    local c = uuid and type(uuid) ~= "string" and uuid
        or uuid and ArayHuman.getNpcByUuid and ArayHuman.getNpcByUuid(uuid)
        or (not uuid and ArayHuman.getNpc and ArayHuman.getNpc())
    local md = c and c:getModData()
    if not md or not md.ARAY_IsNPC or (type(uuid)=="string" and md.ARAY_Uuid ~= uuid) then return nil end
    return c, md.ARAY_Uuid or c
end
local function playerObj() return ArayHuman.getLocalPlayer and ArayHuman.getLocalPlayer() end
local function dist(ax, ay, bx, by) return math.sqrt((ax-bx)^2+(ay-by)^2) end
local function status(text) if ArayHuman.setStatus then ArayHuman.setStatus(text) end end
function ArayHuman.getOrderForUuid(uuid)
    local value = orders[uuid]
    return value and value.world==world() and value.name or "Idle"
end
function ArayHuman.getOrderName(uuid)
    local _, key = resolve(uuid)
    return ArayHuman.getOrderForUuid(uuid or key)
end
function ArayHuman.getOrderLabel(uuid) return LABELS[ArayHuman.getOrderName(uuid)] or "Parado" end
function ArayHuman.clearOrder(uuid)
    local _, key = resolve(uuid)
    if uuid or key then
        ArayHuman.Walking.cancel(uuid or key, "cancelado", true)
        orders[uuid or key] = nil
    end
end
local function fail(key, reason)
    ArayHuman.Walking.cancel(key, "cancelado", true)
    orders[key] = {name="STOP",world=world()}
    status("Caminhada falhou: " .. tostring(reason))
end
local function followTick(key, order)
    if order.world and order.world~=world() then ArayHuman.clearOrder(key); return end
    if orders[key] ~= order or order.name ~= "FOLLOW_PLAYER" or now() < (order.nextAt or 0) then return end
    order.nextAt = now()+750
    local c = resolve(key)
    local player = playerObj()
    if not c or c:isDead() or not player then fail(key,"indisponivel"); return end
    if math.floor(c:getZ()) ~= math.floor(player:getZ()) then fail(key,"outro andar"); return end
    if dist(c:getX(),c:getY(),player:getX(),player:getY()) <= 2 then
        ArayHuman.Walking.cancel(key,"cancelado",true)
        return
    end
    if ArayHuman.walkActive(key) and order.anchorX
        and dist(player:getX(),player:getY(),order.anchorX,order.anchorY) <= 2 then return end
    local cell = getCell()
    local best, bestDist = nil, nil
    for _, offset in ipairs(NEAR) do
        local sq = cell and cell:getGridSquare(math.floor(player:getX())+offset[1],
            math.floor(player:getY())+offset[2],math.floor(player:getZ()))
        if sq and ArayHuman.squareFree(sq,c) then
            local d=dist(c:getX(),c:getY(),sq:getX()+.5,sq:getY()+.5)
            if not bestDist or d<bestDist then best,bestDist=sq,d end
        end
    end
    if not best then fail(key,"sem tile"); return end
    order.anchorX,order.anchorY=player:getX(),player:getY()
    local ok,id = ArayHuman.walkTo(best,"comando",key)
    if ok then order.walkId=id else fail(key,id) end
end
function ArayHuman.onWalkFinished(outcome, source, uuid, walkId)
    if source == "teste" or source == "executor" then return end
    local order = orders[uuid]
    if not order or (order.walkId and order.walkId ~= walkId) then return end
    if order.name == "MOVE_TO" and outcome == "sucesso" then
        orders[uuid] = {name="STAY",world=world()}; status("Ajudante chegou ao destino.")
    elseif outcome ~= "sucesso" and outcome ~= "cancelado" then fail(uuid,outcome) end
end
function ArayHuman.order(cmd, uuid)
    if type(cmd) ~= "table" or not LABELS[cmd.name] then return false end
    local c,key=resolve(uuid)
    if not c or c:isDead() then status("Nenhum ajudante para comandar."); return false end
    if ArayHuman.Executor then ArayHuman.Executor.manualCommand(key) end
    if ArayHuman.Physical and ArayHuman.Physical.busy(key) and cmd.name~="STOP" and cmd.name~="STAY" then
        status("Aguardando termino seguro da interacao."); return false
    end
    ArayHuman.Walking.cancel(key,"cancelado",true)
    local order={name=cmd.name,world=world()}
    orders[key]=order
    if cmd.name=="FOLLOW_PLAYER" then status("Ajudante seguindo."); followTick(key,order); return true end
    if cmd.name=="STAY" or cmd.name=="STOP" then status("Ajudante parado."); return true end
    if cmd.name=="FACE_TARGET" then
        local player=playerObj()
        local ok=player and c.faceLocation and pcall(function() c:faceLocation(player:getX(),player:getY()) end)
        if not ok then fail(key,"olhar") else status("Ajudante olhando para voce.") end
        return ok==true
    end
    if cmd.name=="MOVE_TO" then
        local cell=getCell()
        local sq=cell and cell:getGridSquare(cmd.x,cmd.y,cmd.z)
        if not sq or not ArayHuman.squareFree(sq,c) then fail(key,"destino bloqueado"); return false end
        local ok,id=ArayHuman.walkTo(sq,"comando",key)
        if ok then order.walkId=id; status("Ajudante indo ao destino.") else fail(key,id) end
        return ok
    end
end
Events.OnTick.Add(function()
    for key, order in pairs(orders) do followTick(key,order) end
end)
