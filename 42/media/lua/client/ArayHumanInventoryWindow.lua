require "ISUI/ISCollapsableWindow"
require "ISUI/ISScrollingListBox"
require "ISUI/ISButton"
require "ArayHumanInventory"
ArayHuman=ArayHuman or {}
ArayHuman.InventoryWindow={}
local window
ArayInventoryWindow=ISCollapsableWindow:derive("ArayInventoryWindow")
function ArayInventoryWindow:createChildren()
 ISCollapsableWindow.createChildren(self)
 self.list=ISScrollingListBox:new(12,65,self.width-24,self.height-110)
 self.list:initialise(); self.list:instantiate(); self:addChild(self.list)
 self.list.itemheight=24
 self.list.doDrawItem=function(list,y,item)
  list:drawText(item.text,4,y+3,1,1,1,1,UIFont.Small); return y+list.itemheight
 end
 local refresh=ISButton:new(12,self.height-35,self.width-24,22,"Atualizar (somente leitura)",self,self.refresh)
 refresh:initialise(); refresh:instantiate(); self:addChild(refresh)
 self:refresh()
end
function ArayInventoryWindow:refresh()
 self.list:clear()
 local data,why=ArayHuman.Inventory.readInventory(self.uuid)
 if not data or data.world_id~=self.world_id then self.summary=why or "world_mismatch"; return end
 local function val(v) return v and v.known and tostring(v.value) or "?" end
 self.summary="Carga: "..val(data.weight).." / "..val(data.capacity)..(data.complete and "" or " (leitura parcial)")
 for _,item in ipairs(data.items) do self.list:addItem(item.full_type.." x "..val(item.quantity),{}) end
 if #data.items==0 then self.list:addItem(data.complete and "Inventário vazio." or "Dados indisponíveis.",{}) end
end
function ArayInventoryWindow:render()
 ISCollapsableWindow.render(self)
 self:drawText(self.summary or "?",12,30,1,1,1,1,UIFont.Small)
 self:drawText(self.uuid or "",12,47,.7,.7,.7,1,UIFont.Small)
end
function ArayInventoryWindow:update()
 ISCollapsableWindow.update(self)
 if self.world_id~=ArayHuman.Capabilities.world() then self:setVisible(false); self:removeFromUIManager() end
end
function ArayHuman.InventoryWindow.open(uuid)
 local actor=ArayHuman.Capabilities.actor(uuid); if not actor then return false,"instance_unavailable" end
 if window then window:setVisible(false); window:removeFromUIManager() end
 window=ISCollapsableWindow.new(ArayInventoryWindow,60,60,460,360)
 window.uuid=uuid; window.world_id=ArayHuman.Capabilities.world(); window.title="Inventário NPC — somente leitura"
 window:initialise(); window:instantiate(); window:addToUIManager(); window:setVisible(true)
 return true
end
