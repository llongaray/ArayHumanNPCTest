-- Comparison only: original names, messages and persisted strings stay untouched.
ArayHuman=ArayHuman or {}
local T={}; ArayHuman.Text=T
local nativeOk,nativeChar=pcall(string.char,256)
T.javaStrings=nativeOk and nativeChar:byte(1)==256
function T.char(cp)
 if T.javaStrings then
  if cp<=65535 then return string.char(cp) end
  cp=cp-65536; return string.char(55296+math.floor(cp/1024),56320+cp%1024)
 end
 if cp<128 then return string.char(cp) end
 if cp<2048 then return string.char(192+math.floor(cp/64),128+cp%64) end
 if cp<65536 then return string.char(224+math.floor(cp/4096),128+math.floor(cp/64)%64,128+cp%64) end
 return string.char(240+math.floor(cp/262144),128+math.floor(cp/4096)%64,128+math.floor(cp/64)%64,128+cp%64)
end
function T.bytes(text)
 if not T.javaStrings then return #text end
 local n,i=0,1
 while i<=#text do
  local cp=text:byte(i)
  if cp<128 then n=n+1 elseif cp<2048 then n=n+2
  elseif cp>=55296 and cp<=56319 and i<#text and text:byte(i+1)>=56320 and text:byte(i+1)<=57343 then n=n+4; i=i+1
  else n=n+3 end
  i=i+1
 end
 return n
end
local groups={{'a',{192,193,194,195,196,197,224,225,226,227,228,229}},
 {'e',{200,201,202,203,232,233,234,235}},{'i',{204,205,206,207,236,237,238,239}},
 {'o',{210,211,212,213,214,242,243,244,245,246}},{'u',{217,218,219,220,249,250,251,252}},
 {'c',{199,231}},{'n',{209,241}}}
function T.compare(text)
 if type(text)~='string' then return '' end
 local s=text
 for _,group in ipairs(groups) do for _,cp in ipairs(group[2]) do s=s:gsub(T.char(cp),group[1]) end end
 -- Canonical decomposed Latin combining marks; comparison only.
 for cp=768,776 do s=s:gsub(T.char(cp),'') end
 s=s:gsub(T.char(778),''):gsub(T.char(807),'')
 return s:lower():gsub('%s+',' '):match('^%s*(.-)%s*$')
end
function T.chunks(text,limit)
 local chunks={}; local start,i=1,1
 while i<=#text do
  local size=1; local cp=text:byte(i)
  if T.javaStrings then
   if cp>=55296 and cp<=56319 then size=2 end
  elseif cp>=240 then size=4 elseif cp>=224 then size=3 elseif cp>=192 then size=2 end
  if i+size-start>limit and i>start then chunks[#chunks+1]=text:sub(start,i-1); start=i end
  i=i+size
 end
 if start<=#text then chunks[#chunks+1]=text:sub(start) end
 return chunks
end
