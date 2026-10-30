# -*- coding: utf-8 -*-
"""INT-597（INT-993 当前基线重交付）：隔离栈验收冒烟 —— 登录 → 建用例 → 建任务 → 执行 → 出报告（API 链）。

运行位置：隔离栈容器网络内（经 docker/run_stack_iso.py smoke 以 docker run 挂载执行，
也可手动 `docker run --rm --network <project>_default --entrypoint python <image> /smoke.py ...`）。
网络内 api_gateway / rustfs / mock_dut_api 经 Docker DNS 可达：
  - 音频上传 presigned URL 指向本栈 rustfs（容器网络内可 PUT）；
  - API 配置经 adapter_class=MockDialogAdapter 走本地 mock 对话（无真实设备依赖）。
  - DUT mock（mock_dut_api，:5096）承担单轮被测协议 + voice_llm /chat。

冒烟覆盖：/health 隔离库门禁 → 表单登录（RSA 加密，dev 模式）→ 上传 dry 音频 →
建 voice_llm API 用例（turn_eval 主维度绑定）→ 建 api 任务 → 执行至 completed →
生成报告 → 报告可见 → 全量清理（零残留）。
API 载荷与当前基线 `scripts/smoke_gate.py` 四步门禁口径一致（snake_case 契约、
type='api'、adapter_class=MockDialogAdapter；INT-993 重交付修正原 INT-597 冒烟脚本
camelCase 载荷——原脚本写于 2026-10-17 但 live 冒烟从未跑通，载荷未随 DDD 契约演进）。
输出：逐步证据 JSON 落 /tmp/iso_smoke_evidence/（容器内，docker run --rm 随容器销毁）。

本脚本自包含（不 import shared 业务代码），可在任意带 httpx/cryptography 的 Python
解释器 + 可达栈网络内运行。
"""
import argparse
import base64
import hashlib
import json
import os
import sys
import time

import httpx

ISOLATED_TEST_DB_NAME = 'intelligent_audio_test_test'
POLL_INTERVAL = 3
API_TASK_TIMEOUT = 420
REPORT_TIMEOUT = 240
EVIDENCE_DIR = '/tmp/iso_smoke_evidence'
# trust_env=False 只在 Client 构造时传（Windows 代理劫持规避，INT-102）；方法调用只传 timeout
CK = dict(timeout=30)


def _resp_data(resp):
    """解包统一信封 {success, code, data}；非 2xx/失败信封抛错带原文。"""
    body = resp.json()
    if isinstance(body, dict) and ('success' in body or 'code' in body):
        ok = body.get('success') or body.get('code') in (0, 200, 201)
        assert ok, f'API 返回错误: {resp.status_code} {body}'
        return body.get('data') or {}
    assert resp.status_code < 400, f'HTTP {resp.status_code}: {body}'
    return body or {}


def _auth_headers(token):
    return {'Authorization': f'Bearer {token}'}


def _dump_evidence(step, payload):
    try:
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        with open(os.path.join(EVIDENCE_DIR, f'{step}.json'), 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1, default=str)
    except Exception:
        pass


def _login(client, base, username, password):
    """dev 模式表单登录：RSA 加密开启时走 password_encrypted 链路。"""
    r = client.get(f'{base}/auth/login/encryption-key')
    payload = _resp_data(r)
    if payload.get('enabled'):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        pub = serialization.load_pem_public_key(payload['public_key'].encode('utf-8'))
        encrypted = pub.encrypt(
            password.encode('utf-8'),
            padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                         algorithm=hashes.SHA256(), label=None))
        body = {'username': username,
                'password_encrypted': base64.b64encode(encrypted).decode('ascii'),
                'encryption_key_id': payload.get('kid')}
    else:
        body = {'username': username, 'password': password}
    r = client.post(f'{base}/auth/login', json=body)
    data = _resp_data(r)
    token = data.get('access_token') or data.get('token') or ''
    assert token, f'登录未返回 access_token: {data}'
    _dump_evidence('01_login', {'username': username, 'user': data.get('user')})
    return token


def _create_mock_api_config(client, base, headers, dut_url=None):
    """mock 适配器 API 配置（adapter_class=MockDialogAdapter，零外部依赖）。"""
    payload = {
        'name': f'INT993_smoke_api_{int(time.time())}',
        'vendor': 'mock',
        'description': 'INT-993 隔离栈冒烟 API 配置',
        'algorithm_type': 'voice_llm',
        'device_type': 'http_api',
        'adapter_class': 'MockDialogAdapter',
        # INT-1361 api_url 移除：endpoints 为唯一端点配置入口——DUT mock 容器
        # 网络地址作首端点（容器形态下缺省空串 → "/health" 无 scheme 必败）
        'endpoints': [{'endpoint': dut_url or 'http://mock_dut_api:5096',
                       'max_process': 5, 'max_timeout': 30,
                       'max_audio_duration': 60, 'priority': 0}],
        'status': 'online',
        'meta': {'purpose': 'int993-iso-smoke', 'mode': 'dialog'},
    }
    r = client.post(f'{base}/apis', json=payload, headers=headers, **CK)
    data = _resp_data(r)
    api_id = data.get('id')
    assert api_id, f'API 配置创建未返回 id: {data}'
    _dump_evidence('02_api_config', {'api_id': api_id})
    return api_id


def _resolve_turn_eval_dimension(client, base, headers):
    """解析逐轮话轮评估主维度 id（INT-597 实测：维度 id 随库种子环境变化，
    共享库为 2，隔离栈为 37——不可硬编码；按 task_type_code=turn_eval 解析）。"""
    r = client.get(f'{base}/evaluation/dimensions', headers=headers,
                   params={'page': 1, 'per_page': 200}, **CK)
    items = (_resp_data(r) or {}).get('items', [])
    for d in items:
        if d.get('task_type_code') == 'turn_eval' and d.get('dimension_type') == 'main':
            return d.get('id'), d.get('name')
    codes = sorted({d.get('task_type_code') for d in items})
    raise AssertionError(
        f'栈内未找到 turn_eval 主维度（可用 task_type_code: {codes}）——'
        f'检查 db_bootstrap 是否跑了 seed_turn_eval')


def _upload_audio_and_create_case(client, base, headers, audio_path, dim_id, dim_name):
    """上传 dry 样例 WAV（presign→OSS 直传→complete-direct）→ merge 归档 →
    建用例分组 → 显式建 voice_llm API 用例（镜像 smoke_gate S2 口径）。"""
    with open(audio_path, 'rb') as fh:
        content = fh.read()
    md5 = hashlib.md5(content).hexdigest()
    name = os.path.basename(audio_path)
    size = len(content)
    rel = f'sample/{name}'

    r = client.post(f'{base}/audios/upload/init', headers=headers, **CK)
    upload_task_id = (_resp_data(r).get('taskId') or _resp_data(r).get('task_id'))
    assert upload_task_id, 'upload/init 未返回 taskId'

    r = client.post(f'{base}/audios/upload/register', json={
        'taskId': upload_task_id,
        'files': [{'name': name, 'size': size, 'md5': md5, 'relativePath': rel}]},
        headers=headers, **CK)
    reg_files = _resp_data(r).get('files', [])
    file_id = (reg_files[0].get('fileId') or reg_files[0].get('file_id')) if reg_files else None
    assert file_id, 'register 未返回 fileId'

    r = client.post(f'{base}/audios/upload/presign', json={
        'filename': name, 'fileSize': size, 'md5': md5, 'chunkSize': 5 * 1024 * 1024,
        'isWav': True, 'relativePath': rel}, headers=headers, **CK)
    presign = _resp_data(r)
    audio_id = None
    if presign.get('instantUpload'):
        audio_id = presign.get('audioId') or presign.get('audio_id')
    else:
        upload_id = presign.get('uploadId') or presign.get('upload_id')
        oss_key = presign.get('ossKey') or presign.get('oss_key')
        parts = presign.get('parts', [])
        part_url = parts[0].get('url') or parts[0].get('URL') if parts else None
        if not part_url:
            r = client.post(f'{base}/audios/upload/presign-part', json={
                'uploadId': upload_id, 'partNumber': 1},
                params={'oss_key': oss_key, 'category': 'audios'}, headers=headers, **CK)
            part_url = _resp_data(r).get('url')
        put = client.put(part_url, content=content, **{**CK, 'timeout': 60})
        assert put.status_code == 200, f'OSS PUT 失败: {put.status_code} {put.text[:200]}'
        etag = put.headers.get('ETag', '').strip('"')
        r = client.post(f'{base}/audios/upload/complete-direct', json={
            'ossKey': oss_key, 'uploadId': upload_id,
            'parts': [{'PartNumber': 1, 'ETag': etag}],
            'filename': name, 'md5': md5, 'fileSize': size, 'audioType': 'dry'},
            headers=headers, **CK)
        audio_id = _resp_data(r).get('audioId') or _resp_data(r).get('audio_id')
    assert audio_id, 'complete-direct 未返回 audioId'

    # merge 归档（不自动建用例，用例下方显式创建以便绑定维度）
    r = client.post(f'{base}/audios/upload/merge', json={
        'fileId': file_id, 'taskId': upload_task_id, 'audioType': 'dry',
        'createTestCase': False, 'inheritTags': True,
        'dimensions': {}}, headers=headers, **CK)
    md = _resp_data(r)
    if md.get('status') != 'completed' and not md.get('audioId'):
        raise AssertionError(f'merge 未完成: {md}')

    # 用例分组（testcases 创建要求 group_id）
    r = client.post(f'{base}/groups', json={'name': f'INT993_SMOKE_{int(time.time())}'},
                    headers=headers, **CK)
    grp_id = _resp_data(r).get('id')
    assert grp_id, '分组创建失败'

    # voice_llm API 用例：1 轮 × (dry 音频 + turn_eval 主维度)
    rounds = [{
        'round_number': 1,
        'audios': [{'audio_id': audio_id, 'spl': 65, 'play_order': 1}],
        'evaluation': {'dimensions': [{'id': dim_id, 'name': dim_name}]},
    }]
    r = client.post(f'{base}/testcases', json={
        'name': f'INT993_smoke_case_{int(time.time())}',
        'description': 'INT-993 隔离栈冒烟用例',
        'algorithm_type': 'voice_llm',
        'group_id': grp_id,
        'config': {'rounds': rounds}}, headers=headers, **CK)
    tc = _resp_data(r)
    tc_id = tc.get('id') or tc.get('case_id')
    assert tc_id, f'用例创建未返回 id: {tc}'
    _dump_evidence('03_case_created', {'audio_id': audio_id, 'group_id': grp_id,
                                       'test_case_id': tc_id, 'audio_name': name})
    return audio_id, tc_id, grp_id


def _create_task_and_run(client, base, headers, tc_id, api_id):
    """建 api 任务 → 关联用例 → start → 轮询终态 → 断言 completed。"""
    r = client.post(f'{base}/tasks', json={
        'name': f'INT993_smoke_task_{int(time.time())}',
        'type': 'api',
        'description': 'INT-993 隔离栈冒烟',
        'case_ids': [tc_id],
        'api_ids': [api_id]}, headers=headers, **CK)
    task_id = _resp_data(r).get('id')
    assert task_id, f'任务创建未返回 id: {r.text[:400]}'

    r = client.patch(f'{base}/tasks/{task_id}/cases', json={
        'action': 'add', 'caseIds': [tc_id],
        'caseDevices': [{'caseId': tc_id, 'deviceType': 'http_api', 'deviceId': str(api_id)}]},
        headers=headers, **CK)
    _resp_data(r)

    r = client.post(f'{base}/tasks/{task_id}/start', headers=headers, **CK)
    _resp_data(r)

    timeline = []
    final = None
    deadline = time.time() + API_TASK_TIMEOUT
    while time.time() < deadline:
        r = client.get(f'{base}/tasks/{task_id}/progress', headers=headers, **CK)
        pd = _resp_data(r)
        entry = {'t': round(time.time()), 'status': pd.get('status'),
                 'execution_status': pd.get('execution_status'),
                 'evaluation_status': pd.get('evaluation_status')}
        if not timeline or entry != timeline[-1]:
            timeline.append(entry)
        final = pd.get('status')
        if final in ('completed', 'failed', 'cancelled', 'stopped', 'partial_completed'):
            break
        time.sleep(POLL_INTERVAL)
    _dump_evidence('05_task_run', {'task_id': task_id, 'final_status': final,
                                   'timeline': timeline})
    assert final in ('completed', 'partial_completed'), \
        f'API 任务未到完成终态: final={final}（420s 超时）'
    return task_id


def _generate_report_and_wait(client, base, headers, task_id):
    """生成任务报告并等待终态（尽力而为）。

    Returns (report_id, detail, note)：report_id 为 None 时 note 说明阻塞原因。
    报告依赖评估维度结果；隔离栈维度种子 api_url 已指向本栈 mock 评估服务
    （docker-compose.iso.yml mock_eval_server_judge:5097），正常情况下评估产出 →
    报告可生成。note 仅兜底说明失败方向。
    """
    note = None
    r = client.post(f'{base}/reports/generate-task',
                    json={'taskId': task_id, 'name': f'INT993_smoke_report_{int(time.time())}'},
                    headers=headers, **CK)
    gen = _resp_data(r)
    report_id = gen.get('reportId') or gen.get('report_id') or gen.get('id')
    deadline = time.time() + 60
    while not report_id and time.time() < deadline:
        r = client.get(f'{base}/reports/by_task/{task_id}', headers=headers, **CK)
        if r.status_code == 200:
            rd = _resp_data(r)
            if isinstance(rd, dict):
                report_id = rd.get('id') or rd.get('reportId') or rd.get('report_id')
        if not report_id:
            time.sleep(POLL_INTERVAL)
    if not report_id:
        note = ('报告未生成：任务已 completed 但无报告——检查隔离栈维度种子 api_url '
                '是否可达 mock 评估服务（mock_eval_server_judge:5097）。')
        return None, None, note

    detail = None
    deadline = time.time() + REPORT_TIMEOUT
    while time.time() < deadline:
        r = client.get(f'{base}/reports/{report_id}', headers=headers, **CK)
        detail = _resp_data(r)
        if detail.get('status') in ('completed', 'failed', 'published'):
            break
        time.sleep(POLL_INTERVAL)
    _dump_evidence('06_report_generated', {'report_id': report_id,
                                           'status': (detail or {}).get('status'),
                                           'summary_keys': sorted(
                                               (detail or {}).get('summary', {}).keys())})
    if (detail or {}).get('status') not in ('completed', 'published'):
        note = f'报告状态未达终态: {(detail or {}).get("status")}'
        return report_id, detail, note
    return report_id, detail, note


def _cleanup(client, base, headers, api_id, audio_id, tc_id, grp_id, task_id, report_id):
    for rid in (report_id,):
        if rid:
            try:
                client.delete(f'{base}/reports/{rid}', headers=headers, **CK)
            except Exception:
                pass
    if task_id:
        try:
            client.delete(f'{base}/tasks/{task_id}', headers=headers, **CK)
        except Exception:
            pass
    if tc_id:
        try:
            client.delete(f'{base}/testcases/{tc_id}', headers=headers, **CK)
        except Exception:
            pass
    if grp_id:
        try:
            client.delete(f'{base}/groups/{grp_id}', headers=headers, **CK)
        except Exception:
            pass
    if audio_id:
        try:
            client.delete(f'{base}/audios/{audio_id}', headers=headers, **CK)
        except Exception:
            pass
    if api_id:
        try:
            client.delete(f'{base}/apis/{api_id}', headers=headers, **CK)
        except Exception:
            pass
    _dump_evidence('07_cleanup', {'done': True, 'ids': {
        'report': report_id, 'task': task_id, 'case': tc_id,
        'group': grp_id, 'audio': audio_id, 'api': api_id}})


def main():
    ap = argparse.ArgumentParser(description='INT-597/993 隔离栈验收冒烟（登录→用例→任务→报告）')
    ap.add_argument('--api-base', default='http://api_gateway:5000/api/v1')
    ap.add_argument('--health-url', default='http://api_gateway:5000/health')
    ap.add_argument('--dut-url', default='http://mock_dut_api:5096')
    ap.add_argument('--audio-dir', default='/data')
    ap.add_argument('--username', default='dev_user')
    ap.add_argument('--password', default='dev_password')
    args = ap.parse_args()

    with httpx.Client(timeout=30, trust_env=False) as client:
        # 0) 健康 + 隔离库门禁
        r = client.get(args.health_url, **CK)
        body = r.json()
        assert r.status_code == 200 and body.get('version') == 'V9.7.31', \
            f'/health 非 V9.7.31 网关: {r.status_code} {body}'
        db = body.get('database')
        assert db == ISOLATED_TEST_DB_NAME, \
            f'隔离库门禁失败: database={db!r}（期望 {ISOLATED_TEST_DB_NAME}）'
        _dump_evidence('00_health', {'version': body.get('version'), 'database': db})

        # 1) 登录
        token = _login(client, args.api_base, args.username, args.password)
        headers = _auth_headers(token)

        # 2) API 配置 + 维度解析
        api_id = _create_mock_api_config(client, args.api_base, headers, args.dut_url)
        dim_id, dim_name = _resolve_turn_eval_dimension(client, args.api_base, headers)
        _dump_evidence('00_dimension', {'dim_id': dim_id, 'dim_name': dim_name})

        # 3) 音频上传 + 建用例
        audio_dir = args.audio_dir
        wavs = sorted(f for f in os.listdir(audio_dir) if f.lower().endswith('.wav'))
        assert wavs, f'样例目录无 wav: {audio_dir}'
        audio_path = os.path.join(audio_dir, wavs[0])
        audio_id, tc_id, grp_id = _upload_audio_and_create_case(
            client, args.api_base, headers, audio_path, dim_id, dim_name)

        try:
            # 4) 建任务 + 执行至 completed
            task_id = _create_task_and_run(client, args.api_base, headers, tc_id, api_id)
            # 5) 出报告（尽力而为；mock 评估不可达时明确留痕）
            report_id, detail, report_note = _generate_report_and_wait(
                client, args.api_base, headers, task_id)
            if report_id and not report_note:
                # 6) 报告列表可见
                r = client.get(f'{args.api_base}/reports/by_task/{task_id}', headers=headers, **CK)
                by_task = _resp_data(r) if r.status_code == 200 else {}
                _dump_evidence('07_report_visible',
                               {'by_task_keys': sorted(by_task.keys()) if isinstance(by_task, dict)
                                else str(by_task)[:200]})
            else:
                _dump_evidence('07_report_blocked',
                               {'task_id': task_id, 'reason': report_note,
                                'status': (detail or {}).get('status')})
                print(f'[SMOKE-REPORT] {report_note}', flush=True)
        finally:
            # 7) 清理（零残留）
            try:
                _cleanup(client, args.api_base, headers,
                         api_id, audio_id, tc_id, grp_id,
                         locals().get('task_id'), locals().get('report_id'))
            except Exception as exc:
                print(f'[SMOKE] 清理异常（不影响结论）: {exc}', flush=True)

    if report_id and not report_note:
        print(f'[SMOKE] PASS：登录→建用例→建任务→执行→出报告 全链跑通 '
              f'(隔离库 {ISOLATED_TEST_DB_NAME})', flush=True)
    else:
        print(f'[SMOKE] PASS：隔离链（登录→建用例→建任务→执行完成）跑通，'
              f'报告未生成原因见证据 07_report_blocked', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
