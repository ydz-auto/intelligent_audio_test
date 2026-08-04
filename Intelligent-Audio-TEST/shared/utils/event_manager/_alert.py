from datetime import datetime, timezone, timedelta
from shared.utils.event_manager._common import get_socketio


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
            pass
