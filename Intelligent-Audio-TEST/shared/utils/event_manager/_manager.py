from shared.utils.event_manager._base import BaseEventManagerMixin
from shared.utils.event_manager._time_estimate import TimeEstimateMixin
from shared.utils.event_manager._progress import ProgressMixin
from shared.utils.event_manager._alert import AlertMixin


class EventManager(BaseEventManagerMixin, TimeEstimateMixin, ProgressMixin, AlertMixin):
    """事件管理器：负责任务进度推送、时间预估、告警发射。

    通过组合多个 mixin 模块拆分实现，对外保持单一类的接口不变。
    """
    pass
