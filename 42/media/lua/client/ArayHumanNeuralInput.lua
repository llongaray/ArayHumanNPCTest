-- On-demand data projection, no policy, weights or execution.
require "ArayHumanAgentState"
require "ArayHumanJson"
ArayHuman=ArayHuman or {}
local N={}; ArayHuman.NeuralInput=N
function N.observe(uuid)
 local C=ArayHuman.Capabilities
 if not C.actor(uuid) then return nil,'neural_actor' end
 local s=ArayHuman.AgentState.getSnapshot(uuid)
 if not s or s.uuid~=uuid or s.world_id~=C.world() or not s.active or C.now()<s.captured_at_ms or C.now()-s.captured_at_ms>1500 then return nil,'neural_snapshot_expired' end
 local out={schema_version=1,uuid=uuid,world_id=C.world(),captured_at_ms=s.captured_at_ms,
  profile=s.profile,capabilities=ArayHuman.Capabilities.getCatalog(uuid).actions,
  action_results=s.results or {},events=s.events or {},memory={status='UNAVAILABLE',reason='no_persistent_personal_memory_provider'}}
 local text=ArayHuman.Json.encode(out)
 if not text or ArayHuman.Text.bytes(text)>10000 then
  out.events={}; out.action_results={}; out.partial=true
  text=ArayHuman.Json.encode(out)
 end
 if not text or ArayHuman.Text.bytes(text)>10000 then return nil,'neural_budget' end
 return out
end
