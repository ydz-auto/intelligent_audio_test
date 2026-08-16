# -*- coding: utf-8 -*-
"""
评估维度服务 (WER/SER) API 控制器

该文件定义了评估维度服务的所有 API 端点，包括：
1. 任务创建与处理（本地/远程）
2. 任务状态查询
3. 任务结果获取
4. 任务删除
5. 端点配置管理
6. 并发状态查询
7. 动态并发限制调整
"""

import uuid
import json
import os
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, url_for
from werkzeug.utils import secure_filename
from ..models.task import TaskModel
from ..utils.responses import (
    success_response,        # 成功响应工具函数
    error_response,          # 错误响应工具函数
    CODE_VALIDATION_ERROR,   # 参数验证错误码
    CODE_BUSINESS_ERROR,     # 业务逻辑错误码
    CODE_SERVER_ERROR,       # 服务器内部错误码
    CODE_CONCURRENCY_EXCEEDED  # 并发超过限制错误码
)
from datetime import datetime
from ..config import config  # 配置信息
from ..services.wer_calculator import calculate_wer, calculate_ser, calculate_cpwer, calculate_tcpwer, calculate_stm_wer  # WER/SER 计算函数
from ..services.task_service import calculate_in_process  # 线程池计算包装函数
from ..utils.concurrency import ConcurrencyManager  # 并发管理器

logger = logging.getLogger('api')

# 创建 API Blueprint，所有 API 路由以 /api 开头
api_bp = Blueprint('api', __name__, url_prefix='/api')

class LocalConcurrencyManager:
    """
    本地并发管理器
    
    用于控制本地处理的任务并发数，确保不超过配置的最大并发限制
    """
    _current_concurrency = 0  # 当前并发数
    _lock = threading.Lock()  # 线程锁，确保并发安全
    _max_concurrency = config.LOCAL_MAX_CONCURRENCY  # 最大并发数，从配置中获取

    @classmethod
    def can_start(cls):
        """
        检查是否可以启动新任务
        
        Returns:
            bool: 如果当前并发数小于最大并发数，返回 True，否则返回 False
        """
        with cls._lock:
            return cls._current_concurrency < cls._max_concurrency

    @classmethod
    def increment(cls):
        """
        增加当前并发数
        """
        with cls._lock:
            cls._current_concurrency += 1

    @classmethod
    def decrement(cls):
        """
        减少当前并发数
        """
        with cls._lock:
            cls._current_concurrency = max(0, cls._current_concurrency - 1)

    @classmethod
    def get_current(cls):
        """获取当前并发数（线程安全）"""
        with cls._lock:
            return cls._current_concurrency

    @classmethod
    def get_stats(cls):
        """
        获取本地并发统计信息

        Returns:
            dict: 包含最大并发数、当前并发数和可用并发数的字典
        """
        with cls._lock:
            return {
                'max_concurrency': cls._max_concurrency,
                'current_concurrency': cls._current_concurrency,
                'available_concurrency': cls._max_concurrency - cls._current_concurrency
            }

# 文本文件扩展名（读取内容为字符串）
TEXT_FILE_EXTENSIONS = {'.txt', '.stm', '.rttm', '.json', '.csv', '.srt', '.vtt', '.xml', '.tsv'}

# 线程池（任务以 I/O 密集型为主：ASR HTTP 调用、LLM API 调用、文本比较）
# 使用 ThreadPoolExecutor 替代 ProcessPoolExecutor，避免子进程崩溃导致 BrokenProcessPool
_calc_pool = None
_pool_lock = threading.Lock()
_pool_logger = logging.getLogger('api')


def _get_calc_pool():
    """懒加载线程池"""
    global _calc_pool
    with _pool_lock:
        if _calc_pool is None:
            max_workers = config.LOCAL_MAX_CONCURRENCY
            _calc_pool = ThreadPoolExecutor(max_workers=max_workers)
            _pool_logger.info(f"线程池已创建，max_workers={max_workers}")
    return _calc_pool


def _validate_and_dispatch_task(task_type, task_params, endpoints, caller_task_id=None, eval_task_id=None):
    """
    验证任务参数并分发到本地或远程处理。
    被 create_task 和 create_task_upload 共用。
    caller_task_id 为调用方的任务 ID（可选）。
    eval_task_id 可由调用方预先生成（如 create_task_upload 需要先存文件）。
    """
    SUPPORTED_TASK_TYPES = ['wer', 'ser', 'der', 'cpwer', 'tcpwer', 'stm_wer', 'llm_judge', 'xiaoyi_metrics', 'interruption_metrics', 'takeover']
    if task_type not in SUPPORTED_TASK_TYPES:
        return error_response(f"Unsupported task type: {task_type}. Supported types: {SUPPORTED_TASK_TYPES}", code=CODE_BUSINESS_ERROR)

    if task_type in ['wer', 'ser']:
        if 'rounds' not in task_params:
            if not task_params.get('asr_ref') or not task_params.get('asr_hyp'):
                return error_response(f"Missing required fields for {task_type}: asr_ref, asr_hyp (or 'rounds' for multi-round mode)", code=CODE_VALIDATION_ERROR)
    elif task_type in ['cpwer', 'tcpwer', 'stm_wer']:
        if not task_params.get('ref_stm') or not task_params.get('hyp_stm'):
            return error_response(f"Missing required fields for {task_type}: ref_stm, hyp_stm", code=CODE_VALIDATION_ERROR)
    elif task_type == 'der':
        required_fields = ['rttm_ref', 'stm_ref', 'rttm_res', 'stm_res']
        missing = [f for f in required_fields if not task_params.get(f)]
        if missing:
            return error_response(f"Missing required fields for der: {', '.join(missing)}", code=CODE_VALIDATION_ERROR)
    elif task_type == 'llm_judge':
        # llm_judge：answer/correct_answer 在有 rounds 时从 rounds 取，否则从顶层取
        # model/prompt 有默认值，不是必填
        if not task_params.get('rounds'):
            required_fields = ['answer', 'correct_answer']
            missing = [f for f in required_fields if not task_params.get(f)]
            if missing:
                return error_response(f"Missing required fields for llm_judge: {', '.join(missing)}", code=CODE_VALIDATION_ERROR)
    # xiaoyi_metrics: record_file 可为空，无录音时跳过 ASR 相关指标
    elif task_type == 'interruption_metrics':
        if not task_params.get('user_asr') and not task_params.get('user_chunks'):
            return error_response("Missing required field for interruption_metrics: user_asr (用户提问/打断 ASR)", code=CODE_VALIDATION_ERROR)
        if not task_params.get('model_asr') and not task_params.get('model_chunks'):
            return error_response("Missing required field for interruption_metrics: model_asr (模型恢复 ASR)", code=CODE_VALIDATION_ERROR)

    if eval_task_id is None:
        eval_task_id = f"task_{uuid.uuid4().hex}"

    if endpoints:
        from ..services.remote_service import remote_service
        try:
            remote_task_id = remote_service.create_remote_task(
                task_type=task_type,
                task_params=task_params,
                endpoints=endpoints,
                caller_task_id=caller_task_id
            )
            base_url = request.host_url.rstrip('/')
            return success_response({
                "eval_task_id": remote_task_id,
                "task_id": caller_task_id,
                "status_url": f"{base_url}/api/get_status/{remote_task_id}",
                "final_result_url": f"{base_url}/api/get_final_result/{remote_task_id}",
                "task_type": task_type,
                "msg": "任务已分发到远程端点处理"
            })
        except RuntimeError as e:
            return error_response(str(e), code=CODE_CONCURRENCY_EXCEEDED)
    else:
        if not LocalConcurrencyManager.can_start():
            return error_response(
                f"达到最大并发限制: {config.LOCAL_MAX_CONCURRENCY}",
                code=CODE_CONCURRENCY_EXCEEDED,
                data={
                    "max_concurrency": config.LOCAL_MAX_CONCURRENCY,
                    "current_concurrency": LocalConcurrencyManager.get_current()
                }
            )

        LocalConcurrencyManager.increment()
        try:
            TaskModel.create_task(
                eval_task_id=eval_task_id,
                task_type=task_type,
                task_params=task_params,
                endpoints=None,
                endpoint_url=None,
                task_id=caller_task_id
            )
            TaskModel.update_task_status(eval_task_id, 'processing', started_at=datetime.now().isoformat())
        except Exception:
            LocalConcurrencyManager.decrement()
            raise

        def process_local_task(eval_task_id, task_type, task_params):
            try:
                pool = _get_calc_pool()
                future = pool.submit(calculate_in_process, task_type, task_params)
                result = future.result()  # 阻塞等待线程完成，但释放 GIL，不阻塞 HTTP 处理线程
                if task_type in ('xiaoyi_metrics', 'takeover') and isinstance(result, dict):
                    tl = result.get('takeover_latency')
                    if tl:
                        logger.info(
                            f"[takeover_latency] takeover_latency_ms={tl.get('takeover_latency_ms')} "
                            f"user_last_word_end_ms={tl.get('user_last_word_end_ms')} "
                            f"ai_first_word_start_ms={tl.get('ai_first_word_start_ms')} "
                            f"message={tl.get('message')}"
                        )
                TaskModel.update_task_status(
                    eval_task_id,
                    'completed',
                    completed_at=datetime.now().isoformat(),
                    result=result
                )
            except Exception as e:
                logger.exception(f"[process_local_task] 任务失败 eval_task_id={eval_task_id} task_type={task_type}: {e}")
                TaskModel.update_task_status(
                    eval_task_id,
                    'failed',
                    completed_at=datetime.now().isoformat(),
                    error_msg=str(e)
                )

        def _run_with_decrement(*args, **kwargs):
            try:
                process_local_task(*args, **kwargs)
            finally:
                LocalConcurrencyManager.decrement()

        thread = threading.Thread(target=_run_with_decrement, args=(eval_task_id, task_type, task_params))
        thread.daemon = True
        thread.start()

        base_url = request.host_url.rstrip('/')
        return success_response({
            "eval_task_id": eval_task_id,
            "task_id": caller_task_id,
            "status_url": f"{base_url}/api/get_status/{eval_task_id}",
            "final_result_url": f"{base_url}/api/get_final_result/{eval_task_id}",
            "task_type": task_type,
            "msg": "任务已创建，正在本地处理"
        })


@api_bp.route('/create_task', methods=['POST'])
def create_task():
    """
    创建评估任务
    
    支持本地处理和远程分发两种模式：
    1. 无 endpoints 参数：任务在本地处理
    2. 有 endpoints 参数：任务分发到远程端点处理
    
    请求参数（通用）：
        task_type (str, optional): 任务类型，可选值：'wer', 'ser', 'der', 'cpwer', 'tcpwer', 'stm_wer'，默认值：'wer'
        source_lang (str, optional): 源语言
        target_lang (str, optional): 目标语言
        translate_direct (str, optional): 翻译方向
        endpoints (list, optional): 远程端点列表，用于分布式任务调度
    
    WER/SER 专用参数（纯文本）：
        asr_ref (str): 参考文本（标准答案）
        asr_hyp (str): ASR 识别结果（待评估文本）
    
    CPWER/TCPWER/STM_WER 专用参数（STM格式）：
        ref_stm (str): 参考文本的 STM 格式
        hyp_stm (str): 识别结果的 STM 格式
        collar (float, optional): tcpwer 的时间约束参数（秒），默认 0.0
    
    DER 专用参数：
        rttm_ref (str): 参考音频的 RTTM 文件路径或内容
        stm_ref (str): 参考音频的 STM 文件路径或内容
        rttm_res (str): 识别结果的 RTTM 文件路径或内容
        stm_res (str): 识别结果的 STM 文件路径或内容
    
    其他参数将作为 task_params 传递给具体计算逻辑进行校验
    
    Returns:
        json: 包含任务 ID、状态查询 URL 和结果查询 URL 的响应
    """
    if not request.is_json:
        return error_response("Content-Type must be application/json", status_code=415, code=CODE_VALIDATION_ERROR)
    
    data = request.get_json()
    task_type = data.get('task_type', 'wer')
    endpoints = data.get('endpoints')
    caller_task_id = data.pop('task_id', None)
    task_params = {k: v for k, v in data.items() if k not in ['task_type', 'endpoints', 'task_id']}

    return _validate_and_dispatch_task(task_type, task_params, endpoints, caller_task_id=caller_task_id)


@api_bp.route('/create_task_upload', methods=['POST'])
def create_task_upload():
    """
    创建评估任务（支持文件上传）

    接收 multipart/form-data 请求：
    - 表单字段：task_type, endpoints (JSON字符串), 其他标量参数
    - 文件字段：通过 request.files 接收
      - 文本文件 (.txt/.stm/.rttm/.json/.csv/.srt/.vtt): 读取内容为字符串
      - 二进制文件 (.wav/.mp3 等): 保存到上传目录，使用文件路径
    """
    task_type = request.form.get('task_type', 'wer')
    caller_task_id = request.form.get('task_id')
    eval_task_id = f"task_{uuid.uuid4().hex}"
    storage_id = caller_task_id or eval_task_id
    upload_dir = os.path.join(config.UPLOAD_DIR, storage_id)
    os.makedirs(upload_dir, exist_ok=True)

    # 解析 endpoints（JSON 字符串）
    endpoints = None
    endpoints_str = request.form.get('endpoints')
    if endpoints_str:
        try:
            endpoints = json.loads(endpoints_str)
        except json.JSONDecodeError:
            return error_response("Invalid endpoints JSON format", code=CODE_VALIDATION_ERROR)

    # 构建 task_params：从 form 字段中提取（排除 task_type、endpoints 和 task_id）
    task_params = {}
    for key in request.form:
        if key not in ('task_type', 'endpoints', 'task_id'):
            task_params[key] = request.form[key]

    # 处理文件字段
    uploaded_file_paths = {}  # field_name → 保存后的本地路径
    for field_name, file_storage in request.files.items():
        if not file_storage or not file_storage.filename:
            continue

        filename = secure_filename(file_storage.filename)
        if not filename:
            filename = f"upload_{uuid.uuid4().hex}"

        ext = os.path.splitext(filename)[1].lower()

        if ext in TEXT_FILE_EXTENSIONS:
            # 文本文件：读取内容为字符串
            content = file_storage.read().decode('utf-8', errors='replace')
            task_params[field_name] = content
        else:
            # 二进制文件：保存到上传子目录，使用文件路径
            file_path = os.path.join(upload_dir, filename)
            file_storage.save(file_path)
            task_params[field_name] = file_path
            uploaded_file_paths[field_name] = file_path

    # 解析 rounds JSON 字符串，并把 __MULTIPART__ 占位符替换为上传后的实际路径
    # 遍历每个轮次里所有字段，凡是 '__MULTIPART__:<field_name>' 形式的值都替换成
    # uploaded_file_paths 中对应的上传落盘路径（record_file / user_wav / ai_wav 等）
    rounds_str = task_params.get('rounds')
    if rounds_str and isinstance(rounds_str, str):
        try:
            rounds_list = json.loads(rounds_str)
            if isinstance(rounds_list, list):
                for rd in rounds_list:
                    if not isinstance(rd, dict):
                        continue
                    for fld, val in list(rd.items()):
                        if isinstance(val, str) and val.startswith('__MULTIPART__:'):
                            placeholder_key = val.split(':', 1)[1]
                            if placeholder_key in uploaded_file_paths:
                                rd[fld] = uploaded_file_paths[placeholder_key]
                task_params['rounds'] = rounds_list
        except (json.JSONDecodeError, TypeError):
            pass  # rounds 不是合法 JSON，保持原样

    # xiaoyi_metrics / takeover：单轮时把 rounds[0] 里的字段提到顶层，供校验和计算使用
    # （record_file / user_wav / ai_wav 已作为文件上传保存，这里补充其他标量字段）
    if task_type in ('xiaoyi_metrics', 'takeover'):
        rounds_list = task_params.get('rounds')
        if isinstance(rounds_list, list) and len(rounds_list) == 1 and isinstance(rounds_list[0], dict):
            rd = rounds_list[0]
            for fld in ('record_file', 'user_wav', 'ai_wav', 'pause', 'first_frame_ms', 'start_ms', 'input', 'input_lastword', 'offset_ms'):
                val = rd.get(fld)
                if val is not None and val != '' and not task_params.get(fld):
                    task_params[fld] = val

    return _validate_and_dispatch_task(task_type, task_params, endpoints, caller_task_id=caller_task_id, eval_task_id=eval_task_id)

@api_bp.route('/status', methods=['GET'])
def get_status_info():
    """
    获取并发状态信息
    
    返回本地并发状态和各远程端点的并发情况
    
    Returns:
        json: 包含本地并发统计和远程端点并发统计的响应
    """
    local_stats = LocalConcurrencyManager.get_stats()
    from ..services.remote_service import remote_service
    remote_stats = remote_service.get_endpoints_stats()
    
    endpoints = TaskModel.get_all_endpoints()
    worker_concurrency = {}
    for ep in endpoints:
        url = ep['url']
        ep_stats = remote_stats.get(url, {})
        current = sum(ep_stats.values()) if ep_stats else 0
        
        capabilities = ep.get('capabilities', {})
        max_by_cap = {}
        for task_type, cap in capabilities.items():
            if isinstance(cap, dict):
                max_by_cap[task_type] = cap.get('max_process', 1)
            else:
                max_by_cap[task_type] = 1
        
        worker_concurrency[url] = {
            'current': current,
            'max': ep.get('max_process', 1),
            'available': max(0, ep.get('max_process', 1) - current),
            'by_task_type': max_by_cap
        }
    
    return success_response({
        "local": local_stats,
        "worker_concurrency": worker_concurrency
    })

@api_bp.route('/get_status/<eval_task_id>', methods=['GET'])
def get_status(eval_task_id):
    """
    获取指定任务的状态
    
    Args:
        eval_task_id (str): 评估任务 ID
    
    Returns:
        json: 包含任务状态、类型、时间等信息的响应
    """
    task = TaskModel.get_task(eval_task_id)
    if not task:
        return error_response("Task not found", status_code=404, code=CODE_BUSINESS_ERROR)
    
    return success_response({
        "eval_task_id": task['eval_task_id'],
        "task_id": task.get('task_id'),
        "status": task['status'],
        "task_type": task['task_type'],
        "created_at": task['created_at'],
        "started_at": task['started_at'],
        "completed_at": task['completed_at'],
        "error_msg": task['error_msg']
    })

@api_bp.route('/get_final_result/<eval_task_id>', methods=['GET'])
def get_final_result(eval_task_id):
    """
    获取指定任务的最终评估结果
    
    Args:
        eval_task_id (str): 评估任务 ID
    
    Returns:
        json: 包含评估结果的响应
    """
    task = TaskModel.get_task(eval_task_id)
    if not task:
        return error_response("Task not found", status_code=404, code=CODE_BUSINESS_ERROR)
    
    if task['status'] == 'pending' or task['status'] == 'processing':
        return error_response("Task is still processing", status_code=202, code=CODE_BUSINESS_ERROR, data={
            "eval_task_id": eval_task_id,
            "status": task['status']
        })
    
    if task['status'] == 'failed':
        return error_response(f"Task failed: {task['error_msg']}", status_code=500, code=CODE_SERVER_ERROR, data={
            "eval_task_id": eval_task_id,
            "status": "failed",
            "error_msg": task['error_msg']
        })
    
    result = task['result'] if task['result'] else {}
    if isinstance(result, str):
        result = json.loads(result)
    
    return success_response({
        "eval_task_id": task['eval_task_id'],
        "task_id": task.get('task_id'),
        "status": task['status'],
        "result": result,
        "task_type": task['task_type'],
        "completed_at": task['completed_at']
    })

@api_bp.route('/delete_task/<eval_task_id>', methods=['DELETE'])
def delete_task(eval_task_id):
    """
    删除指定任务
    
    Args:
        eval_task_id (str): 评估任务 ID
    
    Returns:
        json: 删除结果响应
    """
    if TaskModel.delete_task(eval_task_id):
        return success_response({"eval_task_id": eval_task_id}, msg=f"任务 {eval_task_id} 已成功删除")
    else:
        return error_response("Task not found", status_code=404, code=CODE_BUSINESS_ERROR)

@api_bp.route('/endpoints', methods=['GET'])
def list_endpoints():
    """
    列出所有已配置的远程端点
    
    Returns:
        json: 包含所有端点配置的响应
    """
    endpoints = TaskModel.get_all_endpoints()
    return success_response({"endpoints": endpoints})

@api_bp.route('/endpoints', methods=['POST'])
def create_endpoint():
    """
    创建新的远程端点配置
    
    请求参数：
        url (str): 远程服务的基础 URL
        name (str, optional): 端点名称
        capabilities (dict, optional): 详细的并发能力配置
        task_types (list, optional): 支持的任务类型列表
        max_process (int, optional): 默认最大并发数，默认值：1
    
    Returns:
        json: 包含创建的端点配置的响应
    """
    if not request.is_json:
        return error_response("Content-Type must be application/json", status_code=415, code=CODE_VALIDATION_ERROR)
    
    data = request.get_json()
    url = data.get('url')
    name = data.get('name')
    capabilities = data.get('capabilities')
    task_types = data.get('task_types')
    max_process = data.get('max_process', 1)
    
    if not url:
        return error_response("Missing required field: url", code=CODE_VALIDATION_ERROR)
    
    TaskModel.create_endpoint(url, name, capabilities, task_types, max_process)
    
    endpoint = TaskModel.get_endpoint(url)
    return success_response({"endpoint": endpoint}, msg=f"端点 {url} 已成功创建")

@api_bp.route('/endpoints/<path:url>', methods=['GET'])
def get_endpoint(url):
    """
    获取指定端点的配置信息
    
    Args:
        url (str): 端点 URL
    
    Returns:
        json: 包含端点配置的响应
    """
    endpoint = TaskModel.get_endpoint(url)
    if not endpoint:
        return error_response("Endpoint not found", status_code=404, code=CODE_BUSINESS_ERROR)
    
    return success_response({"endpoint": endpoint})

@api_bp.route('/endpoints/<path:url>', methods=['PUT'])
def update_endpoint(url):
    """
    更新指定端点的配置信息
    
    Args:
        url (str): 端点 URL
    
    请求参数（均为可选）：
        name (str): 端点名称
        capabilities (dict): 详细的并发能力配置
        task_types (list): 支持的任务类型列表
        max_process (int): 默认最大并发数
    
    Returns:
        json: 包含更新后的端点配置的响应
    """
    if not request.is_json:
        return error_response("Content-Type must be application/json", status_code=415, code=CODE_VALIDATION_ERROR)
    
    data = request.get_json()
    name = data.get('name')
    capabilities = data.get('capabilities')
    task_types = data.get('task_types')
    max_process = data.get('max_process')
    
    if not TaskModel.get_endpoint(url):
        return error_response("Endpoint not found", status_code=404, code=CODE_BUSINESS_ERROR)
    
    TaskModel.update_endpoint(url, name, capabilities, task_types, max_process)
    
    endpoint = TaskModel.get_endpoint(url)
    return success_response({"endpoint": endpoint}, msg=f"端点 {url} 已成功更新")

@api_bp.route('/endpoints/<path:url>', methods=['DELETE'])
def delete_endpoint(url):
    """
    删除指定的端点配置
    
    Args:
        url (str): 端点 URL
    
    Returns:
        json: 删除结果响应
    """
    if not TaskModel.delete_endpoint(url):
        return error_response("Endpoint not found", status_code=404, code=CODE_BUSINESS_ERROR)
    
    return success_response({"url": url}, msg=f"端点 {url} 已成功删除")

@api_bp.route('/endpoints/<path:url>/concurrency/<task_type>', methods=['PUT'])
def update_endpoint_concurrency(url, task_type):
    """
    动态更新指定端点对特定任务类型的并发限制
    
    Args:
        url (str): 端点 URL
        task_type (str): 任务类型，可选值：'wer', 'ser'
    
    请求参数：
        max_process (int): 新的最大并发数，必须 >= 0
    
    Returns:
        json: 包含更新后的端点配置和更新信息的响应
    """
    if task_type not in ['wer', 'ser', 'der', 'cpwer', 'tcpwer', 'stm_wer', 'llm_judge']:
        return error_response(f"Unsupported task type: {task_type}", code=CODE_BUSINESS_ERROR)
    
    if not request.is_json:
        return error_response("Content-Type must be application/json", status_code=415, code=CODE_VALIDATION_ERROR)
    
    data = request.get_json()
    max_process = data.get('max_process')
    
    if max_process is None or max_process < 0:
        return error_response("Invalid max_process value", code=CODE_VALIDATION_ERROR)
    
    if not TaskModel.get_endpoint(url):
        return error_response("Endpoint not found", status_code=404, code=CODE_BUSINESS_ERROR)
    
    TaskModel.update_endpoint_concurrency(url, task_type, max_process)

    endpoint = TaskModel.get_endpoint(url)
    return success_response({
        "endpoint": endpoint,
        "updated": {
            "task_type": task_type,
            "max_process": max_process
        }
    }, msg=f"端点 {url} 的 {task_type} 任务并发限制已更新为 {max_process}")
