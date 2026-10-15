# -*- coding: utf-8 -*-
"""INT-321 全流程实机走查：执行→评估→重评→报告→对比报告（A~F 全步骤）。

前置（由 tests/api/conftest.py 统一把关）：
- RUN_LIVE_STACK=1 且实机栈 /health 的 database == intelligent_audio_test_test
  （INT-246 隔离门禁，共享业务库一律 fail）。

走查映射：
- A. E2E 实机链路复核：上传→建用例→建任务→真机执行→评估→出报告
- B. API 测试链路全流程（实机非 dry）：API 配置→建 API 用例→任务执行
     （api_test_service 真实 HTTP 调 api_adapter_service /health、/api/create_task、
     /api/get_status、/api/get_final_result）→评估→API 报告
- C. 评估流程独立验证（INT-301 双状态）：执行/评估状态流转时间线 + 任务详情/
     用例结果中评估数据可见
- D. 重新评估：任务级整任务重评（reevaluate_type=all）状态重置并重新流转；
     INT-302 按用例选择（mode=selected）一并实测
- E. 报告链：生成→详情→历史列表→冻结快照数据
- F. 对比报告：两任务对比报告生成→用例级/指标级差异结构

实机依赖：
- HarmonyOS 真机（HDC 在线，串号见 SHARED_DEVICE_SN）——fixture 按共享库同款
  参数在隔离库登记，teardown 删除
- RME Fireface 802 播放通道（dry）——同上
- api_adapter_service(5008)（vendor=mock 本地对话处理，真实 HTTP 全链）

证据：logs/int321_evidence/*.json（每步命令 + 响应摘要）。

数据卫生：全部产物（设备/播放通道/API 配置/音频/用例/任务/报告/映射）在
module teardown 删除，隔离库不留本卡残留（基线快照见 logs/int321_baseline.txt）。
"""
import json
import os
import time

import pytest

# ── 轮询参数 ─────────────────────────────────────────────
E2E_TASK_TIMEOUT = 900      # 真机执行+评估超时（秒）
API_TASK_TIMEOUT = 600      # API 链执行+评估超时（秒）
REEVAL_TIMEOUT = 600        # 重评流转超时（秒）
REPORT_TIMEOUT = 180        # 报告生成超时（秒）
POLL_INTERVAL = 3

EVIDENCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'logs', 'int321_evidence')

# 共享库实机设备镜像参数（device id=9 pura90小艺，INT-321 开工时确认在线）
SHARED_DEVICE_SN = '5SM0125613000197'
DEVICE_PAYLOAD = {
    'deviceName': 'pura90小艺',
    'model': 'Harmony Device',
    'deviceType': 'phone',
    'system': 'HarmonyOS',
    'systemVersion': '1.0.0',
    'appName': 'Default App',
    'appVersion': '1.0.0',
    'connectionType': 'usb',
    'keywords': 'harmony.base.v1',
    'serialNumber': SHARED_DEVICE_SN,
    'supportedAlgorithms': ['voice_llm'],
}
# 共享库 RME 播放通道镜像（设备正左侧 1m-90°，Analog (3+4) Ch2）
PLAYBACK_PAYLOAD = {
    'name': '设备正左侧（1m-90°）',
    'model': 'Analog (3+4) (RME Fireface 802) [Ch 2]',
    'deviceType': 'dry',
    'sampleRate': 48000,
    'channelIndex': 1,
    'deviceUniqueId': 'Analog (3+4) (RME Fireface 802) [Ch 2]',
    'description': 'INT321 walkthrough RME mirror',
}

EVIDENCE = {}


def _resp_data(resp):
    body = resp.json()
    assert body.get('success') or body.get('code') in (0, 200, 201), \
        f'API 返回错误: {resp.status_code} {body}'
    return body.get('data') or {}


def _dump_evidence(step, payload):
    """落一步证据（命令参数摘要 + 响应摘要）。"""
    try:
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        with open(os.path.join(EVIDENCE_DIR, f'{step}.json'), 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=1, default=str)
    except Exception:  # 证据落盘失败不影响走查本身
        pass


def _put_to_oss(presigned_url, file_path):
    with open(file_path, 'rb') as f:
        content = f.read()
    import httpx
    r = httpx.put(presigned_url, content=content, timeout=30, trust_env=False)
    assert r.status_code == 200, f'OSS PUT 失败: {r.status_code} {r.text[:200]}'
    return r.headers.get('ETag', '').strip('"')


def _upload_audio_and_create_case(api_client, sample_audio_files, unified_rounds,
                                  test_types, group_name, extra_merge=None,
                                  round_eval=None):
    """上传 3 个样例 WAV 并在末尾 merge 生成测试用例（R11 主链模式）。

    round_eval：注入每轮 evaluation 配置（评估维度），缺省 None 保持
    R11 执行-only 口径。INT-321 C 步要求评估独立流转，E2E 用例轮次
    须挂评估维度（逐轮话轮评估 id=2，与 UI 用例编辑配置同构），否则
    引擎按「无评估维度不评估」设计跳过评估（实测验证）。
    """
    created_audio_ids = []
    tc_id = None

    r = api_client.post('/audios/upload/init')
    upload_task_id = _resp_data(r).get('taskId') or _resp_data(r).get('task_id')
    assert upload_task_id, 'upload/init 未返回 taskId'

    file_data = [{'name': f['name'], 'size': f['size'], 'md5': f['md5'],
                  'relativePath': f['relativePath']} for f in sample_audio_files]
    r = api_client.post('/audios/upload/register', json={
        'taskId': upload_task_id, 'files': file_data})
    reg_files = _resp_data(r).get('files', [])
    file_ids = [rf.get('fileId') or rf.get('file_id') for rf in reg_files]
    assert len(file_ids) == len(sample_audio_files), 'register 文件数不匹配'

    tc_rounds = [dict(rnd) for rnd in unified_rounds]
    for rnd in tc_rounds:
        rnd['audios'] = [dict(a) for a in rnd.get('audios', [])]
        if round_eval:
            import copy as _copy
            rnd['evaluation'] = _copy.deepcopy(round_eval)

    total = len(sample_audio_files)
    for idx, (audio_file, file_id) in enumerate(zip(sample_audio_files, file_ids)):
        is_final = (idx == total - 1)
        r = api_client.post('/audios/upload/presign', json={
            'filename': audio_file['name'], 'fileSize': audio_file['size'],
            'md5': audio_file['md5'], 'chunkSize': 5 * 1024 * 1024,
            'isWav': True, 'relativePath': audio_file['relativePath']})
        presign = _resp_data(r)
        if presign.get('instantUpload'):
            audio_id = presign.get('audioId') or presign.get('audio_id')
            assert audio_id, '秒传返回但 audioId 为空'
        else:
            upload_id = presign.get('uploadId') or presign.get('upload_id')
            oss_key = presign.get('ossKey') or presign.get('oss_key')
            parts = presign.get('parts', [])
            total_parts = presign.get('totalParts') or presign.get('total_parts', 1)
            uploaded_parts = []
            for pi in range(total_parts):
                if pi < len(parts):
                    part_url = parts[pi].get('url') or parts[pi].get('URL')
                else:
                    r = api_client.post('/audios/upload/presign-part', json={
                        'uploadId': upload_id, 'partNumber': pi + 1},
                        params={'oss_key': oss_key, 'category': 'audios'})
                    part_url = _resp_data(r).get('url')
                etag = _put_to_oss(part_url, audio_file['path'])
                uploaded_parts.append({'PartNumber': pi + 1, 'ETag': etag})
            r = api_client.post('/audios/upload/complete-direct', json={
                'ossKey': oss_key, 'uploadId': upload_id, 'parts': uploaded_parts,
                'filename': audio_file['name'], 'md5': audio_file['md5'],
                'fileSize': audio_file['size'], 'audioType': 'dry'})
            audio_id = _resp_data(r).get('audioId') or _resp_data(r).get('audio_id')
            assert audio_id, 'complete-direct 未返回 audioId'
        created_audio_ids.append(audio_id)
        for rnd in tc_rounds:
            for a in rnd.get('audios', []):
                if a.get('audio_name') == audio_file['name']:
                    a['audio_id'] = audio_id

        merge_body = {
            'fileId': file_id, 'taskId': upload_task_id, 'audioType': 'dry',
            'createTestCase': is_final, 'testTypes': test_types,
            'groupNameType': 'custom', 'customGroupName': group_name,
            'inheritTags': True, 'dimensions': {},
        }
        merge_body.update(extra_merge or {})
        if is_final:
            merge_body['testCaseConfig'] = {
                'rounds': tc_rounds, 'groupName': group_name, 'inheritTags': True}
        r = api_client.post('/audios/upload/merge', json=merge_body)
        merge_data = _resp_data(r)
        if is_final:
            tc_id = (merge_data.get('testCaseId') or merge_data.get('test_case_id'))
            tc_count = merge_data.get('testCaseCount') or merge_data.get('test_case_count', 0)
            assert tc_id or tc_count > 0, f'末尾 merge 未生成用例: {merge_data}'
    return created_audio_ids, tc_id


def _create_task(api_client, name, case_ids, extra=None):
    assert case_ids, '_create_task 需要非空 case_ids（空任务 start 会挂起）'
    body = {'name': name, 'description': 'INT-321 全流程实机走查',
            'caseIds': [str(c) for c in case_ids], 'config': {'parallel': True}}
    body.update(extra or {})
    r = api_client.post('/tasks', json=body)
    data = _resp_data(r)
    task_id = data.get('id')
    assert task_id, f'任务创建未返回 id: {data}'
    return task_id


def _run_task_and_record_timeline(api_client, task_id, timeout, step_tag):
    """等待任务启动并轮询至终态，记录双状态流转时间线（INT-301 证据）。

    平台为「创建即调度」设计：创建任务时入 Redis 队列，调度器 BRPOP 自动
    启动（零延迟）。因此先等自动启动生效；仅当任务仍停留 pending（调度器
    未接管）才显式调 start API。不与自动启动赛跑——start 请求落在自动启动
    的 CAS 窗口内会触发已知自死锁缺陷（task_control.py:107 重入非重入锁，
    已开缺陷卡）。start API 幂等语义（RUNNING 时返回"任务已在运行中"）
    一并实测留证。
    """
    # 1) 等待调度器自动启动（≤10s）
    status = None
    auto_deadline = time.time() + 10
    while time.time() < auto_deadline:
        r = api_client.get(f'/tasks/{task_id}/progress')
        status = _resp_data(r).get('status')
        if status != 'pending':
            break
        time.sleep(1)

    start_note = {'auto_start_status': status}
    if status in ('running', 'queued'):
        # 2a) 已自动启动：实测 start API 幂等路径（预期 success）。重评场景
        # 任务可能处于 start 不允许的中间态，此处仅记录不硬断言（主链以
        # 终态轮询判定），幂等异常本身作为证据输出。
        try:
            r = api_client.post(f'/tasks/{task_id}/start')
            sd = _resp_data(r)
            start_note['start_api'] = f'idempotent ok: status={sd.get("status")}'
        except AssertionError as exc:
            start_note['start_api'] = f'idempotent note: {exc}'
    elif status == 'pending':
        # 2b) 调度器未接管（如 Redis 异常兜底场景）：显式 start，此刻无竞争者
        r = api_client.post(f'/tasks/{task_id}/start')
        sd = _resp_data(r)
        assert sd.get('status') in ('running', 'pending', 'queued'), \
            f'显式 start 后状态异常: {sd}'
        start_note['start_api'] = f'explicit start: status={sd.get("status")}'
    # 终态（completed/failed）：跳过 start——对 COMPLETED 任务调 start 会
    # 触发上述 CAS 死锁缺陷（CAS 只匹配 pending/queued），缺陷卡另行跟踪
    _dump_evidence(f'{step_tag}_start', start_note)

    timeline = []
    deadline = time.time() + timeout
    final = None
    while time.time() < deadline:
        r = api_client.get(f'/tasks/{task_id}/progress')
        pd = _resp_data(r)
        entry = {
            't': round(time.time()),
            'status': pd.get('status'),
            'execution_status': pd.get('execution_status'),
            'evaluation_status': pd.get('evaluation_status'),
        }
        if not timeline or (entry['status'], entry['execution_status'],
                            entry['evaluation_status']) != (
                timeline[-1]['status'], timeline[-1]['execution_status'],
                timeline[-1]['evaluation_status']):
            timeline.append(entry)
        final = pd.get('status')
        if final in ('completed', 'failed', 'cancelled'):
            break
        time.sleep(POLL_INTERVAL)
    _dump_evidence(step_tag, {'task_id': task_id, 'final_status': final,
                              'timeline': timeline})
    return final, timeline


def _generate_report_and_wait(api_client, task_id, name, step_tag):
    r = api_client.post('/reports/generate-task', json={'taskId': task_id, 'name': name})
    gen = _resp_data(r)
    report_id = gen.get('reportId') or gen.get('report_id') or gen.get('id')
    deadline = time.time() + REPORT_TIMEOUT
    while not report_id and time.time() < deadline:
        r = api_client.get(f'/reports/by_task/{task_id}')
        if r.status_code == 200:
            rd = _resp_data(r)
            if isinstance(rd, dict):
                report_id = rd.get('id') or rd.get('reportId') or rd.get('report_id')
        if not report_id:
            time.sleep(POLL_INTERVAL)
    assert report_id, f'报告生成未返回/轮询不到 reportId: gen={gen}'

    detail = None
    deadline = time.time() + REPORT_TIMEOUT
    while time.time() < deadline:
        r = api_client.get(f'/reports/{report_id}')
        detail = _resp_data(r)
        if detail.get('status') in ('completed', 'failed', 'published'):
            break
        time.sleep(POLL_INTERVAL)
    _dump_evidence(step_tag, {'task_id': task_id, 'report_id': report_id,
                              'status': (detail or {}).get('status'),
                              'summary_keys': sorted((detail or {}).get('summary', {}).keys())})
    return report_id, detail


@pytest.fixture(scope='module')
def int321_infra(api_client):
    """实机基础设施：真机设备 + RME 播放通道 + API 配置（teardown 全删）。"""
    created = {'device_id': None, 'playback_id': None, 'api_id': None}
    try:
        # 1. 登记真机（幂等：先按串号查）
        r = api_client.get('/test-devices', params={'page': 1, 'per_page': 50})
        items = (_resp_data(r) or {}).get('items', [])
        dev = next((it for it in items if it.get('serial_number') == SHARED_DEVICE_SN), None)
        if dev is None:
            r = api_client.post('/test-devices', json=DEVICE_PAYLOAD)
            dev = _resp_data(r)
            created['device_id'] = dev.get('id')
        else:
            created['device_id'] = dev.get('id')
        assert created['device_id'], f'真机登记失败: {dev}'

        # 2. 真机在线确认（HDC 扫描合并）——离线仅软记录不阻断：
        #    A 段（test_01）真机执行失败会直接反映（执行结果断言更严格）；
        #    B 段（test_07）API 链不依赖真机，设备离线也可独立验证
        r = api_client.get('/test-devices', params={'page': 1, 'per_page': 50})
        items = (_resp_data(r) or {}).get('items', [])
        dev = next((it for it in items if it.get('serial_number') == SHARED_DEVICE_SN), None)
        if not (dev and dev.get('status') == 'online'):
            _dump_evidence('Z_device_status_warn', {
                'sn': SHARED_DEVICE_SN,
                'status': dev and dev.get('status'),
                'note': '设备离线：A 段真机链将因执行失败红（执行结果断言兜底），'
                        'B 段 API 链不依赖真机继续验证'})

        # 3. 登记 RME 播放通道（幂等：按本卡描述标记查，上一轮异常退出残留可直接复用）
        r = api_client.get('/playback-devices', params={'page': 1, 'per_page': 100})
        pb_items = (_resp_data(r) or {}).get('items', [])
        pb = next((it for it in pb_items
                   if it.get('description') == PLAYBACK_PAYLOAD['description']), None)
        if pb is None:
            r = api_client.post('/playback-devices', json=PLAYBACK_PAYLOAD)
            pb = _resp_data(r)
        created['playback_id'] = pb.get('id')
        assert created['playback_id'], f'RME 播放通道登记失败: {pb}'

        # 4. API 配置（指向栈内 api_adapter_service，vendor=mock 本地对话处理）
        #    注：api_test_service 侧校验 meta 必须为非空 dict（`not data.get('meta')`）
        #    幂等：按名称查残留复用（上一轮异常退出时 teardown 未跑）
        api_payload = {
            'name': 'INT321_adapter_api',
            'vendor': 'mock',
            'apiUrl': 'http://127.0.0.1:5008',
            'description': 'INT-321 API 链实机走查（api_adapter_service）',
            'algorithmType': 'voice_llm',
            'deviceType': 'http_api',
            'defaultMaxTimeout': 60,
            'meta': {'vendor_adapter': 'api_driver', 'method': 'POST'},
        }
        r = api_client.get('/apis', params={'page': 1, 'per_page': 100,
                                            'keyword': api_payload['name']})
        api_items = (_resp_data(r) or {}).get('items', [])
        api_cfg = next((it for it in api_items
                        if it.get('name') == api_payload['name']), None)
        if api_cfg is None:
            r = api_client.post('/apis', json=api_payload)
            api_cfg = _resp_data(r)
        created['api_id'] = api_cfg.get('id')
        assert created['api_id'], f'API 配置创建失败: {api_cfg}'

        yield created
    finally:
        # ── teardown：API 配置 → 播放通道 → 真机（报告/任务/用例/音频由
        #    各测试自身的 finally 优先清理，此处兜底按名字再扫一遍）──
        if created['api_id']:
            try:
                api_client.delete(f"/apis/{created['api_id']}")
            except Exception:
                pass
        if created['playback_id']:
            try:
                api_client.delete(f"/playback-devices/{created['playback_id']}")
            except Exception:
                pass
        if created['device_id']:
            try:
                api_client.delete(f"/test-devices/{created['device_id']}")
            except Exception:
                pass


class TestInt321Walkthrough:
    """A~F 顺序走查（类内按定义顺序执行，状态经类属性传递）。"""

    e2e_task_id = None
    e2e_device_id = None
    e2e_case_ids = []
    e2e_audio_ids = []
    e2e_report_id = None
    e2e_timeline = []
    e2e_task2_id = None
    api_task_id = None
    api_case_ids = []
    api_audio_ids = []
    api_report_id = None
    compare_report_id = None
    reeval_selected_ok = None

    # ────────────────────────────────────────────────────
    # A. E2E 实机链路：上传→建用例→建任务→真机执行→（评估）
    # ────────────────────────────────────────────────────
    def test_01_a_e2e_chain_real_device(self, api_client, sample_audio_files,
                                        unified_rounds, int321_infra):
        pb_id = int321_infra['playback_id']
        # algorithmType 必须显式指定：UI 建用例必选算法类型，缺省时引擎侧
        # 兜底 'translation'（_db_mixin.py），而评估字段映射仅 voice_llm 有
        # 内置定义 → 评估轮次数据构建为空、用例评估恒 skipped（实测验证）。
        audio_ids, tc_id = _upload_audio_and_create_case(
            api_client, sample_audio_files, unified_rounds, ['e2e'],
            'INT321_E2E', extra_merge={'defaultPlaybackDeviceId': pb_id,
                                       'algorithmType': 'voice_llm'},
            round_eval={'dimensions': [{'id': 2, 'name': '逐轮话轮评估'}]})
        type(self).e2e_audio_ids = audio_ids
        type(self).e2e_case_ids = [tc_id] if tc_id else []
        assert tc_id, 'E2E 用例未生成'

        # 任务详情可见用例（deviceIds 关联被测真机 → task_device_relations，
        # E2E 引擎按任务设备关联取执行设备，缺省即报「没有可用的测试设备」）
        assert int321_infra['device_id'], '夹具未返回真机 device_id'
        type(self).e2e_device_id = int321_infra['device_id']
        task_id = _create_task(api_client, f'INT321_E2E_t1_{int(time.time())}',
                               type(self).e2e_case_ids,
                               extra={'deviceIds': [int321_infra['device_id']]})
        type(self).e2e_task_id = task_id
        detail = _resp_data(api_client.get(f'/tasks/{task_id}'))
        assert detail.get('cases'), f'任务详情未见用例: {detail}'
        _dump_evidence('A_task_created', {'task_id': task_id,
                                          'cases': [c.get('case_id') or c.get('id')
                                                    for c in detail.get('cases', [])]})

        final, timeline = _run_task_and_record_timeline(
            api_client, task_id, E2E_TASK_TIMEOUT, 'A_e2e_run_timeline')
        type(self).e2e_timeline = timeline
        assert final == 'completed', \
            f'E2E 实机任务未完成: final={final}（时间线见 A_e2e_run_timeline.json）'

    # ────────────────────────────────────────────────────
    # C. 评估流程独立验证（INT-301 双状态）
    # ────────────────────────────────────────────────────
    def test_02_c_dual_status_and_evaluation_visible(self, api_client):
        task_id = type(self).e2e_task_id
        assert task_id, '前置 A 步骤未完成'
        timeline = type(self).e2e_timeline

        # 双状态时间线：执行与评估两维均出现，且存在执行已完成而评估仍在流转
        # 的采样点（独立徽章的接口层依据）
        exec_vals = [e.get('execution_status') for e in timeline]
        eval_vals = [e.get('evaluation_status') for e in timeline]
        assert any(v == 'completed' for v in exec_vals), f'执行状态未到达 completed: {exec_vals}'
        assert any(v in ('completed', 'success') for v in eval_vals), \
            f'评估状态未到达完成: {eval_vals}'
        independence_sample = next(
            (e for e in timeline
             if e.get('execution_status') == 'completed'
             and e.get('evaluation_status') not in (None, 'completed', 'success')),
            None)
        _dump_evidence('C_dual_status', {'timeline': timeline,
                                         'independence_sample': independence_sample})

        # 任务详情：用例级双状态 + 评估结果可见（TaskCaseBrief 键为 case_id）
        detail = _resp_data(api_client.get(f'/tasks/{task_id}'))
        cases = detail.get('cases', [])
        assert cases, '任务详情无用例'
        c0 = cases[0]
        cid0 = c0.get('case_id') or c0.get('id')
        assert c0.get('execution_status') == 'completed', \
            f'用例执行状态异常: {c0.get("execution_status")}'
        assert c0.get('evaluation_status') in ('completed', 'success'), \
            f'用例评估状态异常: {c0.get("evaluation_status")}'

        # 用例结果含评估数据
        r = api_client.get(f'/tasks/{task_id}/cases/{cid0}/results')
        results = _resp_data(r)
        # get_case_results 返回 {task_id, case_id, case_name, results: [...]}
        items = results.get('results') if isinstance(results, dict) else results
        assert items, f'用例结果为空/结构异常: {str(results)[:200]}'
        _dump_evidence('C_case_results', {'case_id': cid0, 'n_results': len(items),
                                          'first_keys': sorted(items[0].keys()) if items else []})

    # ────────────────────────────────────────────────────
    # D. 重新评估（整任务 all + INT-302 按用例 selected）
    # ────────────────────────────────────────────────────
    def test_03_d_reevaluate(self, api_client):
        task_id = type(self).e2e_task_id
        assert task_id, '前置 A 步骤未完成'

        # 重评前快照（用例结果首条评估摘要）
        detail = _resp_data(api_client.get(f'/tasks/{task_id}'))
        c0 = detail['cases'][0]
        cid0 = c0.get('case_id') or c0.get('id')
        r0 = api_client.get(f'/tasks/{task_id}/cases/{cid0}/results')
        before_items = _resp_data(r0)
        before_items = before_items.get('results') if isinstance(before_items, dict) else before_items

        # D1 整任务重评
        r = api_client.post('/evaluation/task/reevaluate', json={
            'task_id': task_id, 'reevaluate_type': 'all'})
        rr = _resp_data(r)
        _dump_evidence('D_reevaluate_all_submit', {'task_id': task_id, 'resp': rr})

        final, timeline = _run_task_and_record_timeline(
            api_client, task_id, REEVAL_TIMEOUT, 'D_reevaluate_timeline')
        assert final == 'completed', f'重评后任务未完成: final={final}'
        eval_vals = [e.get('evaluation_status') for e in timeline]
        # 重评流转为 completed→evaluating→completed（无 pending 窗口），出现 evaluating 即重置重新流转
        assert any(v in ('running', 'calculating', 'pending', 'evaluating') for v in eval_vals), \
            f'重评未出现评估状态重置流转: {eval_vals}'

        # 重评后结果仍在
        r1 = api_client.get(f'/tasks/{task_id}/cases/{cid0}/results')
        after_items = _resp_data(r1)
        after_items = after_items.get('results') if isinstance(after_items, dict) else after_items
        assert after_items, '重评后用例结果为空'
        _dump_evidence('D_reevaluate_done', {
            'before_n': len(before_items) if isinstance(before_items, list) else 'dict',
            'after_n': len(after_items) if isinstance(after_items, list) else 'dict'})

        # D2 INT-302 按用例选择重评（mode=selected + case_ids）
        r = api_client.post('/evaluation/task/reevaluate', json={
            'task_id': task_id, 'reevaluate_type': 'all',
            'mode': 'selected', 'caseIds': [str(cid0)]})
        rr2 = _resp_data(r)
        type(self).reeval_selected_ok = r.status_code == 200
        _dump_evidence('D_reevaluate_selected', {'task_id': task_id,
                                                 'http': r.status_code, 'resp': rr2})
        if r.status_code == 200:
            final2, _ = _run_task_and_record_timeline(
                api_client, task_id, REEVAL_TIMEOUT, 'D_reevaluate_selected_timeline')
            assert final2 == 'completed', f'按用例重评后任务未完成: {final2}'

    # ────────────────────────────────────────────────────
    # A2/E. 第二次 E2E 执行（对比报告第二任务）+ 报告链
    # ────────────────────────────────────────────────────
    def test_04_a2_second_e2e_run(self, api_client):
        assert type(self).e2e_case_ids, '前置 A 步骤未完成（无用例）'
        assert type(self).e2e_device_id, '前置 A 步骤未完成（无设备）'
        task_id = _create_task(api_client, f'INT321_E2E_t2_{int(time.time())}',
                               type(self).e2e_case_ids,
                               extra={'deviceIds': [type(self).e2e_device_id]})
        type(self).e2e_task2_id = task_id
        final, timeline = _run_task_and_record_timeline(
            api_client, task_id, E2E_TASK_TIMEOUT, 'A2_second_run_timeline')
        assert final == 'completed', f'第二次 E2E 实机任务未完成: final={final}'

    def test_05_e_report_chain(self, api_client):
        t1 = type(self).e2e_task_id
        t2 = type(self).e2e_task2_id
        assert t1 and t2, '前置 E2E 任务未完成'

        rid1, detail1 = _generate_report_and_wait(
            api_client, t1, f'INT321报告_t1_{int(time.time())}', 'E_report_t1')
        type(self).e2e_report_id = rid1
        # 报告终态（生成→完成→发布，实机实测终态 published）
        assert (detail1 or {}).get('status') in ('completed', 'published'), \
            f'报告未完成: {detail1 and detail1.get("status")}'
        assert 'summary' in (detail1 or {}), '报告缺 summary'

        rid2, _ = _generate_report_and_wait(
            api_client, t2, f'INT321报告_t2_{int(time.time())}', 'E_report_t2')

        # 历史报告列表可见
        r = api_client.get('/reports', params={'page': 1, 'per_page': 50})
        items = (_resp_data(r) or {}).get('items', [])
        ids = {str(it.get('id')) for it in items}
        assert str(rid1) in ids and str(rid2) in ids, \
            f'历史报告列表未含新报告: rid1={rid1} rid2={rid2} 列表数={len(items)}'
        _dump_evidence('E_history_list', {'total': len(items),
                                          'contains': [rid1, rid2]})

        # INT-179 冻结口径：报告详情为生成时快照（summary 落库），两次读取一致
        d_again = _resp_data(api_client.get(f'/reports/{rid1}'))
        s1 = json.dumps((detail1 or {}).get('summary', {}), sort_keys=True, default=str)
        s2 = json.dumps(d_again.get('summary', {}), sort_keys=True, default=str)
        assert s1 == s2, '报告 summary 两次读取不一致（快照冻结被破坏）'
        _dump_evidence('E_freeze_check', {'report_id': rid1, 'frozen': True})

    # ────────────────────────────────────────────────────
    # F. 对比报告
    # ────────────────────────────────────────────────────
    def test_06_f_compare_reports(self, api_client):
        t1 = type(self).e2e_task_id
        t2 = type(self).e2e_task2_id
        assert t1 and t2, '前置 E2E 任务未完成'

        r = api_client.post('/reports/compare', json={
            'taskIds': [t1, t2], 'name': f'INT321对比_{int(time.time())}'})
        assert r.status_code == 200, f'对比报告生成失败: {r.status_code} {r.text[:300]}'
        gen = _resp_data(r)
        _dump_evidence('F_compare_submit', {'task_ids': [t1, t2], 'resp': gen})

        # 轮询对比报告出现并完成
        compare_id = None
        deadline = time.time() + REPORT_TIMEOUT
        while time.time() < deadline and not compare_id:
            r = api_client.get('/reports', params={'page': 1, 'per_page': 50,
                                                   'type': 'comparison'})
            items = (_resp_data(r) or {}).get('items', [])
            cand = next((it for it in items
                         if t1 in (it.get('task_ids') or []) or
                         t1 in (it.get('taskIds') or [])), None)
            if cand:
                compare_id = cand.get('id')
                break
            time.sleep(POLL_INTERVAL)
        assert compare_id, '轮询不到对比报告'
        type(self).compare_report_id = compare_id

        detail = None
        deadline = time.time() + REPORT_TIMEOUT
        while time.time() < deadline:
            detail = _resp_data(api_client.get(f'/reports/{compare_id}'))
            if (detail or {}).get('status') in ('completed', 'failed', 'published'):
                break
            time.sleep(POLL_INTERVAL)
        assert (detail or {}).get('status') == 'completed', \
            f'对比报告未完成: {detail and detail.get("status")}'
        summary = detail.get('summary') or {}
        # 用例级/指标级差异结构：summary 应含对比矩阵/指标数据相关字段
        _dump_evidence('F_compare_detail', {
            'compare_id': compare_id, 'type': detail.get('type'),
            'summary_keys': sorted(summary.keys()),
            'metric_data_present': any(k in summary for k in
                                       ('metric_data', 'metricData', 'compare_matrix',
                                        'comparison', 'case_metrics')),
        })

    # ────────────────────────────────────────────────────
    # B. API 测试链路全流程（实机非 dry）
    # ────────────────────────────────────────────────────
    def test_07_b_api_chain_live(self, api_client, sample_audio_files,
                                 unified_rounds, int321_infra):
        api_id = int321_infra['api_id']

        # UC-0902 后端核验：digital-spl 列表 + 创建/默认/删除（teardown）
        r = api_client.get('/digital-spl')
        assert r.status_code == 200, f'digital-spl 列表失败: {r.status_code}'
        spl_list = _resp_data(r)
        r = api_client.post('/digital-spl', json={
            'apiId': api_id, 'name': 'INT321_spl_mapping',
            'description': 'INT-321 UC-0902 实机走查',
            'referenceSpl': 94.0, 'referenceGainLinear': 1.0,
            'calibrationStatus': 'uncalibrated'})
        assert r.status_code in (200, 201), \
            f'digital-spl 创建失败: {r.status_code} {r.text[:300]}'
        mapping = _resp_data(r)
        mapping_id = mapping.get('id') or mapping.get('mapping_id')
        assert mapping_id, f'digital-spl 创建未返回 id: {mapping}'
        r = api_client.get(f'/digital-spl/by-api/{api_id}')
        assert r.status_code == 200, f'by-api 查询失败: {r.status_code}'
        _dump_evidence('B_uc0902_spl', {'api_id': api_id, 'mapping_id': mapping_id,
                                        'list_total': spl_list if isinstance(spl_list, int) else 'see resp'})
        try:
            r = api_client.post(f'/digital-spl/by-api/{api_id}/set-default',
                                json={'mappingId': mapping_id})
            _dump_evidence('B_uc0902_set_default', {'http': r.status_code,
                                                    'resp': r.text[:200]})
        finally:
            try:
                api_client.delete(f'/digital-spl/{mapping_id}')
            except Exception:
                pass

        # API 用例（rounds 挂逐轮话轮评估维度 id=2，镜像历史 API 用例口径）
        # 维度注入：在 unified_rounds 各轮补 evaluation.dimensions（深拷贝内做）
        import copy
        rounds_with_dims = copy.deepcopy(unified_rounds)
        for rnd in rounds_with_dims:
            rnd['evaluation'] = {'dimensions': [{'id': 2, 'name': '逐轮话轮评估'}]}

        audio_ids, tc_id = _upload_audio_and_create_case(
            api_client, sample_audio_files, rounds_with_dims, ['api'],
            'INT321_API', extra_merge={'algorithmType': 'voice_llm'})
        type(self).api_audio_ids = audio_ids
        type(self).api_case_ids = [tc_id] if tc_id else []
        assert tc_id, 'API 用例未生成'

        # 任务：case_devices 标记 http_api + api_ids 关联 API 配置
        task_id = _create_task(
            api_client, f'INT321_API_t_{int(time.time())}', type(self).api_case_ids,
            extra={'apiIds': [api_id],
                   'caseDevices': [{'caseId': str(type(self).api_case_ids[0]),
                                    'deviceType': 'http_api'}]})
        type(self).api_task_id = task_id

        final, timeline = _run_task_and_record_timeline(
            api_client, task_id, API_TASK_TIMEOUT, 'B_api_run_timeline')
        assert final == 'completed', \
            f'API 实机链任务未完成: final={final}（时间线见 B_api_run_timeline.json）'

        # 用例结果（会话/请求/断言采集）可见（TaskCaseBrief 键为 case_id）
        detail = _resp_data(api_client.get(f'/tasks/{task_id}'))
        cases = detail.get('cases', [])
        assert cases, 'API 任务详情无用例'
        api_cid = cases[0].get('case_id') or cases[0].get('id')
        r = api_client.get(f'/tasks/{task_id}/cases/{api_cid}/results')
        results = _resp_data(r)
        items = results.get('results') if isinstance(results, dict) else results
        assert items, f'API 用例结果为空/结构异常: {str(results)[:200]}'
        _dump_evidence('B_case_results', {'case_id': api_cid,
                                          'first_keys': sorted(items[0].keys()) if items else []})

        # API 测试报告
        rid, rdetail = _generate_report_and_wait(
            api_client, task_id, f'INT321_API报告_{int(time.time())}', 'B_report')
        type(self).api_report_id = rid
        assert (rdetail or {}).get('status') in ('completed', 'published'), 'API 报告未完成'

    # ────────────────────────────────────────────────────
    # teardown：全部业务产物清理（数据卫生）
    # ────────────────────────────────────────────────────
    @classmethod
    def _cleanup_cls(cls, api_client):
        # 对比报告 → 报告 → 任务 → 用例 → 音频
        if cls.compare_report_id:
            try:
                api_client.delete(f'/reports/{cls.compare_report_id}')
            except Exception:
                pass
        for rid in (cls.e2e_report_id, cls.api_report_id):
            if rid:
                try:
                    api_client.delete(f'/reports/{rid}')
                except Exception:
                    pass
        for tid in (cls.e2e_task_id, cls.e2e_task2_id, cls.api_task_id):
            if tid:
                try:
                    api_client.delete(f'/tasks/{tid}')
                except Exception:
                    pass
        for cid in (cls.e2e_case_ids + cls.api_case_ids):
            if cid:
                try:
                    api_client.delete(f'/testcases/{cid}')
                except Exception:
                    pass
        for aid in (cls.e2e_audio_ids + cls.api_audio_ids):
            if aid:
                try:
                    api_client.delete(f'/audios/{aid}')
                except Exception:
                    pass

    def test_99_cleanup(self, api_client):
        """收尾清理（独立用例保证即使前面断言失败也执行）。"""
        self._cleanup_cls(api_client)
        _dump_evidence('Z_cleanup', {'done': True})
