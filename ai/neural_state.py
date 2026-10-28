"""Versioned observations only. No policy, rewards, persistence, execution or training."""
import copy
import json

from language_encoder import LanguageEncoder


def build_observation(data, identity, now, encoder=None):
    context=data['context']; agent=data.get('agent_input')
    if now>=data['expires_at_ms'] or not 0<=now-context['captured_at_ms']<=1500:
        raise ValueError('neural_context_expired')
    if agent is not None:
        if not isinstance(agent,dict) or agent.get('schema_version')!=1 or agent.get('uuid')!=data['npc_id'] or agent.get('world_id')!=data['world_id']:
            raise ValueError('neural_identity')
        at=agent.get('captured_at_ms')
        if type(at) is not int or not 0<=now-at<=1500: raise ValueError('neural_snapshot_expired')
    agent=agent or {}
    for key in ('action_results','conversation_memory'):
        if agent.get(key)=={}: agent=dict(agent,**{key:[]})  # Empty Lua arrays cross as {}.
    def field(value,reason):
        if isinstance(value,dict) and value.get('available') is False:
            return {'status':'UNAVAILABLE','reason':value.get('reason',reason),'value':value}
        if isinstance(value,dict) and value.get('known') is False:
            return {'status':'UNKNOWN','reason':value.get('reason',reason),'value':value}
        if isinstance(value,dict) and value.get('complete') is False:
            return {'status':'PARTIAL','value':value}
        return {'status':'KNOWN','value':value} if value is not None else {'status':'UNAVAILABLE','reason':reason}
    out={'schema_version':1,'uuid':data['npc_id'],'world_id':data['world_id'],
         'session_id':data['session_id'],'request_id':data['id'],'captured_at_ms':now,
         'expires_at_ms':min(data['expires_at_ms'],context['captured_at_ms']+1500),
         'language':(encoder or LanguageEncoder()).encode(data['message']),
         'message':data['message'],'routing':data['routing'],
         'identity':field(identity,'identity_unavailable'),'profile':field(agent.get('profile'),'profile_unavailable'),
         'perception':field({k:context.get(k) for k in ('position','visibility','zombies','doors','nearby_npcs')},'perception_unavailable'),
         'threat':field(context.get('threat'),'threat_unknown'),
         'health':field(context.get('survival'),'health_unknown'),
         'inventory':field(context.get('inventory'),'inventory_unknown'),
         'capabilities':field(agent.get('capabilities'),'capabilities_unavailable'),
         'action_results':field(agent.get('action_results'),'results_unavailable'),
         'personal_memory':{'status':'UNAVAILABLE','reason':'no_persistent_personal_memory_provider'},
         'conversation_memory':field(agent.get('conversation_memory'),'conversation_memory_unavailable')}
    if len(json.dumps(out,ensure_ascii=False).encode('utf-8'))>32768: raise ValueError('neural_budget')
    return copy.deepcopy(out)
