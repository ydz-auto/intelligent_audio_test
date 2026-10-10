import threading
import time
import logging
import requests
from datetime import datetime
from ..models.task import TaskModel
from ..utils.concurrency import ConcurrencyManager
from ..utils.decorators import limit_task_concurrency

logger = logging.getLogger('task_service')


def notify_callback(callback_url, eval_task_id, task_type, caller_task_id, status, result=None, error_msg=None):
    """任务完成/失败后，通过回调 URL 主动通知调用方（事件化，替代调用方轮询）。

    带简单重试：失败后指数退避重试 3 次；仍失败则放弃（调用方有兜底结算线程补查）。
    """
    if not callback_url:
        return
    payload = {
        'eval_task_id': eval_task_id,
        'task_id': caller_task_id,
        'task_type': task_type,
        'status': status,
        'result': result,
        'error_msg': error_msg,
    }
    for attempt in range(3):
        try:
            requests.post(callback_url, json=payload, timeout=10)
            return
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                logger.warning(f'回调通知失败(已重试): eval_task_id={eval_task_id}, callback_url={callback_url}, err={e}')

class TaskService:
    _worker_thread = None
    _stop_event = threading.Event()

    CALCULATORS = {}

    @classmethod
    def register_calculator(cls, task_type, calculator_func):
        cls.CALCULATORS[task_type] = calculator_func

    @staticmethod
    def _prepare_params(task_params, task_type=None):
        """统一从 task_params 中提取并准备各类计算所需的参数。

        返回一个 dict，包含各 calculator 可能用到的字段：
          - normalize
          - source_lang / target_lang
          - translate_direct（兼容 translate_direct 和 translation_direction 两种 key）
          - collar（默认 0.0；der 任务默认 0.5）
          - skip_overlap（默认 False）
          - 原始字段：asr_ref, asr_hyp, ref_stm, hyp_stm, rttm_ref/stm_ref, rttm_res/stm_res
        多轮场景（task_params['rounds'] 非空）会把每轮的同名字段按 \\n 拼接折叠成
        单轮文本，calculator 无需感知多轮。llm_judge 的特殊参数由
        _prepare_llm_judge_params 单独处理（不经过此折叠，需保留每轮结构）。
        """
        task_params = task_params or {}

        # 翻译方向：兼容 translate_direct 和 translation_direction 两种命名
        translate_direct = (
            task_params.get('translate_direct')
            or task_params.get('translation_direction')
        )

        # collar 默认值随任务类型不同
        collar_default = 0.5 if task_type == 'der' else 0.0

        # 各指标用到的扁平字段：rounds 模式下按 key 从每轮取值并拼接
        flat_keys = ('asr_ref', 'asr_hyp', 'ref_stm', 'hyp_stm',
                     'rttm_ref', 'stm_ref', 'rttm_res', 'stm_res')

        rounds = task_params.get('rounds')
        flat = {}
        if rounds and isinstance(rounds, list):
            # 多轮：按 key 把每轮的值收集起来，过滤掉空值后用 \n 拼接
            for k in flat_keys:
                values = []
                for rd in rounds:
                    if isinstance(rd, dict):
                        v = rd.get(k)
                        if v is None:
                            continue
                        if isinstance(v, dict) and 'text' in v:
                            v = v['text']
                        if v != '':
                            values.append(str(v))
                flat[k] = '\n'.join(values) if values else None
        else:
            # 单轮：直接取扁平字段
            for k in flat_keys:
                flat[k] = task_params.get(k)

        return {
            'normalize': task_params.get('normalize', False),
            'source_lang': task_params.get('source_lang'),
            'target_lang': task_params.get('target_lang'),
            'translate_direct': translate_direct,
            **flat,
            'collar': task_params.get('collar', collar_default),
            'skip_overlap': task_params.get('skip_overlap', False),
        }

    @staticmethod
    def _unwrap_value(val):
        """提取参数值：如果是 {'text': '...', 'json': [...]} 格式则取 text 字段，否则原样返回"""
        if isinstance(val, dict) and 'text' in val:
            return val['text']
        return val

    @staticmethod
    def _prepare_llm_judge_params(task_params):
        """为 llm_judge 准备参数，收集透传的 extra_kwargs。

        字段名与 param_mappings 的 target_param 一致：
        - answer: 设备回答
        - correct_answer: 参考答案
        - question: 设备识别的问题
        - query: 参考问题
        - record_file: 音频文件路径

        correct_answer / query 可能是 {'text': '...', 'json': []} 格式（reference_params 生成），
        需要提取 text 字段转为纯字符串。
        """
        task_params = task_params or {}
        reserved = ('answer', 'correct_answer', 'question', 'query',
                    'record_file', 'model', 'prompt',
                    'max_tokens', 'temperature', 'scoring_criteria',
                    'rounds')
        extra_kwargs = {
            k: v for k, v in task_params.items()
            if k not in reserved
        }
        from ..config import config
        llm_config = getattr(config, 'LLM_JUDGE', {})
        default_model = llm_config.get('default_model', 'gpt-4')
        default_prompt = llm_config.get('prompt_template', '')

        unwrap = TaskService._unwrap_value

        # rounds 内的字段也需要解包
        rounds = task_params.get('rounds')
        if rounds and isinstance(rounds, list):
            rounds = [
                {k: unwrap(v) for k, v in rd.items()} if isinstance(rd, dict) else rd
                for rd in rounds
            ]

        return {
            'answer': unwrap(task_params.get('answer', '')),
            'correct_answer': unwrap(task_params.get('correct_answer', '')),
            'question': unwrap(task_params.get('question', '')),
            'query': unwrap(task_params.get('query', '')),
            'record_file': task_params.get('record_file', ''),
            'rounds': rounds,
            'model': task_params.get('model') or default_model,
            'prompt': task_params.get('prompt') or default_prompt,
            'max_tokens': task_params.get('max_tokens', 1024),
            'temperature': task_params.get('temperature', 0.1),
            'scoring_criteria': task_params.get('scoring_criteria'),
            'extra_kwargs': extra_kwargs,
        }

    @staticmethod
    def calculate(task_type, task_params):
        task_params = task_params or {}

        calculator = TaskService.CALCULATORS.get(task_type)
        if calculator is None:
            raise ValueError(f"Unknown task type: {task_type}")

        result = calculator.run(task_params)

        # 整体评估模式 + calculator 声明支持逐轮 → 附加 per_round[]（逐轮结果回填）
        # 默认仅当响应可附加（dict）且为整体评估（round_number 不存在）且有多轮数据（>=2轮）时生效
        # calculator 可通过属性调整：
        #   min_rounds_for_aggregate  — 触发聚合的最少轮数（reject_judge 单轮=1 也要走聚合，
        #                               保证 n_ 前缀数量字段与 n_reject_rounds 在单轮场景同样产出）
        #   aggregate_overall_only    — False 时逐轮评估（round_number 有值）也允许聚合
        rounds = task_params.get('rounds')
        is_overall = task_params.get('round_number') in (None, '')
        min_rounds = getattr(calculator, 'min_rounds_for_aggregate', 2)
        aggregate_overall_only = getattr(calculator, 'aggregate_overall_only', True)
        if rounds and (is_overall or not aggregate_overall_only) and len(rounds) >= min_rounds:
            # 计算器已在结果里返回原生 per_round[]（如 turn_eval/interruption 整体合并评估
            # 一次产出全部逐轮结果）时，直接复用并跳过默认逐轮切片重跑。
            # 避免额外 N 次 ASR/LLM，且保证逐轮口径与整体（turns）一致；
            # 重跑产生的是另一遍独立评估，结果与整体不一致（曾导致逐轮 TRD 落错分）。
            if isinstance(result, dict) and isinstance(result.get('per_round'), list) and result['per_round']:
                return result
            try:
                per_round = calculator._calculate_per_round(task_params)
                # reject_judge 的 _calculate_per_round 会通过 _agg_result 返回聚合结果
                # 聚合结果覆盖顶层 result（数量+占比），per_round 附加为逐轮明细
                agg_result = getattr(calculator, '_agg_result', None)
                if agg_result is not None:
                    result = agg_result
                result['per_round'] = per_round
            except Exception as e:
                # 不阻断，整体结果已返回
                print(f"[TaskService] {task_type} per_round 计算失败: {e}")

        return result

    @staticmethod
    def get_concurrency_info():
        return ConcurrencyManager.get_stats()

    @staticmethod
    def start_worker():
        if TaskService._worker_thread is None or not TaskService._worker_thread.is_alive():
            TaskService._stop_event.clear()
            TaskService._worker_thread = threading.Thread(target=TaskService._process_tasks, daemon=True)
            TaskService._worker_thread.start()

    @staticmethod
    def stop_worker():
        TaskService._stop_event.set()
        if TaskService._worker_thread:
            TaskService._worker_thread.join()

    @staticmethod
    def _process_tasks():
        # 延迟导入，避免与 controllers.api 循环依赖（api.py 顶层导入了本模块）
        from ..controllers.api import LocalConcurrencyManager
        while not TaskService._stop_event.is_set():
            pending_tasks = TaskModel.get_pending_tasks()
            if pending_tasks:
                print(f"Worker: Found {len(pending_tasks)} pending tasks")
            for task in pending_tasks:
                if TaskService._stop_event.is_set():
                    break
                
                task_type = task.get('task_type', 'wer')
                
                # 与直处理路径共用维度并发位 + 全局并发位：
                # 先占维度位（按 CONCURRENCY_LIMITS），再占全局位（LOCAL_MAX_CONCURRENCY），
                # 避免 worker 在全局已满时再叠加启动任务导致总并发超限。
                if ConcurrencyManager.try_start(task_type):
                    if LocalConcurrencyManager.try_start():
                        print(f"Worker: Starting task {task['eval_task_id']} (Type: {task_type})")
                        TaskModel.update_task_status(task['eval_task_id'], 'processing', started_at=datetime.now().isoformat())
                        threading.Thread(target=TaskService._run_queued_task, args=(task,), daemon=True).start()
                    else:
                        # 全局并发位已满，释放维度位，任务继续保持 pending 等待
                        ConcurrencyManager.decrement(task_type)
                
            time.sleep(1)

    @staticmethod
    def _run_queued_task(task):
        """worker 启动的排队任务：计算完成后同时释放全局与维度并发位。

        维度位由 _run_task_wrapper 上的 limit_task_concurrency 装饰器释放；
        这里负责释放全局位。
        """
        from ..controllers.api import LocalConcurrencyManager
        try:
            TaskService._run_task_wrapper(task)
        finally:
            LocalConcurrencyManager.decrement()

    @staticmethod
    @limit_task_concurrency
    def _run_task_wrapper(task):
        TaskService._run_task(task)

    @staticmethod
    def _run_task(task):
        eval_task_id = task['eval_task_id']
        task_type = task['task_type']
        task_params = task.get('task_params', {})

        # 事件化回调：调用方传 callback_url，算完后主动通知，替代调用方轮询等待
        callback_url = (task_params or {}).get('callback_url') or task.get('callback_url')
        caller_task_id = task.get('task_id')

        try:
            result = TaskService.calculate(task_type, task_params)

            # calculator 返回 is_success=False 表示评估内部失败（如 LLM 调用失败），
            # 任务应标记为 failed，而非 completed
            if isinstance(result, dict) and result.get('is_success') is False:
                error_msg = result.get('message', '评估失败')
                TaskModel.update_task_status(
                    eval_task_id,
                    'failed',
                    completed_at=datetime.now().isoformat(),
                    error_msg=error_msg
                )
                notify_callback(callback_url, eval_task_id, task_type, caller_task_id,
                                'failed', error_msg=error_msg)
                return

            TaskModel.update_task_status(
                eval_task_id, 
                'completed', 
                completed_at=datetime.now().isoformat(),
                result=result
            )
            notify_callback(callback_url, eval_task_id, task_type, caller_task_id,
                            'completed', result=result)

        except Exception as e:
            TaskModel.update_task_status(
                eval_task_id,
                'failed',
                completed_at=datetime.now().isoformat(),
                error_msg=str(e)
            )
            notify_callback(callback_url, eval_task_id, task_type, caller_task_id,
                            'failed', error_msg=str(e))

def calculate_in_process(task_type, task_params):
    """模块级函数，供 ThreadPoolExecutor 调用。
    线程池中运行，直接调用即可，无需子进程日志初始化。"""
    return TaskService.calculate(task_type, task_params)
