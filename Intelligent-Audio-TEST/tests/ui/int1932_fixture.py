# -*- coding: utf-8 -*-
"""INT-1932 验收夹具：真实库（intelligent_audio_test）上的 AI 复核可判分维度夹具。

环境缺口：真实库唯一 llm_judge 维度（164）无 API 端点、其余维度端点 100.70.20.135:8888
不可达 → AI 复核执行链只能落 failed，无法验「成功路径」。本夹具按既有 llm-judge 夹具口径
造一条可判分维度，端点指向宿主侧替身 tests/ui/int1932_llm_stub.py：

  1) dimensions       新建「接线测试_INT1932_LLMJudge」（task_type_code=int1932_llm_judge）
     api_url=http://host.docker.internal:<port>，api_settings.body_template={}
  2) evaluation_dimension_params  output: llm_judge_score(field_path=score, main, 阈值 0.7)
                                   reasoning(field_path=reasoning)
  3) test_result_dimensions       给目标结果补一条该维度的评估记录（completed + 上下文）
  4) test_cases.config            三个目标用例的 dimensions 临时替换为 [新维度]（便于会话只发一条）

全部改动先在 snapshot 里记录，teardown 逐项还原（含 ai_reviews / test_result_reviews /
TRD / test_results / task_case_relations / test_tasks 统计 / 用例 config）。

用法：
  python tests/ui/int1932_fixture.py setup
  python tests/ui/int1932_fixture.py teardown
  python tests/ui/int1932_fixture.py status
"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

PG = 'intelligent-audio-test-postgres-1'
DB = 'intelligent_audio_test'
USER = 'intelligent_audio_test'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1932')
SNAP = os.path.join(ART, 'fixture_snapshot.json')
STUB_PORT = int(os.environ.get('INT1932_STUB_PORT', '5312'))

TASK_ID = 419
TARGETS = [
    {'result_id': 5716, 'case_id': '14a13fa8-679d-4179-8608-a24e86cbbc3d', 'tag': 'JS177', 'role': '会话保存/回显'},
    {'result_id': 5714, 'case_id': '77ca28bc-be7b-47b4-b84f-19cb83caf5c6', 'tag': 'JS161', 'role': '快速复核·采纳'},
    {'result_id': 5715, 'case_id': '0dc13869-a63c-4632-be72-2efd4e0e4f39', 'tag': 'JS062', 'role': '快速复核·驳回'},
]
DIM_NAME = '接线测试_INT1932_LLMJudge'


def psql(sql, tuples_only=True):
    cmd = ['docker', 'exec', '-i', PG, 'psql', '-q', '-U', USER, '-d', DB, '-v', 'ON_ERROR_STOP=1']
    if tuples_only:
        cmd += ['-t', '-A']
    cmd += ['-f', '-']
    p = subprocess.run(cmd, input=sql.encode('utf-8'), capture_output=True)
    out = p.stdout.decode('utf-8', 'replace')
    err = p.stderr.decode('utf-8', 'replace')
    if p.returncode != 0:
        raise RuntimeError(f'psql failed: {err[-2000:]}')
    return out


def q(v):
    """SQL 字符串字面量"""
    return "'" + str(v).replace("'", "''") + "'"


def jq(v):
    """SQL json 字面量（dollar quoting）"""
    return '$j$' + json.dumps(v, ensure_ascii=False) + '$j$'


def setup():
    os.makedirs(ART, exist_ok=True)
    if os.path.isfile(SNAP):
        raise SystemExit('已有快照，先 teardown 再 setup')
    snap = {'targets': TARGETS, 'task_id': TASK_ID, 'dim_name': DIM_NAME}
    ids = ','.join(str(t['result_id']) for t in TARGETS)
    case_ids = ','.join(q(t['case_id']) for t in TARGETS)

    snap['case_configs'] = json.loads(psql(
        f'select coalesce(json_object_agg(id, config), json_build_object()::json)::text from test_cases where id in ({case_ids});'))
    snap['results'] = json.loads(psql(
        f'select coalesce(json_object_agg(id, row_to_json(r)), json_build_object()::json)::text '
        f'from (select * from test_results where id in ({ids})) r;'))
    snap['task_cases'] = json.loads(psql(
        f"select coalesce(json_object_agg(test_case_id, row_to_json(t)), json_build_object()::json)::text "
        f"from (select * from task_case_relations where task_id={TASK_ID} and test_case_id in ({case_ids})) t;"))
    snap['task'] = json.loads(psql(
        f'select row_to_json(t)::text from (select id,total_cases,completed_cases,failed_cases,status '
        f'from test_tasks where id={TASK_ID}) t;'))
    snap['trd'] = json.loads(psql(
        f'select coalesce(json_agg(row_to_json(t)), \'[]\'::json)::text from '
        f'(select * from test_result_dimensions where test_result_id in ({ids})) t;'))
    snap['max_ids'] = {
        'ai_reviews': int(psql('select coalesce(max(id),0) from ai_reviews;').strip().splitlines()[0]),
        'test_result_reviews': int(psql('select coalesce(max(id),0) from test_result_reviews;').strip().splitlines()[0]),
        'trd': int(psql('select coalesce(max(id),0) from test_result_dimensions;').strip().splitlines()[0]),
        'dimensions': int(psql('select coalesce(max(id),0) from dimensions;').strip().splitlines()[0]),
        'params': int(psql('select coalesce(max(id),0) from evaluation_dimension_params;').strip().splitlines()[0]),
    }
    with open(SNAP, 'w', encoding='utf-8') as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)

    # 1) 维度 + 参数
    body_template = {}
    api_settings = {'method': 'POST', 'headers': {}, 'body_template': body_template,
                    'timeout': 60000}
    api_url = f'http://host.docker.internal:{STUB_PORT}'
    dim_id = int(psql(f"""
insert into dimensions(name,keywords,dimension_type,parent_dimension_id,task_type_code,category_id,type,result_type,
  result_min,result_max,decimal_places,weight,estimated_exec_time,status,deleted,api_status,api_endpoints,api_url,
  score_unit,statistic_method,visibility,rule,api_settings,created_at,updated_at)
values({q(DIM_NAME)},{q('llm_judge,接线测试,INT1932')},'main',null,'int1932_llm_judge',null,'auto',1,
  0,1,2,1,60,true,false,'online',null,{q(api_url)},
  '分','average','shared',{jq({"rules": [], "defaultScore": 0})},{jq(api_settings)},now(),now())
returning id;""").strip().splitlines()[0])
    psql(f"""
insert into evaluation_dimension_params(dimension_id,param_code,param_name,label,field_type,required,default_value,
  help_text,ui_order,deleted,created_at,updated_at,param_direction,field_path,agg_role,output_role,visible_in_report,pass_threshold)
values
 ({dim_id},'llm_judge_score','LLM判分','LLM判分','number',true,null,'接线测试夹具主评分',1,false,now(),now(),'output','score','main','main',true,0.7),
 ({dim_id},'reasoning','复检理由','复检理由','string',false,null,'接线测试夹具复检理由',2,false,now(),now(),'output','reasoning',null,'helper',true,null),
 ({dim_id},'question','问题ASR','问题ASR','text',false,null,'接线测试夹具输入',1,false,now(),now(),'input',null,null,null,true,null);""")

    # 2) TRD 记录 + 3) 用例 config
    for t in TARGETS:
        req_body = {'question': f'接线测试_INT1932 {t["tag"]} 问题 ASR',
                    'answer': f'接线测试_INT1932 {t["tag"]} 被测回复 ASR',
                    'correct_answer': '拒识成功，不应回复',
                    'query': '接线测试_INT1932 复核上下文'}
        psql(f"""
insert into test_result_dimensions(test_result_id,dimension_id,algorithm_type,dimension_value,score,status,
  evaluation_status,error_message,api_raw_response,api_request_body,created_at,round_number)
values({t['result_id']},{dim_id},'int1932_llm_judge',0.86,0.86,'passed','completed',null,
  {jq({"reasoning": "接线测试_INT1932 原始评估评语"})},{jq(req_body)},now(),0);""")
        cfg = json.loads(json.dumps(snap['case_configs'][t['case_id']]))
        orig_dims = cfg.get('dimensions') or []
        cfg['dimensions'] = [{'id': str(dim_id), 'name': DIM_NAME, 'weight': 100, 'threshold': 70}]
        cfg['_int1932_orig_dimensions'] = orig_dims
        psql(f"update test_cases set config={jq(cfg)}::json where id={q(t['case_id'])};")

    snap['dim_id'] = dim_id
    with open(SNAP, 'w', encoding='utf-8') as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    print(json.dumps({'ok': True, 'dim_id': dim_id, 'snapshot': SNAP}, ensure_ascii=False))


def teardown():
    if not os.path.isfile(SNAP):
        raise SystemExit('没有快照，无需还原')
    snap = json.load(open(SNAP, encoding='utf-8'))
    dim_id = snap['dim_id']
    ids = ','.join(str(t['result_id']) for t in snap['targets'])
    case_ids = ','.join(q(t['case_id']) for t in snap['targets'])
    m = snap['max_ids']

    sql = []
    sql.append(f'delete from ai_reviews where id > {m["ai_reviews"]} and result_id in ({ids});')
    sql.append(f'delete from test_result_reviews where id > {m["test_result_reviews"]} and task_id={TASK_ID};')
    sql.append(f'delete from test_result_dimensions where id > {m["trd"]} and test_result_id in ({ids});')
    # 还原既有 TRD 行（采纳会经 SetDimensionReviewStatusByResultIds 改 status/evaluation_status）
    for row in snap['trd']:
        sql.append(
            'update test_result_dimensions set dimension_value={v}, score={s}, status={st}, evaluation_status={es} where id={i};'.format(
                v='null' if row.get('dimension_value') is None else row['dimension_value'],
                s='null' if row.get('score') is None else row['score'],
                st='null' if row.get('status') is None else q(row['status']),
                es=q(row['evaluation_status']), i=row['id']))
    # 还原 test_results
    for r in snap['results'].values():
        sql.append(
            'update test_results set execution_status={ex}, reviewed={rv}, reviewed_by_user_id={rbu}, '
            'reviewed_at={ra}, last_review_comment={lc}, last_review_action={la} where id={i};'.format(
                ex=q(r['execution_status']),
                rv=r.get('reviewed') or 0,
                rbu='null' if r.get('reviewed_by_user_id') is None else r['reviewed_by_user_id'],
                ra='null' if r.get('reviewed_at') is None else q(r['reviewed_at']),
                lc='null' if r.get('last_review_comment') is None else q(r['last_review_comment']),
                la='null' if r.get('last_review_action') is None else q(r['last_review_action']),
                i=r['id']))
    # 还原 task_case_relations
    for tc in snap['task_cases'].values():
        sql.append(
            'update task_case_relations set status={st}, execution_status={ex}, evaluation_status={es}, '
            'updated_by_user_id={ub} where task_id={t} and test_case_id={c};'.format(
                st=q(tc['status']), ex='null' if tc.get('execution_status') is None else q(tc['execution_status']),
                es='null' if tc.get('evaluation_status') is None else q(tc['evaluation_status']),
                ub='null' if tc.get('updated_by_user_id') is None else tc['updated_by_user_id'],
                t=TASK_ID, c=q(tc['test_case_id'])))
    # 还原任务统计
    tk = snap['task']
    sql.append('update test_tasks set total_cases={t}, completed_cases={c}, failed_cases={f} where id={i};'.format(
        t=tk['total_cases'], c=tk['completed_cases'], f=tk['failed_cases'], i=TASK_ID))
    # 还原用例 config
    for cid, cfg in snap['case_configs'].items():
        sql.append(f'update test_cases set config={jq(cfg)}::json where id={q(cid)};')
    # 删夹具维度
    sql.append(f'delete from evaluation_dimension_params where dimension_id={dim_id};')
    sql.append(f'delete from dimensions where id={dim_id};')
    psql('\n'.join(sql))

    left = psql(
        'select json_build_object('
        f"'ai_reviews',(select count(*) from ai_reviews where id > {m['ai_reviews']}),"
        f"'reviews',(select count(*) from test_result_reviews where id > {m['test_result_reviews']}),"
        f"'trd',(select count(*) from test_result_dimensions where id > {m['trd']}),"
        f"'dim',(select count(*) from dimensions where id={dim_id}),"
        f"'params',(select count(*) from evaluation_dimension_params where dimension_id={dim_id})"
        ')::text;').strip()
    cfg_same = json.loads(psql(
        f'select coalesce(json_object_agg(id, config), json_build_object()::json)::text from test_cases where id in ({case_ids});'))
    unchanged = all(json.loads(json.dumps(cfg_same[k])) == json.loads(json.dumps(v))
                    for k, v in snap['case_configs'].items())
    os.remove(SNAP)
    print(json.dumps({'ok': True, 'left_over': json.loads(left), 'case_config_restored': unchanged},
                     ensure_ascii=False))


def status():
    if not os.path.isfile(SNAP):
        print(json.dumps({'snapshot': None}, ensure_ascii=False))
        return
    snap = json.load(open(SNAP, encoding='utf-8'))
    ids = ','.join(str(t['result_id']) for t in snap['targets'])
    print(psql(f'select id,result_id,dimension_id,status,verdict,confidence,adopted,rejected from ai_reviews '
               f'where result_id in ({ids}) and dimension_id={snap["dim_id"]} order by id;'))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    {'setup': setup, 'teardown': teardown, 'status': status}[cmd]()
