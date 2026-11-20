# -*- coding: utf-8 -*-
"""Run 事件唤醒实现。

- LocalRunWakeup：进程内 Condition，多 SSE 订阅者各自等待代际变化；
- RedisRunWakeup：额外发布 ``agent_run_wakeup`` 唤醒消息（只带 run_id，
  事件正文仍以 DB 为唯一事实源），后台订阅线程收到后转成本地唤醒。
  Redis 不可用时静默退化为轮询（wait 超时后由调用方回表读增量）。
"""
import json
import logging
import threading
from typing import Dict

from agent_service.domain.ports.run_wakeup import RunWakeup

logger = logging.getLogger(__name__)


class LocalRunWakeup(RunWakeup):
    def __init__(self):
        self._condition = threading.Condition()
        self._generation: Dict[str, int] = {}
        self._closed = False

    def notify(self, run_id: str) -> None:
        with self._condition:
            self._generation[run_id] = self._generation.get(run_id, 0) + 1
            self._condition.notify_all()

    def wait(self, run_id: str, timeout: float) -> bool:
        with self._condition:
            start = self._generation.get(run_id, 0)
            if self._closed:
                return False
            return self._condition.wait_for(
                lambda: self._generation.get(run_id, 0) != start,
                timeout=timeout,
            )

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class RedisRunWakeup(LocalRunWakeup):
    def __init__(self, redis_url: str, channel: str):
        super().__init__()
        self._redis_url = redis_url
        self._channel = channel
        self._listener = None
        self._stopping = threading.Event()
        self._redis_warned = False

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = threading.Thread(
            target=self._listen, name='agent-run-wakeup', daemon=True)
        self._listener.start()

    def notify(self, run_id: str) -> None:
        super().notify(run_id)
        try:
            import redis
            client = redis.from_url(self._redis_url)
            client.publish(self._channel, json.dumps({'run_id': run_id}))
        except Exception:  # noqa: BLE001 - 唤醒失败不影响正确性（仍会轮询）
            if not self._redis_warned:
                self._redis_warned = True
                logger.warning('Redis 唤醒发布失败，退化为轮询', exc_info=True)

    def _listen(self) -> None:
        while not self._stopping.is_set():
            try:
                import redis
                client = redis.from_url(self._redis_url)
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(self._channel)
                while not self._stopping.is_set():
                    message = pubsub.get_message(timeout=1.0)
                    if not message or message.get('type') != 'message':
                        continue
                    try:
                        payload = json.loads(message.get('data') or b'{}')
                    except (ValueError, TypeError):
                        continue
                    run_id = payload.get('run_id')
                    if run_id:
                        super().notify(run_id)
            except Exception:  # noqa: BLE001
                if not self._redis_warned:
                    self._redis_warned = True
                    logger.warning('Redis 唤醒订阅失败，退化为轮询', exc_info=True)
                self._stopping.wait(3.0)

    def close(self) -> None:
        self._stopping.set()
        super().close()
