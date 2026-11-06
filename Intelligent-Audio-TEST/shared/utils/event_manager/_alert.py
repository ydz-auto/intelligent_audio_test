from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


class AlertMixin:
    def emit_alert(self, task_id, message, level='error'):
        """任务告警统一经 EventBus TASK_EVENTS / task_alert 发布（api_gateway 转发 error_alert）。"""
        try:
            utc_plus_8 = timezone(timedelta(hours=8))
            alert_data = {
                "task_id": task_id,
                "message": message,
                "level": level,
                "time": datetime.now(utc_plus_8).isoformat()
            }
            from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
            EventBus().publish(EventChannel.TASK_EVENTS, EventType.TASK_ALERT, {
                'event': 'error_alert',
                'task_id': str(task_id),
                'data': alert_data,
            })
        except Exception:
            logger.warning("发送告警事件失败，task_id=%s, level=%s", task_id, level, exc_info=True)
