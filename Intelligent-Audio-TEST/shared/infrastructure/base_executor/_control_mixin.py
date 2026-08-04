# -*- coding: utf-8 -*-
"""暂停 / 停止控制相关方法"""
import time


class ControlMixin:
    """处理暂停和停止逻辑（从中央存储获取事件）

    多实例部署下，先查 Redis 分布式标志位（其它实例发出的 stop/pause），
    再查本进程 threading.Event。单实例下 Redis 开关关闭，零开销。
    """

    def _handle_control(self, task_id):
        # 分布式控制标志位（多实例下，其它实例发出的 stop/pause 信号）
        from shared.utils import distributed_coordinator as dc
        if dc.is_flag_set(f'task:stop:{task_id}'):
            raise Exception("任务已停止（分布式停止信号）")
        if dc.is_flag_set(f'task:pause:{task_id}'):
            self._log(level='INFO', content="检测到暂停指令（分布式），等待恢复...", task_id=task_id)
            while dc.is_flag_set(f'task:pause:{task_id}'):
                if dc.is_flag_set(f'task:stop:{task_id}'):
                    raise Exception("任务已停止")
                time.sleep(0.5)
            self._log(level='INFO', content="任务已恢复执行", task_id=task_id)

        # 本进程内 Event（兼容单实例模式）
        stop_event, pause_event = self._get_control_events(task_id)

        if stop_event is not None and stop_event.is_set():
            raise Exception("任务已停止")

        if pause_event is not None and not pause_event.is_set():
            self._log(level='INFO', content="检测到暂停指令，等待恢复...", task_id=task_id)
            while pause_event is not None and not pause_event.is_set():
                if stop_event is not None and stop_event.is_set():
                    raise Exception("任务已停止")
                # 多实例下也检查分布式停止信号
                if dc.is_flag_set(f'task:stop:{task_id}'):
                    raise Exception("任务已停止（分布式停止信号）")
                pause_event.wait(timeout=0.5)
            self._log(level='INFO', content="任务已恢复执行", task_id=task_id)

    def _get_control_events(self, task_id):
        """获取控制事件

        直接从本进程的 execution_engine 单例获取 threading.Event 对象。
        execution_engine 是进程内单例，stop_flags/pause_flags
        是进程内 Event，无需跨进程获取。
        多实例下的跨进程信号由 _handle_control 中的 Redis 标志位补充。
        """
        engine = self.execution_engine
        if engine is None:
            return None, None
        stop_event = engine.stop_flags.get(task_id)
        pause_event = engine.pause_flags.get(task_id)
        return stop_event, pause_event
