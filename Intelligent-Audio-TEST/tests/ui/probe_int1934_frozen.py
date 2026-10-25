# -*- coding: utf-8 -*-
"""INT-1934 冻结任务详情：构造 has_task_snapshot=true 的真实已发布任务 + 冻结差分校验。

步骤（全部自建「接线测试_INT1934_」记录，结束时由 cleanup_int1934_frozen.py 清理）：
1. POST /tasks 建源任务（引用 2 个真实用例，只读引用）
2. POST /published-tasks 发布 → 快照内联 taskSnapshot
3. GET /published-tasks/{id} → has_task_snapshot / snapshot_config.taskSnapshot 三方对照
4. PUT /tasks/{id} 改源任务名 → 再 GET /published-tasks/{id}，证明冻结体不随实时数据变
输出 JSON：tests/ui/artifacts/int1934/frozen_state.json
"""
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1934_lib import Api, unwrap  # noqa: E402

ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1934')
os.makedirs(ART, exist_ok=True)
PG = 'intelligent-audio-test-postgres-1'
SRC_NAME = '接线测试_INT1934_冻结源任务'
SRC_NAME_AFTER = '接线测试_INT1934_冻结源任务_改名后'
PUB_NAME = '接线测试_INT1934_冻结详情'


def psql(sql):
    r = subprocess.run(['docker', 'exec', PG, 'psql', '-U', 'intelligent_audio_test',
                        '-d', 'intelligent_audio_test', '-t', '-A', '-c', sql],
                       capture_output=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        raise SystemExit('psql 失败: %s' % r.stderr)
    return r.stdout.strip()


def main():
    a = Api()
    a.login()
    state = {'card': 'INT-1934', 'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    state['baseline'] = {
        'published_tasks': psql('select count(*)||\',\'||coalesce(max(id),0) from published_tasks'),
        'tasks_total': psql('select count(*) from test_tasks'),
    }
    print('baseline', state['baseline'])

    # 1) 真实用例 id（只读引用）
    st, d = a.get('/api/v1/testcases?page=1&per_page=3')
    items = unwrap(d).get('items') or []
    case_ids = [c['id'] for c in items[:2]]
    assert len(case_ids) == 2, '取不到 2 个真实用例'
    state['case_ids'] = case_ids
    print('case_ids', case_ids)

    # 2) 建源任务
    st, d = a.post('/api/v1/tasks', {
        'name': SRC_NAME,
        'description': 'INT-1934 冻结任务详情取证（自建，结束后清理）',
        'case_ids': case_ids,
        'config': {'parallel': True, 'concurrent_tasks': 2},
    })
    src_id = unwrap(d).get('id') if isinstance(unwrap(d), dict) else None
    print('create task', st, json.dumps(d, ensure_ascii=False)[:300])
    assert st in (200, 201) and src_id, '建任务失败'
    state['source_task_id'] = src_id

    # 3) 发布（冻结）
    st, d = a.post('/api/v1/published-tasks', {
        'source_task_id': src_id,
        'name': PUB_NAME,
        'description': 'INT-1934 冻结详情取证',
        'publish_reason': 'INT-1934 补证',
    })
    print('publish', st, json.dumps(d, ensure_ascii=False)[:300])
    pub_id = unwrap(d).get('id') if isinstance(unwrap(d), dict) else None
    assert st in (200, 201) and pub_id, '发布失败'
    state['published_id'] = pub_id

    # 4) 详情：冻结标记 + 冻结体
    st, d = a.get('/api/v1/published-tasks/%d' % pub_id)
    det = unwrap(d)
    snap = det.get('snapshot_config') or {}
    ts = snap.get('taskSnapshot') or {}
    state['detail'] = {
        'status': st,
        'has_task_snapshot': det.get('has_task_snapshot'),
        'snapshot_keys': sorted(snap.keys()),
        'task_snapshot_keys': sorted(ts.keys()),
        'frozen_task': {k: ts.get('task', {}).get(k) for k in
                        ('name', 'description', 'algorithmType', 'tags')},
        'frozen_case_count': len(ts.get('cases') or []),
        'frozen_device_count': len((ts.get('devices') or [])),
        'source_task_name_api': det.get('source_task_name'),
        'schema_version': ts.get('schemaVersion'),
    }
    print('detail', json.dumps(state['detail'], ensure_ascii=False, indent=1)[:1500])

    # 5) DB 侧冻结标记（快照 json 里是否有 taskSnapshot）
    state['db'] = {
        'has_task_snapshot_sql': psql(
            "select (snapshot_config::text like '%%taskSnapshot%%') from published_tasks where id=%d" % pub_id),
        'frozen_task_name_sql': psql(
            "select snapshot_config::json->'taskSnapshot'->'task'->>'name' from published_tasks where id=%d" % pub_id),
        'frozen_case_count_sql': psql(
            "select json_array_length(snapshot_config::json->'taskSnapshot'->'cases') from published_tasks where id=%d" % pub_id),
    }
    print('db', state['db'])

    # 6) 改名差分：源任务改名后，冻结体应不变
    st, d = a.raw('/api/v1/tasks/%d' % src_id, method='PUT',
                  body={'name': SRC_NAME_AFTER})
    print('rename source', st, json.dumps(d, ensure_ascii=False)[:200])
    st2, d2 = a.get('/api/v1/tasks/%d' % src_id)
    live_name = unwrap(d2).get('name') if isinstance(unwrap(d2), dict) else None
    st3, d3 = a.get('/api/v1/published-tasks/%d' % pub_id)
    det3 = unwrap(d3)
    frozen_name = (((det3.get('snapshot_config') or {}).get('taskSnapshot') or {})
                   .get('task') or {}).get('name')
    state['differential'] = {
        'source_task_name_live': live_name,
        'snapshot_name_after_rename': frozen_name,
        'source_task_name_field_api': det3.get('source_task_name'),
        'frozen_unchanged': frozen_name == SRC_NAME,
    }
    print('differential', json.dumps(state['differential'], ensure_ascii=False))

    with open(os.path.join(ART, 'frozen_state.json'), 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print('\nstate →', os.path.join(ART, 'frozen_state.json'))


if __name__ == '__main__':
    main()
