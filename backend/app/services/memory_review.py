from __future__ import annotations
import json, re
from datetime import datetime, timezone
from typing import Any
from sqlmodel import Session, select
from app.models import MemoryDemandEvent, MemoryMaterializationCandidate, MemoryModule, MemoryTopologySnapshot, Node, Thread

def _clean(v: Any='')->str: return re.sub(r'\s+',' ',str(v or '')).strip()
def _loads(raw: str|None, fallback: Any)->Any:
    try: return json.loads(raw or '')
    except Exception: return fallback
def _clip(v: Any='', n:int=240)->str:
    t=_clean(v); return t if len(t)<=n else t[:n-1].strip()+'…'
def _hash(s:str)->int:
    h=0
    for ch in s: h=((h<<5)-h+ord(ch)) & 0xffffffff
    return h

def _node_text(node: Node)->str:
    payload=_loads(node.payload_json,{})
    parts=[node.text or '']
    if isinstance(payload,dict): parts.extend(str(payload.get(k) or '') for k in ('text','summary','query','content','message','answer'))
    return _clean(' '.join(parts))

def collect_review_evidence(session: Session, thread: Thread, limit:int=400)->list[dict[str,Any]]:
    out=[]
    nodes=session.exec(select(Node).where(Node.thread_id==thread.id).order_by(Node.created_at.desc()).limit(limit)).all()
    for n in reversed(nodes):
        text=_node_text(n)
        if text: out.append({'kind':'node','source':f'node:{n.id}','source_id':n.id,'node_type':n.type,'text':text,'created_at':n.created_at.isoformat()})
    meta=_loads(thread.meta_json,{})
    if isinstance(meta,dict):
        for key in ('summary','memory','team_blueprint','team_config','runtime_rules'):
            if key in meta: out.append({'kind':'thread_meta','source':f'thread.meta_json:{key}','source_id':key,'text':json.dumps(meta.get(key),ensure_ascii=False)})
    return out

def _classify(text:str,row:dict[str,Any])->dict[str,Any]|None:
    t=_clean(text)
    if len(t)<6: return None
    src=re.search(r'https?://|공식|source|citation|출처|근거|검색|웹|지도|maps?|uploaded|upload|사진|image',t,re.I)
    corr=re.search(r'아니|틀렸|정정|수정|잘못|아니라|착각|확인.*필요|wrong|actually|instead',t,re.I)
    loc=re.search(r'역|출구|주소|위치|근처|도보|거리|station|address|near|venue|located',t,re.I)
    sch=re.search(r'마감|일정|등록|개최|프로그램|deadline|schedule|registration|fee|venue|ICDE|학회|conference|visa',t,re.I)
    img=re.search(r'사진|이미지|보이|접시|음식|크루아상|요거트|샐러드|바나나|image|photo|looks like|appears',t,re.I)
    price=re.search(r'가격|비용|원|달러|fee|price|cost|₩|\$',t)
    cats=[]
    if loc: cats.append('location')
    if sch: cats.append('schedule_or_public_event')
    if img: cats.append('image_observation')
    if price: cats.append('price_or_fee')
    if corr: cats.append('correction_or_retraction')
    if not cats: return None
    high=bool(loc or sch or img or price)
    status='contradiction_or_retraction_signal' if corr else ('has_source_signal' if src else ('unsupported_or_weak' if high else 'needs_review'))
    return {'claim_id':f"claim_{_hash((row.get('source') or '')+':'+t[:120])}",'claim':_clip(t,360),'categories':cats,'source':row.get('source') or row.get('kind') or 'memory','source_id':row.get('source_id') or '', 'evidence_status':status,'risk':'high' if (high and status=='unsupported_or_weak') or corr else 'medium','recommended_action':'create_retraction_or_learned_rule_candidate' if corr else ('verify_before_commit_or_answer' if high and status=='unsupported_or_weak' else 'keep_as_reviewable_candidate')}

def build_claim_evidence_overview(session: Session, thread: Thread)->dict[str,Any]:
    seen=set(); claims=[]
    for row in collect_review_evidence(session,thread):
        chunks=[c for c in re.split(r'(?<=[.!?。！？])\s+|\n+',row.get('text') or '') if _clean(c)] or [row.get('text') or '']
        for ch in chunks[:30]:
            c=_classify(ch,row)
            if not c or c['claim_id'] in seen: continue
            seen.add(c['claim_id']); claims.append(c)
            if len(claims)>=80: break
        if len(claims)>=80: break
    unsupported=[c for c in claims if c.get('evidence_status')=='unsupported_or_weak']; retract=[c for c in claims if c.get('evidence_status')=='contradiction_or_retraction_signal']
    return {'summary':{'claim_count':len(claims),'unsupported_count':len(unsupported),'retraction_signal_count':len(retract),'high_risk_count':len([c for c in claims if c.get('risk')=='high'])},'claims':claims,'recommendations':[*( ['High-risk unsupported claims should remain proposals until verified.'] if unsupported else []),*( ['User corrections should create retraction candidates and increase verifier pressure.'] if retract else []),'Do not commit public facts, image observations, prices, schedules, or locations without provenance/freshness metadata.']}

def _latest_topology(session:Session,thread:Thread)->dict[str,Any]:
    snap=session.exec(select(MemoryTopologySnapshot).where(MemoryTopologySnapshot.thread_id==thread.id).order_by(MemoryTopologySnapshot.created_at.desc()).limit(1)).first()
    if not snap: return {}
    payload=_loads(snap.topology_json,{})
    if not isinstance(payload,dict): payload={}
    payload.setdefault('mode',snap.mode); payload.setdefault('state',snap.state); payload.setdefault('stress_score',snap.stress_score)
    return payload

def build_pressure_overview(session: Session, thread: Thread)->dict[str,Any]:
    top=_latest_topology(session,thread); stress=top.get('stress') if isinstance(top.get('stress'),dict) else top; reasons=stress.get('reasons') if isinstance(stress.get('reasons'),list) else []; stats=stress.get('stats') if isinstance(stress.get('stats'),dict) else {}; score=float(stress.get('score') or top.get('stress_score') or 0)
    demands=session.exec(select(MemoryDemandEvent).where(MemoryDemandEvent.thread_id==thread.id).order_by(MemoryDemandEvent.created_at.desc()).limit(120)).all(); cands=session.exec(select(MemoryMaterializationCandidate).where(MemoryMaterializationCandidate.thread_id==thread.id).order_by(MemoryMaterializationCandidate.created_at.desc()).limit(40)).all(); mods=session.exec(select(MemoryModule).where(MemoryModule.thread_id==thread.id).order_by(MemoryModule.created_at.desc()).limit(40)).all()
    signals=[]
    if score>=3: signals.append('memory_split_or_materialization_pressure')
    if stats.get('correction_count') or 'correction_or_retraction' in reasons: signals.append('correction_retraction_pressure')
    if stats.get('artifact_count') or 'artifact_pressure' in reasons: signals.append('artifact_grounding_pressure')
    if demands: signals.append('memory_demand_observed')
    if cands: signals.append('materialization_candidates_pending')
    return {'memory':{'mode':top.get('mode') or top.get('state') or 'unknown','stress_score':score,'reasons':reasons,'stats':stats,'demand_event_count':len(demands),'candidate_count':len(cands),'module_count':len(mods)},'pressure_signals':signals,'recommended_actions':[*( ['Create retraction proposals for corrected claims and require evidence before reuse.'] if 'correction_retraction_pressure' in signals else []),*( ['Inspect materialization candidates; create shadow modules before canonical write-path changes.'] if cands or score>=3 else []),*( ['Require artifact/image observations to carry source ids and confidence before commit.'] if 'artifact_grounding_pressure' in signals else []),'Use the Review Queue to approve/reject memory, rule, skill, and materialization candidates.']}

def _rule_props(evidence:list[dict[str,Any]])->list[dict[str,Any]]:
    rows=[r for r in evidence if re.search(r"하지 말|하지마|기억만|파일.*아니|규칙|앞으로|선호|원칙|rule|prefer|don't|do not",r.get('text') or '',re.I)]
    return [{'proposal_id':f"proposal_rule_{i}_{_hash(r.get('text') or '')}",'kind':'learned_rule_candidate','title':'Possible learned rule','summary':_clip(r.get('text'),240),'source':r.get('source'),'source_id':r.get('source_id'),'risk':'medium','status':'pending_review','recommended_action':'review_in_goc_before_activating'} for i,r in enumerate(rows[-8:])]

def build_review_queue(session: Session, thread: Thread)->dict[str,Any]:
    evidence=collect_review_evidence(session,thread); claims=build_claim_evidence_overview(session,thread); props=[]
    for c in claims['claims']:
        if c.get('risk')=='high' or c.get('evidence_status')!='has_source_signal':
            kind='memory_retraction' if c.get('evidence_status')=='contradiction_or_retraction_signal' else 'claim_verification'
            props.append({'proposal_id':f"proposal_{c['claim_id']}",'kind':kind,'title':'User correction / possible retraction' if kind=='memory_retraction' else 'High-risk claim needs evidence','summary':c.get('claim'),'source':c.get('source'),'source_id':c.get('source_id'),'risk':c.get('risk'),'status':'pending_review','recommended_action':c.get('recommended_action')})
    props.extend(_rule_props(evidence))
    for row in session.exec(select(MemoryMaterializationCandidate).where(MemoryMaterializationCandidate.thread_id==thread.id).order_by(MemoryMaterializationCandidate.created_at.desc()).limit(8)).all(): props.append({'proposal_id':f'proposal_materialize_{row.id}','kind':'materialization_candidate','title':row.title or row.domain or 'Memory materialization candidate','summary':f"{row.recommendation or 'watch'} · score {row.score:.2f}",'source':f'memory_materialization_candidate:{row.id}','risk':'medium','status':row.status or 'candidate','recommended_action':'create_shadow_module_after_review' if row.recommendation=='create_shadow_table' else 'watch_or_save_candidate'})
    for mod in session.exec(select(MemoryModule).where(MemoryModule.thread_id==thread.id).order_by(MemoryModule.created_at.desc()).limit(8)).all(): props.append({'proposal_id':f'proposal_skill_{mod.module_id}','kind':'skill_candidate','title':f'{mod.title or mod.domain or mod.module_id} read skill candidate','summary':f'Shadow module has {mod.row_count} rows; read-only operations can be reviewed before enabling write functions.','source':f'memory_module:{mod.module_id}','risk':'low','status':'pending_review','recommended_action':'enable_read_only_skill_after_review'})
    seen=set(); out=[]
    for p in props:
        if p['proposal_id'] in seen: continue
        seen.add(p['proposal_id']); out.append(p)
    return {'summary':{'proposal_count':len(out),'memory_proposals':len([p for p in out if re.search(r'claim|memory|materialization',p.get('kind') or '')]),'rule_proposals':len([p for p in out if 'rule' in (p.get('kind') or '')]),'skill_proposals':len([p for p in out if 'skill' in (p.get('kind') or '')]),'high_risk_count':len([p for p in out if p.get('risk')=='high'])},'proposals':out[:80],'next_steps':['Approve, reject, edit, mark stale, merge, or promote candidates in GoC.','Treat agent writes as proposals; runtime/GoC should commit only reviewed low-risk memory.']}

def build_memory_review_overview(session: Session, thread: Thread)->dict[str,Any]:
    return {'ok':True,'kind':'memory_rule_skill_review_overview','generated_at':datetime.now(timezone.utc).isoformat(),'claims':build_claim_evidence_overview(session,thread),'pressure':build_pressure_overview(session,thread),'review_queue':build_review_queue(session,thread),'policy':{'principle':'agent proposes, runtime commits, GoC reviews','safe_defaults':['explicit /rule can be active','learned rules stay candidates','shadow tables are projections','write skills require approval']}}
