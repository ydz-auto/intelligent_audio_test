# -*- coding: utf-8 -*-
"""INT-472：compose 容器栈四步冒烟驱动（登录→建用例→dry 执行→报告）。

对齐 INT-314 冒烟门禁四步语义，但目标栈为 compose 容器栈（网关 :5000，业务库
intelligent_audio_test）——这是负责人拍板的容器化部署落地验收冒烟，含写操作，
资源一律带唯一 tag 创建并登记，finally 全量软删清理 + 零残留终检。

与 scripts/smoke_gate.py 的差异（INT-246 隔离纪律仍约束常规门禁，本脚本仅
INT-472 部署验收一次性使用）：
- 目标网关 :5000（compose 栈），非 :6000 并行隔离栈；
- 维度 api_url 临时指向宿主 mock 裁判（容器经 host.docker.internal 可达），
  冒烟结束恢复原值（业务库配置不被污染）；
- presign 直传 URL 宿主为 rustfs（容器网络名），宿主侧 PUT 时改写连接目标为
  127.0.0.1:9000 并保留原 Host 头（S3 SigV4 签名覆盖 Host 头，改连接目标
  不改 Host 签名仍有效）；
- DB 断言/残留终检查业务库（DATABASE_URL）。

用法（仓库根）：
    python scripts/compose_stack_smoke.py --json
前置：
    compose 栈已 up（网关 :5000）；
    mock 裁判已在宿主 0.0.0.0:5097 监听：
        python mock_services/mock_eval_server_judge.py --host 0.0.0.0 --port 5097
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import httpx  # noqa: E402
import psycopg2  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding  # noqa: E402

from scripts.smoke_gate import (  # noqa: E402
    GateFail, resp_data, step, _exc_detail, encrypt_pw,
)

def _env_val(key: str, default: str) -> str:
    """读取 .env 中某键的值（run_stack 同源口径）。"""
    env_path = os.path.join(PROJECT_ROOT, '.env')
    if os.path.isfile(env_path):
        with open(env_path, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(key + '='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    return os.environ.get(key, default)


# compose 网关宿主端口（过渡期 scratch 覆盖，.env API_GATEWAY_PORT）
GATEWAY = f"http://127.0.0.1:{_env_val('API_GATEWAY_PORT', '5000')}"
API_BASE = f'{GATEWAY}/api/v1'
# 容器栈首跑执行链较宿主慢（任务执行+评估 ~35s 实测），请求超时放宽到 120s
CK = dict(timeout=120, trust_env=False)
SAMPLE_DIR = os.path.join(PROJECT_ROOT, 'doc', 'voice_llm', '样例')
SAMPLE_AUDIO_FILES = ['2026144010.wav', '2026144019.wav']
TAG = f'INT472SMOKE_{secrets.token_hex(4)}'
PY = sys.executable

# 宿主 mock 裁判（容器内经 host.docker.internal 可达宿主 5097）
MOCK_JUDGE_PORT = 5097
CONTAINER_JUDGE_URL = f'http://host.docker.internal:{MOCK_JUDGE_PORT}'


def biz_db_url() -> str:
    """业务库连接串（.env DATABASE_URL + POSTGRES_PORT 宿主端口覆盖）。

    compose 过渡期 infra 宿主端口走 scratch（POSTGRES_PORT=15432），业务库
    在 compose postgres 容器内；端口按覆盖值对齐，库名/凭据同 .env。
    """
    url = _env_val('DATABASE_URL', os.environ.get('DATABASE_URL', ''))
    if not url:
        raise GateFail('.env 无 DATABASE_URL，无法连接业务库断言/终检')
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(url)
    pg_port = _env_val('POSTGRES_PORT', '5432')
    userinfo = ''
    if parts.username:
        userinfo = parts.username
        if parts.password:
            userinfo += ':' + parts.password
        userinfo += '@'
    netloc = f'{userinfo}{parts.hostname}:{pg_port}'
    return urlunsplit((parts.scheme, netloc, parts.path, '', ''))


def H(token):
    return {'Authorization': f'Bearer {token}'}


def _req(method: str, url: str, retries: int = 4, **kwargs) -> httpx.Response:
    """请求 + 连接复位重试（容器栈网关 keep-alive 偶发 WinError 10054，重试兜底）。"""
    last = None
    for _ in range(retries):
        try:
            return httpx.request(method, url, **{**CK, **kwargs})
        except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError) as e:
            last = e
            time.sleep(1)
    raise last


def _put_presigned(url: str, content: bytes) -> httpx.Response:
    """PUT 到 presign 直传 URL。

    presign URL 宿主为容器网络名 `rustfs:9000`（OSS_ENDPOINT），宿主侧不可解析。
    改写连接目标为发布端口 127.0.0.1:{RUSTFS_PORT}，并保留原 Host 头（S3 SigV4
    签名覆盖 Host 头，只有 Host 与原值一致签名才有效；连接目标不影响签名）。
    """
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(url)
    headers = {}
    if parts.hostname == 'rustfs':
        headers['Host'] = parts.netloc
        rustfs_port = _env_val('RUSTFS_PORT', '9000')
        url = urlunsplit((parts.scheme, f'127.0.0.1:{rustfs_port}', parts.path,
                          parts.query, parts.fragment))
    return httpx.put(url, content=content, headers=headers, **CK)


# ── 维度临时重指（业务库配置保护：记录原值 → 指宿主裁判 → 结束后恢复）──
_dim_restore = []  # (id, old_api_url)


def repoint_turn_eval_dimension(url: str):
    conn = psycopg2.connect(url, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, api_url FROM dimensions WHERE task_type_code='turn_eval' "
                "AND deleted=FALSE ORDER BY id")
            rows = cur.fetchall()
            if not rows:
                raise GateFail('业务库 turn_eval 维度未种子化（db_bootstrap 失败？）')
            for dim_id, old in rows:
                _dim_restore.append((dim_id, old))
                cur.execute('UPDATE dimensions SET api_url=%s WHERE id=%s',
                            (CONTAINER_JUDGE_URL, dim_id))
        conn.commit()
        print(f'[前置] 业务库 {len(rows)} 个 turn_eval 维度临时指向宿主裁判 '
              f'{CONTAINER_JUDGE_URL}（冒烟后恢复）', flush=True)
    finally:
        conn.close()


def restore_dimensions(url: str):
    if not _dim_restore:
        return
    conn = psycopg2.connect(url, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            for dim_id, old in _dim_restore:
                cur.execute('UPDATE dimensions SET api_url=%s WHERE id=%s',
                            (old, dim_id))
        conn.commit()
        print(f'[收尾] 已恢复 {len(_dim_restore)} 个维度 api_url 原值', flush=True)
    finally:
        conn.close()


# ── S1 登录（对齐 smoke_gate：encryption-key → RSA-OAEP）──────────────
def encryption_key() -> dict:
    r = httpx.get(f'{API_BASE}/auth/login/encryption-key', **CK)
    if r.status_code == 401:
        raise GateFail('GET /auth/login/encryption-key 返回 401（公钥下发应在白名单）')
    r.raise_for_status()
    return r.json()


def s1_login() -> str:
    doc = encryption_key()
    if doc.get('enabled'):
        r = httpx.post(f'{API_BASE}/auth/login',
                       json={'username': 'admin', **encrypt_pw('admin123', doc)}, **CK)
    else:
        # AUTH_MODE=off 且加密关闭时明文登录
        r = httpx.post(f'{API_BASE}/auth/login',
                       json={'username': 'admin', 'password': 'admin123'}, **CK)
    body = r.json() if r.status_code == 200 else {}
    tok = body.get('access_token') or (body.get('data') or {}).get('access_token') or ''
    if r.status_code != 200 or not tok:
        raise GateFail(f'登录失败 HTTP {r.status_code}: {r.text[:400]}')
    step('S1 登录（compose 网关）', True, f'gateway={GATEWAY} token_len={len(tok)}')
    return tok


# ── S2 建用例（dry 样例上传 + voice_llm API 用例 + turn_eval 绑定）───
def s2_create_case(token: str, created: dict) -> dict:
    created.setdefault('audio_ids', [])
    created.setdefault('tc_ids', [])
    created.setdefault('api_cfg_ids', [])
    created.setdefault('group_ids', [])

    missing = [os.path.join(SAMPLE_DIR, name) for name in SAMPLE_AUDIO_FILES
               if not os.path.isfile(os.path.join(SAMPLE_DIR, name))]
    if missing:
        raise GateFail('dry 样例音频缺失: ' + '; '.join(missing))

    h = H(token)
    conn = psycopg2.connect(biz_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM dimensions WHERE task_type_code='turn_eval' "
                        "AND deleted=FALSE ORDER BY id LIMIT 1")
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise GateFail('turn_eval 主维度未种子化')
    turn_eval_dim_id = row[0]

    r = httpx.post(f'{API_BASE}/apis', headers=h, **CK,
                   json={'name': f'{TAG}_mock_api',
                         'vendor': 'mock', 'description': 'INT-472 compose 冒烟 mock',
                         'algorithm_type': 'voice_llm', 'device_type': 'http_api',
                         'adapter_class': 'MockDialogAdapter', 'status': 'online',
                         'meta': {'purpose': 'int472-compose-smoke', 'mode': 'dialog'}})
    api_cfg_id = resp_data(r).get('id')
    if not api_cfg_id:
        raise GateFail(f'API 配置创建失败: {r.text[:300]}')
    created['api_cfg_ids'].append(api_cfg_id)

    # 上传 dry 样例（presign 直传；URL 宿主 rustfs → 127.0.0.1 改写）
    files = []
    for name in SAMPLE_AUDIO_FILES:
        p = os.path.join(SAMPLE_DIR, name)
        with open(p, 'rb') as f:
            files.append({'path': p, 'name': name, 'size': os.path.getsize(p),
                          'md5': hashlib.md5(f.read()).hexdigest(),
                          'relativePath': f'sample/{name}'})

    r = httpx.post(f'{API_BASE}/audios/upload/init', headers=h, **CK)
    upload_task_id = resp_data(r).get('taskId') or resp_data(r).get('task_id')
    if not upload_task_id:
        raise GateFail(f'upload/init 未返回 taskId: {r.text[:300]}')

    r = httpx.post(f'{API_BASE}/audios/upload/register', headers=h, **CK,
                   json={'taskId': upload_task_id,
                         'files': [{'name': f['name'], 'size': f['size'], 'md5': f['md5'],
                                    'relativePath': f['relativePath']} for f in files]})
    reg = resp_data(r).get('files', [])
    if len(reg) != len(files):
        raise GateFail(f'register 文件数不符: {r.text[:300]}')
    file_ids = [rf.get('fileId') or rf.get('file_id') for rf in reg]

    for idx, (f, fid) in enumerate(zip(files, file_ids)):
        r = httpx.post(f'{API_BASE}/audios/upload/presign', headers=h, **CK,
                       json={'filename': f['name'], 'fileSize': f['size'],
                             'md5': f['md5'], 'chunkSize': 5 * 1024 * 1024,
                             'isWav': True, 'relativePath': f['relativePath']})
        pres = resp_data(r)
        audio_id = None
        if pres.get('instantUpload'):
            audio_id = pres.get('audioId') or pres.get('audio_id')
        else:
            up_id = pres.get('uploadId') or pres.get('upload_id')
            oss_key = pres.get('ossKey') or pres.get('oss_key')
            parts = pres.get('parts', [])
            total_parts = pres.get('totalParts') or pres.get('total_parts', 1)
            uploaded = []
            for pi in range(total_parts):
                if pi < len(parts):
                    purl = parts[pi].get('url') or parts[pi].get('URL')
                else:
                    rr = httpx.post(f'{API_BASE}/audios/upload/presign-part', headers=h, **CK,
                                    json={'uploadId': up_id, 'partNumber': pi + 1},
                                    params={'oss_key': oss_key,
                                            'category': pres.get('category', 'audios')})
                    purl = resp_data(rr).get('url')
                # 容器网络名 rustfs 在宿主机不可解析 → 改写 + 保留原 Host 头
                with open(f['path'], 'rb') as fh:
                    pr = _put_presigned(purl, fh.read())
                if pr.status_code != 200:
                    raise GateFail(f'OSS PUT {pr.status_code}: {pr.text[:200]}')
                uploaded.append({'PartNumber': pi + 1,
                                 'ETag': pr.headers.get('ETag', '').strip('"')})
            r = httpx.post(f'{API_BASE}/audios/upload/complete-direct', headers=h, **CK,
                           json={'ossKey': oss_key, 'uploadId': up_id, 'parts': uploaded,
                                 'filename': f['name'], 'md5': f['md5'],
                                 'fileSize': f['size'], 'audioType': 'dry'})
            audio_id = resp_data(r).get('audioId') or resp_data(r).get('audio_id')
        if not audio_id:
            raise GateFail(f'音频 {f["name"]} 未获得 audioId: {r.text[:300]}')
        created['audio_ids'].append(audio_id)

        r = httpx.post(f'{API_BASE}/audios/upload/merge', headers=h, **CK,
                       json={'fileId': fid, 'taskId': upload_task_id,
                             'audioType': 'dry', 'createTestCase': False,
                             'inheritTags': True, 'dimensions': {}})
        md = resp_data(r)
        if md.get('status') != 'completed' and not md.get('audioId'):
            raise GateFail(f'merge 未完成: {json.dumps(md, ensure_ascii=False)[:300]}')

    r = httpx.post(f'{API_BASE}/groups', headers=h, **CK,
                   json={'name': f'{TAG}_组'})
    grp_id = resp_data(r).get('id')
    if not grp_id:
        raise GateFail(f'分组创建失败: {r.text[:300]}')
    created['group_ids'].append(grp_id)

    rounds = [{'round_number': i + 1,
               'audios': [{'audio_id': aid, 'spl': 65, 'play_order': 1}],
               'evaluation': {'dimensions': [{'id': turn_eval_dim_id, 'name': '逐轮话轮评估'}]}}
              for i, aid in enumerate(created['audio_ids'])]
    r = httpx.post(f'{API_BASE}/testcases', headers=h, **CK,
                   json={'name': f'{TAG}_API用例',
                         'description': 'INT-472 compose 冒烟（自建自清）',
                         'algorithm_type': 'voice_llm',
                         'group_id': grp_id,
                         'config': {'rounds': rounds}})
    tc = resp_data(r)
    tc_id = tc.get('id') or tc.get('case_id')
    if not tc_id:
        raise GateFail(f'用例创建失败: {r.text[:400]}')
    created['tc_ids'].append(tc_id)
    created['tc_id'] = tc_id
    created['api_cfg_id'] = api_cfg_id
    step('S2 建用例（dry 样例上传 + voice_llm 用例 + turn_eval 绑定）', True,
         f'audio={created["audio_ids"]} tc={tc_id}')
    return created


# ── S3 dry 执行 ─────────────────────────────────────────────────────
def s3_execute(token: str, created: dict) -> int:
    h = H(token)
    tc_id = created['tc_id']
    r = httpx.post(f'{API_BASE}/tasks', headers=h, **CK,
                   json={'name': f'{TAG}_任务', 'type': 'api',
                         'description': 'INT-472 compose 冒烟 dry 执行',
                         'case_ids': [tc_id],
                         'api_ids': [created['api_cfg_id']]})
    task_id = resp_data(r).get('id')
    if not task_id:
        raise GateFail(f'任务创建失败: {r.text[:400]}')
    created['task_id'] = task_id

    r = httpx.patch(f'{API_BASE}/tasks/{task_id}/cases', headers=h, **CK,
                    json={'action': 'add', 'caseIds': [tc_id],
                          'caseDevices': [{'caseId': tc_id,
                                           'deviceType': 'http_api',
                                           'deviceId': str(created['api_cfg_id'])}]})
    resp_data(r)

    r = httpx.post(f'{API_BASE}/tasks/{task_id}/start', headers=h, **CK)
    resp_data(r)

    deadline = time.time() + 420
    final_status = None
    while time.time() < deadline:
        rr = httpx.get(f'{API_BASE}/tasks/{task_id}/progress', headers=h, **CK)
        final_status = (resp_data(rr).get('status') or '').lower()
        if final_status in ('completed', 'failed', 'cancelled', 'stopped',
                            'partial_completed'):
            break
        time.sleep(3)
    if final_status not in ('completed', 'partial_completed'):
        raise GateFail(f'任务 {task_id} 未到完成终态（final={final_status}，420s 超时）')

    conn = psycopg2.connect(biz_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT execution_status, evaluation_status FROM task_case_relations '
                        'WHERE task_id=%s AND test_case_id=%s', (task_id, str(tc_id)))
            row = cur.fetchone()
            cur.execute('SELECT count(*) FROM test_results WHERE task_id=%s', (task_id,))
            result_count = cur.fetchone()[0]
    finally:
        conn.close()
    if not row:
        raise GateFail(f'任务 {task_id} 未找到用例关系行')
    exec_st, eval_st = row
    if result_count < 1:
        raise GateFail(f'任务 {task_id} 无 test_results 行（执行链未落结果）')
    if (exec_st or '').lower() != 'completed' or (eval_st or '').lower() != 'completed':
        raise GateFail(f'任务 {task_id} 用例链状态异常: execution={exec_st} '
                       f'evaluation={eval_st}')
    step('S3 dry 执行（mock 适配器 api 任务 → 执行/评估双 completed）', True,
         f'task={task_id} exec={exec_st} eval={eval_st} results={result_count}')
    return task_id


# ── S4 报告 ─────────────────────────────────────────────────────────
def s4_report(token: str, created: dict) -> int:
    h = H(token)
    task_id = created['task_id']
    r = _req('POST', f'{API_BASE}/reports/generate-task', headers=h,
             json={'taskId': task_id, 'name': f'{TAG}_报告',
                   'description': 'INT-472 compose 冒烟报告'})
    gd = resp_data(r)
    report_id = gd.get('reportId') or gd.get('report_id') or gd.get('id')
    deadline = time.time() + 180
    report = None
    while time.time() < deadline:
        if not report_id:
            rr = _req('GET', f'{API_BASE}/reports/by_task/{task_id}', headers=h)
            if rr.status_code == 200:
                try:
                    report_id = resp_data(rr).get('id')
                except GateFail:
                    report_id = None
            time.sleep(3)
            continue
        rr = _req('GET', f'{API_BASE}/reports/{report_id}', headers=h)
        report = resp_data(rr)
        if report.get('status') in ('completed', 'failed', 'published'):
            break
        time.sleep(3)
    if not report_id:
        raise GateFail(f'报告未生成: {json.dumps(gd, ensure_ascii=False)[:300]}')
    if not report or report.get('status') not in ('completed', 'published'):
        raise GateFail(f'报告 {report_id} 未达完成终态')
    summary = report.get('summary') or {}
    if not isinstance(summary, dict) or not summary:
        raise GateFail(f'报告 {report_id} summary 为空')
    created['report_id'] = report_id
    step('S4 报告（generate-task → 完成 + summary）', True,
         f'report={report_id} status={report.get("status")} summary_keys={len(summary)}')
    return report_id


# ── 清理（自建自清）──────────────────────────────────────────────────
def cleanup(token: str, created: dict) -> list:
    h = H(token)
    residue = []
    if created.get('report_id'):
        try:
            _req('DELETE', f'{API_BASE}/reports/{created["report_id"]}', headers=h)
        except Exception as e:
            residue.append(f'report {created["report_id"]}: {e}')
    if created.get('task_id'):
        try:
            _req('DELETE', f'{API_BASE}/tasks/{created["task_id"]}', headers=h)
        except Exception as e:
            residue.append(f'task {created["task_id"]}: {e}')
    for tc_id in created.get('tc_ids', []):
        try:
            _req('DELETE', f'{API_BASE}/testcases/{tc_id}', headers=h)
        except Exception as e:
            residue.append(f'tc {tc_id}: {e}')
    for aid in created.get('audio_ids', []):
        try:
            _req('DELETE', f'{API_BASE}/audios/{aid}', headers=h)
        except Exception as e:
            residue.append(f'audio {aid}: {e}')
    for api_id in created.get('api_cfg_ids', []):
        try:
            _req('DELETE', f'{API_BASE}/apis/{api_id}', headers=h)
        except Exception as e:
            residue.append(f'api_cfg {api_id}: {e}')
    for gid in created.get('group_ids', []):
        try:
            _req('DELETE', f'{API_BASE}/groups/{gid}', headers=h)
        except Exception as e:
            residue.append(f'group {gid}: {e}')
    return residue


def residue_check() -> list:
    residue = []
    conn = None
    try:
        conn = psycopg2.connect(biz_db_url(), connect_timeout=5)
        with conn.cursor() as cur:
            for table, col, live in [('test_tasks', 'name', 'deleted=FALSE'),
                                     ('test_cases', 'name', 'deleted=FALSE'),
                                     ('apis', 'name', 'deleted=FALSE'),
                                     ('test_case_groups', 'name', 'deleted=FALSE'),
                                     ('test_reports', 'name', 'deleted=FALSE'),
                                     ('published_tasks', 'name', "status<>'archived'")]:
                try:
                    cur.execute(f'SELECT id FROM {table} WHERE {col} LIKE %s AND {live}',
                                (f'%{TAG}%',))
                    for (row_id,) in cur.fetchall():
                        residue.append(f'{table}:{row_id}')
                except psycopg2.Error:
                    conn.rollback()
    except Exception as e:
        residue.append(f'residue_check 异常: {e}')
    finally:
        if conn:
            conn.close()
    return residue


def main():
    parser = argparse.ArgumentParser(description='INT-472 compose 容器栈四步冒烟')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    from scripts.smoke_gate import _STEPS  # 复用步骤记录器
    _STEPS.clear()

    created = {}
    token = ''
    exit_code = 0
    fail_detail = ''
    residue = []
    db = biz_db_url()
    try:
        repoint_turn_eval_dimension(db)
        try:
            token = s1_login()
            s2_create_case(token, created)
            s3_execute(token, created)
            s4_report(token, created)
        except GateFail as e:
            exit_code = 1
            fail_detail = str(e)
        except Exception as e:
            exit_code = 1
            fail_detail = f'异常逃逸（已收敛）: {_exc_detail(e)}'
        finally:
            residue = cleanup(token, created)

        passed = sum(1 for _, ok, _ in _STEPS if ok)
        total = len(_STEPS)
        leftover = residue_check()
        if leftover:
            exit_code = 1
            note = f'数据残留（可按 tag {TAG} 手动清理后复跑）: {leftover}'
            fail_detail = note if not fail_detail else f'{fail_detail}；{note}'
        if residue:
            exit_code = 1
            note = f'清理失败: {residue}'
            fail_detail = note if not fail_detail else f'{fail_detail}；{note}'
        print(f'==== INT-472 compose 冒烟: {passed}/{total} 步 PASS '
              f'{"—— 通过" if exit_code == 0 else "—— 不通过"} ====')
        if fail_detail:
            print(f'失败定位: {fail_detail}')
    except GateFail as e:
        exit_code = 1
        fail_detail = f'前置失败: {e}'
        print(f'[FAIL] {fail_detail}')
    except Exception as e:
        exit_code = 1
        fail_detail = f'前置异常: {_exc_detail(e)}'
        print(f'[FAIL] {fail_detail}')
    finally:
        try:
            restore_dimensions(db)
        except Exception as e:
            print(f'[收尾][WARN] 维度恢复失败（请手动恢复）: {e}')

    if args.json:
        print(json.dumps({
            'gate': 'INT-472-compose', 'pass': exit_code == 0,
            'steps': [{'step': n, 'ok': ok, 'detail': d} for n, ok, d in _STEPS],
            'fail_detail': fail_detail, 'residue': residue, 'tag': TAG,
        }, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
