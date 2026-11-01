# -*- coding: utf-8 -*-
"""INT-2312：用例导出异步作业（A 卡）。

验收口径（卡面「可测验收标准·单测」）：
1. 提交校验：空 ids / 非法 format / 超上限 → 400，文案与同步接口一致；
2. 幂等：同参数两次提交 → 同一 task_id 且线程池 submit 只被调用 1 次；
   idempotency_key 命中同样生效；原任务 failed 后重提新建；
3. 并发：同用户在办 → 429 且体里带 task_id/status；队列深度到上限 → 429；
4. 状态机：queued→running→done 全字段推进；phase running 期间非空、终态为 null；
5. 部分失败：单条抛异常 → done、exported=1、missing=[{id, reason:'rpc_error'}]、
   ZIP 内 manifest missing_case_ids 含该 id；
6. exported==0 → failed + EXPORT_NO_DATA；
7. 音频不可用（ACL 抛错）→ failed，不产出下载链接；
8. 归属：非创建人非 admin → 404；创建人 / admin → 200；
9. 下载：非 done → 409；expired → 410；done → 200 且 Content-Disposition 文件名口径一致；
10. 身份透传：worker 执行期间 get_current_user_id() == 提交人；
11. 内存纪律：ZIP 拿到的是有 fileno() 的文件对象，音频走临时文件（不累积 content）；
12. 重启接管：running → failed(GATEWAY_RESTARTED)；queued → 重新提交。

全部用例不连真实栈：Redis 用内存替身、存储与 gRPC ACL 用替身隔离。
"""
import asyncio
import io
import json
import os
import time
import zipfile

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from api_gateway.application.services.testcase import (
    testcase_export_job as job_module,
)
from api_gateway.application.services.testcase import (
    testcase_export_service as svc_module,
)
from api_gateway.application.services.testcase.testcase_export_job import (
    ExportJobStatus,
    TestCaseExportJobManager,
)
from api_gateway.domain.dto.api_gateway_acl_dto import CommandResultDTO
from api_gateway.routes import testcase_bp as route_module
from shared.infrastructure.config import BaseConfig
from shared.infrastructure.user_context import get_current_user_id

USER_ID = 42
OTHER_USER_ID = 99


# ----------------------------------------------------------------------
# 替身：内存作业存储 / 记录型线程池 / 内存存储
# ----------------------------------------------------------------------
class FakeJobStore:
    """与 ExportJobStore 同接口的内存实现（不连 Redis）。"""

    def __init__(self):
        self.hashes = {}
        self.user_active = {}
        self.idem = {}
        self.pending = {}
        self.ping_ok = True
        self.cas_calls = 0

    def ping(self):
        if not self.ping_ok:
            raise RuntimeError('redis down')

    def save(self, task_id, fields, ttl_seconds):
        bucket = self.hashes.setdefault(task_id, {})
        for key, value in fields.items():
            # 深拷贝，模拟 Redis 的 JSON 序列化（防止测试里共享可变对象）
            bucket[key] = json.loads(json.dumps(value))

    def load(self, task_id):
        bucket = self.hashes.get(task_id)
        return json.loads(json.dumps(bucket)) if bucket else {}

    def delete(self, task_id):
        self.hashes.pop(task_id, None)

    def cas_status(self, task_id, expected_status, fields, ttl_seconds):
        self.cas_calls += 1
        bucket = self.hashes.get(task_id)
        if not bucket or bucket.get('status') != expected_status:
            return False
        self.save(task_id, fields, ttl_seconds)
        return True

    def claim_user(self, user_id, task_id, ttl_seconds):
        if user_id in self.user_active:
            return False
        self.user_active[user_id] = task_id
        return True

    def get_user_active(self, user_id):
        return self.user_active.get(user_id)

    def release_user(self, user_id):
        self.user_active.pop(user_id, None)

    def set_idem(self, fingerprint, task_id, ttl_seconds):
        self.idem[fingerprint] = task_id

    def get_idem(self, fingerprint):
        return self.idem.get(fingerprint)

    def delete_idem(self, fingerprint):
        self.idem.pop(fingerprint, None)

    def enqueue(self, task_id):
        self.pending[task_id] = time.time()

    def dequeue(self, task_id):
        self.pending.pop(task_id, None)

    def queue_depth(self):
        return len(self.pending)

    def scan_job_ids(self):
        return list(self.hashes.keys())


class RecordingExecutor:
    """记录 submit 调用、不真正开线程（测试里手动 _run_job 驱动）。"""

    def __init__(self):
        self.calls = []

    def submit(self, fn, *args, **kwargs):
        self.calls.append((fn, args))
        return None

    def shutdown(self, wait=False, cancel_futures=False):
        pass


class FakeStorage:
    def __init__(self, url=None):
        self.files = {}
        self.deleted = []
        self.url = url

    def save_file(self, local_path, category, key, allow_fallback=True):
        path = f'local://{category}/{key}'
        with open(local_path, 'rb') as fh:
            self.files[path] = fh.read()
        return path

    def delete(self, path):
        self.deleted.append(path)
        self.files.pop(path, None)

    def load_stream(self, path):
        return io.BytesIO(self.files[path])

    def get_url(self, path, expires=3600):
        return self.url


@pytest.fixture
def manager():
    return TestCaseExportJobManager(
        store=FakeJobStore(),
        executor=RecordingExecutor(),
        storage=FakeStorage(),
    )


# ----------------------------------------------------------------------
# 夹具
# ----------------------------------------------------------------------
def _case_detail(case_id, config=None):
    return CommandResultDTO(success=True, data={
        'id': case_id,
        'name': f'case-{case_id}',
        'description': '',
        'group_name': 'g',
        'group_id': 'g1',
        'tags': [],
        'config': config or {},
    })


def _patch_detail(monkeypatch, case_ids, config=None):
    wanted = set(case_ids)

    def _fake(tc_id):
        if tc_id not in wanted:
            return CommandResultDTO(success=False, message='not found', data=None)
        return _case_detail(tc_id, config)
    monkeypatch.setattr(svc_module._testcase_acl, 'get_testcase_detail', _fake)


def _submit(manager, payload, identity=(USER_ID, False)):
    return manager.submit(payload, identity)


def _run(manager, payload, identity=(USER_ID, False)):
    """提交并同步执行一个作业，返回 task_id。"""
    body, code = _submit(manager, payload, identity)
    assert code == 202, body
    task_id = body['task_id']
    manager._run_job(task_id)
    return task_id


def _zip_bytes(manager, status_body):
    path = status_body['result']['path']
    return zipfile.ZipFile(io.BytesIO(manager._storage.files[path]))


# ----------------------------------------------------------------------
# 1. 提交校验（文案与同步接口一致）
# ----------------------------------------------------------------------
def test_submit_validation_matches_sync_messages(manager, monkeypatch):
    body, code = _submit(manager, {'ids': []})
    assert code == 400
    assert body['message'] == '未指定要导出的用例ID'

    body, code = _submit(manager, {'ids': ['a'], 'format': 'xml'})
    assert code == 400
    assert body['message'] == '不支持的导出格式: xml'

    monkeypatch.setattr(BaseConfig, 'TESTCASE_EXPORT_JOB_MAX_IDS', 2)
    body, code = _submit(manager, {'ids': ['a', 'b', 'c']})
    assert code == 400
    assert body['message'] == 'ids 超过上限'

    assert manager._store.hashes == {}, '校验失败不得落任何作业'


def test_submit_returns_503_when_redis_unavailable(manager):
    manager._store.ping_ok = False
    body, code = _submit(manager, {'ids': ['a']})
    assert code == 503
    assert '暂不可用' in body['message']


# ----------------------------------------------------------------------
# 2. 幂等
# ----------------------------------------------------------------------
def test_same_request_reuses_task_id_and_submits_once(manager, monkeypatch):
    _patch_detail(monkeypatch, ['c1'])
    payload = {'ids': ['c1'], 'format': 'zip'}

    first, code1 = _submit(manager, payload)
    second, code2 = _submit(manager, payload)

    assert code1 == 202 and code2 == 202
    assert first['task_id'] == second['task_id']
    assert len(manager._executor.calls) == 1, '幂等命中不得重复入池'
    assert first['total'] == 1
    assert first['poll_after_ms'] == 1000
    assert first['expires_at']


def test_idempotency_key_wins_over_request_fingerprint(manager, monkeypatch):
    _patch_detail(monkeypatch, ['c1', 'c2'])
    first, _ = _submit(manager, {'ids': ['c1'], 'idempotency_key': 'k-1'})
    second, _ = _submit(manager, {'ids': ['c2'], 'idempotency_key': 'k-1'})
    assert first['task_id'] == second['task_id']
    assert len(manager._executor.calls) == 1


def test_failed_job_is_not_reused_by_idempotency(manager, monkeypatch):
    monkeypatch.setattr(
        svc_module._testcase_acl, 'get_testcase_detail',
        lambda _id: CommandResultDTO(success=False, data=None))
    payload = {'ids': ['c1'], 'format': 'zip'}

    first, _ = _submit(manager, payload)
    manager._run_job(first['task_id'])
    assert manager._store.load(first['task_id'])['status'] == 'failed'

    second, code = _submit(manager, payload)
    assert code == 202
    assert second['task_id'] != first['task_id'], 'failed 后重提必须新建'


def test_racing_same_params_submit_reuses_task_id(manager, monkeypatch):
    """几乎同时的同参双提交：后者抢在办位失败时，复查幂等键仍返回原 task_id。"""
    _patch_detail(monkeypatch, ['c1'])
    payload = {'ids': ['c1'], 'format': 'zip'}

    first, code1 = _submit(manager, payload)
    assert code1 == 202

    # 模拟后者到达时前者已抢到在办位（claim 失败），幂等键也已写好
    monkeypatch.setattr(manager._store, 'claim_user', lambda *a, **k: False)
    second, code2 = _submit(manager, payload)

    assert code2 == 202
    assert second['task_id'] == first['task_id'], '同参并发提交不得落到 429'
    assert len(manager._executor.calls) == 1


# ----------------------------------------------------------------------
# 3. 并发闸
# ----------------------------------------------------------------------
def test_active_job_blocks_second_submit_with_429(manager, monkeypatch):
    _patch_detail(monkeypatch, ['c1', 'c2'])
    first, _ = _submit(manager, {'ids': ['c1']})
    body, code = _submit(manager, {'ids': ['c2']})

    assert code == 429
    assert body['message'] == '已有导出任务在进行'
    assert body['data'] == {'task_id': first['task_id'], 'status': 'queued'}


def test_queue_depth_limit_returns_429(manager, monkeypatch):
    _patch_detail(monkeypatch, ['c1'])
    monkeypatch.setattr(BaseConfig, 'TESTCASE_EXPORT_JOB_MAX_QUEUE', 1)
    manager._store.pending['existing'] = time.time()

    body, code = _submit(manager, {'ids': ['c1']})
    assert code == 429
    assert body['message'] == '导出任务队列已满，请稍后重试'


# ----------------------------------------------------------------------
# 4. 状态机
# ----------------------------------------------------------------------
def test_state_machine_queued_running_done(manager, monkeypatch):
    _patch_detail(monkeypatch, ['c1', 'c2'])
    body, code = _submit(manager, {'ids': ['c1', 'c2'], 'format': 'zip'})
    task_id = body['task_id']

    job = manager._store.load(task_id)
    assert job['status'] == 'queued' and job['phase'] is None
    status_body, http_code = manager.get_status(task_id, (USER_ID, False))
    assert http_code == 200
    assert status_body['status'] == 'queued' and status_body['phase'] is None
    assert status_body['progress'] == {
        'total': 2, 'processed': 0, 'exported': 0, 'missing': []}
    assert status_body['result'] is None and status_body['error'] is None

    # 打包阶段落 running + phase=packaging
    observed = {}
    original_pack_zip = svc_module.TestCaseExportService._pack_zip

    def spy_pack_zip(spec, export_data, missing_case_ids, sink):
        snapshot = manager._store.load(task_id)
        observed['status'] = snapshot['status']
        observed['phase'] = snapshot['phase']
        return original_pack_zip(spec, export_data, missing_case_ids, sink)

    monkeypatch.setattr(
        svc_module.TestCaseExportService, '_pack_zip', staticmethod(spy_pack_zip))
    manager._run_job(task_id)
    assert observed == {'status': 'running', 'phase': 'packaging'}

    job = manager._store.load(task_id)
    assert job['status'] == 'done'
    assert job['phase'] is None
    assert job['started_at'] and job['finished_at']

    status_body, _ = manager.get_status(task_id, (USER_ID, False))
    assert status_body['status'] == 'done'
    assert status_body['phase'] is None
    assert status_body['error'] is None
    assert status_body['progress'] == {
        'total': 2, 'processed': 2, 'exported': 2, 'missing': []}
    assert status_body['result']['format'] == 'zip'
    assert status_body['result']['filename'].startswith('testcases_export_')
    assert status_body['result']['filename'].endswith('.zip')
    assert status_body['result']['size'] > 0
    # 在办位已释放
    assert manager._store.get_user_active(USER_ID) is None


def test_download_url_present_only_when_storage_can_presign(manager, monkeypatch):
    _patch_detail(monkeypatch, ['c1'])
    task_id = _run(manager, {'ids': ['c1']})

    # 本地降级：get_url 返回 None → 字段省略
    status_body, _ = manager.get_status(task_id, (USER_ID, False))
    assert 'download_url' not in status_body['result']

    manager._storage.url = 'https://oss.example/signed'
    status_body, _ = manager.get_status(task_id, (USER_ID, False))
    assert status_body['result']['download_url'] == 'https://oss.example/signed'


# ----------------------------------------------------------------------
# 5. 部分失败
# ----------------------------------------------------------------------
def test_partial_failure_reports_missing_and_still_produces_zip(manager, monkeypatch):
    def fake_detail(tc_id):
        if tc_id == 'bad':
            raise RuntimeError('rpc down')
        return _case_detail(tc_id)
    monkeypatch.setattr(svc_module._testcase_acl, 'get_testcase_detail', fake_detail)

    task_id = _run(manager, {'ids': ['ok1', 'bad'], 'format': 'zip'})
    status_body, _ = manager.get_status(task_id, (USER_ID, False))

    assert status_body['status'] == 'done'
    assert status_body['progress'] == {
        'total': 2, 'processed': 2, 'exported': 1,
        'missing': [{'id': 'bad', 'reason': 'rpc_error'}],
    }

    zf = _zip_bytes(manager, status_body)
    manifest = json.loads(zf.read('manifest.json'))
    assert manifest['missing_case_ids'] == ['bad']
    assert manifest['total_count'] == 1


def test_not_found_reason_for_unsuccessful_detail(manager, monkeypatch):
    """下游返回 success=false（含无权限被伪装成不存在）→ reason=not_found。"""
    calls = []

    def fake_detail(tc_id):
        calls.append(tc_id)
        return CommandResultDTO(success=False, data=None)
    monkeypatch.setattr(svc_module._testcase_acl, 'get_testcase_detail', fake_detail)

    export_data, missing = svc_module.TestCaseExportService._fetch_export_data(
        svc_module.ExportSpec(ids=['gone'], format='zip'))
    assert export_data == []
    assert missing == [{'id': 'gone', 'reason': 'not_found'}]
    assert calls == ['gone']


# ----------------------------------------------------------------------
# 6. exported == 0
# ----------------------------------------------------------------------
def test_no_exported_rows_fails_with_no_data(manager, monkeypatch):
    monkeypatch.setattr(
        svc_module._testcase_acl, 'get_testcase_detail',
        lambda _id: CommandResultDTO(success=False, data=None))

    body, _ = _submit(manager, {'ids': ['x'], 'format': 'zip'})
    task_id = body['task_id']
    manager._run_job(task_id)

    status_body, _ = manager.get_status(task_id, (USER_ID, False))
    assert status_body['status'] == 'failed'
    assert status_body['error']['code'] == 'EXPORT_NO_DATA'
    assert status_body['result'] is None
    assert manager._store.get_user_active(USER_ID) is None
    # failed → 幂等键删除（可用同参数重提）
    assert manager._store.idem == {}


# ----------------------------------------------------------------------
# 7. 音频不可用 → failed，不产出下载链接
# ----------------------------------------------------------------------
def test_audio_source_unavailable_fails_job(manager, monkeypatch):
    audio_config = {'rounds': [{'round_number': 1, 'audios': [{'audio_id': 11}]}]}
    _patch_detail(monkeypatch, ['c1'], config=audio_config)
    monkeypatch.setattr(
        svc_module._audio_acl, 'get_one',
        lambda _id: CommandResultDTO(success=False, data=None))

    def _boom(_payload):
        raise RuntimeError('audio service down')
    monkeypatch.setattr(svc_module._audio_acl, 'get_by_ids', _boom)

    body, _ = _submit(manager, {
        'ids': ['c1'], 'format': 'zip', 'include_audios': True})
    task_id = body['task_id']
    manager._run_job(task_id)

    status_body, _ = manager.get_status(task_id, (USER_ID, False))
    assert status_body['status'] == 'failed'
    assert status_body['error']['code'] == 'EXPORT_AUDIO_UNAVAILABLE'
    assert status_body['result'] is None


# ----------------------------------------------------------------------
# 8. 归属
# ----------------------------------------------------------------------
def test_ownership_404_for_other_user_and_200_for_admin(manager, monkeypatch):
    _patch_detail(monkeypatch, ['c1'])
    task_id = _run(manager, {'ids': ['c1']})

    payload, code = manager.get_status(task_id, (OTHER_USER_ID, False))
    assert code == 404

    info, err = manager.get_download(task_id, (OTHER_USER_ID, False))
    assert info is None and err[1] == 404

    payload, code = manager.get_status(task_id, (OTHER_USER_ID, True))
    assert code == 200

    payload, code = manager.get_status('not-exist', (USER_ID, False))
    assert code == 404


# ----------------------------------------------------------------------
# 9. 下载语义
# ----------------------------------------------------------------------
def test_download_states(manager, monkeypatch):
    _patch_detail(monkeypatch, ['c1'])
    body, _ = _submit(manager, {'ids': ['c1'], 'format': 'zip'})
    task_id = body['task_id']

    info, err = manager.get_download(task_id, (USER_ID, False))
    assert info is None
    assert err[1] == 409 and err[0]['message'] == '导出未完成'

    manager._run_job(task_id)
    info, err = manager.get_download(task_id, (USER_ID, False))
    assert err is None
    assert info['media_type'] == 'application/zip'
    assert info['filename'].startswith('testcases_export_')

    manager._store.save(task_id, {'status': ExportJobStatus.EXPIRED.value}, 100)
    info, err = manager.get_download(task_id, (USER_ID, False))
    assert info is None
    assert err[1] == 410 and err[0]['message'] == '导出文件已过期，请重新导出'


def test_download_410_when_artifact_object_missing(manager, monkeypatch):
    """产物对象已不在存储（被清理 / 存储漂移）→ 410，不给半截流。"""
    _patch_detail(monkeypatch, ['c1'])
    task_id = _run(manager, {'ids': ['c1'], 'format': 'zip'})
    manager._storage.files.clear()

    info, err = manager.get_download(task_id, (USER_ID, False))
    assert info is None and err[1] == 410


def test_download_route_streams_with_sync_filename_contract(manager, monkeypatch):
    _patch_detail(monkeypatch, ['c1'])
    task_id = _run(manager, {'ids': ['c1'], 'format': 'zip'})
    path = manager._store.load(task_id)['result']['path']

    monkeypatch.setattr(job_module, 'get_export_job_manager', lambda: manager)
    monkeypatch.setattr(
        route_module, 'capture_identity', lambda: (USER_ID, False))
    # 取流在应用层（路由不直触 Storage），替身按 path 返回文件流
    monkeypatch.setattr(
        manager._storage, 'load_stream',
        lambda _path: io.BytesIO(manager._storage.files[_path]))

    response = route_module.download_export_job(task_id)
    assert response.status_code == 200
    assert response.media_type == 'application/zip'
    disposition = response.headers['content-disposition']
    assert 'attachment;' in disposition
    assert 'testcases_export_' in disposition and '.zip' in disposition

    async def _collect(iterator):
        return [chunk async for chunk in iterator]

    chunks = asyncio.run(_collect(response.body_iterator))
    assert b''.join(chunks) == manager._storage.files[path]


# ----------------------------------------------------------------------
# 10. 身份透传
# ----------------------------------------------------------------------
def test_worker_runs_with_submitter_identity(manager, monkeypatch):
    seen = []

    def fake_detail(tc_id):
        seen.append(get_current_user_id())
        return _case_detail(tc_id)
    monkeypatch.setattr(svc_module._testcase_acl, 'get_testcase_detail', fake_detail)

    _run(manager, {'ids': ['c1', 'c2']})
    assert seen == [USER_ID, USER_ID], 'worker 内必须带提交人身份（否则私有用例静默少条）'


# ----------------------------------------------------------------------
# 11. 内存纪律
# ----------------------------------------------------------------------
def test_zip_writes_to_file_object_and_audio_streams_via_tmp_file(manager, monkeypatch):
    audio_config = {'rounds': [{'round_number': 1, 'audios': [{'audio_id': 11}]}]}
    _patch_detail(monkeypatch, ['c1'], config=audio_config)
    monkeypatch.setattr(
        svc_module._audio_acl, 'get_one',
        lambda _id: CommandResultDTO(success=True, data={'name': 'play'}))
    monkeypatch.setattr(
        svc_module._audio_acl, 'get_by_ids',
        lambda _payload: CommandResultDTO(success=True, data=[{
            'id': 11, 'name': 'play', 'file_path': 'oss://b/play.wav',
            'format': 'wav'}]))

    loaded_paths = []

    def fake_load_file(path, local_path=None, allow_fallback=True):
        loaded_paths.append((path, local_path))
        assert not isinstance(path, (bytes, bytearray)), '不得整条读字节'
        with open(local_path, 'wb') as fh:
            fh.write(b'RIF' * 1000)
        return local_path
    monkeypatch.setattr(svc_module._storage, 'load_file', fake_load_file)

    captured = {}
    real_zipfile = zipfile.ZipFile

    def spy_zipfile(file, mode='r', *args, **kwargs):
        captured.setdefault('sink', file)
        return real_zipfile(file, mode, *args, **kwargs)
    monkeypatch.setattr(svc_module.zipfile, 'ZipFile', spy_zipfile)

    task_id = _run(manager, {
        'ids': ['c1'], 'format': 'zip', 'include_audios': True})

    sink = captured['sink']
    assert hasattr(sink, 'fileno'), 'ZIP 必须写到真实文件对象（不是内存缓冲）'
    assert sink.name.endswith('.zip')

    assert loaded_paths and loaded_paths[0][0] == 'oss://b/play.wav'
    # 音频先落临时文件（目录存在），写包后即删除
    tmp_path = loaded_paths[0][1]
    assert os.path.dirname(tmp_path) and not os.path.exists(tmp_path)

    status_body, _ = manager.get_status(task_id, (USER_ID, False))
    zf = _zip_bytes(manager, status_body)
    manifest = json.loads(zf.read('manifest.json'))
    assert manifest['audio_file_count'] == 1
    assert manifest['audios'][0]['md5']


def test_audio_entries_carry_no_binary_content(monkeypatch):
    monkeypatch.setattr(
        svc_module._audio_acl, 'get_by_ids',
        lambda _payload: CommandResultDTO(success=True, data=[{
            'id': 11, 'name': 'play', 'file_path': 'oss://b/play.wav',
            'format': 'wav'}]))
    entries, missing = svc_module.TestCaseExportService._collect_audio_package_entries([
        {'id': 'c1', 'config': {'rounds': [{'audios': [{'audio_id': 11}]}]}}])
    assert missing == []
    assert 'content' not in entries[0], '音频二进制不得累积进条目列表'
    assert entries[0]['file_path'] == 'oss://b/play.wav'


# ----------------------------------------------------------------------
# 12. 重启接管 / 清理
# ----------------------------------------------------------------------
def test_takeover_fails_running_and_requeues_queued(manager, monkeypatch):
    _patch_detail(monkeypatch, ['a', 'b'])
    running, _ = _submit(manager, {'ids': ['a']}, (USER_ID, False))
    queued, _ = _submit(manager, {'ids': ['b']}, (OTHER_USER_ID, False))
    manager._store.save(running['task_id'], {'status': 'running'}, 100)
    manager._executor.calls.clear()

    manager.takeover_on_startup()

    job = manager._store.load(running['task_id'])
    assert job['status'] == 'failed'
    assert job['error']['code'] == 'GATEWAY_RESTARTED'
    assert manager._store.get_user_active(USER_ID) is None

    assert [call[1][0] for call in manager._executor.calls] == [queued['task_id']]


def test_cleanup_expires_artifact_and_deletes_object(manager, monkeypatch):
    _patch_detail(monkeypatch, ['c1'])
    task_id = _run(manager, {'ids': ['c1']})
    path = manager._store.load(task_id)['result']['path']

    manager._store.save(task_id, {'artifact_expires_ts': time.time() - 1}, 100)
    manager.cleanup_once()

    job = manager._store.load(task_id)
    assert job['status'] == 'expired'
    assert manager._storage.deleted == [path]
    info, err = manager.get_download(task_id, (USER_ID, False))
    assert info is None and err[1] == 410


# ----------------------------------------------------------------------
# 13. worker 兜底（存储异常不得让任务卡在 queued / 占着在办位）
# ----------------------------------------------------------------------
def test_worker_store_error_fails_job_and_releases_slot(manager, monkeypatch):
    """`_run_job` 整段兜底：cas_status 抛异常也要落 failed 并释放在办位。

    线程池会静默吞异常，漏出去任务就停在 queued（且已出队），排队深度不回落。
    """
    _patch_detail(monkeypatch, ['c1'])
    body, code = _submit(manager, {'ids': ['c1']})
    assert code == 202
    task_id = body['task_id']

    def _boom(*args, **kwargs):
        raise RuntimeError('redis down')
    monkeypatch.setattr(manager._store, 'cas_status', _boom)

    manager._run_job(task_id)  # 异常不得逃逸出工作线程

    job = manager._store.load(task_id)
    assert job['status'] == 'failed'
    assert job['error']['code'] == 'EXPORT_INTERNAL_ERROR'
    assert manager._store.get_user_active(USER_ID) is None
    assert task_id not in manager._store.pending, '兜底要出队，否则排队深度一直挡提交'
