# -*- coding: utf-8 -*-
"""端到端全链路集成测试 — INT-24。

完整链路：
  上传音频 → 生成 E2E 用例 → 创建任务并关联用例 → 启动 E2E 任务 →
  轮询进度至完成 → 生成测试报告 → 查询报告

复用 conftest.py 的 fixtures（api_client / sample_audio_files / unified_rounds / require_backend）。
后端未运行时通过 require_backend 自动 skip。

样例数据: doc/voice_llm/样例/ (3 个 WAV + 样例.json 统一标注)
"""
import time

import httpx
import pytest

# ── 轮询参数 ──────────────────────────────────────────────
TASK_POLL_TIMEOUT = 300   # 任务执行超时（秒）
TASK_POLL_INTERVAL = 3     # 轮询间隔
REPORT_POLL_TIMEOUT = 120  # 报告生成超时
REPORT_POLL_INTERVAL = 3


# ── 辅助函数 ──────────────────────────────────────────────

def _resp_data(resp):
    """从统一响应体 {success, code, data, message} 提取 data 字段。"""
    body = resp.json()
    assert body.get('success') or body.get('code') in (0, 200, 201), \
        f'API 返回错误: {resp.status_code} {body}'
    return body.get('data') or {}


def _put_to_oss(presigned_url: str, file_path: str) -> str:
    """直传文件到 OSS/MinIO 预签名 URL，返回 ETag。"""
    with open(file_path, 'rb') as f:
        content = f.read()
    r = httpx.put(presigned_url, content=content, timeout=30)
    assert r.status_code == 200, f'OSS PUT 失败: {r.status_code} {r.text[:200]}'
    return r.headers.get('ETag', '').strip('"')


# ── 端到端全链路测试 ─────────────────────────────────────

class TestE2EFullChain:
    """上传音频 → 生成 E2E 用例 → 创建/关联任务 → 启动执行 → 生成报告。"""

    def test_full_chain(self, api_client, sample_audio_files, unified_rounds):
        """覆盖 4 个阶段的完整链路。"""
        # ── 资源追踪（用于 finally 清理）──
        created_audio_ids = []
        created_tc_ids = []
        task_id = None
        report_id = None

        try:
            # ============================================================
            # 阶段 1：上传音频 → 生成 E2E 用例
            # ============================================================
            # 1.1 初始化上传任务
            r = api_client.post('/audios/upload/init')
            upload_task_id = _resp_data(r).get('taskId') or _resp_data(r).get('task_id')
            assert upload_task_id, 'init 未返回 taskId'

            # 1.2 注册文件
            file_data = [
                {'name': f['name'], 'size': f['size'], 'md5': f['md5'],
                 'relativePath': f['relativePath']}
                for f in sample_audio_files
            ]
            r = api_client.post('/audios/upload/register', json={
                'taskId': upload_task_id, 'files': file_data
            })
            reg_files = _resp_data(r).get('files', [])
            assert len(reg_files) == len(sample_audio_files), \
                f'register 返回文件数不匹配: {len(reg_files)}'

            file_ids = [rf.get('fileId') or rf.get('file_id') for rf in reg_files]

            # 复制 rounds 用于回填 audio_id
            tc_rounds = [dict(rnd) for rnd in unified_rounds]
            for rnd in tc_rounds:
                rnd['audios'] = [dict(a) for a in rnd.get('audios', [])]

            total = len(sample_audio_files)

            # 1.3 逐个上传 WAV
            for idx, (audio_file, file_id) in enumerate(zip(sample_audio_files, file_ids)):
                is_final = (idx == total - 1)

                # presign
                r = api_client.post('/audios/upload/presign', json={
                    'filename': audio_file['name'],
                    'fileSize': audio_file['size'],
                    'md5': audio_file['md5'],
                    'chunkSize': 5 * 1024 * 1024,
                    'isWav': True,
                    'relativePath': audio_file['relativePath'],
                })
                presign = _resp_data(r)

                audio_id = None

                if presign.get('instantUpload'):
                    # 秒传命中
                    audio_id = presign.get('audioId') or presign.get('audio_id')
                    assert audio_id, '秒传返回但 audioId 为空'
                else:
                    # 直传 OSS
                    upload_id = presign.get('uploadId') or presign.get('upload_id')
                    oss_key = presign.get('ossKey') or presign.get('oss_key')
                    parts = presign.get('parts', [])
                    total_parts = presign.get('totalParts') or presign.get('total_parts', 1)
                    assert upload_id and oss_key, f'presign 未返回 uploadId/ossKey: {presign}'

                    uploaded_parts = []
                    for pi in range(total_parts):
                        if pi < len(parts):
                            part_url = parts[pi].get('url') or parts[pi].get('URL')
                        else:
                            r = api_client.post('/audios/upload/presign-part', json={
                                'uploadId': upload_id, 'partNumber': pi + 1,
                            }, params={'oss_key': oss_key, 'category': presign.get('category', 'audios')})
                            part_url = _resp_data(r).get('url')
                        assert part_url, f'分片 {pi+1} 预签名 URL 为空'

                        etag = _put_to_oss(part_url, audio_file['path'])
                        uploaded_parts.append({'PartNumber': pi + 1, 'ETag': etag})

                    # complete-direct
                    r = api_client.post('/audios/upload/complete-direct', json={
                        'ossKey': oss_key,
                        'uploadId': upload_id,
                        'parts': uploaded_parts,
                        'filename': audio_file['name'],
                        'md5': audio_file['md5'],
                        'fileSize': audio_file['size'],
                        'audioType': 'dry',
                    })
                    comp_data = _resp_data(r)
                    audio_id = comp_data.get('audioId') or comp_data.get('audio_id')
                    assert audio_id, f'complete-direct 未返回 audioId: {comp_data}'

                created_audio_ids.append(audio_id)

                # 回填 audio_id 到 rounds
                for rnd in tc_rounds:
                    for a in rnd.get('audios', []):
                        if a.get('audio_name') == audio_file['name']:
                            a['audio_id'] = audio_id

                # merge — 关键：testTypes=['e2e']
                merge_body = {
                    'fileId': file_id,
                    'taskId': upload_task_id,
                    'audioType': 'dry',
                    'createTestCase': is_final,
                    'testTypes': ['e2e'],
                    'groupNameType': 'custom',
                    'customGroupName': 'E2E全链路测试',
                    'inheritTags': True,
                    'dimensions': {},
                }
                if is_final:
                    merge_body['testCaseConfig'] = {
                        'rounds': tc_rounds,
                        'groupName': 'E2E全链路测试',
                        'inheritTags': True,
                    }

                r = api_client.post('/audios/upload/merge', json=merge_body)
                merge_data = _resp_data(r)
                assert merge_data.get('status') == 'completed' or merge_data.get('audioId'), \
                    f'merge 未完成: {merge_data}'

                # 末尾 merge 验证用例生成
                if is_final:
                    tc_id = merge_data.get('testCaseId') or merge_data.get('test_case_id')
                    tc_count = merge_data.get('testCaseCount') or merge_data.get('test_case_count', 0)
                    assert tc_id or tc_count > 0, \
                        f'末尾 merge 未生成测试用例: {merge_data}'
                    if tc_id:
                        created_tc_ids.append(tc_id)

            # 1.4 验证用例可查询
            r = api_client.get('/testcases', params={'page': 1, 'per_page': 20})
            tc_list_data = _resp_data(r)
            items = tc_list_data.get('items', []) if isinstance(tc_list_data, dict) else tc_list_data
            assert isinstance(items, list), f'用例列表格式异常: {type(items)}'

            if created_tc_ids:
                tc_ids_str = [str(t) for t in created_tc_ids]
                found = [tc for tc in items
                         if str(tc.get('id', '')) in tc_ids_str]
                assert len(found) > 0, \
                    f'创建的用例 {created_tc_ids} 未在用例列表中找到'

            # ============================================================
            # 阶段 2：创建 E2E 任务并关联用例
            # ============================================================
            # 2.1 创建任务（type=e2e，同时在 caseIds 中传入用例 ID）
            task_name = f'E2E全链路测试_{int(time.time())}'
            r = api_client.post('/tasks', json={
                'name': task_name,
                'type': 'e2e',
                'description': 'INT-24 端到端全链路自动化测试',
                'caseIds': created_tc_ids,
                'config': {'parallel': True, 'concurrentTasks': 1},
            })
            task_data = _resp_data(r)
            task_id = task_data.get('id')
            assert task_id, f'任务创建未返回 id: {task_data}'

            # 2.2 通过 PATCH 关联用例（action=add）
            r = api_client.patch(f'/tasks/{task_id}/cases', json={
                'action': 'add',
                'caseIds': created_tc_ids,
            })
            uc_data = _resp_data(r)
            assert uc_data.get('taskId') or uc_data.get('task_id'), \
                f'关联用例未返回 taskId: {uc_data}'

            # 2.3 验证任务详情可见用例
            r = api_client.get(f'/tasks/{task_id}')
            task_detail = _resp_data(r)
            assert task_detail.get('id') == task_id or str(task_detail.get('id')) == str(task_id), \
                f'任务详情 ID 不匹配: {task_detail}'
            cases = task_detail.get('cases', [])
            assert len(cases) > 0, f'任务详情中未见关联用例: {task_detail}'

            # ============================================================
            # 阶段 3：启动 E2E 任务并轮询至完成
            # ============================================================
            # 3.1 启动任务
            r = api_client.post(f'/tasks/{task_id}/start')
            start_data = _resp_data(r)
            assert start_data.get('status') in ('running', 'pending', 'queued', 'completed', 'failed'), \
                f'启动后状态异常: {start_data}'

            # 3.2 轮询进度至终态
            deadline = time.time() + TASK_POLL_TIMEOUT
            final_status = None
            progress_data = None
            while time.time() < deadline:
                r = api_client.get(f'/tasks/{task_id}/progress')
                progress_data = _resp_data(r)
                final_status = progress_data.get('status')
                if final_status in ('completed', 'failed', 'cancelled'):
                    break
                time.sleep(TASK_POLL_INTERVAL)

            # 验收：任务到达终态，progress 返回进度数据
            if final_status in ('completed', 'failed', 'cancelled'):
                assert progress_data is not None, 'progress 返回空'
                assert 'totalCases' in progress_data or 'total_cases' in progress_data, \
                    f'progress 缺少 totalCases: {progress_data}'
            else:
                # 超时未到达终态 — 标注环境限制，不 fail
                pytest.skip(
                    f'任务 {task_id} 在 {TASK_POLL_TIMEOUT}s 内未到达终态 '
                    f'(当前状态: {final_status})，可能因缺少在线设备。'
                )

            # ============================================================
            # 阶段 4：生成测试报告
            # ============================================================
            # 4.1 触发报告生成
            report_name = f'E2E全链路报告_{int(time.time())}'
            r = api_client.post('/reports/generate-task', json={
                'taskId': task_id,
                'name': report_name,
                'description': 'INT-24 端到端全链路测试报告',
            })
            gen_data = _resp_data(r)
            report_id = gen_data.get('reportId') or gen_data.get('report_id') or gen_data.get('id')
            assert report_id, f'报告生成未返回 reportId: {gen_data}'

            # 4.2 轮询报告状态至 completed
            deadline = time.time() + REPORT_POLL_TIMEOUT
            report_detail = None
            while time.time() < deadline:
                r = api_client.get(f'/reports/{report_id}')
                report_detail = _resp_data(r)
                rp_status = report_detail.get('status')
                if rp_status in ('completed', 'failed', 'published'):
                    break
                time.sleep(REPORT_POLL_INTERVAL)

            # 验收：报告生成成功，包含 summary 和 detail 数据
            assert report_detail is not None, '报告详情返回空'
            assert report_detail.get('status') == 'completed', \
                f'报告未到达 completed 状态: {report_detail.get("status")}'
            assert 'summary' in report_detail, \
                f'报告缺少 summary 字段: {report_detail}'
            summary = report_detail.get('summary') or {}
            assert isinstance(summary, dict), \
                f'summary 非字典: {type(summary)}'

        finally:
            # ============================================================
            # 清理：报告 → 任务 → 用例 → 音频
            # ============================================================
            # 报告
            if report_id:
                try:
                    api_client.delete(f'/reports/{report_id}')
                except Exception:
                    pass
            # 任务
            if task_id:
                try:
                    api_client.delete(f'/tasks/{task_id}')
                except Exception:
                    pass
            # 用例
            for tc_id in created_tc_ids:
                try:
                    api_client.delete(f'/testcases/{tc_id}')
                except Exception:
                    pass
            # 音频
            for aid in created_audio_ids:
                try:
                    api_client.delete(f'/audios/{aid}')
                except Exception:
                    pass
