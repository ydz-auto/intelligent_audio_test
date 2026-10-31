import os
import time
import json
import logging
import requests
import traceback
import threading
from shared.infrastructure.storage import storage
from shared.models.common_enums import RedisKeyPrefix, EvalTaskStatus, EvalErrorKind
from evaluation_service.infrastructure.evaluation_mixin import EvaluationLoggerMixin
from shared.utils.config_manager import config_manager

logger = logging.getLogger(__name__)


class EvalTaskRegistry:
    """在途评估任务注册表（V9.7.10 eval_callback_registry 的本服务等价物）

    V9.7.31 评估链为进程内同步消费（create_task → Redis 回调/HTTP 轮询 → 写结果），
    无独立回调端点；本注册表承担等价职责（INT-174）：
    - 登记 create_task 成功的在途评估任务（eval_task_id → task_id/endpoint_url），
      结果消费完毕即注销；
    - pop_by_task(task_id)：重新评估提交前按应用任务 ID 摘除全部在途条目并标记
      取消 —— 被摘除的旧评估任务，其结果到达后被消费方幂等忽略，不污染新评估
      结果（方案A），并携带 endpoint_url 供调用方通知子服务真正取消（方案B）。

    INT-308 新增 case 级取消：
    - register 增加 test_case_id 登记；
    - cancel_by_case(task_id, test_case_id)：执行中删除用例/任务停止时按
      (task_id, test_case_id) 摘除在途评估任务并标记 case 级取消；
    - is_case_cancelled：worker 消费与结果落库前核销——已取消用例的评估
      任务丢弃不执行、结果不落库（防"已删用例出评估结果"的幽灵数据）。
    """

    _lock = threading.Lock()
    _entries = {}      # eval_task_id -> {'task_id': int, 'endpoint_url': str, 'test_case_id': str}
    _cancelled = {}    # 已被 pop_by_task / cancel_by_case 摘除的 eval_task_id（有序，FIFO 淘汰）
    _CANCELLED_CAP = 4096
    _cancelled_cases = {}  # 'task_id:test_case_id' -> reason（case 级取消标记，有序，FIFO 淘汰）
    _CANCELLED_CASES_CAP = 4096
    # case 取消标记 Redis TTL：覆盖 Redis 持久化队列的消费周期（远长于最长评估
    # 等待上限 evaluation_service.eval_max_wait_time，缺省 72000s = 20h；重启+队列
    # 重放场景后自然过期，不留永久垃圾）
    _CASE_CANCELLED_TTL = 86400

    @staticmethod
    def _norm_task_id(task_id):
        try:
            return int(task_id)
        except (TypeError, ValueError):
            return task_id

    @classmethod
    def register(cls, eval_task_id, task_id, endpoint_url, test_case_id=None, dim_key=None):
        """登记在途评估任务（同 eval_task_id 重复登记幂等覆盖）

        dim_key：本次提交覆盖的维度组标识（INT-2250 重投判重用）——同一用例的不同
        维度组会并发提交，判重必须带上维度组，不能只按 (task_id, test_case_id)。
        """
        with cls._lock:
            cls._entries[eval_task_id] = {
                'task_id': cls._norm_task_id(task_id),
                'endpoint_url': endpoint_url,
                'test_case_id': str(test_case_id) if test_case_id else None,
                'dim_key': dim_key,
            }

    @classmethod
    def has_inflight(cls, task_id, test_case_id, endpoint_url=None, dim_key=None):
        """该 (task_id, test_case_id, 维度组) 是否已在某端点在途（INT-2250 重投判重）

        换端点重投同一评估前调用：同一维度组已在该端点有在途评估时不重复提交，
        避免重复计分/重复占用端点并发。endpoint_url / dim_key 为 None 时不做该项限定。
        """
        task_id = cls._norm_task_id(task_id)
        case_id = str(test_case_id) if test_case_id else None
        if case_id is None:
            return False
        with cls._lock:
            for ctx in cls._entries.values():
                if ctx.get('task_id') != task_id or ctx.get('test_case_id') != case_id:
                    continue
                if endpoint_url is not None and ctx.get('endpoint_url') != endpoint_url:
                    continue
                if dim_key is not None and ctx.get('dim_key') != dim_key:
                    continue
                return True
            return False

    @classmethod
    def unregister(cls, eval_task_id):
        """结果消费完毕后注销（已被 pop_by_task / cancel_by_case 摘除的为 no-op）"""
        with cls._lock:
            cls._entries.pop(eval_task_id, None)

    @classmethod
    def _pop_entries_locked(cls, predicate):
        """按谓词摘除在途条目并标记取消（须持锁调用），返回 [(eval_task_id, endpoint_url), ...]"""
        removed = []
        for eval_task_id, ctx in list(cls._entries.items()):
            if predicate(ctx):
                removed.append((eval_task_id, ctx.get('endpoint_url')))
                cls._entries.pop(eval_task_id, None)
                cls._cancelled[eval_task_id] = True
        while len(cls._cancelled) > cls._CANCELLED_CAP:
            cls._cancelled.pop(next(iter(cls._cancelled)))
        return removed

    @classmethod
    def pop_by_task(cls, task_id):
        """按应用任务 ID 摘除并返回全部在途评估任务，返回 [(eval_task_id, endpoint_url), ...]

        摘除即标记取消：旧评估任务的结果到达时被消费方幂等忽略（方案A）。
        """
        task_id = cls._norm_task_id(task_id)
        with cls._lock:
            return cls._pop_entries_locked(lambda ctx: ctx.get('task_id') == task_id)

    @classmethod
    def cancel_by_case(cls, task_id, test_case_id, reason=''):
        """按 (task_id, test_case_id) 摘除在途评估任务并标记 case 级取消（INT-308）。

        返回 [(eval_task_id, endpoint_url), ...] 供调用方通知子服务真正取消（方案B）；
        case 级取消标记供 worker 消费/结果落库前核销（丢弃不执行、不落库）。
        幂等：重复取消返回空列表，标记不覆盖既有 reason。

        取消标记同步落 Redis（eval:case_cancelled:{task_id}:{case_id} + TTL，
        INT-308 审计#2）：eval_service 重启后已入 Redis 持久化队列的已取消
        评估任务仍会被核销（is_case_cancelled 先查内存后查 Redis），
        不与"Redis 队列为跨重启持久化而设计"的语义矛盾。Redis 不可用时
        降级仅内存标记（与队列降级内存模式的语义边界一致）。
        """
        task_id = cls._norm_task_id(task_id)
        case_key = f'{task_id}:{test_case_id}'
        with cls._lock:
            removed = cls._pop_entries_locked(
                lambda ctx: ctx.get('task_id') == task_id
                and str(ctx.get('test_case_id') or '') == str(test_case_id))
            cls._cancelled_cases.setdefault(case_key, reason or 'case_cancelled')
            while len(cls._cancelled_cases) > cls._CANCELLED_CASES_CAP:
                cls._cancelled_cases.pop(next(iter(cls._cancelled_cases)))
        cls._persist_case_cancelled(task_id, test_case_id)
        return removed

    @classmethod
    def _persist_case_cancelled(cls, task_id, test_case_id):
        """case 取消标记写 Redis（best effort，失败降级内存标记仍生效）"""
        try:
            from shared.models.common_enums import RedisKeyPrefix
            from shared.utils import distributed_coordinator as dc
            key = (f'{RedisKeyPrefix.EVAL_CASE_CANCELLED.value}:'
                   f'{task_id}:{test_case_id}')
            dc.set_flag(key, value=1, ttl=cls._CASE_CANCELLED_TTL)
        except Exception as e:
            logger.warning("case 取消标记写 Redis 失败（降级内存标记）: task_id=%s, case_id=%s: %s",
                           task_id, test_case_id, e)

    @classmethod
    def _check_redis_case_cancelled(cls, task_id, test_case_id):
        """读 Redis case 取消标记（Redis 不可用时返回 False，由内存标记兜底）"""
        try:
            from shared.models.common_enums import RedisKeyPrefix
            from shared.utils import distributed_coordinator as dc
            key = (f'{RedisKeyPrefix.EVAL_CASE_CANCELLED.value}:'
                   f'{task_id}:{test_case_id}')
            return dc.is_flag_set(key)
        except Exception:
            return False

    @classmethod
    def is_case_cancelled(cls, task_id, test_case_id):
        """该 (task_id, test_case_id) 的评估是否已被取消（幂等读取，不消费标记）

        先查进程内存标记（本进程取消），未命中再查 Redis（其他实例取消 /
        eval_service 重启后），双通道覆盖多实例与重启场景（审计#2）。
        """
        task_id = cls._norm_task_id(task_id)
        with cls._lock:
            if f'{task_id}:{test_case_id}' in cls._cancelled_cases:
                return True
        return cls._check_redis_case_cancelled(task_id, test_case_id)

    @classmethod
    def is_cancelled(cls, eval_task_id):
        """该评估任务是否已被摘除取消（幂等读取，不消费标记）"""
        with cls._lock:
            return eval_task_id in cls._cancelled


eval_task_registry = EvalTaskRegistry()


class ApiRequestHandler(EvaluationLoggerMixin):
    """
    负责发起HTTP请求、管理异步任务流程（创建、轮询、获取结果）
    """

    @staticmethod
    def _connection_error(message):
        """构造连接级错误响应（INT-107：标注 __error_kind__，供降级路径识别端点不可达）"""
        return {'__error__': message, '__error_kind__': EvalErrorKind.CONNECTION.value}

    @staticmethod
    def _timeout_error(message):
        """构造端点超时错误响应（INT-2250：连接已建立但无响应，结果未知，不换端点）"""
        return {'__error__': message, '__error_kind__': EvalErrorKind.TIMEOUT.value}

    @staticmethod
    def _classify_request_exception(exc):
        """把请求异常归入评估错误类别（INT-2250）

        - ConnectTimeout / ConnectionError：连接级失败（端点不可达、DNS、连接被拒）→ connection
        - 其余 Timeout（ReadTimeout / Timeout）：连接已建立但无响应，评估结果未知 → timeout
        - 其它异常（序列化、解析等本地错误）：不分类，按未分类错误原样上报

        注意判定顺序：requests 的 ConnectTimeout 同时继承 ConnectionError 与 Timeout，
        必须先判连接级，否则会被误归为「结果未知」而不触发兜底端点。
        """
        if isinstance(exc, requests.exceptions.ConnectTimeout):
            return EvalErrorKind.CONNECTION.value
        if isinstance(exc, requests.exceptions.ConnectionError):
            return EvalErrorKind.CONNECTION.value
        if isinstance(exc, requests.exceptions.Timeout):
            return EvalErrorKind.TIMEOUT.value
        return None

    def _error_response_for_exception(self, exc, error_message):
        """按异常类别构造响应体（INT-2250）：连接级/超时带 __error_kind__，其余只带 __error__"""
        kind = self._classify_request_exception(exc)
        if kind == EvalErrorKind.CONNECTION.value:
            return self._connection_error(error_message)
        if kind == EvalErrorKind.TIMEOUT.value:
            return self._timeout_error(error_message)
        return {'__error__': error_message}

    def make_api_request(self, url, method, headers, payload, timeout=10):
        """
        发起API请求，支持GET和POST方法
        """
        resp_data = None

        try:
            # 创建请求头副本，避免修改原始数据
            request_headers = headers.copy() if headers else {}

            if method == 'GET':
                resp = requests.get(url, params=payload, headers=request_headers, timeout=timeout)
            else:
                # 确保POST请求使用正确的Content-Type
                if 'Content-Type' not in request_headers:
                    request_headers['Content-Type'] = 'application/json'
                # 确保POST请求总是有有效的payload，避免JSON解析错误
                if payload is None:
                    payload = {}
                resp = requests.post(url, json=payload, headers=request_headers, timeout=timeout)

            # 尝试解析JSON响应，无论状态码是什么
            try:
                resp_data = resp.json()
            except json.JSONDecodeError:
                # 非JSON响应，直接返回响应文本
                resp_data = resp.text

            if resp.status_code != 200:
                # 记录错误信息，但仍然返回响应数据，以便后续处理
                error_msg = f"API 返回错误: {resp.status_code}，请求URL: {url}，请求方法: {method}，请求头: {request_headers}，请求体: {payload}，响应内容: {resp.text}"
                self._log(
                    level='ERROR',
                    category='execution',
                    content=error_msg
                )
                # 将错误信息添加到响应数据中，方便后续处理
                if isinstance(resp_data, dict):
                    resp_data['__error__'] = error_msg
                else:
                    resp_data = {'__error__': error_msg, '__raw_response__': resp_data}
        except Exception as e:
            # 网络错误等异常情况（INT-2250：按连接级/超时分类，错误文案带方法与 URL 便于定位）
            error_msg = f"{method} {url} 请求异常: {str(e)}"
            self._log(
                level='ERROR',
                category='execution',
                content=f"API请求异常: {error_msg}"
            )
            # 返回异常信息作为响应数据；连接级失败标注 __error_kind__（INT-107 降级路径）
            resp_data = self._error_response_for_exception(e, error_msg)

        return resp_data

    def create_task(self, url, payload, timeout=10, task_id=None):
        """
        创建WER/SER计算任务
        """
        headers = {'Content-Type': 'application/json'}
        create_task_url = f"{url}/api/create_task"
        if task_id:
            payload = {**payload, 'task_id': task_id}
        return self.make_api_request(create_task_url, 'POST', headers, payload, timeout)

    def _extract_files_from_payload(self, payload, audio_field_names=None):
        """
        从 payload 中提取文件（data URI 或文件路径），转为 multipart 上传字段。

        遍历顶层字段和 rounds 列表里的字段。对于 ``audio_field_names`` 集合中的
        字段（field_mapper 中 type='audio' 的字段），会尝试提取为文件上传。
        单轮时，rounds[0] 里的音频字段会被提到顶层上传，rounds 里删掉该字段。
        多轮时，每轮的音频字段提取为 ``rounds_{index}_{field_name}`` 上传，
        rounds JSON 里对应值替换为 ``__MULTIPART__:rounds_{index}_{field_name}`` 占位符。

        支持的文件值形式：
        - data URI（``data:audio/wav;base64,...``）
        - 绝对路径（本地存在）
        - 相对路径（基于 STATIC_BASE_PATH 配置目录解析，本地存在）

        结构化音频字段（如被播放音频 audios 列表 ``[{audio_path, spl, ...}, ...]``）：
        递归遍历 dict/list 内部，凡是可解析为文件的字符串值都提取上传，
        原值替换为 ``__MULTIPART__:<upload_key>`` 占位符（eval_server 侧递归还原为落盘路径）。

        Args:
            payload: 请求体字典
            audio_field_names: set/list，需要作为文件上传的字段名集合。
                               为 None 时默认使用 {'record_file'}。

        Returns:
            (form_fields, files) 元组
            - form_fields: 不含文件的标量字段（dict/list 转 JSON 字符串）
            - files: {field_name: (filename, bytes, content_type)} 字典
        """
        if audio_field_names is None:
            audio_field_names = {'record_file'}
        audio_field_names = set(audio_field_names)

        form_fields = {}
        files = {}

        for key, value in payload.items():
            if key == 'rounds' and isinstance(value, list):
                # 深拷贝，避免修改原始 payload
                rounds_copy = json.loads(json.dumps(value))
                if len(rounds_copy) == 1 and isinstance(rounds_copy[0], dict):
                    # 单轮：把字符串音频字段提到顶层上传，rounds 里删掉该字段
                    rd = rounds_copy[0]
                    for field_name in list(audio_field_names):
                        field_value = rd.get(field_name)
                        if isinstance(field_value, str) and field_value:
                            if self._is_oss_pass_through(field_value):
                                # 透传模式：oss:// 路径提到顶层 form_fields，
                                # 由 eval_server 本地从对象存储下载（镜像文件提取逻辑，但不做字节上传）
                                rd.pop(field_name, None)
                                form_fields[field_name] = field_value
                                continue
                            rd.pop(field_name, None)
                            self._extract_single_file(field_name, field_value, files,
                                                      form_fields_fallback=form_fields,
                                                      fallback_key=field_name, fallback_value=field_value)
                else:
                    # 多轮：每轮的音频字段提取为 rounds_{idx}_{field_name}
                    for idx, rd in enumerate(rounds_copy):
                        if not isinstance(rd, dict):
                            continue
                        for field_name in audio_field_names:
                            field_value = rd.get(field_name)
                            if isinstance(field_value, str) and field_value:
                                if self._is_oss_pass_through(field_value):
                                    # 透传模式：保持 oss:// 字符串在 rounds 中，eval_server 侧递归解析下载
                                    continue
                                upload_field_name = f'rounds_{idx}_{field_name}'
                                extracted = self._extract_single_file(upload_field_name, field_value, files)
                                if extracted:
                                    rd[field_name] = f'__MULTIPART__:{upload_field_name}'
                # 结构化字段（dict/list，如 played_audios、background_noise、interferers）：
                # 递归提取内部文件值，替换为 __MULTIPART__ 占位符
                # （不限 audio_field_names，覆盖 field_type=json 的结构化音频参数，
                #   包括噪声和干扰人音频）
                for idx, rd in enumerate(rounds_copy):
                    if not isinstance(rd, dict):
                        continue
                    for field_name in list(rd.keys()):
                        field_value = rd.get(field_name)
                        if isinstance(field_value, (dict, list)):
                            rd[field_name] = self._extract_nested_files(
                                field_value, f'rounds_{idx}_{field_name}', files
                            )
                form_fields[key] = json.dumps(rounds_copy)
            elif isinstance(value, str) and self._is_file_value(value):
                self._extract_single_file(key, value, files, form_fields_fallback=form_fields, fallback_key=key, fallback_value=value)
            elif key in audio_field_names and isinstance(value, (dict, list)):
                # 顶层结构化音频字段：递归提取内部文件值，替换为 __MULTIPART__ 占位符
                form_fields[key] = json.dumps(self._extract_nested_files(value, key, files))
            elif isinstance(value, (dict, list)):
                form_fields[key] = json.dumps(value)
            elif isinstance(value, bool):
                # multipart 上传会把 Python bool 序列化成 "True"/"False"（首字母大写），
                # eval_server 白名单只认小写 'true'/'false'，这里统一转小写
                form_fields[key] = 'true' if value else 'false'
            else:
                form_fields[key] = value

        return form_fields, files

    def _is_oss_pass_through(self, value):
        """判断值是否为 oss:// 透传路径。

        oss:// 前缀本身就是信号：透传模式下不会作为 multipart 文件提取，
        而是原样传给 eval_server，由其在本地从对象存储下载后计算，
        避免文件字节在主服务与评估服务之间流转。
        """
        return isinstance(value, str) and value.startswith('oss://')

    @staticmethod
    def _is_file_value(value):
        """判断字符串值是否可能是文件（data URI、本地路径或 OSS key）。"""
        if not isinstance(value, str) or not value:
            return False
        if value.startswith('data:') and ',' in value:
            return True
        if len(value) >= 4096:
            return False
        # 绝对路径（本地文件）
        if os.path.isabs(value):
            return os.path.exists(value)
        # oss:// 路径不作为文件提取，原样透传给 eval_server，
        # 由其在本地从对象存储下载（避免字节流转）
        if value.startswith('oss://'):
            return False
        # 存储路径（兼容裸 OSS key）
        try:
            path = value if value.startswith(('oss://', 'local://')) else storage.build_path('audios', value)
            return storage.exists(path)
        except Exception:
            return False

    @classmethod
    def _extract_single_file(cls, field_name, value, files, form_fields_fallback=None, fallback_key=None, fallback_value=None):
        """提取单个文件到 files 字典。成功返回 True，失败时回退到 form_fields。"""
        try:
            if isinstance(value, str) and value.startswith('data:') and ',' in value:
                header, data = value.split(',', 1)
                mime = header.split(':')[1].split(';')[0] if ':' in header else 'application/octet-stream'
                import base64
                file_bytes = base64.b64decode(data)

                ext_map = {
                    'audio/wav': '.wav', 'audio/x-wav': '.wav',
                    'audio/mpeg': '.mp3', 'audio/mp3': '.mp3',
                    'audio/flac': '.flac', 'audio/ogg': '.ogg',
                    'audio/mp4': '.m4a', 'audio/aac': '.aac',
                }
                ext = ext_map.get(mime, '.bin')
                filename = f"{field_name}{ext}"
                files[field_name] = (filename, file_bytes, mime)
                return True
            elif isinstance(value, str) and len(value) < 4096:
                # 绝对路径（本地文件）直接用；相对路径作为 OSS key 下载到临时文件
                if os.path.isabs(value) and os.path.exists(value):
                    resolved = value
                else:
                    resolved = cls._resolve_relative_path(value)
                if resolved and os.path.exists(resolved):
                    with open(resolved, 'rb') as f:
                        file_bytes = f.read()
                    filename = os.path.basename(resolved)
                    files[field_name] = (filename, file_bytes, 'application/octet-stream')
                    return True
        except Exception:
            logger.debug("提取文件字段 %s 失败", field_name, exc_info=True)
        # 回退
        if form_fields_fallback is not None and fallback_key is not None:
            form_fields_fallback[fallback_key] = fallback_value
        return False

    def _extract_nested_files(self, value, prefix, files):
        """递归提取嵌套结构（dict/list）中的文件值，替换为 __MULTIPART__ 占位符

        用于结构化音频字段（如被播放音频 audios 列表 [{audio_path, spl, ...}]）：
        遍历内部所有字符串值，凡是可解析为文件的（data URI / 本地路径 / 存储 key）
        都提取为 multipart 文件字段上传，原值替换为 ``__MULTIPART__:<upload_key>``。

        Args:
            value: dict/list/标量 嵌套结构
            prefix: 上传字段名前缀（如 rounds_0_played_audios）
            files: 已有的上传文件字典（避免重复 key）
        Returns:
            替换文件值后的同构结构
        """
        if isinstance(value, dict):
            return {
                k: self._extract_nested_files(v, f'{prefix}_{k}', files)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [
                self._extract_nested_files(item, f'{prefix}_{i}', files)
                for i, item in enumerate(value)
            ]
        if isinstance(value, str) and value and self._is_file_value(value):
            upload_key = prefix
            seq = 0
            while upload_key in files:
                seq += 1
                upload_key = f'{prefix}_{seq}'
            if self._extract_single_file(upload_key, value, files):
                return f'__MULTIPART__:{upload_key}'
        return value

    @staticmethod
    def _resolve_relative_path(value):
        """
        将相对路径（OSS key）解析为本地临时文件路径。

        音频文件存储在 OSS audios bucket，value 视为 OSS key，
        下载到临时文件后返回本地路径。失败返回 None。
        """
        # 本地文件直接返回
        norm = value.replace('\\', os.sep).replace('/', os.sep)
        if os.path.exists(norm):
            return os.path.abspath(norm)

        # 作为存储路径下载到临时文件
        try:
            path = value if value.startswith(('oss://', 'local://')) else storage.build_path('audios', value)
            return storage.load_file(path)
        except Exception:
            logger.debug("解析相对路径 %r 失败", value, exc_info=True)
            return None

    def create_task_upload(self, url, form_fields, files, timeout=30, task_id=None):
        """
        通过 multipart/form-data 创建评估任务（支持文件上传）
        """
        create_task_url = f"{url}/api/create_task_upload"

        if task_id:
            form_fields['task_id'] = task_id

        multipart_files = {}
        for field_name, (filename, file_bytes, content_type) in files.items():
            multipart_files[field_name] = (filename, file_bytes, content_type)

        try:
            resp = requests.post(create_task_url, data=form_fields, files=multipart_files, timeout=timeout)
            try:
                resp_data = resp.json()
            except json.JSONDecodeError:
                resp_data = resp.text

            if resp.status_code != 200:
                self._log(
                    level='ERROR',
                    category='execution',
                    content=f"上传API返回错误: {resp.status_code}, URL: {create_task_url}, 响应: {resp.text}"
                )
                if isinstance(resp_data, dict):
                    resp_data['__error__'] = f"HTTP {resp.status_code}"
                else:
                    resp_data = {'__error__': f"HTTP {resp.status_code}", '__raw_response__': resp_data}

            return resp_data
        except Exception as e:
            error_msg = f"POST {create_task_url} 请求异常: {str(e)}"
            self._log(
                level='ERROR',
                category='execution',
                content=f"上传API请求异常: {error_msg}"
            )
            return self._error_response_for_exception(e, error_msg)

    def get_task_status(self, url, eval_task_id, timeout=30):
        """
        查询评估任务状态
        """
        status_url = f"{url}/api/get_status/{eval_task_id}"
        return self.make_api_request(status_url, 'GET', {}, {}, timeout)

    def get_task_result(self, url, eval_task_id, timeout=30):
        """
        获取评估任务结果
        """
        result_url = f"{url}/api/get_final_result/{eval_task_id}"
        return self.make_api_request(result_url, 'GET', {}, {}, timeout)

    def _get_redis_client(self):
        """获取 Redis 客户端，不可用时返回 None"""
        try:
            from shared.utils.redis_pubsub import RedisPubSub
            client = RedisPubSub().redis_client
            client.ping()
            return client
        except Exception:
            return None

    def _wait_for_redis_callback(self, eval_task_id, max_wait_time, task_id=None, test_case_id=None, api_id=None):
        """通过 Redis Pub/Sub 回调消费评估结果

        eval_server 完成后会将结果推送到 eval:result:{eval_task_id} 频道。
        此方法阻塞等待该消息，超时返回 None 表示需要降级到 HTTP 轮询。

        Returns:
            dict 或 None: 收到结果则返回，超时返回 None
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return None

        callback_channel = f"{RedisKeyPrefix.EVAL_RESULT.value}:{eval_task_id}"
        self._log('info', f'尝试 Redis 回调消费: channel={callback_channel}, timeout={max_wait_time}秒',
                  task_id=task_id, test_case_id=test_case_id, api_id=api_id)

        pubsub = None
        try:
            pubsub = redis_client.pubsub()
            pubsub.subscribe(callback_channel)

            # 消费已有的订阅消息，带超时
            deadline = time.time() + max_wait_time
            while time.time() < deadline:
                # INT-308：等待期间检查 case 级取消标记（用例删除/任务停止）
                if task_id is not None and test_case_id and \
                        eval_task_registry.is_case_cancelled(task_id, str(test_case_id)):
                    self._log('info', f'评估任务已随用例删除/任务停止取消，停止回调等待: eval_task_id={eval_task_id}',
                              task_id=task_id, test_case_id=test_case_id, api_id=api_id)
                    return {'__cancelled__': True, '__error__': '评估任务已随用例删除/任务停止取消'}
                message = pubsub.get_message(timeout=1.0)
                if message and message.get('type') == 'message':
                    data = message.get('data')
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')
                    try:
                        result = json.loads(data)
                        self._log('info', f'Redis 回调收到结果: eval_task_id={eval_task_id}',
                                  task_id=task_id, test_case_id=test_case_id, api_id=api_id)
                        return result
                    except (json.JSONDecodeError, TypeError):
                        self._log('warning', f'Redis 回调消息解析失败: {data}',
                                  task_id=task_id, test_case_id=test_case_id, api_id=api_id)
                        return None
                time.sleep(0.1)

            # 超时，未收到回调
            self._log('info', f'Redis 回调消费超时，降级为 HTTP 轮询: eval_task_id={eval_task_id}',
                      task_id=task_id, test_case_id=test_case_id, api_id=api_id)
            return None
        except Exception as e:
            self._log('warning', f'Redis 回调消费异常，降级为 HTTP 轮询: {e}',
                      task_id=task_id, test_case_id=test_case_id, api_id=api_id)
            return None
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe()
                    pubsub.close()
                except Exception:
                    pass

    def wait_for_task_completion(self, url, eval_task_id, max_wait_time=None, poll_interval=None, test_case_id=None, api_id=None, task_id=None):
        """等待评估任务完成

        优先使用 Redis Pub/Sub 回调消费模式（Phase 3.2）：
        - 提交任务时 eval_server 完成后会推送结果到 eval:result:{eval_task_id} 频道
        - 如果 Redis 不可用或回调超时，降级为 HTTP 轮询

        Args:
            url: eval_server 地址
            eval_task_id: 评估任务ID
            max_wait_time: 最大等待时间（秒），None 时从 config_manager 读取
            poll_interval: 轮询间隔（秒），None 时从 config_manager 读取
            test_case_id: 用例ID
            api_id: API ID
            task_id: 应用任务ID
        """
        # 配置化：参数从 config_manager 读取
        effective_max_wait = max_wait_time or config_manager.get_value('evaluation_service', 'eval_max_wait_time', 600)
        effective_poll_interval = poll_interval or config_manager.get_value('evaluation_service', 'poll_interval', 5)
        redis_callback_timeout = config_manager.get_value('evaluation_service', 'redis_result_callback_timeout', 5)

        self._log('info', f'开始等待评估任务完成: eval_task_id={eval_task_id}, max_wait_time={effective_max_wait}秒',
                  task_id=task_id, test_case_id=test_case_id, api_id=api_id)

        # 1. 优先尝试 Redis 回调消费模式
        redis_result = self._wait_for_redis_callback(
            eval_task_id, redis_callback_timeout,
            task_id=task_id, test_case_id=test_case_id, api_id=api_id
        )
        if redis_result is not None:
            # Redis 回调收到结果
            if isinstance(redis_result, dict):
                if redis_result.get('status') == EvalTaskStatus.FAILED.value:
                    error_msg = redis_result.get('error_msg', 'Task failed')
                    self._log('error', f'评估任务失败(Redis回调): eval_task_id={eval_task_id}, error={error_msg}',
                              task_id=task_id, test_case_id=test_case_id, api_id=api_id)
                    return {'__error__': error_msg}
                # 成功结果直接返回
                return redis_result
            return redis_result

        # 2. Redis 不可用或回调超时，降级为 HTTP 轮询
        self._log('info', f'降级为 HTTP 轮询模式: eval_task_id={eval_task_id}, poll_interval={effective_poll_interval}秒',
                  task_id=task_id, test_case_id=test_case_id, api_id=api_id)

        start_time = time.time()
        poll_count = 0

        # INT-2250：轮询期失败分类与快速失败阈值（配置化，拒绝魔法数字）。
        # 端点中途挂掉时，原先只打 WARNING 一直轮询到 eval_max_wait_time（缺省 72000s=20h），
        # 端点消费线程被无结果任务长期占用、最终错误只剩「评估任务超时」。改为连续 N 次
        # 同类失败即快速失败，并把「端点不可达 / 端点超时 / 业务失败」类别落进 __error_kind__。
        max_conn_failures = int(config_manager.get_value(
            'evaluation_service', 'eval_poll_max_connection_failures', 3) or 3)
        max_timeout_failures = int(config_manager.get_value(
            'evaluation_service', 'eval_poll_max_timeout_failures', 3) or 3)
        max_business_failures = int(config_manager.get_value(
            'evaluation_service', 'eval_poll_max_business_failures', 6) or 6)
        conn_streak = 0       # 连续连接级失败（端点不可达）
        timeout_streak = 0    # 连续端点超时（结果未知）
        business_streak = 0   # 连续业务级失败（HTTP 错误/状态查询被拒）

        while time.time() - start_time < effective_max_wait:
            poll_count += 1

            # INT-174：该评估任务已被重新评估提交摘除（方案A）——立即退出等待，
            # 结果由消费方按取消隔离，不再继续轮询
            if eval_task_registry.is_cancelled(eval_task_id):
                self._log('info', f'评估任务已被重新评估取消，停止等待: eval_task_id={eval_task_id}',
                          task_id=task_id, test_case_id=test_case_id, api_id=api_id)
                return {'__cancelled__': True, '__error__': '评估任务已被重新评估取消'}

            status_response = self.get_task_status(url, eval_task_id)

            if isinstance(status_response, dict) and status_response.get('code') == 0:
                # 状态查询成功即清零连续失败计数（只看连续失败，容忍偶发抖动）
                conn_streak = timeout_streak = business_streak = 0
                data = status_response.get('data') or {}
                status = data.get('status', '')
                elapsed_time = int(time.time() - start_time)

                if status == EvalTaskStatus.COMPLETED.value:
                    self._log('info', f'评估任务完成: eval_task_id={eval_task_id}, 耗时={elapsed_time}秒',
                              task_id=task_id, test_case_id=test_case_id, api_id=api_id)
                    result_response = self.get_task_result(url, eval_task_id)
                    return result_response
                elif status == EvalTaskStatus.FAILED.value:
                    error_msg = data.get('error_msg', 'Task failed')
                    self._log('error', f'评估任务失败: eval_task_id={eval_task_id}, error={error_msg}',
                              task_id=task_id, test_case_id=test_case_id, api_id=api_id)
                    # 业务级失败（任务执行失败）：不带 __error_kind__，与既有兜底契约一致
                    # （不切换端点，避免重复计分）
                    return {'__error__': error_msg}
                elif status == 'canceled':
                    # INT-174：子服务 cancel_task（方案B）已生效，任务不会产生结果与回调
                    self._log('info', f'评估任务已被子服务取消: eval_task_id={eval_task_id}',
                              task_id=task_id, test_case_id=test_case_id, api_id=api_id)
                    return {'__cancelled__': True, '__error__': '评估任务已被取消'}
                else:
                    self._log('info', f'等待评估任务: eval_task_id={eval_task_id}, status={status}, 已等待={elapsed_time}秒, 第{poll_count}次查询',
                              task_id=task_id, test_case_id=test_case_id, api_id=api_id)
            else:
                # INT-2250：按错误类别累计连续失败；达到阈值立即收敛为可定位的失败原因
                kind = status_response.get('__error_kind__') if isinstance(status_response, dict) else None
                if isinstance(status_response, dict):
                    failure_text = str(status_response.get('__error__')
                                       or status_response.get('msg') or status_response)
                else:
                    failure_text = str(status_response)
                if kind == EvalErrorKind.CONNECTION.value:
                    conn_streak += 1
                    timeout_streak = business_streak = 0
                    streak, limit = conn_streak, max_conn_failures
                elif kind == EvalErrorKind.TIMEOUT.value:
                    timeout_streak += 1
                    conn_streak = business_streak = 0
                    streak, limit = timeout_streak, max_timeout_failures
                else:
                    business_streak += 1
                    conn_streak = timeout_streak = 0
                    streak, limit = business_streak, max_business_failures

                self._log('warning',
                          f'查询评估任务状态失败: eval_task_id={eval_task_id}, kind={kind or "unclassified"}, '
                          f'连续失败={streak}/{limit}, response={status_response}',
                          task_id=task_id, test_case_id=test_case_id, api_id=api_id)

                if streak >= limit:
                    elapsed_time = int(time.time() - start_time)
                    if kind == EvalErrorKind.CONNECTION.value:
                        fail_msg = (f'评估端点不可达: 端点 {url} 连续 {streak} 次查询状态失败'
                                    f'（eval_task_id={eval_task_id}, 已等待={elapsed_time}秒），'
                                    f'放弃等待: {failure_text}')
                        fail_kind = EvalErrorKind.CONNECTION.value
                    elif kind == EvalErrorKind.TIMEOUT.value:
                        fail_msg = (f'评估端点响应超时: 端点 {url} 连续 {streak} 次查询无响应'
                                    f'（eval_task_id={eval_task_id}, 已等待={elapsed_time}秒），'
                                    f'评估结果未知: {failure_text}')
                        fail_kind = EvalErrorKind.TIMEOUT.value
                    else:
                        fail_msg = (f'评估任务状态查询连续失败: 端点 {url} 连续 {streak} 次返回错误'
                                    f'（eval_task_id={eval_task_id}, 已等待={elapsed_time}秒）: {failure_text}')
                        fail_kind = EvalErrorKind.BUSINESS.value
                    self._log('error', fail_msg, task_id=task_id,
                              test_case_id=test_case_id, api_id=api_id)
                    return {'__error__': fail_msg, '__error_kind__': fail_kind}

            # INT-308 停止传播：轮询间隔 sleep 拆片，片间检查 case 级取消标记——
            # 用例删除/任务停止取消评估时 ≤1s 退出等待，不再睡满整个 poll_interval
            sleep_remaining = effective_poll_interval
            while sleep_remaining > 0:
                if isinstance(task_id, (int, str)) and test_case_id and \
                        eval_task_registry.is_case_cancelled(task_id, str(test_case_id)):
                    return {'__cancelled__': True, '__error__': '评估任务已随用例删除/任务停止取消'}
                slice_wait = min(1.0, sleep_remaining)
                time.sleep(slice_wait)
                sleep_remaining -= slice_wait

        # INT-2250：等待上限耗尽属「结果未知」——带 timeout 类别，提示端点/配置可定位项
        timeout_msg = (f"评估任务超时: eval_task_id={eval_task_id}, 端点 {url} 在 "
                       f"{effective_max_wait}秒 内未返回终态（结果未知，请检查该端点或 "
                       f"evaluation_service.eval_max_wait_time 配置）")
        self._log('error', timeout_msg, task_id=task_id, test_case_id=test_case_id, api_id=api_id)
        return {'__error__': timeout_msg, '__error_kind__': EvalErrorKind.TIMEOUT.value}
