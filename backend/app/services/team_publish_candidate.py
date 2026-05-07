from __future__ import annotations
from typing import Any
from sqlmodel import Session
from app.models import Thread
from app.services.team_blueprint import export_thread_team_blueprint

def _d(v: Any)->dict[str,Any]: return v if isinstance(v,dict) else {}
def _l(v: Any)->list[Any]: return v if isinstance(v,list) else []
def _c(v: Any,n:int=512)->str: return str(v or '').strip()[:n]
def _id(v: Any,n:int=128)->str: return ''.join(ch if ch.isalnum() or ch in '._:-' else '_' for ch in _c(v,n).lower()).strip('_')
def _pick(*xs: Any)->str:
    for x in xs:
        t=_c(x)
        if t: return t
    return ''
def _uniq(xs: Any, *, max_items:int=32, lower:bool=False)->list[str]:
    out=[]; seen=set()
    for x in _l(xs):
        t=_c(x,128); k=_id(t) if lower else t.lower()
        if not t or k in seen: continue
        seen.add(k); out.append(k if lower else t)
        if len(out)>=max_items: break
    return out

def _bp(m:dict[str,Any])->dict[str,Any]: return _d(m.get('blueprint') or m.get('team_blueprint') or m.get('teamBlueprint'))
def _team(m:dict[str,Any])->dict[str,Any]: return _d(m.get('team') or m.get('team_seed') or m.get('teamSeed'))
def _plan(m:dict[str,Any])->dict[str,Any]:
    b=_bp(m); t=_team(m); st=_d(b.get('structure') or t.get('structure_v2') or t.get('structureV2') or t.get('structure'))
    return _d(b.get('memory_plan') or b.get('memoryPlan') or t.get('memory_plan') or t.get('memoryPlan') or st.get('memory_plan'))
def _agents(m:dict[str,Any])->list[dict[str,Any]]:
    b=_bp(m); t=_team(m); st=_d(b.get('structure') or t.get('structure_v2') or t.get('structureV2') or t.get('structure'))
    src=_l(t.get('agents')) or _l(st.get('participants')); rows=[]
    for i,raw in enumerate(src[:24]):
        r=_d(raw); rp=_d(r.get('role_profile') or r.get('roleProfile'))
        rows.append({'agent_id':_id(r.get('agent_id') or r.get('id') or r.get('participant_id') or r.get('name') or f'agent_{i+1}') or f'agent_{i+1}','name':_pick(r.get('name'),r.get('display_label'),r.get('label'),r.get('agent_id'),r.get('participant_id'),f'Agent {i+1}'),'role':_id(rp.get('role') or r.get('role') or r.get('role_id') or 'agent') or 'agent','purpose':_pick(rp.get('purpose'),r.get('purpose'),r.get('description')),'publish_action':'promote_to_role_contract'})
    return rows

def _surface_text(s:dict[str,Any])->str:
    parts=[s.get(k) for k in ('surface_id','surfaceId','file_name','fileName','title','purpose','visibility','visibility_scope','publish_visibility')]
    parts += _l(s.get('semantic_slots') or s.get('semanticSlots')) + _l(s.get('tags'))
    return ' '.join(_c(x,256).lower() for x in parts if _c(x))
def _private(s:dict[str,Any])->bool: return any(tok in _surface_text(s) for tok in ('user','private','personal','secret','credential','token','upload','artifact','conversation','turns','chat','itinerary','hotel','flight','passport','visa','billing','invoice'))
def _public(s:dict[str,Any])->bool:
    text=_surface_text(s); vis=_id(s.get('visibility') or s.get('visibility_scope') or s.get('visibilityScope') or s.get('publish_visibility') or s.get('publishVisibility'))
    if vis in {'public','sourced_public','reusable'}: return True
    prov=_d(s.get('provenance') or s.get('source') or s.get('sources'))
    if prov and any(tok in str(prov).lower() for tok in ('public','official','web','url','source')): return True
    return any(tok in text for tok in ('public','official','web','source','sourced','knowledge','kb','reference','conference','cfp','paper','doc','docs','api','research','evidence','glossary'))
def _classify(s:dict[str,Any])->dict[str,Any]:
    sid=_id(s.get('surface_id') or s.get('surfaceId') or s.get('file_name') or s.get('fileName') or 'surface') or 'surface'; label=_pick(s.get('title'),s.get('label'),s.get('file_name'),s.get('fileName'),sid); slots=_uniq(s.get('semantic_slots') or s.get('semanticSlots') or [],max_items=12,lower=True)
    if _private(s): return {'surface_id':sid,'label':label,'classification':'keep_private','publish_action':'exclude_private_memory','reason':'Looks user-, artifact-, upload-, credential-, or conversation-specific.','semantic_slots':slots}
    if _public(s): return {'surface_id':sid,'label':label,'classification':'public_reusable_knowledge','publish_action':'optional_sourced_knowledge_pack','reason':'Looks reusable or public-sourceable; publish as a refreshable knowledge pack, not raw private memory.','semantic_slots':slots}
    return {'surface_id':sid,'label':label,'classification':'memory_contract_only','publish_action':'publish_schema_not_content','reason':'Publish the surface purpose/read-write contract; clone gets fresh private memory.','semantic_slots':slots}
def _rules(m:dict[str,Any])->list[dict[str,Any]]:
    b=_bp(m); t=_team(m); rows=[]
    for raw in _l(b.get('runtime_rules') or b.get('runtimeRules') or t.get('runtime_rules') or t.get('runtimeRules') or t.get('rules')):
        r=_d(raw); text=raw if isinstance(raw,str) else _pick(r.get('text'),r.get('rule'),r.get('summary'))
        if _c(text): rows.append({'text':_c(text,1000),'source':'team_runtime_rule','publish_action':'publish_as_rule'})
    if _d(b.get('artifact_contract') or t.get('artifact_contract') or t.get('artifactContract')): rows.append({'text':'Do not create or deliver workspace artifacts unless the latest user request explicitly asks for an artifact.','source':'artifact_contract','publish_action':'publish_as_rule'})
    seen=set(); out=[]
    for r in rows:
        k=r['text'].lower()
        if k in seen: continue
        seen.add(k); out.append(r)
    return out[:20]

def build_team_publish_candidate_from_manifest(manifest:dict[str,Any], *, visibility:str='private_review')->dict[str,Any]:
    b=_bp(manifest); t=_team(manifest); p=_plan(manifest); surfaces=[_classify(_d(x)) for x in (_l(p.get('surfaces')) or _l(b.get('memory_map') or b.get('memoryMap')))]
    agents=_agents(manifest); top=_d(b.get('topology') or _d(_d(t.get('structure_v2') or t.get('structureV2') or t.get('structure')).get('topology'))); knowledge=[s for s in surfaces if s['classification']=='public_reusable_knowledge']; private=[s for s in surfaces if s['classification']=='keep_private']; schema=[s for s in surfaces if s['classification']=='memory_contract_only']; rules=_rules(manifest)
    candidate={'kind':'goc.team_publish_candidate','schema_version':1,'title':_pick(b.get('title'),t.get('team_name'),'Configured Team'),'description':_pick(b.get('description'),t.get('task_brief')),'visibility':visibility,'behavior_spec':{'runtime_rules':[r['text'] for r in rules],'artifact_policy':'explicit_request_only' if any('artifact' in r['text'].lower() for r in rules) else 'unspecified'},'agents':[{k:a.get(k) for k in ('agent_id','name','role','purpose')} for a in agents],'team_motif':{'pattern':_c(top.get('pattern') or 'hybrid',64) or 'hybrid','execution_pattern':_c(top.get('execution_pattern') or top.get('executionPattern'),64),'final_participant_id':_c(top.get('final_participant_id') or top.get('finalParticipantId'),128)},'memory_contract':{'initial_mode':'fresh_private_on_clone','publish_memory_content_by_default':False,'surfaces':[{'surface_id':s['surface_id'],'label':s['label'],'content_policy':'optional_knowledge_pack' if s['classification']=='public_reusable_knowledge' else ('exclude' if s['classification']=='keep_private' else 'schema_only')} for s in surfaces]},'knowledge_dependencies':[{'surface_id':s['surface_id'],'title':s['label'],'install_default':'ask','refresh_on_clone':True} for s in knowledge],'clone_policy':{'private_memory':'fresh_on_clone','credential_binding':'never_copy','provider_state':'never_copy','knowledge_packs':'ask' if knowledge else 'none'}}
    return {'ok':True,'candidate':candidate,'review':{'summary':{'agents':len(agents),'runtime_rules':len(rules),'memory_surfaces':len(surfaces),'optional_knowledge_packs':len(knowledge),'private_exclusions':len(private),'schema_only_surfaces':len(schema)},'promote_to_rules':rules,'promote_to_roles':agents,'promote_to_team_motif':[{'text':f"{candidate['team_motif']['pattern']}{' · '+candidate['team_motif']['execution_pattern'] if candidate['team_motif']['execution_pattern'] else ''}",'publish_action':'publish_as_team_motif'}],'publish_as_knowledge_pack':knowledge,'keep_private':private,'publish_schema_only':schema,'warnings':[*(['Public/reusable memory should be published as sourced knowledge packs with freshness policy.'] if knowledge else []),*(['Private/user/artifact/upload memory is excluded from public clone by default.'] if private else []),'Clone installs roles/rules/team contract with fresh private memory; credentials and provider state are never copied.']}}

def build_thread_team_publish_candidate(session: Session, thread: Thread, *, visibility:str='private_review')->dict[str,Any]: return build_team_publish_candidate_from_manifest(export_thread_team_blueprint(session,thread), visibility=visibility)
