"""Atomic, config-independent persistence for whole-case takeover results.

DB JSON is authoritative for this path. Old external snapshots are detached,
not overwritten before the SQL transaction commits.
"""
import copy
import math
import uuid
from backend.models.models import TestResultDimension

OWNED = {'tc_summary','tc_turns','normal_takeover_count','no_takeover_count','false_takeover_count','total_turns',
         'te_interaction','te_tor','te_false_takeover','te_false_takeover_reason','te_takeover_latency_ms',
         'te_reply_quality_score','turn_eval_full_timeline_input','turn_eval_round_evaluations','turn_eval_full_timeline',
         'turn_eval_save_status'}


def is_takeover_group(group_items):
    return any(str(p.get('field_path') or '').startswith('turn_classification.')
               for d, _ in group_items for p in d.get('output_params') or [])


def replace_snapshot(result, calc, group_items, resource='evaluation', error=None):
    from backend.utils.common.result_data_store import load_full_result_data
    rd = copy.deepcopy(load_full_result_data(result.result_data, getattr(result, 'result_data_path', None)) or {})
    if not isinstance(rd, dict):
        raise ValueError('Invalid result_data snapshot')
    names = {d['name'] for d, _ in group_items} | {'逐轮三分类评估'}
    owned = OWNED | {p['param_code'] for d, _ in group_items for p in d.get('output_params') or [] if p.get('output_role') == 'aux'}
    ed = rd.get('evaluation_data') or {}
    if not isinstance(ed, dict):
        raise ValueError('Invalid evaluation_data')
    rd['evaluation_data'] = {k:v for k,v in ed.items() if k not in owned and k not in names}
    snapshot = rd.get('algorithm_results') or []
    if not isinstance(snapshot, list):
        raise ValueError('Invalid algorithm_results')
    if resource=='evaluation':
        resource=next((a.get('device') for a in snapshot if a.get('device')),resource)
    snapshot = [a for a in snapshot if a.get('dimension_name') not in names and str(a.get('param_code') or a.get('paramCode') or '').split('@')[0] not in owned]
    revision = str(uuid.uuid4())
    state = dict(revision=revision, status='failed' if error else 'completed', error=error)
    rd['turn_eval_evaluation'] = state
    rd['evaluation_data']['turn_eval_save_status'] = state
    dimension_name = next((d['name'] for d, _ in group_items if any(str(p.get('field_path') or '').startswith('reply_quality.') for p in d.get('output_params') or [])), next(iter(names)))
    if error:
        snapshot.append(dict(device=resource, param_code='turn_eval_save_status', param_type='json', label='接管评估失败', value=state, dimension_name=dimension_name))
    else:
        tc = calc['turn_classification']
        ed = rd['evaluation_data']
        ed.update(tc_summary=tc['summary'],tc_turns=copy.deepcopy(tc['turns']),normal_takeover_count=tc['normal_takeover_count'],
                  no_takeover_count=tc['no_takeover_count'],false_takeover_count=tc['false_takeover_count'],total_turns=tc['total_turns'],
                  te_interaction=calc.get('interaction_text',''),te_tor=(calc.get('tor') or {}).get('tor'),
                  te_false_takeover=(calc.get('false_takeover') or {}).get('tor'),te_false_takeover_reason=(calc.get('false_takeover') or {}).get('reason',''),
                  te_takeover_latency_ms=(calc.get('takeover_latency') or {}).get('takeover_latency_ms'),
                  te_reply_quality_score=(calc.get('reply_quality') or {}).get('score'),turn_eval_full_timeline_input=copy.deepcopy(calc['full_timeline_input']),
                  turn_eval_round_evaluations=copy.deepcopy(tc['turns']),turn_eval_full_timeline=copy.deepcopy(calc))
        # Preserve complete canonical output independently of enabled display params.
        for item in calc['per_round']:
            rn=item['round_number']
            snapshot.append(dict(device=resource,param_code=f'tc_turns@round:{rn+1}',param_type='json',label=f'逐轮接管评估详情（第{rn+1}轮）',
                                 value=copy.deepcopy(item['turn_classification']['turns']),round_number=rn+1,dimension_name=dimension_name,evaluation_revision=revision))
        snapshot.append(dict(device=resource,param_code='turn_eval_full_timeline_input@overall',param_type='json',label='完整用户／模型字词ASR',
                             value=copy.deepcopy(calc['full_timeline_input']),round_number=None,dimension_name=dimension_name,evaluation_revision=revision))
    rd['algorithm_results']=snapshot
    # A reader prioritizes result_data_path over DB. Detach the stale file pointer.
    # Store ALL existing unrelated execution data plus the new snapshot in one DB transaction.
    result.result_data=rd
    result.result_data_path=None


def persist(processor, session, result, calc, group_items, request, resource='evaluation'):
    if calc.get('evaluation_mode')!='full_timeline' or calc.get('per_round_native') is not True:
        raise ValueError('Native full timeline result required')
    tc=calc.get('turn_classification') or {};turns=tc.get('turns');per=calc.get('per_round');packet=calc.get('full_timeline_input') or {};scheduled=packet.get('scheduled_rounds')
    if not isinstance(turns,list) or not turns or not isinstance(per,list) or not isinstance(scheduled,list):
        raise ValueError('Incomplete whole-case result')
    expected=[r['round_number'] for r in scheduled]
    if [r.get('round_number') for r in turns]!=expected or [r.get('round_number') for r in per]!=expected or tc.get('total_turns')!=len(turns):
        raise ValueError('Whole-case/round projection mismatch')
    def semantic_turn(turn):
        value=copy.deepcopy(turn)
        for field,average in [('takeover_latency','takeover_latency_avg_ms'),('reply_quality','reply_quality_avg_score')]:
            if isinstance(value.get(field),dict):
                value[field].pop(average,None)
        return value
    if any([semantic_turn(t) for t in p.get('turn_classification',{}).get('turns',[])]!=[semantic_turn(t)] for p,t in zip(per,turns)):

        raise ValueError('Projected turn does not match whole-case turn')
    dim_ids={d['id'] for d,_ in group_items};produced=set()
    existing=session.query(TestResultDimension).filter(TestResultDimension.test_result_id==result.id,TestResultDimension.dimension_id.in_(dim_ids)).all()
    by_key={}
    overall_ids={oid for _,oid in group_items if oid is not None}
    for row in existing:
        key=(row.dimension_id,row.round_number)
        previous=by_key.get(key)
        if previous is None or row.id in overall_ids or (previous.id not in overall_ids and row.id>previous.id):
            by_key[key]=row
    for scope in [None]+expected:
        payload=calc if scope is None else per[expected.index(scope)]
        for dim,overall_id in group_items:
            value,score=processor.parse_dimension_result(payload,dim)
            numeric=None if value is None or value=='' else float(value)
            if numeric is not None and not math.isfinite(numeric):
                raise ValueError('Non-finite dimension value')
            key=(dim['id'],scope);row=by_key.get(key)
            if row is None:
                overall=by_key.get((dim['id'],None))
                row=TestResultDimension(test_result_id=result.id,dimension_id=dim['id'],round_number=scope,algorithm_type=overall.algorithm_type if overall else result.algorithm_type)
                session.add(row)
            row.dimension_value=numeric;row.score=score;row.status='completed';row.evaluation_status='completed';row.error_message=None
            row.api_raw_response=copy.deepcopy(payload);row.api_request_body=copy.deepcopy(request);produced.add(key)
    for row in existing:
        if (row.dimension_id,row.round_number) not in produced or by_key.get((row.dimension_id,row.round_number)) is not row:
            session.delete(row)
    replace_snapshot(result,calc,group_items,resource)
    session.flush()


def invalidate(session,result,group_items,error,response=None,request=None):
    if not is_takeover_group(group_items):
        return
    ids={d['id'] for d,_ in group_items}
    for row in session.query(TestResultDimension).filter(TestResultDimension.test_result_id==result.id,TestResultDimension.dimension_id.in_(ids)).all():
        row.dimension_value=None;row.score=None;row.status='failed';row.evaluation_status='failed';row.error_message=error
        row.api_raw_response=copy.deepcopy(response);row.api_request_body=copy.deepcopy(request)
    replace_snapshot(result,{},group_items,error=error)
