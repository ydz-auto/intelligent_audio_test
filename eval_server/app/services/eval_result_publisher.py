# -*- coding: utf-8 -*-
"""评估结果事件化发布（Redis Pub/Sub）。

任务进入终态（completed / failed）后，把结果发布到 ``eval:result:{eval_task_id}``
频道；平台侧 evaluation_service 已订阅该频道（Redis 回调优先、HTTP 轮询兜底），
事件先到即可直接落库，无需等待轮询。

约定：
- 频道名与平台 ``RedisKeyPrefix.EVAL_RESULT`` 完全一致（``eval:result``，无环境前缀）。
- payload 与平台 ``/api/get_final_result`` 消费口径对齐：
    成功 ``{"status": "completed", "code": 0, "data": {"result": {...}, ...}}``
    失败 ``{"status": "failed", "error_msg": "..."}``
- Redis 未配置/不可用时静默降级（平台轮询兜底），绝不阻断评估。
"""
import json
import logging
import threading

logger = logging.getLogger('eval_result_publisher')

_CHANNEL_PREFIX = 'eval:result'

_pub_client = None
_pub_lock = threading.Lock()


def _get_redis_client():
    """惰性创建并缓存发布用 Redis 客户端；未配置或不可用返回 None。"""
    global _pub_client
    with _pub_lock:
        if _pub_client is not None:
            return _pub_client
        try:
            from app.config import config
        except Exception:
            return None
        url = getattr(config, 'REDIS_URL', '') or ''
        if not url:
            return None
        try:
            import redis
            client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            _pub_client = client
        except Exception as e:
            logger.warning(f'[eval_result_publisher] Redis 不可用，评估结果事件降级为平台轮询: {e}')
            _pub_client = None
        return _pub_client


def publish_eval_result(eval_task_id, task_type, task_id, status,
                        result=None, error_msg=None):
    """发布任务终态事件；任何异常只记日志，不向上抛（平台有轮询兜底）。"""
    if not eval_task_id:
        return
    client = _get_redis_client()
    if client is None:
        return

    if status == 'failed':
        payload = {
            'status': 'failed',
            'code': 500,
            'error_msg': error_msg or 'Task failed',
            'eval_task_id': eval_task_id,
            'task_id': task_id,
            'task_type': task_type,
        }
    else:
        payload = {
            'status': 'completed',
            'code': 0,
            'eval_task_id': eval_task_id,
            'task_id': task_id,
            'task_type': task_type,
            'data': {
                'eval_task_id': eval_task_id,
                'task_id': task_id,
                'task_type': task_type,
                'status': 'completed',
                'result': result,
            },
        }

    try:
        client.publish(f'{_CHANNEL_PREFIX}:{eval_task_id}',
                       json.dumps(payload, ensure_ascii=False, default=str))
    except Exception as e:
        logger.warning(f'[eval_result_publisher] 发布评估结果事件失败 eval_task_id={eval_task_id}: {e}')
