# -*- coding: utf-8 -*-
"""音频文件夹上传 → 生成测试用例 API 集成测试。

测试链路（与前端 uploadProcess.ts 的 WAV 直传流程一致）:
  1. POST /audios/upload/init         → taskId
  2. POST /audios/upload/register     → [fileId, ...]
  3. 循环每个 WAV:
     a. POST /audios/upload/presign   → uploadId, ossKey, presigned URLs
     b. PUT <presigned_url>           → 直传 OSS/MinIO
     c. POST /audios/upload/complete-direct → audioId
     d. POST /audios/upload/merge     → 非末尾文件 createTestCase=false;
                                         末尾文件 createTestCase=true + testCaseConfig
  4. 验证测试用例已生成

样例数据: doc/voice_llm/样例/ (3 个 WAV + 样例.json 统一标注)
"""
import httpx
import pytest

# ── 辅助函数 ──────────────────────────────────────────────

def _resp_data(resp):
    """从统一响应体提取 data 字段。"""
    body = resp.json()
    assert body.get('success') or body.get('code') in (0, 200), \
        f'API 返回错误: {body}'
    return body.get('data') or {}


def _put_to_oss(presigned_url: str, file_path: str) -> str:
    """直传文件到 OSS/MinIO 预签名 URL，返回 ETag。"""
    with open(file_path, 'rb') as f:
        content = f.read()
    r = httpx.put(presigned_url, content=content, timeout=30)
    assert r.status_code == 200, f'OSS PUT 失败: {r.status_code} {r.text[:200]}'
    return r.headers.get('ETag', '').strip('"')


# ── 契约测试: 单接口验证 ─────────────────────────────────

class TestAudioUploadContract:
    """各上传接口的契约/边界测试。"""

    def test_init_upload(self, api_client):
        """POST /audios/upload/init 返回 taskId。"""
        r = api_client.post('/audios/upload/init')
        data = _resp_data(r)
        assert 'taskId' in data or 'task_id' in data
        task_id = data.get('taskId') or data.get('task_id')
        assert task_id, 'taskId 为空'

    def test_presign_missing_fields(self, api_client):
        """POST /audios/upload/presign 缺少必填字段时返回 4xx。"""
        r = api_client.post('/audios/upload/presign', json={})
        assert 400 <= r.status_code < 500, f'期望 4xx, 实际 {r.status_code}'

    def test_merge_missing_fields(self, api_client):
        """POST /audios/upload/merge 缺少必填字段时返回 4xx。"""
        r = api_client.post('/audios/upload/merge', json={})
        assert 400 <= r.status_code < 500, f'期望 4xx, 实际 {r.status_code}'

    def test_complete_direct_missing_fields(self, api_client):
        """POST /audios/upload/complete-direct 缺少必填字段时返回 4xx。"""
        r = api_client.post('/audios/upload/complete-direct', json={})
        assert 400 <= r.status_code < 500, f'期望 4xx, 实际 {r.status_code}'


# ── 端到端: 文件夹上传生成用例 ───────────────────────────

class TestFolderUploadGenerateTestCase:
    """文件夹上传音频 → 生成多轮测试用例完整链路。"""

    def test_folder_upload_with_unified_rounds(
        self, api_client, sample_audio_files, unified_rounds
    ):
        """上传 3 个 WAV + 统一标注 rounds → 生成测试用例。"""
        created_audio_ids = []
        created_tc_ids = []

        try:
            # ── Step 1: 初始化上传任务 ──
            r = api_client.post('/audios/upload/init')
            task_id = _resp_data(r).get('taskId') or _resp_data(r).get('task_id')
            assert task_id, 'init 未返回 taskId'

            # ── Step 2: 注册文件 ──
            file_data = [
                {'name': f['name'], 'size': f['size'], 'md5': f['md5'],
                 'relativePath': f['relativePath']}
                for f in sample_audio_files
            ]
            r = api_client.post('/audios/upload/register', json={
                'taskId': task_id, 'files': file_data
            })
            reg_files = _resp_data(r).get('files', [])
            assert len(reg_files) == len(sample_audio_files), \
                f'register 返回文件数不匹配: {len(reg_files)}'

            # 构建 fileId 列表
            file_ids = [rf.get('fileId') or rf.get('file_id') for rf in reg_files]

            # 复制 rounds 用于回填 audio_id
            tc_rounds = [dict(r) for r in unified_rounds]
            for rnd in tc_rounds:
                rnd['audios'] = [dict(a) for a in rnd.get('audios', [])]

            total = len(sample_audio_files)

            # ── Step 3: 逐个上传 WAV ──
            for idx, (audio_file, file_id) in enumerate(zip(sample_audio_files, file_ids)):
                is_final = (idx == total - 1)

                # 3a. presign
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

                # 秒传命中
                if presign.get('instantUpload'):
                    audio_id = presign.get('audioId') or presign.get('audio_id')
                    assert audio_id, '秒传返回但 audioId 为空'
                else:
                    # 3b. 直传 OSS
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
                            # 请求额外分片 URL
                            r = api_client.post('/audios/upload/presign-part', json={
                                'uploadId': upload_id, 'partNumber': pi + 1,
                            }, params={'oss_key': oss_key, 'category': presign.get('category', 'audios')})
                            part_url = _resp_data(r).get('url')
                        assert part_url, f'分片 {pi+1} 预签名 URL 为空'

                        etag = _put_to_oss(part_url, audio_file['path'])
                        uploaded_parts.append({'PartNumber': pi + 1, 'ETag': etag})

                    # 3c. complete-direct (WAV 直传完成登记)
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

                # 回填 audio_id 到 rounds（按文件名匹配）
                for rnd in tc_rounds:
                    for a in rnd.get('audios', []):
                        if a.get('audio_name') == audio_file['name']:
                            a['audio_id'] = audio_id

                # 3d. merge
                merge_body = {
                    'fileId': file_id,
                    'taskId': task_id,
                    'audioType': 'dry',
                    'createTestCase': is_final,
                    'testTypes': ['api'],
                    'groupNameType': 'custom',
                    'customGroupName': 'API测试_文件夹上传',
                    'inheritTags': True,
                    'dimensions': {},
                }
                if is_final:
                    merge_body['testCaseConfig'] = {
                        'rounds': tc_rounds,
                        'groupName': 'API测试_文件夹上传',
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
                    if tc_id:
                        created_tc_ids.append(tc_id)
                    # 验证用例数 > 0
                    assert tc_count > 0 or tc_id, \
                        f'末尾 merge 未生成测试用例: {merge_data}'

            # ── Step 4: 验证用例可查询 ──
            r = api_client.get('/testcases')
            tc_list_data = _resp_data(r)
            # 在用例列表中查找新创建的用例
            items = tc_list_data.get('items', []) if isinstance(tc_list_data, dict) else tc_list_data
            assert isinstance(items, list), f'用例列表格式异常: {type(items)}'

            # 如果 merge 返回了 testCaseId，验证它在列表中
            if created_tc_ids:
                tc_ids_str = [str(t) for t in created_tc_ids]
                found = [tc for tc in items
                         if str(tc.get('id', '')) in tc_ids_str]
                assert len(found) > 0, \
                    f'创建的用例 {created_tc_ids} 未在用例列表中找到'

        finally:
            # ── 清理: 删除创建的用例和音频 ──
            for tc_id in created_tc_ids:
                try:
                    api_client.delete(f'/testcases/{tc_id}')
                except Exception:
                    pass
            for aid in created_audio_ids:
                try:
                    api_client.delete(f'/audios/{aid}')
                except Exception:
                    pass
