# -*- coding: utf-8 -*-
"""INT-1934 冻结夹具状态落盘（可重入）：读取已构造的 published_tasks 22 / 源任务 694，
补齐 DB(psql) + API 两方数据，写 artifacts/int1934/frozen_state.json。"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1934_lib import Api, unwrap  # noqa: E402

ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1934')
PG = 'intelligent-audio-test-postgres-1'
PUB_ID = 22
SRC_ID = 694
SRC_NAME = '接线测试_INT1934_冻结源任务'


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
    st, d = a.get('/api/v1/published-tasks/%d' % PUB_ID)
    det = unwrap(d)
    snap = det.get('snapshot_config') or {}
    ts = snap.get('taskSnapshot') or {}
    st2, d2 = a.get('/api/v1/tasks/%d' % SRC_ID)
    live = unwrap(d2)
    state = {
        'card': 'INT-1934',
        'published_id': PUB_ID,
        'source_task_id': SRC_ID,
        'baseline_published_tasks': '2,12',
        'detail': {
            'status': st,
            'has_task_snapshot': det.get('has_task_snapshot'),
            'snapshot_keys': sorted(snap.keys()),
            'task_snapshot_keys': sorted(ts.keys()),
            'frozen_task': {k: (ts.get('task') or {}).get(k) for k in
                            ('name', 'description', 'algorithmType', 'tags')},
            'frozen_case_count': len(ts.get('cases') or []),
            'frozen_device_count': len(ts.get('devices') or []),
            'schema_version': ts.get('schemaVersion'),
            'source_task_name_api': det.get('source_task_name'),
        },
        'db': {
            'has_taskSnapshot': psql(
                "select (snapshot_config::text like '%%taskSnapshot%%') "
                "from published_tasks where id=%d" % PUB_ID),
            'frozen_task_name': psql(
                "select snapshot_config::json->'taskSnapshot'->'task'->>'name' "
                "from published_tasks where id=%d" % PUB_ID),
            'frozen_case_count': psql(
                "select json_array_length(snapshot_config::json->'taskSnapshot'->'cases') "
                "from published_tasks where id=%d" % PUB_ID),
            'frozen_schema_version': psql(
                "select snapshot_config::json->'taskSnapshot'->>'schemaVersion' "
                "from published_tasks where id=%d" % PUB_ID),
            'source_task_name_live': psql(
                "select name from test_tasks where id=%d" % SRC_ID),
        },
        'differential': {
            'live_task_name': live.get('name'),
            'frozen_name_unchanged': ((ts.get('task') or {}).get('name') == SRC_NAME),
            'source_task_name_field_api_live': det.get('source_task_name'),
        },
    }
    with open(os.path.join(ART, 'frozen_state.json'), 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(json.dumps(state, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
