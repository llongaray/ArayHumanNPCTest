-- Bounded data codec. Never loads or evaluates source text.
require "ArayHumanText"
ArayHuman=ArayHuman or {}
local J={}; ArayHuman.Json=J
function J.encode(value)
 local seen={}; local nodes=0
 local function encode(v,depth)
  nodes=nodes+1; assert(nodes<=8192 and depth<=16,"json_budget")
  local t=type(v)
  if t=="nil" then return "null" end
  if t=="boolean" then return tostring(v) end
  if t=="number" then assert(v==v and math.abs(v)~=math.huge,"json_number"); return v%1==0 and string.format('%.0f',v) or tostring(v) end
  if t=="string" then return '"'..v:gsub('[%z\1-\31\\"]',function(c)
   if c=='"' then return '\\"' elseif c=='\\' then return '\\\\' end
   return string.format('\\u%04x',c:byte()) end)..'"' end
  assert(t=="table" and not getmetatable(v) and not seen[v],"json_type")
  seen[v]=true; local out={}; local n=0; local array=true
  for k in pairs(v) do n=n+1; if type(k)~="number" or k%1~=0 or k<1 or k>#v then array=false end end
  if array and n>0 then for _,x in ipairs(v) do out[#out+1]=encode(x,depth+1) end
  else for k,x in pairs(v) do assert(type(k)=="string","json_key"); out[#out+1]=encode(k,depth+1)..":"..encode(x,depth+1) end end
  seen[v]=nil; return (array and n>0 and "[" or "{")..table.concat(out,",")..(array and n>0 and "]" or "}")
 end
 local ok,result=pcall(encode,value,0); if not ok or ArayHuman.Text.bytes(result)>65536 then return nil,"json_invalid_or_budget" end
 return result
end
function J.decode(text)
 if type(text)~="string" or ArayHuman.Text.bytes(text)>65536 then return nil,"json_budget" end
 local i,nodes=1,0
 local function skip() while text:sub(i,i):match("%s") do i=i+1 end end
 local function str()
  assert(text:sub(i,i)=='"'); i=i+1; local out={}
  while i<=#text do
   local c=text:sub(i,i); i=i+1
   if c=='"' then return table.concat(out) end
   if c=='\\' then
    local e=text:sub(i,i); i=i+1; local escapes={['"']='"',['\\']='\\',['/']='/',n='\n',r='\r',t='\t',b='\b',f='\f'}
    if e=='u' then
     local hex=text:sub(i,i+3); assert(hex:match('^%x%x%x%x$')); i=i+4; local cp=tonumber(hex,16)
     if cp>=0xD800 and cp<=0xDBFF then
      assert(text:sub(i,i+1)=='\\u',"json_surrogate"); i=i+2
      local low=text:sub(i,i+3); assert(low:match('^%x%x%x%x$')); i=i+4; low=tonumber(low,16)
      assert(low>=0xDC00 and low<=0xDFFF,"json_surrogate"); cp=0x10000+(cp-0xD800)*1024+low-0xDC00
     else assert(cp<0xDC00 or cp>0xDFFF,"json_surrogate") end
     out[#out+1]=ArayHuman.Text.char(cp)
    else assert(escapes[e],"json_escape"); out[#out+1]=escapes[e] end
   else assert(c:byte()>=32,"json_control"); out[#out+1]=c end
  end
  error("json_string")
 end
 local value
 value=function(depth)
  nodes=nodes+1; assert(nodes<=8192 and depth<=16,"json_budget"); skip(); local c=text:sub(i,i)
  if c=='"' then return str() end
  if c=='{' or c=='[' then
   i=i+1; skip(); local close=c=='{' and '}' or ']'; local r={}; local keys={}
   if text:sub(i,i)==close then i=i+1; return r end
   while true do
    local k=#r+1
    if c=='{' then skip(); k=str(); assert(not keys[k],"json_duplicate"); keys[k]=true; skip(); assert(text:sub(i,i)==':'); i=i+1 end
    r[k]=value(depth+1); skip(); local sep=text:sub(i,i); i=i+1
    if sep==close then return r end; assert(sep==',',"json_separator")
   end
  end
  for token,v in pairs({['true']=true,['false']=false}) do if text:sub(i,i+#token-1)==token then i=i+#token; return v end end
  if text:sub(i,i+3)=='null' then i=i+4; return nil end
  local raw=text:sub(i):match('^-?%d+%.?%d*[eE][+-]?%d+') or text:sub(i):match('^-?%d+%.?%d*')
  assert(raw and not raw:match('^-?0%d') and not raw:match('%.$'),"json_number")
  local number=tonumber(raw); assert(number and number==number and math.abs(number)~=math.huge); i=i+#raw; return number
 end
 local ok,result=pcall(value,0); if not ok then return nil,"json_invalid" end
 skip(); if i<=#text then return nil,"json_trailing" end
 return result
end
