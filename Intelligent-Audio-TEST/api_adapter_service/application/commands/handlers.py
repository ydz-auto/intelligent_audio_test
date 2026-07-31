# -*- coding: utf-8 -*-
"""命令处理器：委托给已有的 services/ 与 adapters/。

应用层只做用例编排，不实现具体 IO 逻辑：
- 会话状态 → services.session_store
- 任务/结果 → services.task_manager
- 适配器选择/调用 → adapters.factory.select_adapter
- 配置 → utils.config
"""

import uuid

from api_adapter_service.application.commands.dialog_commands import (
    CreateDialogTaskCommand,
    CloseSessionCommand,
)
from api_adapter_service.services.session_store import session_store
from api_adapter_service.services.task_manager import task_manager
from api_adapter_service.adapters.factory import select_adapter
from api_adapter_service.utils.config import config
from api_adapter_service.utils.logger import logger


class CreateDialogTaskHandler:
    """创建并执行一轮对话任务。

    对应 routes/api.py 中 /api/v1/tasks 的同步逻辑。
    不返回 HTTPResponse，只返回纯 dict 结果，由接口层组装响应。
    """

    def handle(self, cmd: CreateDialogTaskCommand) -> dict:
        session_id = cmd.session_id
        task_id = str(uuid.uuid4())

        # 1) 合并 vendor 配置
        base_vendor_config = config.get_vendor_config(cmd.vendor)
        merged_config = {**base_vendor_config}
        override = cmd.vendor_config_override
        if override:
            if override.get('api_url'):
                merged_config['base_url'] = override['api_url']
            if override.get('headers'):
                merged_config['headers'] = override['headers']
            if override.get('timeout'):
                merged_config['timeout'] = override['timeout']

        # 2) 确保会话存在（委托 session_store）
        session_config = base_vendor_config.get('session', {})
        session_store.ensure_session(
            session_id=session_id,
            task_id=task_id,
            context_mode=session_config.get('context_mode', 'full'),
            max_history_rounds=session_config.get('max_history_rounds', 10),
            session_timeout=session_config.get('session_timeout', 60),
        )
        # 领域事件（仅记录日志，未来可挂载事件总线）
        logger.info(
            f'[event] SessionCreated session={session_id} task={task_id}'
        )

        # 3) 注册任务（委托 task_manager）
        task_manager.create_task(
            task_id,
            session_id=session_id,
            round=cmd.round,
            vendor=cmd.vendor,
            task_type=cmd.task_type,
        )
        task_manager.update_task_status(task_id, 'processing')

        try:
            # 4) 选择适配器（委托 adapters.factory）
            adapter = select_adapter(cmd.vendor, merged_config, is_dialog=True)

            # 5) 发送请求
            result = adapter.send_request(
                task_id=task_id,
                session_id=session_id,
                input_type=cmd.input_type,
                input_data=cmd.actual_input,
                source_lang=cmd.source_lang,
                target_lang=cmd.target_lang,
                context=cmd.context,
                context_for_request=cmd.context_for_request,
                algorithm_params=cmd.algorithm_params,
                case_algorithm_params=cmd.case_algorithm_params,
                translation_direction=cmd.translation_direction,
                round_number=cmd.round,
                total_rounds=cmd.total_rounds,
                task_type=cmd.task_type,
            )

            # 6) 更新会话存储
            output_text = result.get('asr_text', '') or result.get('output', '')
            session_store.add_round(
                session_id=session_id,
                round_idx=cmd.round,
                input_text=cmd.display_input,
                output_text=output_text,
                latency=result.get('latency', 0),
            )

            # 7) 存储轮次结果
            task_manager.add_round_result(task_id, cmd.round, result)
            task_manager.update_task_status(task_id, 'completed')

            logger.info(
                f'[event] RoundCompleted session={session_id} '
                f'task={task_id} round={cmd.round} '
                f'latency={result.get("latency", 0)}'
            )

            return {
                'code': 0,
                'msg': 'success',
                'task_id': task_id,
                'output_content': output_text,
                'output': output_text,
                'asr_text': result.get('asr_text', ''),
                'trans_text': result.get('trans_text', ''),
                'output_audio_path': result.get('raw_response', {}).get(
                    'output_audio_path'
                ),
                'response_metrics': {
                    'latency': result.get('latency', 0),
                },
            }

        except Exception as e:
            logger.error(f'Task processing failed: {e}', exc_info=True)
            task_manager.update_task_status(task_id, 'failed', str(e))
            return {
                'code': 5000,
                'msg': f'Task processing failed: {str(e)}',
                'task_id': task_id,
            }


class CloseSessionHandler:
    """关闭/销毁会话。"""

    def handle(self, cmd: CloseSessionCommand) -> dict:
        session_store.destroy_session(cmd.session_id)
        logger.info(
            f'[event] SessionClosed session={cmd.session_id}'
        )
        return {
            'code': 0,
            'msg': f'session {cmd.session_id} destroyed',
        }


# 命令处理器单例
create_dialog_task_handler = CreateDialogTaskHandler()
close_session_handler = CloseSessionHandler()
