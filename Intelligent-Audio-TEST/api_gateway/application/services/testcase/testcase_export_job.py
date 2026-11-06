# -*- coding: utf-8 -*-
"""用例导出异步作业（INT-2312）。

背景：大范围导出的同步接口在一次 HTTP 长连接里逐条取详情再整包回传，
580 条实测 64.85s，近 1100 条即逼近 15173 反代 300s 上限；含音频时产物可达
GB 级，整包驻留内存会撑爆网关（uvicorn workers=1）。

本模块把导出改成「提交 ──▶ 后台线程池执行 ──▶ 轮询状态 ──▶ 下载产物」：

- 提交（POST /testcases/export/jobs）秒级返回 202 + task_id；
- 作业状态存 Redis（HASH），复用 RedisStore，与 refresh_task 同口径；
- 执行体在网关内 ThreadPoolExecutor 跑，产物落临时文件 → storage.save_file；
- 每用户同时最多 1 个在办作业（user:{id}:active），全局排队深度受
  TESTCASE_EXPORT_JOB_MAX_QUEUE 约束；同参数/同 idempotency_key 复用原 task_id；
- 重启接管：running → failed(GATEWAY_RESTARTED)，queued → 重新入池（不重放
  running：导出是可重试的用户动作，重放会二次拉满 gRPC）；
- 清理线程：产物到期删对象置 expired，作业 TTL 到期删 HASH。

红线：worker 内不得触碰 `request`（后台线程读不到请求上下文），请求体在路由
里解析后随作业记录传入；操作人身份用 capture_identity/run_with_identity 显式
透传，否则私有用例会被下游按「不存在」静默少条。
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from typing import Dict, List, Optional, Tuple

from redis.exceptions import WatchError

from api_gateway.utils.error_codes import ErrorCode
from api_gateway.utils.response import error_response
from shared.infrastructure.config import BaseConfig
from shared.infrastructure.storage import Storage
from shared.infrastructure.user_context import run_with_identity
from shared.utils.query_utils import now_cst
from shared.utils.redis_pubsub import RedisStore

logger = logging.getLogger(__name__)

# ---- Redis 键 ----
JOB_KEY_PREFIX = 'testcase_export:job:'
USER_ACTIVE_KEY_TEMPLATE = 'testcase_export:user:{user_id}:active'
IDEM_KEY_PREFIX = 'testcase_export:idem:'
# ZSET：score=入队时间，member=task_id；ZCARD 即排队深度，出队即 ZREM
PENDING_KEY = 'testcase_export:pending'

# ---- 存储 ----
ARTIFACT_CATEGORY = 'testcase_exports'

# ---- 契约常量 ----
POLL_AFTER_MS = 1000
# 进度写频：每 20 条或每 1 秒写一次（取先到），终态必写一次
PROGRESS_WRITE_EVERY = 20
PROGRESS_WRITE_INTERVAL_SECONDS = 1.0


class ExportJobErrorCode(StrEnum):
    """作业级错误码（字符串枚举，不混进 HTTP 整数码表）。"""

    NO_DATA = 'EXPORT_NO_DATA'
    # audio_service 不可用：整包失败，不产出半包（沿用 INT-2214 口径）
    AUDIO_UNAVAILABLE = 'EXPORT_AUDIO_UNAVAILABLE'
    STORAGE_FAILED = 'EXPORT_STORAGE_FAILED'
    INTERNAL_ERROR = 'EXPORT_INTERNAL_ERROR'
    GATEWAY_RESTARTED = 'GATEWAY_RESTARTED'


class ExportJobStatus(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    DONE = 'done'
    FAILED = 'failed'
    EXPIRED = 'expired'


class ExportJobPhase(StrEnum):
    FETCHING = 'fetching'
    PACKAGING = 'packaging'
    UPLOADING = 'uploading'


# 幂等命中后可复用的状态：已终结为 done 也复用（产物在 TTL 内可下载）
_IDEMPOTENT_REUSABLE_STATUSES = (
    ExportJobStatus.QUEUED,
    ExportJobStatus.RUNNING,
    ExportJobStatus.DONE,
)
# 每用户在办口径
_ACTIVE_STATUSES = (ExportJobStatus.QUEUED, ExportJobStatus.RUNNING)


class ExportExecutionError(Exception):
    """导出执行体的业务失败：`code` 取 ExportJobErrorCode。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _export_service():
    """延迟导入导出服务：本模块只对外提供作业编排，不参与导出实现。"""
    from api_gateway.application.services.testcase import testcase_export_service
    return testcase_export_service


def _status_value(value) -> Optional[str]:
    """枚举/字符串归一成状态字符串。"""
    return str(value) if value is not None else None


def _loads(raw):
    """Redis 原始值 → Python 对象（不存在返回 None）。"""
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode('utf-8')
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


class ExportJobStore:
    """异步导出作业的 Redis 存储。

    作业记录用 HASH（字段值为 JSON），与 ``RedisStore.save_task`` 口径一致：
    每用户的在办键、幂等键是 STRING，排队用 ZSET。
    """

    def __init__(self, store: Optional[RedisStore] = None):
        self._store = store

    def _redis_store(self) -> RedisStore:
        if self._store is None:
            self._store = RedisStore()
        return self._store

    @property
    def _redis(self):
        return self._redis_store().redis_client

    # ---- 连通性 ----
    def ping(self) -> None:
        """探测 Redis 可达（不可达即抛异常，提交接口据此回 503）。"""
        self._redis.ping()

    # ---- 作业 HASH ----
    def save(self, task_id: str, fields: dict, ttl_seconds: int) -> None:
        self._redis_store().save_task(
            f'{JOB_KEY_PREFIX}{task_id}', fields, ttl_seconds)

    def load(self, task_id: str) -> dict:
        return self._redis_store().load_task(f'{JOB_KEY_PREFIX}{task_id}')

    def delete(self, task_id: str) -> None:
        self._redis_store().delete_task(f'{JOB_KEY_PREFIX}{task_id}')

    def cas_status(self, task_id: str, expected_status: str, fields: dict,
                   ttl_seconds: int) -> bool:
        """把作业从 expected_status 原子推进到新状态（WATCH/MULTI）。

        只有当前状态仍等于 expected 才写入，避免同一 task_id 被执行两次。
        """
        key = f'{JOB_KEY_PREFIX}{task_id}'
        client = self._redis
        with client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    current = _loads(pipe.hget(key, 'status'))
                    if current != expected_status:
                        pipe.unwatch()
                        return False
                    pipe.multi()
                    pipe.hset(key, mapping={
                        k: json.dumps(v, ensure_ascii=False)
                        for k, v in fields.items()})
                    if ttl_seconds > 0:
                        pipe.expire(key, ttl_seconds)
                    pipe.execute()
                    return True
                except WatchError:
                    continue

    # ---- 每用户在办位 ----
    def claim_user(self, user_id, task_id: str, ttl_seconds: int) -> bool:
        """抢占该用户的在办位（SET NX），已被占用返回 False。"""
        return bool(self._redis.set(
            USER_ACTIVE_KEY_TEMPLATE.format(user_id=user_id), task_id,
            nx=True, ex=ttl_seconds))

    def get_user_active(self, user_id) -> Optional[str]:
        value = self._redis.get(USER_ACTIVE_KEY_TEMPLATE.format(user_id=user_id))
        return value.decode('utf-8') if isinstance(value, bytes) else value

    def release_user(self, user_id) -> None:
        self._redis.delete(USER_ACTIVE_KEY_TEMPLATE.format(user_id=user_id))

    # ---- 幂等键 ----
    def set_idem(self, fingerprint: str, task_id: str, ttl_seconds: int) -> None:
        self._redis.set(f'{IDEM_KEY_PREFIX}{fingerprint}', task_id, ex=ttl_seconds)

    def get_idem(self, fingerprint: str) -> Optional[str]:
        value = self._redis.get(f'{IDEM_KEY_PREFIX}{fingerprint}')
        return value.decode('utf-8') if isinstance(value, bytes) else value

    def delete_idem(self, fingerprint: str) -> None:
        self._redis.delete(f'{IDEM_KEY_PREFIX}{fingerprint}')

    # ---- 排队 ZSET ----
    def enqueue(self, task_id: str) -> None:
        self._redis.zadd(PENDING_KEY, {task_id: time.time()})

    def dequeue(self, task_id: str) -> None:
        self._redis.zrem(PENDING_KEY, task_id)

    def queue_depth(self) -> int:
        return int(self._redis.zcard(PENDING_KEY))

    # ---- 枚举作业 ----
    def scan_job_ids(self) -> List[str]:
        task_ids = []
        for key in self._redis.scan_iter(match=f'{JOB_KEY_PREFIX}*', count=200):
            key = key.decode('utf-8') if isinstance(key, bytes) else key
            task_ids.append(key[len(JOB_KEY_PREFIX):])
        return task_ids


class TestCaseExportJobManager:
    """异步导出作业编排器（每个网关进程一个实例）。"""

    # 名字以 Test 开头，避免被 pytest 当成测试类收集
    __test__ = False

    def __init__(self, store: Optional[ExportJobStore] = None,
                 executor=None, storage: Optional[Storage] = None):
        self._store = store or ExportJobStore()
        self._executor = executor
        self._storage = storage or Storage()
        self._lock = threading.Lock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------
    # 提交
    # ------------------------------------------------------------------
    def submit(self, payload, identity) -> Tuple[dict, int]:
        """校验并受理一次导出作业，返回 (响应体, HTTP 状态码)。"""
        svc = _export_service()
        spec, err = svc.TestCaseExportService.parse_request(
            payload, max_ids=BaseConfig.TESTCASE_EXPORT_JOB_MAX_IDS)
        if err is not None:
            return err

        user_id, is_admin = identity if identity else (None, False)

        # Redis 不可达时不能假装 202：任务没人跑，用户会一直轮询
        try:
            self._store.ping()
        except Exception:
            logger.warning("导出作业存储（Redis）不可用，拒绝受理", exc_info=True)
            return error_response(
                '导出服务暂不可用，请稍后重试',
                code=ErrorCode.EXTERNAL_SERVICE_ERROR, http_code=503)

        fingerprint = self._fingerprint(spec.to_dict(), user_id)
        resumed = self._resume_idempotent(fingerprint)
        if resumed is not None:
            return self._accepted_payload(resumed), 202

        conflict = self._current_active(user_id)
        if conflict is not None:
            return self._conflict_response(*conflict)

        if self._store.queue_depth() >= BaseConfig.TESTCASE_EXPORT_JOB_MAX_QUEUE:
            return error_response('导出任务队列已满，请稍后重试', http_code=429)

        job = self._new_job(spec, user_id, is_admin, fingerprint)
        task_id = job['task_id']
        ttl = BaseConfig.TESTCASE_EXPORT_JOB_TTL_SECONDS

        # 先用 SET NX 抢该用户的在办位，再落作业：并发提交时后到者直接 429，
        # 不会出现「作业已写入但没抢到位、需要回滚删除」的窗口
        if not self._store.claim_user(user_id, task_id, ttl):
            # 几乎同时的同参双提交：前者可能刚抢到在办位、幂等键也刚写好，
            # 复查一次再决定 429，避免同参连点拿到「已有任务在进行」
            resumed = self._resume_idempotent(fingerprint)
            if resumed is not None:
                return self._accepted_payload(resumed), 202
            conflict = self._current_active(user_id)
            if conflict is not None:
                return self._conflict_response(*conflict)
            return error_response('已有导出任务在进行', http_code=429)

        self._store.save(task_id, job, ttl)
        self._store.set_idem(fingerprint, task_id, ttl)
        self._store.enqueue(task_id)
        self._submit_worker(task_id)
        logger.info("导出作业已受理 task_id=%s total=%s user=%s",
                    task_id, job['total'], user_id)
        return self._accepted_payload(job), 202

    @staticmethod
    def _fingerprint(spec: Dict, user_id) -> str:
        """幂等指纹：显式 key 优先，否则按用户 + 请求内容。"""
        if spec.get('idempotency_key'):
            raw = f"{user_id}|k|{spec['idempotency_key']}"
        else:
            ids = sorted(str(i) for i in spec.get('ids') or [])
            raw = (f"{user_id}|h|{','.join(ids)}|{spec.get('format')}"
                   f"|{spec.get('include_reference_params')}"
                   f"|{spec.get('include_audios')}")
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def _resume_idempotent(self, fingerprint: str) -> Optional[dict]:
        task_id = self._store.get_idem(fingerprint)
        if not task_id:
            return None
        job = self._store.load(task_id)
        if job and _status_value(job.get('status')) in _IDEMPOTENT_REUSABLE_STATUSES:
            return job
        # 原任务 failed / expired（或记录已过期）：删键新建
        self._store.delete_idem(fingerprint)
        return None

    def _current_active(self, user_id) -> Optional[Tuple[str, str]]:
        task_id = self._store.get_user_active(user_id)
        if not task_id:
            return None
        job = self._store.load(task_id)
        status = _status_value(job.get('status')) if job else None
        if status in _ACTIVE_STATUSES:
            return task_id, status
        # 陈旧键（终态没清干净）：释放后按空闲处理
        self._store.release_user(user_id)
        return None

    @staticmethod
    def _conflict_response(task_id: str, status: str) -> Tuple[dict, int]:
        payload, http_code = error_response('已有导出任务在进行', http_code=429)
        payload['data'] = {'task_id': task_id, 'status': status}
        return payload, http_code

    @staticmethod
    def _new_job(spec, user_id, is_admin, fingerprint: str) -> dict:
        now = now_cst()
        created_ts = time.time()
        ttl = BaseConfig.TESTCASE_EXPORT_JOB_TTL_SECONDS
        total = len(spec.ids)
        return {
            'task_id': str(uuid.uuid4()),
            'status': ExportJobStatus.QUEUED.value,
            'phase': None,
            'total': total,
            'progress': {'total': total, 'processed': 0,
                         'exported': 0, 'missing': []},
            'request': spec.to_dict(),
            'result': None,
            'error': None,
            'created_by_user_id': user_id,
            'identity': [user_id, bool(is_admin)],
            'created_at': now.isoformat(),
            'created_ts': created_ts,
            'expires_at':
                (now + _seconds_to_delta(ttl)).isoformat(),
            'started_at': None,
            'finished_at': None,
            'artifact_expires_ts': None,
            'idem_fingerprint': fingerprint,
        }

    @staticmethod
    def _accepted_payload(job: dict) -> dict:
        return {
            'task_id': job.get('task_id'),
            'status': _status_value(job.get('status')),
            'total': job.get('total', 0),
            'created_at': job.get('created_at'),
            'expires_at': job.get('expires_at'),
            'poll_after_ms': POLL_AFTER_MS,
        }

    # ------------------------------------------------------------------
    # 状态查询 / 下载
    # ------------------------------------------------------------------
    def get_status(self, task_id: str, identity) -> Tuple[dict, int]:
        job = self._load_for_owner(task_id, identity)
        if job is None:
            # 不存在 / TTL 已过 / 非创建人非 admin：统一 404，防枚举
            return error_response('导出任务不存在', http_code=404)

        status = _status_value(job.get('status'))
        result = None
        if status == ExportJobStatus.DONE.value:
            result = dict(job.get('result') or {})
            url = self._download_url(result.get('path'))
            if url:
                result['download_url'] = url
            else:
                # 本地降级时预签名不可用 → 字段省略，前端走下载端点
                result.pop('download_url', None)

        return {
            'task_id': job.get('task_id'),
            'status': status,
            # phase 仅 running 非空
            'phase': _status_value(job.get('phase'))
                     if status == ExportJobStatus.RUNNING.value else None,
            'progress': job.get('progress') or {
                'total': job.get('total', 0), 'processed': 0,
                'exported': 0, 'missing': []},
            'result': result,
            # error 仅 failed 非空
            'error': job.get('error')
                     if status == ExportJobStatus.FAILED.value else None,
            'created_by_user_id': job.get('created_by_user_id'),
            'created_at': job.get('created_at'),
            'started_at': job.get('started_at'),
            'finished_at': job.get('finished_at'),
        }, 200

    def get_download(self, task_id: str, identity):
        """返回 (下载信息, None) 或 (None, error_response)。"""
        job = self._load_for_owner(task_id, identity)
        if job is None:
            return None, error_response('导出任务不存在', http_code=404)

        status = _status_value(job.get('status'))
        if status == ExportJobStatus.EXPIRED.value:
            return None, error_response('导出文件已过期，请重新导出', http_code=410)
        if status != ExportJobStatus.DONE.value:
            return None, error_response('导出未完成', http_code=409)

        result = job.get('result') or {}
        path = result.get('path')
        if not path:
            return None, error_response('导出文件已过期，请重新导出', http_code=410)

        # 取流下沉在应用层：路由只做 StreamingResponse 包装，不直触 Infrastructure
        try:
            stream = self._storage.load_stream(path)
        except Exception:
            logger.warning("读取导出产物失败 path=%s", path, exc_info=True)
            return None, error_response('导出文件已过期，请重新导出', http_code=410)

        svc = _export_service()
        return {
            'stream': stream,
            'filename': result.get('filename') or 'testcases_export',
            'media_type': svc.EXPORT_MEDIA_TYPES.get(
                result.get('format'), 'application/octet-stream'),
        }, None

    def _load_for_owner(self, task_id: str, identity) -> Optional[dict]:
        job = self._store.load(task_id)
        if not job:
            return None
        user_id, is_admin = identity if identity else (None, False)
        owner = job.get('created_by_user_id')
        if not is_admin and owner is not None and owner != user_id:
            return None
        return job

    def _download_url(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        try:
            return self._storage.get_url(
                path, expires=BaseConfig.TESTCASE_EXPORT_DOWNLOAD_URL_TTL_SECONDS)
        except Exception:
            logger.warning("生成导出下载链接失败 path=%s", path, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------
    @property
    def executor(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=BaseConfig.TESTCASE_EXPORT_MAX_WORKERS,
                    thread_name_prefix='testcase-export')
            return self._executor

    def _submit_worker(self, task_id: str) -> None:
        self.executor.submit(self._run_job, task_id)

    def _run_job(self, task_id: str) -> None:
        """工作线程入口：整段兜底。

        线程池会静默吞异常：`load` / `cas_status` 这类 Redis 异常若漏在最外层
        try 之外，任务会停在 `queued`（且已从 pending 出队），排队深度不回落、
        用户一路轮询到 TTL。所以这里全包，任何未捕获异常都落到 `failed`。
        """
        try:
            self._run_job_inner(task_id)
        except Exception:
            logger.exception("导出作业执行异常 task_id=%s", task_id)
            self._abort_job(task_id)

    def _run_job_inner(self, task_id: str) -> None:
        """出队 → CAS 置 running → 带身份执行（异常由 `_run_job` 兜底）。"""
        try:
            self._store.dequeue(task_id)
        except Exception:
            logger.warning("导出作业出队失败 task_id=%s", task_id, exc_info=True)

        job = self._store.load(task_id)
        if not job:
            logger.info("导出作业 %s 已不存在（TTL 过期或被清理），跳过", task_id)
            return

        started_at = now_cst().isoformat()
        if not self._store.cas_status(
                task_id, ExportJobStatus.QUEUED.value,
                {'status': ExportJobStatus.RUNNING.value,
                 'phase': ExportJobPhase.FETCHING.value,
                 'started_at': started_at},
                self._remaining_ttl(job)):
            logger.info("导出作业 %s 状态已非 queued，跳过执行", task_id)
            return

        job.update({'status': ExportJobStatus.RUNNING.value,
                    'phase': ExportJobPhase.FETCHING.value,
                    'started_at': started_at})

        identity = tuple(job.get('identity') or (None, False))
        run_with_identity(identity, self._execute_job, job)

    def _abort_job(self, task_id: str) -> None:
        """未捕获异常兜底：置 failed、释放在办位、重试一次出队。

        作业记录都读不到时（Redis 不可用）只能记日志：在办位键带任务 TTL，
        且 `_current_active` 遇到记录缺失/终态会自愈释放。
        """
        try:
            self._store.dequeue(task_id)
        except Exception:
            logger.warning("兜底出队失败 task_id=%s", task_id, exc_info=True)

        try:
            job = self._store.load(task_id)
        except Exception:
            logger.warning("兜底读取导出作业失败 task_id=%s", task_id, exc_info=True)
            return
        if not job:
            return
        self._fail(job, ExportJobErrorCode.INTERNAL_ERROR, '导出任务异常终止')

    def _execute_job(self, job: dict) -> None:
        svc = _export_service()
        task_id = job['task_id']
        spec = svc.ExportSpec(**job['request'])
        state = {
            'phase': ExportJobPhase.FETCHING.value,
            'last_write': 0.0,
            'last_processed': 0,
            'progress': job.get('progress') or {
                'total': job.get('total', 0), 'processed': 0,
                'exported': 0, 'missing': []},
        }

        def on_progress(progress) -> None:
            snapshot = {
                'total': progress.total,
                'processed': progress.processed,
                'exported': progress.exported,
                'missing': list(progress.missing),
            }
            state['progress'] = snapshot
            now = time.monotonic()
            phase_changed = progress.phase != state['phase']
            due = (progress.processed - state['last_processed']
                   >= PROGRESS_WRITE_EVERY) or (
                       now - state['last_write']
                       >= PROGRESS_WRITE_INTERVAL_SECONDS)
            if not phase_changed and not due:
                return
            state['phase'] = progress.phase
            state['last_processed'] = progress.processed
            state['last_write'] = now
            self._write(job, {'phase': progress.phase, 'progress': snapshot})

        try:
            artifact = svc.TestCaseExportService.execute_export(
                spec, on_progress=on_progress)
        except svc.ExportExecutionError as e:
            logger.warning("导出作业失败 task_id=%s code=%s message=%s",
                           task_id, e.code, e.message)
            self._fail(job, e.code, e.message)
            return

        path = None
        try:
            self._write(job, {
                'phase': ExportJobPhase.UPLOADING.value,
                'progress': state['progress'],
            })
            path = self._storage.save_file(
                artifact.local_path, ARTIFACT_CATEGORY,
                f'{task_id}/{artifact.filename}')
        except Exception:
            logger.exception("导出产物上传存储失败 task_id=%s", task_id)
            self._fail(job, ExportJobErrorCode.STORAGE_FAILED,
                       '导出文件保存失败，请稍后重试')
            return
        finally:
            if artifact.temp_dir:
                shutil.rmtree(artifact.temp_dir, ignore_errors=True)

        # 终态带上最终进度快照（processed/exported 单调不减）
        job['progress'] = state['progress']
        self._complete(job, artifact, path)

    def _complete(self, job: dict, artifact, path: str) -> None:
        finished_at = now_cst()
        fields = {
            'status': ExportJobStatus.DONE.value,
            'phase': None,
            'finished_at': finished_at.isoformat(),
            'result': {
                'format': artifact.format,
                'filename': artifact.filename,
                'size': artifact.size,
                'path': path,
            },
            'progress': job.get('progress'),
            'artifact_expires_ts':
                time.time() + BaseConfig.TESTCASE_EXPORT_ARTIFACT_TTL_SECONDS,
        }
        # 进度快照由调用方写入；这里只保证终态带最终计数
        self._safe_save(job, fields)
        self._safe_release(job)
        logger.info("导出作业完成 task_id=%s size=%s", job['task_id'],
                    artifact.size)

    def _fail(self, job: dict, code, message: str) -> None:
        fields = {
            'status': ExportJobStatus.FAILED.value,
            'phase': None,
            'finished_at': now_cst().isoformat(),
            'error': {'code': str(code), 'message': message},
        }
        self._safe_save(job, fields)
        self._safe_release(job)
        fingerprint = job.get('idem_fingerprint')
        if fingerprint:
            try:
                self._store.delete_idem(fingerprint)
            except Exception:
                logger.warning("删除导出幂等键失败 task_id=%s",
                               job.get('task_id'), exc_info=True)

    def _write(self, job: dict, fields: dict) -> None:
        self._store.save(job['task_id'], fields, self._remaining_ttl(job))

    def _safe_save(self, job: dict, fields: dict) -> None:
        try:
            self._write(job, fields)
        except Exception:
            logger.exception("写导出作业状态失败 task_id=%s", job.get('task_id'))

    def _safe_release(self, job: dict) -> None:
        try:
            self._store.release_user(job.get('created_by_user_id'))
        except Exception:
            logger.warning("释放在办位失败 task_id=%s",
                           job.get('task_id'), exc_info=True)

    @staticmethod
    def _remaining_ttl(job: dict) -> int:
        created_ts = job.get('created_ts') or time.time()
        remaining = int(created_ts + BaseConfig.TESTCASE_EXPORT_JOB_TTL_SECONDS
                        - time.time())
        return max(remaining, 1)

    # ------------------------------------------------------------------
    # 维护：重启接管 + 过期清理
    # ------------------------------------------------------------------
    def start_maintenance(self) -> None:
        """启动时接管遗留作业，并起清理线程（网关 lifespan 调用）。"""
        self._stop.clear()
        self.takeover_on_startup()
        thread = threading.Thread(
            target=self._cleanup_loop, daemon=True,
            name='testcase-export-cleanup')
        self._cleanup_thread = thread
        thread.start()

    def takeover_on_startup(self) -> None:
        """重启接管：running → failed(GATEWAY_RESTARTED)，queued → 重新入池。

        不把 running 当 queued 重放：导出是可重试的用户动作，重放会二次拉满 gRPC。
        """
        try:
            task_ids = self._store.scan_job_ids()
        except Exception:
            logger.warning("扫描遗留导出作业失败（Redis 不可用？）", exc_info=True)
            return

        for task_id in task_ids:
            try:
                job = self._store.load(task_id)
            except Exception:
                logger.warning("读取遗留导出作业失败 task_id=%s", task_id,
                               exc_info=True)
                continue
            if not job:
                continue
            status = _status_value(job.get('status'))
            if status == ExportJobStatus.RUNNING.value:
                self._fail(job, ExportJobErrorCode.GATEWAY_RESTARTED,
                           '网关重启，导出任务已中断，请用相同参数重新提交')
            elif status == ExportJobStatus.QUEUED.value:
                logger.info("接管遗留排队导出作业 task_id=%s", task_id)
                self._submit_worker(task_id)

    def _cleanup_loop(self) -> None:
        while not self._stop.wait(
                BaseConfig.TESTCASE_EXPORT_CLEANUP_INTERVAL_SECONDS):
            try:
                self.cleanup_once()
            except Exception:
                logger.warning("导出作业清理轮次失败", exc_info=True)

    def cleanup_once(self) -> None:
        """一轮清理：产物到期置 expired 并删对象，作业 TTL 到期删 HASH。"""
        now = time.time()
        try:
            task_ids = self._store.scan_job_ids()
        except Exception:
            logger.warning("扫描导出作业失败", exc_info=True)
            return

        for task_id in task_ids:
            try:
                job = self._store.load(task_id)
            except Exception:
                logger.warning("读取导出作业失败 task_id=%s", task_id,
                               exc_info=True)
                continue
            if not job:
                # 作业已过期删除，修剪残留的排队成员
                self._safe_dequeue(task_id)
                continue

            status = _status_value(job.get('status'))
            artifact_deadline = job.get('artifact_expires_ts')
            if (status == ExportJobStatus.DONE.value and artifact_deadline
                    and now >= artifact_deadline):
                self._expire(job)
                continue

            created_ts = job.get('created_ts') or now
            if now >= created_ts + BaseConfig.TESTCASE_EXPORT_JOB_TTL_SECONDS:
                try:
                    self._store.delete(task_id)
                    self._safe_dequeue(task_id)
                except Exception:
                    logger.warning("删除过期导出作业失败 task_id=%s", task_id,
                                   exc_info=True)

    def _expire(self, job: dict) -> None:
        """产物到期：删存储对象、置 expired、删幂等键。"""
        path = (job.get('result') or {}).get('path')
        if path:
            try:
                self._storage.delete(path)
            except Exception:
                logger.warning("删除过期导出产物失败 path=%s", path,
                               exc_info=True)
        try:
            self._write(job, {'status': ExportJobStatus.EXPIRED.value,
                              'phase': None})
        except Exception:
            logger.warning("置导出作业 expired 失败 task_id=%s",
                           job.get('task_id'), exc_info=True)
        fingerprint = job.get('idem_fingerprint')
        if fingerprint:
            try:
                self._store.delete_idem(fingerprint)
            except Exception:
                logger.warning("删除导出幂等键失败 task_id=%s",
                               job.get('task_id'), exc_info=True)
        self._safe_dequeue(job.get('task_id'))

    def _safe_dequeue(self, task_id: Optional[str]) -> None:
        if not task_id:
            return
        try:
            self._store.dequeue(task_id)
        except Exception:
            logger.warning("导出作业出队失败 task_id=%s", task_id, exc_info=True)

    def shutdown(self) -> None:
        """停止清理线程与线程池（进程退出 / 测试收尾）。"""
        self._stop.set()
        with self._lock:
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)


def _seconds_to_delta(seconds: int):
    from datetime import timedelta
    return timedelta(seconds=int(seconds))


_manager: Optional[TestCaseExportJobManager] = None
_manager_lock = threading.Lock()


def get_export_job_manager() -> TestCaseExportJobManager:
    """进程内单例（路由与 lifespan 共用同一线程池与存储）。"""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = TestCaseExportJobManager()
    return _manager
