import threading
import time
from datetime import datetime
from ..models.task import TaskModel
from .wer_calculator import calculate_wer, calculate_ser, calculate_cpwer, calculate_tcpwer, calculate_stm_wer, calculate_multi_round_wer
from ..config import config
from ..utils.concurrency import ConcurrencyManager
from ..utils.decorators import limit_task_concurrency

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
          - 原始字段：asr_ref, asr_result, ref_stm, hyp_stm, rttm_ref/stm_ref, rttm_res/stm_res
          - rounds（如果存在）
        llm_judge 的特殊参数由 _prepare_llm_judge_params 单独处理。
        """
        task_params = task_params or {}

        # 翻译方向：兼容 translate_direct 和 translation_direction 两种命名
        translate_direct = (
            task_params.get('translate_direct')
            or task_params.get('translation_direction')
        )

        # collar 默认值随任务类型不同
        collar_default = 0.5 if task_type == 'der' else 0.0

        return {
            'normalize': task_params.get('normalize', False),
            'source_lang': task_params.get('source_lang'),
            'target_lang': task_params.get('target_lang'),
            'translate_direct': translate_direct,
            'asr_ref': task_params.get('asr_ref'),
            'asr_result': task_params.get('asr_result'),
            'ref_stm': task_params.get('ref_stm'),
            'hyp_stm': task_params.get('hyp_stm'),
            'rttm_ref': task_params.get('rttm_ref'),
            'stm_ref': task_params.get('stm_ref'),
            'rttm_res': task_params.get('rttm_res'),
            'stm_res': task_params.get('stm_res'),
            'collar': task_params.get('collar', collar_default),
            'skip_overlap': task_params.get('skip_overlap', False),
            'rounds': task_params.get('rounds'),
        }

    @staticmethod
    def _prepare_llm_judge_params(task_params):
        """为 llm_judge 准备参数，收集透传的 extra_kwargs。

        字段名与 param_mappings 的 target_param 一致：
        - answer: 设备回答
        - correct_answer: 参考答案
        - question: 设备识别的问题
        - query: 参考问题
        - record_file: 音频文件路径
        """
        task_params = task_params or {}
        reserved = ('answer', 'correct_answer', 'question', 'query',
                    'record_file', 'model', 'prompt',
                    'max_tokens', 'temperature', 'scoring_criteria',
                    'source_lang', 'target_lang', 'normalize', 'rounds')
        extra_kwargs = {
            k: v for k, v in task_params.items()
            if k not in reserved
        }
        return {
            'answer': task_params.get('answer', ''),
            'correct_answer': task_params.get('correct_answer', ''),
            'question': task_params.get('question', ''),
            'query': task_params.get('query', ''),
            'record_file': task_params.get('record_file', ''),
            'rounds': task_params.get('rounds'),
            'model': task_params.get('model', 'gpt-4'),
            'prompt': task_params.get('prompt', ''),
            'max_tokens': task_params.get('max_tokens', 1024),
            'temperature': task_params.get('temperature', 0.1),
            'scoring_criteria': task_params.get('scoring_criteria'),
            'source_lang': task_params.get('source_lang', 'zh'),
            'target_lang': task_params.get('target_lang', 'en'),
            'extra_kwargs': extra_kwargs,
        }

    @staticmethod
    def calculate(task_type, task_params):
        task_params = task_params or {}

        if task_type in TaskService.CALCULATORS:
            calculator = TaskService.CALCULATORS[task_type]
            return calculator(task_params)

        p = TaskService._prepare_params(task_params, task_type)

        if task_type == 'wer':
            if p['rounds'] is not None:
                return calculate_multi_round_wer(
                    rounds=p['rounds'],
                    source_lang=p['source_lang'],
                    target_lang=p['target_lang'],
                    normalize=p['normalize'],
                )
            return calculate_wer(
                p['asr_ref'], p['asr_result'],
                p['source_lang'], p['target_lang'], p['translate_direct'],
                normalize=p['normalize'],
            )
        elif task_type == 'ser':
            return calculate_ser(
                p['asr_ref'], p['asr_result'],
                p['source_lang'], p['target_lang'], p['translate_direct'],
                normalize=p['normalize'],
            )
        elif task_type == 'cpwer':
            return calculate_cpwer(
                p['ref_stm'], p['hyp_stm'],
                p['source_lang'], p['target_lang'], p['translate_direct'],
                normalize=p['normalize'],
            )
        elif task_type == 'tcpwer':
            return calculate_tcpwer(
                p['ref_stm'], p['hyp_stm'],
                p['source_lang'], p['target_lang'], p['translate_direct'],
                p['collar'],
                normalize=p['normalize'],
            )
        elif task_type == 'stm_wer':
            return calculate_stm_wer(
                p['ref_stm'], p['hyp_stm'],
                p['source_lang'], p['target_lang'], p['translate_direct'],
                normalize=p['normalize'],
            )
        elif task_type == 'der':
            from .der_calculator import calculate_der
            return calculate_der(
                p['rttm_ref'], p['stm_ref'], p['rttm_res'], p['stm_res'],
                p['source_lang'], p['target_lang'], p['translate_direct'],
                p['collar'], p['skip_overlap'],
                normalize=p['normalize'],
            )
        elif task_type == 'llm_judge':
            from .llm_judge_calculator import evaluate_with_llm
            jp = TaskService._prepare_llm_judge_params(task_params)
            return evaluate_with_llm(
                answer=jp.get('answer', ''),
                correct_answer=jp.get('correct_answer', ''),
                question=jp.get('question', ''),
                query=jp.get('query', ''),
                record_file=jp.get('record_file', ''),
                rounds=jp.get('rounds'),
                model=jp['model'],
                prompt=jp['prompt'],
                max_tokens=jp['max_tokens'],
                temperature=jp['temperature'],
                scoring_criteria=jp['scoring_criteria'],
                source_lang=jp['source_lang'],
                target_lang=jp['target_lang'],
                **jp['extra_kwargs'],
            )
        else:
            raise ValueError(f"Unknown task type: {task_type}")

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
        while not TaskService._stop_event.is_set():
            pending_tasks = TaskModel.get_pending_tasks()
            if pending_tasks:
                print(f"Worker: Found {len(pending_tasks)} pending tasks")
            for task in pending_tasks:
                if TaskService._stop_event.is_set():
                    break
                
                task_type = task.get('task_type', 'wer')
                
                if ConcurrencyManager.can_start(task_type):
                    print(f"Worker: Starting task {task['eval_task_id']} (Type: {task_type})")
                    ConcurrencyManager.increment(task_type)
                    TaskModel.update_task_status(task['eval_task_id'], 'processing', started_at=datetime.now().isoformat())
                    threading.Thread(target=TaskService._run_task_wrapper, args=(task,), daemon=True).start()
                
            time.sleep(1)

    @staticmethod
    @limit_task_concurrency
    def _run_task_wrapper(task):
        TaskService._run_task(task)

    @staticmethod
    def _run_task(task):
        eval_task_id = task['eval_task_id']
        task_type = task['task_type']
        task_params = task.get('task_params', {})

        try:
            result = TaskService.calculate(task_type, task_params)
            
            TaskModel.update_task_status(
                eval_task_id, 
                'completed', 
                completed_at=datetime.now().isoformat(),
                result=result
            )
        except Exception as e:
            TaskModel.update_task_status(
                eval_task_id, 
                'failed', 
                completed_at=datetime.now().isoformat(),
                error_msg=str(e)
            )


def calculate_in_process(task_type, task_params):
    """模块级函数，供 ProcessPoolExecutor 调用（可被 pickle 序列化到子进程）"""
    return TaskService.calculate(task_type, task_params)
