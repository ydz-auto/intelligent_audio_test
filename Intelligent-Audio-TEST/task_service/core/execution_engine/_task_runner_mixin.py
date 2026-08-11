import time
from datetime import datetime
from task_service.infrastructure.persistence.models import Task, TaskCase, TestCase
from shared.models.database import get_db_session


class TaskRunnerMixin:
    """任务执行核心逻辑：包含 _run_task 及其拆分出的子方法"""

    def _run_task(self, task_id, stop_event, pause_event):
        """执行测试任务的核心方法

        Args:
            task_id: 任务ID
            stop_event: 停止事件，用于通知任务停止
            pause_event: 暂停事件，用于通知任务暂停/恢复
        """
        try:
            from task_service.infrastructure.persistence.models import Log, TaskCase
            from shared.models.database import remove_db_session

            # 使用本地会话获取任务对象（初始设置，765-797）
            local_db_session = get_db_session()
            try:
                # 获取任务对象
                task = local_db_session.get(Task, task_id)
                if not task:
                    self._log(
                        level='ERROR',
                        content=f"任务 {task_id} 不存在，无法执行",
                        task_id=task_id
                    )
                    return

                # 记录任务开始日志
                self._log(
                    level='INFO',
                    content=f"开始执行任务 {task_id}, 类型: {task.type}",
                    task_id=task_id
                )

                # 更新任务状态为运行中，并记录开始时间
                task.status = 'running'
                task.started_at = datetime.now(self.utc_plus_8)
                local_db_session.commit()
                # 发送进度更新，传递task对象以便触发强制更新逻辑
                self._emit_progress(task)
            finally:
                local_db_session.close()

            try:
                # API任务初始化（799-860）
                should_continue = self._init_task_execution(task_id)
                if not should_continue:
                    return

                # 主循环：处理测试用例（862-1170）
                self._process_task_main_loop(task_id, stop_event, pause_event)

                # 检查是否所有测试用例都已执行完成，提前更新任务状态（1172-1230）
                task = self._update_post_loop_status(task_id)

                # 等待所有测试用例执行完成（1232-1444）
                self._wait_for_cases_completion(task_id, task, stop_event)

                # 最终状态更新（1446-1520）
                self._finalize_task_status(task_id, task, stop_event)
            except Exception as e:
                # 异常处理（1522-1621）
                self._handle_task_exception(task_id, e)
            finally:
                # 清理任务资源（1622-1690）
                self._cleanup_task_resources(task_id, stop_event)
        finally:
            # 后台线程结束时清理本线程 DB session，防止连接泄漏
            try:
                from shared.models.database import remove_db_session
                remove_db_session()
            except Exception:
                pass

    def _init_task_execution(self, task_id):
        """API任务初始化（799-860）

        Returns:
            True 表示初始化成功，False 表示任务不存在或初始化失败
        """
        # 使用本地会话确保独立可靠的会话
        local_db_session = get_db_session()
        try:
            # 重新获取任务对象，确保它在有效会话中
            task = local_db_session.get(Task, task_id)
            if not task:
                self._log(
                    level='ERROR',
                    content=f"任务 {task_id} 不存在，无法执行",
                    task_id=task_id
                )
                return False

            # API任务初始化
            if task.type == 'api':
                try:
                    from task_service.infrastructure.persistence.models import TaskAPI
                    # 获取API配置
                    task_api = local_db_session.query(TaskAPI).filter_by(task_id=task.id).first()
                    api_config = None
                    if task_api:
                        # P3 改造：通过 gRPC 调用 api_test_service 获取 API 配置，替代直连 PO
                        try:
                            from shared.clients.grpc_clients import get_api_test_service_stub
                            from shared.proto import api_test_service_pb2 as api_pb
                            from shared.utils.grpc_json import loads as _loads
                            stub = get_api_test_service_stub()
                            resp = stub.GetAPIConfig(api_pb.GetAPIConfigRequest(api_id=task_api.api_id))
                            if resp.success and resp.data:
                                api_config = _loads(resp.data, {})
                        except Exception as grpc_e:
                            self._log(
                                level='WARNING',
                                content=f"通过 gRPC 获取 API 配置失败 (api_id={task_api.api_id}): {str(grpc_e)}",
                                task_id=task_id
                            )

                    # 获取可用的API端点
                    # 注意：gRPC 返回的 dict 中端点字段名为 'endpoints'（对应 _api_to_dict）
                    available_endpoints = []
                    if api_config and api_config.get('endpoints'):
                        available_endpoints = [ep for ep in api_config.get('endpoints') if ep.get('status') == 'online']
                        available_endpoints.sort(key=lambda x: x.get('priority', 0), reverse=True)

                    # 确定最大工作线程数
                    if available_endpoints:
                        # 计算所有可用端点的最大进程数之和
                        max_workers = sum(ep.get('max_process', 5) for ep in available_endpoints)
                    elif api_config:
                        max_workers = api_config.get('default_max_process', 5)
                    else:
                        max_workers = 5

                    # 保存API配置和可用端点到任务对象
                    task._api_config = api_config
                    task._available_endpoints = available_endpoints

                    # 微服务化后：不再创建本地线程池，API 用例通过 gRPC 调用 api_test_service 执行
                    # api_test_service 内部管理自己的线程池和并发控制
                    self._log(
                        level='INFO',
                        content=f"API任务 {task_id} 初始化成功，执行下沉到 api_test_service",
                        task_id=task_id,
                        api_id=api_config.get('id') if api_config else None
                    )
                except Exception as e:
                    self._log(
                        level='ERROR',
                        content=f"API任务 {task_id} 初始化失败: {str(e)}",
                        task_id=task_id
                    )
                    # API任务初始化失败，将任务标记为失败
                    task.status = 'failed'
                    task.completed_at = datetime.now(self.utc_plus_8)
                    task.error_message = f"API任务初始化失败: {str(e)}"
                    local_db_session.commit()
                    return False
        finally:
            local_db_session.close()

        return True

    def _process_task_main_loop(self, task_id, stop_event, pause_event):
        """主循环：处理测试用例（862-1170）"""
        while not stop_event.is_set():
            # 使用本地会话确保独立可靠的会话
            local_db_session = get_db_session()
            try:
                # 重新获取任务对象，确保它在有效会话中
                task = local_db_session.get(Task, task_id)
                if not task:
                    self._log(
                        level='ERROR',
                        content=f"任务 {task_id} 不存在，无法执行",
                        task_id=task_id
                    )
                    break

                # 获取下一个待执行的测试用例
                tc_rel = local_db_session.query(TaskCase).filter_by(
                    task_id=task_id,
                    execution_status='pending'
                ).order_by(TaskCase.created_at.asc()).first()

                if not tc_rel:
                    # 对于API任务，检查是否还有正在执行或评估的用例
                    if task.type == 'api':
                        # 检查是否有正在执行或评估的用例
                        in_progress_count = local_db_session.query(TaskCase).filter(
                            TaskCase.task_id == task_id,
                            TaskCase.execution_status.in_(['queued', 'running'])
                        ).count()

                        # 检查是否有正在评估的用例（评估可能在执行完成后才开始）
                        evaluating_count = local_db_session.query(TaskCase).filter(
                            TaskCase.task_id == task_id,
                            TaskCase.evaluation_status.in_(['running', 'calculating', 'queued', 'pending'])
                        ).count()

                        if in_progress_count > 0 or evaluating_count > 0:
                            # 有用例正在执行或评估，等待完成事件通知
                            total_in_progress = in_progress_count + evaluating_count
                            self._log(
                                level='DEBUG',
                                content=f"等待 {total_in_progress} 个执行中/评估中的用例完成 (执行中: {in_progress_count}, 评估中: {evaluating_count})...",
                                task_id=task_id
                            )

                            # 释放当前数据库会话，等待事件通知
                            local_db_session.close()

                            # 事件驱动等待：评估/执行完成时会被 notify_case_completed 唤醒
                            completion_event = self.task_completion_events.get(task_id)
                            if completion_event:
                                completion_event.wait(timeout=5)
                            else:
                                time.sleep(1)

                            # 继续下一次循环检查
                            continue

                    # 确认没有待执行和执行中的用例，真正完成
                    self._log(
                        level='INFO',
                        content=f"任务 {task_id} 所有用例执行完成，退出主循环",
                        task_id=task_id
                    )
                    break

                # 检查是否需要暂停
                if not pause_event.is_set():
                    self._emit_progress(task)
                    pause_event.wait()  # 等待暂停标志被设置（恢复执行）

                # 检查是否需要停止
                if stop_event.is_set():
                    break

                # 设备状态检查（仅E2E任务需要）
                device_check_passed, error_message = self._check_e2e_devices(
                    task_id, task, tc_rel, local_db_session
                )

                # 设备检查失败处理
                if not device_check_passed:
                    tc_rel.status = 'failed'
                    tc_rel.execution_status = 'failed'  # 更新execution_status为failed，避免死循环
                    tc_rel.completed_at = datetime.now(self.utc_plus_8)
                    tc_rel.duration = 0
                    tc_rel.error_message = error_message
                    local_db_session.commit()

                    # 更新任务统计信息
                    success_count = local_db_session.query(TaskCase).filter(
                        TaskCase.task_id == task_id,
                        TaskCase.status == 'completed'
                    ).count()
                    task.completed_cases = success_count
                    task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='failed').count()
                    local_db_session.commit()

                    # 发送告警和进度更新
                    self._emit_alert(task_id, error_message)
                    self._emit_progress(task)
                    continue

                # 不预先设置状态，状态由执行引擎内部管理
                # pending → running → completed/failed
                # 注意：只有真正进入等待队列的用例才会被统计为"排队中"

                # 重新获取任务对象以避免 detached instance 问题
                task = local_db_session.get(Task, task_id)
                if not task:
                    continue

                # 根据任务类型执行测试用例
                if task.type == 'api':
                    try:
                        # 原子占用用例，避免重复提交
                        tc_rel_id = tc_rel.id
                        claimed = local_db_session.query(TaskCase).filter(
                            TaskCase.id == tc_rel_id,
                            TaskCase.task_id == task_id,
                            TaskCase.execution_status == 'pending'
                        ).update(
                            {
                                TaskCase.execution_status: 'queued',
                                TaskCase.status: 'running'
                            },
                            synchronize_session=False
                        )
                        if claimed != 1:
                            local_db_session.rollback()
                            continue
                        local_db_session.commit()

                        # 微服务化后：直接同步通过 gRPC 调用 api_test_service 执行
                        # api_test_service 内部管理自己的线程池和并发控制
                        self._execute_api_case(task_id, tc_rel_id)
                        continue
                    except Exception as e:
                        # API任务执行异常，标记为失败，不执行E2E流程
                        self._log(
                            level='ERROR',
                            content=f"API任务执行异常: {str(e)}",
                            task_id=task_id
                        )
                        tc_rel.status = 'failed'
                        tc_rel.execution_status = 'failed'
                        tc_rel.error_message = f"API任务执行异常: {str(e)}"
                        local_db_session.commit()
                        continue
                else:
                    # E2E任务直接执行
                    # 注意：这里会阻塞直到E2E用例执行完成
                    success = self._execute_e2e_case(task_id, tc_rel.id)

                    # 重新获取tc_rel对象，因为execute_e2e_case方法内部可能已经更新了它
                    tc_rel = local_db_session.get(TaskCase, tc_rel.id)

                    # 更新任务统计信息
                    success_count = local_db_session.query(TaskCase).filter(
                        TaskCase.task_id == task_id,
                        TaskCase.status == 'completed'
                    ).count()
                    task.completed_cases = success_count
                    task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='failed').count()

                    # 发送告警（如果执行失败）
                    if not success:
                        # E2E执行失败时，若用例仍停留在pending（gRPC内部未自行更新状态），
                        # 必须将状态置为failed，避免while循环反复取到同一个用例造成死循环
                        if tc_rel.execution_status not in ('completed', 'failed'):
                            tc_rel.execution_status = 'failed'
                            tc_rel.status = 'failed'
                            # 评估状态也置为completed，避免后续任务级状态判定误认为"评估中"
                            tc_rel.evaluation_status = 'completed'
                            tc_rel.completed_at = datetime.now(self.utc_plus_8)
                            tc_rel.error_message = tc_rel.error_message or 'E2E用例执行失败（gRPC返回失败或异常）'
                        self._emit_alert(task_id, f"用例执行失败: {tc_rel.test_case_id}")

                local_db_session.commit()
                self._emit_progress(task)  # 发送进度更新
            finally:
                local_db_session.close()

    def _check_e2e_devices(self, task_id, task, tc_rel, local_db_session):
        """检查E2E设备状态（937-1068）

        Args:
            task_id: 任务ID
            task: 任务对象
            tc_rel: 任务用例关联对象
            local_db_session: 数据库会话

        Returns:
            tuple: (device_check_passed, error_message)
        """
        device_check_passed = True
        error_message = ""

        if task.type == 'e2e':
            self._log(
                level='DEBUG',
                content=f"开始检查设备状态: 任务ID={task_id}, 用例ID={tc_rel.id}",
                task_id=task_id
            )

            from task_service.infrastructure.persistence.models import TaskDevice
            task_device_relations = local_db_session.query(TaskDevice).filter_by(task_id=task_id).all()
            device_ids = [rel.device_id for rel in task_device_relations]

            self._log(
                level='DEBUG',
                content=f"设备关联信息: 关联数={len(task_device_relations)}, 设备ID列表={device_ids}",
                task_id=task_id
            )

            if not device_ids:
                device_check_passed = True
                self._log(
                    level='DEBUG',
                    content=f"没有关联设备，设备检查通过",
                    task_id=task_id
                )
            else:
                # P3 改造：通过 gRPC 调用 e2e_test_service 的 DeviceConfigService.GetDeviceStatuses
                # 批量获取设备状态，替代直连 Device PO
                devices = []
                try:
                    import json as _json
                    from shared.clients.grpc_clients import get_device_config_service_stub
                    from shared.proto import device_service_pb2 as e2e_pb
                    from shared.utils.grpc_json import loads as _loads
                    stub = get_device_config_service_stub()
                    resp = stub.GetDeviceStatuses(e2e_pb.GetDeviceStatusesRequest(
                        data=_json.dumps({'ids': device_ids}),
                    ))
                    if resp.success and resp.data:
                        payload = _loads(resp.data, {})
                        devices = payload.get('items', []) if isinstance(payload, dict) else []
                except Exception as grpc_e:
                    self._log(
                        level='ERROR',
                        content=f"通过 gRPC 获取设备状态失败: {str(grpc_e)}",
                        task_id=task_id
                    )
                self._log(
                    level='DEBUG',
                    content=f"查询到设备数量={len(devices)}",
                    task_id=task_id
                )
                for device in devices:
                    device_status = device.get('status')
                    self._log(
                        level='DEBUG',
                        content=f"检查设备状态: 设备ID={device.get('id')}, 设备名称={device.get('name')}, 状态={device_status}",
                        task_id=task_id,
                        device_id=device.get('id')
                    )
                    if device_status != 'online':
                        device_check_passed = False
                        error_message = f"被测设备 {device.get('name')} 离线，无法执行测试"
                        self._log(
                            level='ERROR',
                            content=error_message,
                            task_id=task_id,
                            device_id=device.get('id')
                        )
                        break
            # else:
            #     self._log(
            #         level='DEBUG',
            #         content=f"跳过设备检查 (API任务不需要): 任务ID={task_id}, 用例ID={tc_rel.id}",
            #         task_id=task_id
            #     )

            # 检查播放设备状态 - 只有E2E测试需要检查播放设备
            if device_check_passed and task.type == 'e2e':
                self._log(
                    level='DEBUG',
                    content=f"开始检查播放设备状态",
                    task_id=task_id
                )
                case = local_db_session.get(TestCase, tc_rel.test_case_id)
                if case:
                    playback_devices = set()
                    # 从配置中获取音频播放设备
                    # audios 存储在 rounds[].audios 中（rounds-as-top-level 格式）
                    config = case.config or {}
                    rounds = config.get('rounds', []) if isinstance(config, dict) else []
                    audios = []
                    for round_item in rounds:
                        if isinstance(round_item, dict):
                            round_audios = round_item.get('audios', [])
                            if isinstance(round_audios, list):
                                audios.extend(round_audios)
                    self._log(
                        level='DEBUG',
                        content=f"E2E用例配置: 音频数量={len(audios)}",
                        task_id=task_id
                    )
                    for audio in audios:
                        pb_dev_id = audio.get('playback_device_id')
                        if pb_dev_id:
                            playback_devices.add(pb_dev_id)

                    self._log(
                        level='DEBUG',
                        content=f"播放设备ID集合: {playback_devices}",
                        task_id=task_id
                    )

                    # 检查播放设备状态
                    for device_id in playback_devices:
                        # P3 改造：通过 gRPC 调用 e2e_test_service 的
                        # PlaybackConfigService.GetPlaybackDevice 获取播放设备，替代直连 PO
                        playback_dev = None
                        try:
                            from shared.clients.grpc_clients import get_playback_config_service_stub
                            from shared.proto import device_service_pb2 as e2e_pb
                            from shared.utils.grpc_json import loads as _loads
                            stub = get_playback_config_service_stub()
                            resp = stub.GetPlaybackDevice(e2e_pb.GetPlaybackDeviceRequest(
                                device_id=int(device_id),
                            ))
                            if resp.success and resp.data:
                                playback_dev = _loads(resp.data, {})
                        except Exception as grpc_e:
                            self._log(
                                level='ERROR',
                                content=f"通过 gRPC 获取播放设备失败 (id={device_id}): {str(grpc_e)}",
                                task_id=task_id
                            )
                        if playback_dev:
                            pb_dev_status = playback_dev.get('status')
                            self._log(
                                level='DEBUG',
                                content=f"检查播放设备: 设备ID={device_id}, 设备名称={playback_dev.get('name')}, 状态={pb_dev_status}",
                                task_id=task_id
                            )
                            if pb_dev_status != 'online':
                                device_check_passed = False
                                error_message = f"播放设备 {playback_dev.get('name')} 离线，无法执行测试"
                                self._log(
                                    level='ERROR',
                                    content=error_message,
                                    task_id=task_id
                                )
                                break
                        else:
                            device_check_passed = False
                            error_message = f"找不到播放设备，ID: {device_id}"
                            self._log(
                                level='ERROR',
                                content=error_message,
                                task_id=task_id
                            )
                            break
                else:
                    self._log(
                        level='DEBUG',
                        content=f"未找到测试用例: {tc_rel.test_case_id}",
                        task_id=task_id
                    )

        return device_check_passed, error_message

    def _update_post_loop_status(self, task_id):
        """检查是否所有测试用例都已执行完成，提前更新任务状态（1172-1230）

        Returns:
            task 对象（可能为 None）
        """
        local_db_session = get_db_session()
        try:
            task = local_db_session.get(Task, task_id)
            if task:
                # 获取所有测试用例
                all_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id).count()
                # 获取已处理的测试用例（状态为completed/failed/skipped）
                all_processed_cases = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.status.in_(['completed', 'failed', 'skipped'])
                ).count()
                # 获取运行中的测试用例 (只包括执行中、排队中，不包括评估中/待评估)
                running_cases = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.execution_status.in_(['running', 'queued'])
                ).count()
                failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='failed').count()
                completed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='completed').count()

                # 如果所有测试用例都已处理完成，提前更新任务状态
                if all_processed_cases == all_cases and running_cases == 0:
                    # 检查是否还有用例在评估中
                    evaluating_cases = local_db_session.query(TaskCase).filter(
                        TaskCase.task_id == task_id,
                        TaskCase.evaluation_status.in_(['running', 'calculating', 'queued', 'pending'])
                    ).count()

                    if evaluating_cases > 0:
                        # 还有用例在评估中，设为 evaluating 过渡态
                        task.status = 'evaluating'
                    elif all_cases > 0:
                        if failed_cases > 0:
                            task.status = 'failed'
                        else:
                            task.status = 'completed'
                    else:
                        task.status = 'completed'

                    # 提前更新任务状态和统计信息，后续等待循环会继续监控评估完成
                    # 最终状态由评估服务的 _post_evaluate_updates 统一确认

                    if task.status in ['completed', 'failed']:
                        # 更新任务完成时间和实际执行时长
                        task.completed_at = datetime.now(self.utc_plus_8)
                        if task.started_at:
                            # 确保 started_at 是带时区的 datetime 对象
                            if task.started_at.tzinfo is None:
                                task.started_at = task.started_at.replace(tzinfo=self.utc_plus_8)
                            # 计算实际执行时长（秒）
                            task.actual_duration = int((task.completed_at - task.started_at).total_seconds())
                    # 更新任务的已完成用例数和失败用例数
                    task.completed_cases = completed_cases
                    task.failed_cases = failed_cases
                    local_db_session.commit()
                    # 发送最终进度更新
                    self._emit_progress(task)
        finally:
            local_db_session.close()

        return task

    def _wait_for_cases_completion(self, task_id, task, stop_event):
        """API/E2E任务：等待所有测试用例执行完成（1232-1444）"""
        if task.type not in ('api', 'e2e'):
            return

        # 等待所有测试用例的执行状态都不是running或queued
        max_wait_time = self.test_case_wait_time  # 从配置文件读取的超时时间
        wait_start_time = time.time()
        last_log_time = 0
        last_counts = None

        # 需要获取 all_cases 数量，用于后续日志输出
        local_db_session = get_db_session()
        try:
            all_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id).count()
        finally:
            local_db_session.close()

        while True:
            local_db_session = get_db_session()
            try:
                local_db_session.expire_all()

                task_obj = local_db_session.query(Task).filter_by(id=task_id).first()
                task_status = task_obj.status if task_obj else 'unknown'

                from sqlalchemy import func
                status_counts = local_db_session.query(
                    TaskCase.execution_status,
                    TaskCase.evaluation_status,
                    TaskCase.status,
                    func.count(TaskCase.id)
                ).filter(TaskCase.task_id == task_id).group_by(
                    TaskCase.execution_status,
                    TaskCase.evaluation_status,
                    TaskCase.status
                ).all()

                running_cases = 0
                queued_cases = 0
                execution_running_cases = 0
                execution_success_cases = 0
                execution_failed_cases = 0
                evaluation_running_cases = 0
                evaluation_success_cases = 0
                evaluation_failed_cases = 0
                all_processed_cases = 0
                passed_cases = 0
                failed_cases = 0

                for exec_status, eval_status, final_status, count in status_counts:
                    if exec_status in ['running', 'queued']:
                        running_cases += count
                    if exec_status == 'queued':
                        queued_cases += count
                    if exec_status == 'running':
                        execution_running_cases += count
                    if exec_status == 'completed':
                        execution_success_cases += count
                    if exec_status == 'failed':
                        execution_failed_cases += count
                    if eval_status in ['running', 'queued']:
                        evaluation_running_cases += count
                    if eval_status == 'completed':
                        evaluation_success_cases += count
                    if eval_status == 'failed':
                        evaluation_failed_cases += count
                    if final_status in ['completed', 'failed', 'skipped']:
                        all_processed_cases += count
                    if final_status == 'completed':
                        passed_cases += count
                    if final_status == 'failed':
                        failed_cases += count

                current_counts = (
                    running_cases, queued_cases, execution_running_cases, evaluation_running_cases,
                    execution_success_cases, evaluation_success_cases,
                    failed_cases, execution_failed_cases, evaluation_failed_cases,
                    all_processed_cases, task_status
                )

                # 添加详细调试日志
                self._log(
                    level='DEBUG',
                    content=f"任务 {task_id} 统计结果: "
                           f"all_cases={all_cases}, "
                           f"running={running_cases}, "
                           f"all_processed={all_processed_cases}, "
                           f"evaluation_success={evaluation_success_cases}, "
                           f"evaluation_failed={evaluation_failed_cases}",
                    task_id=task_id
                )

                # 检查任务是否已停止
                if task_status == 'stopped':
                    # 任务已停止，将所有未完成的测试用例标记为失败
                    uncompleted_cases = local_db_session.query(TaskCase).filter(
                        TaskCase.task_id == task_id,
                        TaskCase.execution_status.in_(['running', 'queued'])
                    ).all()
                    for tc in uncompleted_cases:
                        tc.status = 'failed'
                        tc.execution_status = 'failed'
                        tc.completed_at = datetime.now(self.utc_plus_8)
                        tc.duration = 0
                        tc.error_message = '任务被停止，用例执行中断'
                    local_db_session.commit()

                    self._log(
                        level='INFO',
                        content=f"任务已停止，标记 {len(uncompleted_cases)} 个未完成用例为失败",
                        task_id=task_id
                    )
                    break

                # 当所有用例都已处理完成（无论成功失败），退出等待
                if running_cases == 0 and all_processed_cases == all_cases:
                    # 检查是否还有用例在评估中
                    evaluating_cases = local_db_session.query(TaskCase).filter(
                        TaskCase.task_id == task_id,
                        TaskCase.evaluation_status.in_(['running', 'calculating', 'queued', 'pending'])
                    ).count()

                    if evaluating_cases > 0:
                        # 还有用例在评估中，事件驱动等待
                        self._log(
                            level='INFO',
                            content=f"等待测试用例执行完成 |任务状态：{task_status} 总用例数: {all_cases}, 运行中: {running_cases} (排队中: {queued_cases}, 执行中: {execution_running_cases}, 评估中: {evaluation_running_cases}, 执行成功: {execution_success_cases}), 已完成： {all_cases -running_cases}(评估成功: {evaluation_success_cases}, 失败: {failed_cases} (执行失败: {execution_failed_cases}, 评估失败: {evaluation_failed_cases}))",
                            task_id=task_id
                        )
                        local_db_session.close()
                        completion_event = self.task_completion_events.get(task_id)
                        if completion_event:
                            completion_event.wait(timeout=5)
                        else:
                            time.sleep(1)
                        continue

                    # 注意：不在此处更新任务状态，由评估服务的 _post_evaluate_updates 统一更新
                    # 避免执行引擎和评估服务重复更新导致状态不一致
                    task_obj = local_db_session.query(Task).filter_by(id=task_id).first()
                    if task_obj:
                        task_obj.completed_cases = passed_cases
                        task_obj.failed_cases = failed_cases
                        local_db_session.commit()
                        # 更新task_status为新状态，确保日志中显示正确状态
                        task_status = task_obj.status

                    self._log(
                        level='INFO',
                        content=f"等待测试用例执行完成 |任务状态：{task_status} 总用例数: {all_cases}, 运行中: {running_cases} (排队中: {queued_cases}, 执行中: {execution_running_cases}, 评估中: {evaluation_running_cases}, 执行成功: {execution_success_cases}), 已完成： {all_cases -running_cases}(评估成功: {evaluation_success_cases}, 失败: {failed_cases} (执行失败: {execution_failed_cases}, 评估失败: {evaluation_failed_cases}))",
                        task_id=task_id
                    )
                    break
                elif running_cases == 0:
                    # 特殊情况：所有用例都已完成运行，但可能存在状态未更新的情况
                    # 检查每个用例的状态，确保它们都被正确标记为completed或failed
                    all_task_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id).all()
                    updated = False
                    for tc in all_task_cases:
                        if tc.status not in ['completed', 'failed', 'skipped']:
                            # 如果用例状态不是completed或failed，根据执行状态和评估状态推断
                            if tc.execution_status == 'completed':
                                # 执行完成，检查评估状态
                                if tc.evaluation_status == 'completed':
                                    tc.status = 'completed'
                                    tc.completed_at = datetime.now(self.utc_plus_8)
                                elif tc.evaluation_status == 'failed':
                                    # 评估失败，标记为失败
                                    tc.status = 'failed'
                                    tc.completed_at = datetime.now(self.utc_plus_8)
                                elif tc.evaluation_status in ['running', 'queued', 'pending']:
                                    # 如果还在评估中或待评估，保持running状态，不标记为失败
                                    tc.status = 'running'
                                    continue
                                else:
                                    # 其他评估状态（如unknown等），标记为失败
                                    tc.status = 'failed'
                                    tc.completed_at = datetime.now(self.utc_plus_8)
                            else:
                                # 执行未完成，标记为失败
                                tc.status = 'failed'
                                tc.completed_at = datetime.now(self.utc_plus_8)
                            updated = True
                    if updated:
                        local_db_session.commit()
                        self._log(
                            level='DEBUG',
                            content=f"修复用例状态 |任务ID：{task_id} 更新了 {sum(1 for tc in all_task_cases if tc.status not in ['completed', 'failed'])} 个用例的状态",
                            task_id=task_id
                        )

                # 仅在状态变化或超过10秒时记录日志
                current_time = time.time()
                if current_counts != last_counts or current_time - last_log_time >= 10:
                    self._log(
                        level='INFO',
                        content=f"等待测试用例执行完成 |任务状态：{task_status} 总用例数: {all_cases}, 运行中: {running_cases} (排队中: {queued_cases}, 执行中: {execution_running_cases}, 评估中: {evaluation_running_cases}, 执行成功: {execution_success_cases}), 已完成： {all_cases -running_cases}(评估成功: {evaluation_success_cases}, 失败: {failed_cases} (执行失败: {execution_failed_cases}, 评估失败: {evaluation_failed_cases}))",
                        task_id=task_id
                    )
                    last_log_time = current_time
                    last_counts = current_counts

                if time.time() - wait_start_time > max_wait_time:
                    self._log(
                        level='WARNING',
                        content=f"等待测试用例执行完成超时，还有 {running_cases} 个用例状态为running或queued",
                        task_id=task_id
                    )
                    break
                # 事件驱动等待：评估/执行完成时会被 notify_case_completed 唤醒
                local_db_session.close()
                completion_event = self.task_completion_events.get(task_id)
                if completion_event:
                    completion_event.wait(timeout=5)
                else:
                    time.sleep(2)
                continue
            finally:
                try:
                    local_db_session.close()
                except Exception:
                    pass

    def _finalize_task_status(self, task_id, task, stop_event):
        """最终状态更新（1446-1520）"""
        # 检查任务状态，如果是暂停状态则保持暂停，不改变状态
        if task.status != 'paused':
            # 使用本地会话确保独立可靠的会话
            local_db_session = get_db_session()
            try:
                # 重新获取任务对象，确保它在有效会话中
                task = local_db_session.get(Task, task_id)
                if not task:
                    # 任务不存在，直接返回，不继续处理
                    return

                # 根据停止事件和执行结果更新任务状态
                if stop_event.is_set():
                    task.status = 'stopped'
                else:
                    # 检查是否所有测试用例都失败
                    all_cases = local_db_session.query(TaskCase).filter_by(task_id=task.id).count()
                    failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task.id, status='failed').count()
                    all_processed_cases = local_db_session.query(TaskCase).filter(
                        TaskCase.task_id == task.id,
                        TaskCase.status.in_(['completed', 'failed', 'skipped'])
                    ).count()

                    # 成功完成的用例数量
                    successfully_completed_cases = local_db_session.query(TaskCase).filter_by(
                        task_id=task.id,
                        status='completed'
                    ).count()

                    # 动态更新任务的total_cases字段，确保进度计算准确
                    task.total_cases = all_cases

                    # 确保所有测试用例都已处理完成
                    if all_processed_cases == all_cases:
                        if failed_cases > 0:
                            task.status = 'failed'
                        else:
                            task.status = 'completed'
                    else:
                        # 如果还有测试用例未完成，标记为失败
                        task.status = 'failed'
                        # 将所有未处理的测试用例标记为失败，避免任务被重新执行
                        unprocessed_cases = local_db_session.query(TaskCase).filter(
                            TaskCase.task_id == task.id,
                            TaskCase.status.notin_(['completed', 'failed', 'skipped'])
                        ).all()
                        for tc in unprocessed_cases:
                            tc.status = 'failed'
                            tc.execution_status = 'failed'
                            tc.completed_at = datetime.now(self.utc_plus_8)
                            tc.duration = 0
                            tc.error_message = "任务执行失败，未处理的用例被标记为失败"

                # 记录任务完成时间和实际执行时长
                task.completed_at = datetime.now(self.utc_plus_8)
                if task.started_at:
                    # 确保 started_at 是带时区的 datetime 对象
                    if task.started_at.tzinfo is None:
                        task.started_at = task.started_at.replace(tzinfo=self.utc_plus_8)
                    # 计算实际执行时长（秒）
                    task.actual_duration = int((task.completed_at - task.started_at).total_seconds())

                # 更新任务的已完成用例数和失败用例数
                success_count = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.status == 'completed'
                ).count()
                task.completed_cases = success_count
                task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='failed').count()

                local_db_session.commit()
                # 在关闭会话前发送任务完成进度更新
                self._emit_progress(task)
            finally:
                local_db_session.close()

    def _handle_task_exception(self, task_id, e):
        """异常处理（1522-1621）"""
        import traceback
        error_trace = traceback.format_exc()

        # 使用本地会话确保独立可靠的会话
        local_db_session = get_db_session()
        try:
            # 重新获取任务对象，确保它在有效会话中
            task = local_db_session.get(Task, task_id)
            if not task:
                self._log(
                    level='ERROR',
                    content=f"任务 {task_id} 不存在，无法更新状态",
                    task_id=task_id
                )
                # 任务不存在，直接返回，不继续处理
                return

            # 更新所有正在执行的测试用例状态为 failed
            running_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, execution_status='running').all()
            for tc_rel in running_cases:
                tc_rel.status = 'failed'
                tc_rel.execution_status = 'failed'
                tc_rel.completed_at = datetime.now(self.utc_plus_8)
                if tc_rel.started_at:
                    # 确保两个datetime对象都具有相同的时区信息
                    try:
                        if tc_rel.started_at.tzinfo is None:
                            # 如果started_at不带时区，将其转换为带时区的datetime对象
                            started_at_with_tz = tc_rel.started_at.replace(tzinfo=self.utc_plus_8)
                            completed_at_with_tz = datetime.now(self.utc_plus_8)
                        else:
                            started_at_with_tz = tc_rel.started_at
                            completed_at_with_tz = datetime.now(self.utc_plus_8)
                        # 计算执行时长
                        tc_rel.duration = int((completed_at_with_tz - started_at_with_tz).total_seconds())
                    except Exception as duration_error:
                        # 如果计算失败，设置时长为0
                        tc_rel.duration = 0
                tc_rel.error_message = f"任务执行异常: {str(e)}"

            # 更新任务状态为失败
            task.status = 'failed'
            task.completed_at = datetime.now(self.utc_plus_8)
            if task.started_at:
                # 确保两个datetime对象都具有相同的时区信息
                if task.started_at.tzinfo is None:
                    started_at_with_tz = task.started_at.replace(tzinfo=self.utc_plus_8)
                    completed_at_with_tz = task.completed_at
                elif task.completed_at.tzinfo is None:
                    started_at_with_tz = task.started_at
                    completed_at_with_tz = task.completed_at.replace(tzinfo=self.utc_plus_8)
                else:
                    started_at_with_tz = task.started_at
                    completed_at_with_tz = task.completed_at
                # 计算实际执行时长
                task.actual_duration = int((completed_at_with_tz - started_at_with_tz).total_seconds())

            # 更新任务统计信息
            task.completed_cases = local_db_session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.status == 'completed'
            ).count()
            task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='failed').count()

            local_db_session.commit()

            # 记录详细错误日志
            self._log(
                level='ERROR',
                content=f"任务 {task_id} 执行失败: {str(e)}\n{error_trace}",
                task_id=task_id
            )

            # 发送告警和进度更新
            self._emit_alert(task_id, f"任务执行异常: {str(e)}")
            self._emit_progress(task)

            # 记录错误日志
            self._log(
                level='ERROR',
                content=f"执行任务 {task_id} 时发生错误: {str(e)}",
                task_id=task_id
            )
            self._log(
                level='DEBUG',
                content=f"错误详情: {error_trace}",
                task_id=task_id
            )
        except Exception as ex:
            # 记录会话操作异常
            self._log(
                level='ERROR',
                category='database',
                content=f"处理任务异常时发生数据库会话错误: {str(ex)}\n{traceback.format_exc()}",
                task_id=task_id
            )
        finally:
            local_db_session.close()

    def _cleanup_task_resources(self, task_id, stop_event):
        """清理任务资源（1622-1690）"""
        # 重新检查任务状态，决定是否清理资源
        should_cleanup = True
        local_db_session = get_db_session()
        try:
            task = local_db_session.get(Task, task_id)
            # 只有当任务明确处于 'paused' 状态时，才保留资源（以便恢复）
            # 如果任务被停止 ('stopped')、完成 ('completed') 或失败 ('failed')，必须清理
            if task and task.status == 'paused' and not stop_event.is_set():
                should_cleanup = False
        except Exception as e:
            self._log(level='WARNING', content=f"获取任务状态失败，默认清理资源: {str(e)}", task_id=task_id)
        finally:
            local_db_session.close()

        if should_cleanup:
            # 清理运行状态
            with self.queue_lock:
                if task_id in self.running_tasks:
                    task_type = self.running_tasks[task_id]
                    del self.running_tasks[task_id]

                    if task_type == 'e2e':
                        self.running_e2e = False
                    else:
                        # 释放占用的 API ID
                        local_db_session = get_db_session()
                        try:
                            from task_service.infrastructure.persistence.models import TaskAPI
                            task_apis = local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
                            for api_rel in task_apis:
                                if api_rel.api_id in self.running_apis:
                                    self.running_apis.remove(api_rel.api_id)
                        finally:
                            local_db_session.close()

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
                cleanup_session = get_db_session()
                try:
                    tc_rel_ids = [
                        tc_id for (tc_id,) in
                        cleanup_session.query(TaskCase.id).filter_by(task_id=task_id).all()
                    ]
                    for tc_rel_id in tc_rel_ids:
                        self.round_progress_cache.pop(tc_rel_id, None)
                finally:
                    cleanup_session.close()
            except Exception:
                pass

            # 检查队列并启动下一个任务
            self._check_queue()
