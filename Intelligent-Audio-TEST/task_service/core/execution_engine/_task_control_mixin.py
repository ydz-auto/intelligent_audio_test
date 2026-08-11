import threading
from datetime import datetime
from collections import deque
from task_service.infrastructure.persistence.models import Task, TaskCase
from shared.models.database import get_db_session
from shared.utils import distributed_coordinator as _dc

# gRPC 调用封装函数（模块级）
from task_service.core.execution_engine._grpc_helpers import (
    _stop_task_audio_via_grpc,
    _cleanup_devices_via_grpc,
    _unregister_task_events_via_grpc,
    _get_task_events_via_grpc,
    _register_task_events_via_grpc,
)


class TaskControlMixin:
    """任务控制相关的方法：启动、排队检查、移除、控制（暂停/恢复/停止）"""

    def start_task(self, task_id):
        """启动测试任务

        Args:
            task_id: 任务ID

        Returns:
            tuple: (是否成功, 状态消息)
        """
        # 检查任务是否已在运行或队列中
        if task_id in self.workers and self.workers[task_id].is_alive():
            return False, "任务已在运行中"
        
        with self.queue_lock:
            if any(t['id'] == task_id for t in self.task_queue):
                return False, "任务已在队列中"

        # 获取任务类型和关联的API
        local_db_session = get_db_session()
        try:
            task = local_db_session.get(Task, task_id)
            if not task:
                return False, "任务不存在"
            
            task_type = task.type
            
            # 获取任务关联的API ID
            from task_service.infrastructure.persistence.models import TaskAPI
            task_apis = local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
            api_ids = [task_api.api_id for task_api in task_apis]
        finally:
            local_db_session.close()
        
        # 检查是否可以立即执行
        with self.queue_lock:
            can_run = False
            
            if task_type == 'e2e':
                # E2E任务：同时只允许一个E2E任务运行
                if not self.running_e2e:
                    can_run = True
            else:
                # API任务：检查是否有相同API在运行
                overlapping_apis = set(api_ids) & self.running_apis
                if not overlapping_apis:
                    can_run = True
            
            if can_run:
                # 可以立即执行，创建停止和暂停事件
                stop_event = threading.Event()
                pause_event = threading.Event()
                pause_event.set()  # 初始状态为非暂停

                # 创建任务完成事件（用于替代忙等待）
                self.task_completion_events[task_id] = threading.Event()

                # 注册任务控制事件（通过 gRPC 同步到 e2e_test_service）
                _register_task_events_via_grpc(task_id, stop_event, pause_event)

                # 更新运行状态
                self.running_tasks[task_id] = task_type
                if task_type == 'e2e':
                    self.running_e2e = True
                else:
                    self.running_apis.update(api_ids)

                # 更新任务状态为running
                # 多实例下用 DB 条件 UPDATE 做任务抢占 CAS，避免重复启动
                local_db_session = get_db_session()
                try:
                    # CAS: 只有 pending/queued 状态才能翻转为 running
                    claimed = local_db_session.query(Task).filter(
                        Task.id == task_id,
                        Task.status.in_(['pending', 'queued'])
                    ).update({Task.status: 'running'}, synchronize_session=False)
                    if claimed != 1:
                        # 已被其它实例抢占，回滚本地运行状态
                        local_db_session.rollback()
                        with self.queue_lock:
                            self.running_tasks.pop(task_id, None)
                            if task_type == 'e2e':
                                self.running_e2e = False
                            else:
                                self.running_apis.difference_update(api_ids)
                        return False, "任务已被其它实例启动"
                    local_db_session.commit()
                finally:
                    local_db_session.close()

                # 创建任务执行线程
                thread = threading.Thread(target=self._run_task, args=(task_id, stop_event, pause_event))
                self.workers[task_id] = thread
                self.stop_flags[task_id] = stop_event
                self.pause_flags[task_id] = pause_event

                # 启动线程
                thread.start()
                return True, "任务已启动"
            else:
                if len(self.task_queue) >= self.max_queue_size:
                    return False, f"任务队列已满 ({self.max_queue_size})"
                self.task_queue.append({
                    'id': task_id,
                    'type': task_type,
                    'api_ids': api_ids,
                })
            
            # 更新任务状态为queued
            local_db_session = get_db_session()
            try:
                task = local_db_session.get(Task, task_id)
                if task:
                    task.status = 'queued'
                    local_db_session.commit()
            finally:
                local_db_session.close()
            
            # 触发调度器立即检查
            self.trigger_scheduler_check()
            
            return True, "任务已加入队列"
    
    def _check_queue(self):
        """检查任务队列，启动可以执行的任务，一次启动多个可执行任务"""
        local_db_session = get_db_session()
        try:
            tasks_to_start = []
            
            with self.queue_lock:
                remaining_tasks = deque()
                
                while self.task_queue:
                    queued_task = self.task_queue.popleft()
                    task_id = queued_task['id']
                    task_type = queued_task['type']
                    api_ids = queued_task['api_ids']

                    task = local_db_session.get(Task, task_id)
                    task_status = task.status if task else None
                    
                    if task_status == 'stopped':
                        continue
                    
                    can_run = False
                    
                    if task_type == 'e2e':
                        if not self.running_e2e:
                            can_run = True
                    else:
                        overlapping_apis = set(api_ids) & self.running_apis
                        if not overlapping_apis:
                            can_run = True
                    
                    if can_run:
                        self.running_tasks[task_id] = task_type
                        if task_type == 'e2e':
                            self.running_e2e = True
                        else:
                            self.running_apis.update(api_ids)
                        
                        if task:
                            task.status = 'running'
                            local_db_session.commit()
                        
                        tasks_to_start.append({
                            'task_id': task_id,
                            'task': task
                        })
                    else:
                        remaining_tasks.append(queued_task)
                
                self.task_queue = remaining_tasks
            
            for task_info in tasks_to_start:
                task_id = task_info['task_id']

                stop_event = threading.Event()
                pause_event = threading.Event()
                pause_event.set()

                # 创建任务完成事件（用于替代忙等待）
                self.task_completion_events[task_id] = threading.Event()

                thread = threading.Thread(target=self._run_task, args=(task_id, stop_event, pause_event))
                self.workers[task_id] = thread
                self.stop_flags[task_id] = stop_event
                self.pause_flags[task_id] = pause_event
                
                thread.start()
        finally:
            local_db_session.close()
    
    def remove_from_queue(self, task_id):
        """
        从任务队列中移除指定任务
        
        Args:
            task_id: 任务ID
        """
        with self.queue_lock:
            new_queue = deque()
            removed = False
            for queued_task in self.task_queue:
                if queued_task['id'] == task_id:
                    removed = True
                else:
                    new_queue.append(queued_task)
            self.task_queue = new_queue
        return removed

    def control_task(self, task_id, action):
        """
        控制任务执行（暂停、恢复、停止）

        Args:
            task_id: 任务ID
            action: 操作类型，可选值：'pause', 'resume', 'stop'

        Returns:
            tuple: (是否成功, 状态消息)
        """
        # 处理停止任务操作，从队列中移除
        if action == 'stop':
            self.remove_from_queue(task_id)

        # 使用本地会话确保独立可靠的会话
        local_db_session = get_db_session()
        try:
            task = local_db_session.get(Task, task_id)
            if not task:
                return False, "任务不存在"

            # 检查任务状态是否允许执行操作
            if action == 'pause':
                if task.status not in ['running', 'queued']:
                    return False, "只有执行中或排队中的任务才能暂停"
            elif action == 'resume':
                if task.status != 'paused':
                    return False, "只有已暂停的任务才能恢复"
            elif action == 'stop':
                if task.status not in ['running', 'paused', 'queued', 'evaluating']:
                    return False, "只有执行中、已暂停、排队中或评估中的任务才能停止"

            # 对于停止操作，即使任务不在workers中，也应该执行
            if action == 'stop':
                # 更新任务状态为stopped
                task.status = 'stopped'
                task.completed_at = datetime.now(self.utc_plus_8)
                
                # 只处理未完成的用例（执行中、排队中、待执行），保留已完成用例的状态
                cases = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    ~TaskCase.status.in_(['completed', 'failed', 'skipped'])
                ).all()
                for tc in cases:
                    tc.status = 'skipped'
                    tc.execution_status = 'stopped'
                    tc.evaluation_status = 'stopped'
                    tc.started_at = None
                    tc.completed_at = datetime.now(self.utc_plus_8)
                    tc.duration = None
                    tc.error_message = '任务被手动停止'
                
                local_db_session.commit()

                # 分布式停止信号（多实例下通知所有实例的执行线程）
                # 优先广播，确保 gRPC 调用失败时不阻塞停止信号传播
                _dc.set_flag(f'task:stop:{task_id}')
                _dc.clear_flag(f'task:pause:{task_id}')

                # 如果任务在workers中，设置停止标志
                if task_id in self.workers:
                    self.stop_flags[task_id].set()  # 设置停止标志
                    self.pause_flags[task_id].set()  # 确保任务不处于暂停状态，以便能响应停止指令
                    # 唤醒等待线程，使其能立即检测到 stop_event
                    self.notify_case_completed(task_id)

                # 停止所有音频播放（通过 gRPC 调用 e2e_test_service 的 AudioService）
                # 放在 Redis 标志位之后，gRPC 失败不影响停止信号传播
                try:
                    _stop_task_audio_via_grpc(task_id)
                except Exception as e:
                    self._log(level='WARNING',
                              content=f"停止音频播放 gRPC 调用失败(不阻塞停止流程): {e}",
                              task_id=task_id)
                self._emit_progress(task)  # 发送进度更新

                # 通过 gRPC 通知 e2e_test_service 同步停止事件
                if task_id in self.workers:
                    try:
                        _register_task_events_via_grpc(
                            task_id, self.stop_flags[task_id], self.pause_flags[task_id]
                        )
                    except Exception as e:
                        self._log(level='WARNING',
                                  content=f"同步停止事件 gRPC 调用失败(不阻塞停止流程): {e}",
                                  task_id=task_id)
                
                # 立即清理运行状态，避免新任务进入排队
                with self.queue_lock:
                    if task_id in self.running_tasks:
                        task_type = self.running_tasks[task_id]
                        del self.running_tasks[task_id]
                        
                        if task_type == 'e2e':
                            self.running_e2e = False
                        else:
                            # 释放占用的 API ID
                            try:
                                from task_service.infrastructure.persistence.models import TaskAPI
                                task_apis = local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
                                for api_rel in task_apis:
                                    if api_rel.api_id in self.running_apis:
                                        self.running_apis.remove(api_rel.api_id)
                            except Exception as e:
                                self._log(level='WARNING', content=f"清理API资源时发生错误: {str(e)}", task_id=task_id)
                
                # 清理线程和标志位
                self.workers.pop(task_id, None)
                self.stop_flags.pop(task_id, None)
                self.pause_flags.pop(task_id, None)
                self.task_completion_events.pop(task_id, None)
                # 清理进度缓存，避免内存泄漏
                self.task_progress_cache.pop(task_id, None)
                self.last_progress_update.pop(task_id, None)
                # 清理多轮进度缓存（key 为 tc_rel_id，需查询当前任务的用例 ID）
                try:
                    tc_rel_ids = [
                        tc_id for (tc_id,) in
                        local_db_session.query(TaskCase.id).filter_by(task_id=task_id).all()
                    ]
                    for tc_rel_id in tc_rel_ids:
                        self.round_progress_cache.pop(tc_rel_id, None)
                except Exception:
                    pass

                # 检查队列并启动下一个任务
                self._check_queue()

                # 通过 gRPC 调用 e2e_test_service 的 DeviceService
                _cleanup_devices_via_grpc(task_id)
                _unregister_task_events_via_grpc(task_id)
                
                return True, "任务已停止"
            else:
                # 对于暂停和恢复操作，需要任务在workers中
                if action == 'pause' and task.status == 'queued':
                    self.remove_from_queue(task_id)
                    task.status = 'paused'
                    local_db_session.commit()
                    self._emit_progress(task)
                    return True, "任务已暂停"

                if action == 'resume' and task_id not in self.workers:
                    if task.type == 'api':
                        from task_service.infrastructure.persistence.models import TaskAPI
                        api_ids = [
                            rel.api_id
                            for rel in local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
                        ]
                        with self.queue_lock:
                            self.task_queue.append({"id": task.id, "type": "api", "api_ids": api_ids, "app": app})
                        task.status = 'queued'
                        local_db_session.commit()
                        self._emit_progress(task)
                        self.trigger_scheduler_check()
                        return True, "任务已恢复"
                    return False, "未找到运行中的任务"

                if task_id not in self.workers:
                    return False, "未找到运行中的任务"

                if action == 'pause':
                    # 暂停任务
                    self.pause_flags[task_id].clear()  # 清除暂停标志，触发暂停
                    # 分布式暂停信号（多实例下通知所有实例的执行线程）
                    _dc.set_flag(f'task:pause:{task_id}')
                    # 通过 gRPC 通知 e2e_test_service 同步暂停事件
                    _register_task_events_via_grpc(
                        task_id, self.stop_flags[task_id], self.pause_flags[task_id]
                    )
                    task.status = 'paused'  # 更新任务状态
                    
                    # 对于 API 任务，不重置执行中的用例状态为 pending
                    # 因为 API 线程是在 pause_event 上阻塞，恢复时会自动继续执行
                    # 如果重置为 pending，会导致调度器重新启动新线程，造成重复执行
                    if task.type == 'e2e':
                        # E2E 任务是同步顺序执行的，暂停时可以将当前正在执行的用例重置
                        # 但为了统一和简单，建议也不重置，让 E2E 执行器内部处理暂停
                        running_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, execution_status='running').all()
                        for tc in running_cases:
                            tc.execution_status = 'pending'
                            tc.completed_at = None
                            tc.duration = None
                    
                    local_db_session.commit()
                    # 暂停时停止所有音频播放（通过 gRPC AudioService）
                    _stop_task_audio_via_grpc(task_id)
                    # 暂停时清理设备并注销事件（通过 gRPC DeviceService）
                    _cleanup_devices_via_grpc(task_id)
                    _unregister_task_events_via_grpc(task_id)
                    self._emit_progress(task)  # 发送进度更新
                    return True, "任务已暂停"
                elif action == 'resume':
                    # 恢复任务
                    # 检查事件是否还存在，如果不存在需要重新注册
                    # 跨服务调用：通过 gRPC DeviceService 获取任务事件
                    if _get_task_events_via_grpc(task_id) is None:
                        # 重新注册事件
                        if task_id not in self.pause_flags:
                            self.pause_flags[task_id] = threading.Event()
                        if task_id not in self.stop_flags:
                            self.stop_flags[task_id] = threading.Event()
                        # 跨服务调用：通过 gRPC DeviceService 注册任务事件
                        _register_task_events_via_grpc(task_id, self.stop_flags[task_id], self.pause_flags[task_id])

                    self.pause_flags[task_id].set()  # 设置暂停标志，恢复执行
                    # 清除分布式暂停信号（多实例下通知所有实例恢复执行）
                    _dc.clear_flag(f'task:pause:{task_id}')
                    # 通过 gRPC 通知 e2e_test_service 同步恢复事件
                    _register_task_events_via_grpc(
                        task_id, self.stop_flags[task_id], self.pause_flags[task_id]
                    )
                    task.status = 'running'  # 更新任务状态
                    local_db_session.commit()
                    self._emit_progress(task)  # 发送进度更新
                    return True, "任务已恢复"
                return False, "无效的操作指令"
        finally:
            local_db_session.close()
