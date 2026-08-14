from datetime import datetime, timezone, timedelta
import logging
from shared.utils.event_manager._common import get_socketio

logger = logging.getLogger(__name__)


class AlertMixin:
    def emit_alert(self, task_id, message, level='error'):
        try:
            utc_plus_8 = timezone(timedelta(hours=8))
            alert_data = {
                "task_id": task_id,
                "message": message,
                "level": level,
                "time": datetime.now(utc_plus_8).isoformat()
            }
            _socketio = get_socketio()
            if _socketio:
                _socketio.emit_sync('error_alert', alert_data)
        except Exception:
            logger.warning("发送告警事件失败，task_id=%s, level=%s", task_id, level, exc_info=True)
