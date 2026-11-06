# -*- coding: utf-8 -*-
"""LLM 调用审计日志

每次 ``call_llm`` 调用写一条 JSONL，记录原始请求（剥离 base64 音视频）/ 原始响应 / token / 失败原因。
- 与应用日志(LOG_DIR) 完全分开，单独存放到 config.LLM_CALL_LOG_DIR，按日一个 .jsonl 文件
- 永不轮转、不删除，每条永久保留（用户明确要求）
- 日志自身失败只告警、绝不抛，不影响评估
- 受 config.LLM_CALL_LOG_ENABLED 开关控制
"""
import copy
import json
import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 并发追加写锁（call_llm 在 ThreadPoolExecutor 下并发）
_lock = threading.Lock()


def _sanitize(obj: Any) -> Any:
    """深拷贝并剥离 base64 音视频数据，保留结构与全部文本元数据。

    - input_audio.data（纯 base64 音频）→ 占位符 + 字符数
    - image_url.url 以 data: 开头（base64 视频/图片 data URI）→ 占位符 + 字符数
    其余字段（model/messages/text/max_tokens/temperature 等）原样深拷贝保留。
    """
    if isinstance(obj, dict):
        result: Dict[str, Any] = {}
        for k, v in obj.items():
            # input_audio 内层 dict: {'data': <base64>, 'format': 'wav'}
            if k == 'data' and isinstance(v, str) and 'format' in obj:
                result[k] = f'<base64 omitted, {len(v)} chars>'
            # image_url 内层 dict: {'url': 'data:video/mp4;base64,...'}
            elif k == 'url' and isinstance(v, str) and v.startswith('data:'):
                result[k] = f'<data uri omitted, {len(v)} chars>'
            else:
                result[k] = _sanitize(v)
        return result
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    # 标量原样返回；dict/list 已处理，无需 deepcopy
    return obj


def _today_file() -> str:
    today = datetime.now().strftime('%Y-%m-%d')
    return os.path.join(_log_dir(), f'{today}.jsonl')


def _log_dir() -> str:
    from app.config import config
    return getattr(config, 'LLM_CALL_LOG_DIR', '')


def _enabled() -> bool:
    from app.config import config
    return getattr(config, 'LLM_CALL_LOG_ENABLED', True)


def _extract_tokens(data: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """从响应 data.usage 取 token；失败/缺省全 0"""
    usage = {}
    if isinstance(data, dict):
        usage = data.get('usage', {}) or {}
    return {
        'input': usage.get('prompt_tokens', 0) or 0,
        'output': usage.get('completion_tokens', 0) or 0,
        'total': usage.get('total_tokens', 0) or 0,
    }


def log_llm_call(model: str,
                 payload: Dict[str, Any],
                 data: Optional[Dict[str, Any]],
                 context: Optional[Dict[str, Any]],
                 status: str,
                 error: Optional[Dict[str, Any]] = None,
                 attempts: int = 1) -> None:
    """写一条 LLM 调用审计日志（成功或失败均记）。

    Args:
        model: 模型名
        payload: 发给 LLM 的原始请求体（含 base64 音视频，本函数内剥离）
        data: LLM 响应解析后的 dict（成功时含 choices+usage）；失败时 None
        context: 调用方上下文，如 {'dimension': 'interruption_llm', 'event_index': 3}
        status: 'success' | 'failed'
        error: 失败原因 dict {'type', 'message', 'status_code'?, 'body_snippet'?}；成功时 None
        attempts: 本次调用实际发起的 HTTP 请求次数（含重试）
    """
    try:
        if not _enabled():
            return
        log_dir = _log_dir()
        if not log_dir:
            return
        os.makedirs(log_dir, exist_ok=True)

        entry = {
            'ts': datetime.now().isoformat(),
            'model': model,
            'status': status,
            'attempts': attempts,
            'tokens': _extract_tokens(data) if status == 'success' else
                      {'input': 0, 'output': 0, 'total': 0},
            'raw_request': _sanitize(payload),
            'raw_response': data if status == 'success' else None,
            'error': error,
            'context': context or {},
        }
        line = json.dumps(entry, ensure_ascii=False)
        with _lock:
            with open(_today_file(), 'a', encoding='utf-8') as f:
                f.write(line + '\n')
    except Exception as e:
        logger.warning(f'[llm_call_logger] 写 LLM 调用日志失败: {e}')
