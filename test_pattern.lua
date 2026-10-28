local json = '{"id":"test","ok":true,"kind":"pong"}'
local pattern1 = '"ok"%s*:%s*(true|false)'
local pattern2 = '"ok"%s*:%s*true'
local pattern3 = '"ok"%s*:%s*false'
print("Testing Lua pattern matching:")
print("JSON: " .. json)
print("")
print("Pattern 1 (with |): " .. pattern1)
local result1 = string.match(json, pattern1)
print("Result: " .. tostring(result1))
print("")
print("Pattern 2 (true only): " .. pattern2)
local result2 = string.match(json, pattern2)
print("Result: " .. tostring(result2))
