import threading
import time
from datetime import datetime
from ..models.task import TaskModel
from .wer_calculator import calculate_wer, calculate_ser, calculate_cpwer, calculate_tcpwer, calculate_stm_wer
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
    def calculate(task_type, task_params):
        task_params = task_params or {}
        normalize = task_params.get('normalize', False)

        if task_type in TaskService.CALCULATORS:
            calculator = TaskService.CALCULATORS[task_type]
            return calculator(task_params)
        
        if task_type == 'wer':
            return calculate_wer(
                task_params.get('asr_ref'),
                task_params.get('asr_result'),
                task_params.get('source_lang'),
                task_params.get('target_lang'),
                task_params.get('translate_direct') or task_params.get('translation_direction'),
                normalize=normalize
            )
        elif task_type == 'ser':
            return calculate_ser(
                task_params.get('asr_ref'),
                task_params.get('asr_result'),
                task_params.get('source_lang'),
                task_params.get('target_lang'),
                task_params.get('translate_direct') or task_params.get('translation_direction'),
                normalize=normalize
            )
        elif task_type == 'cpwer':
            return calculate_cpwer(
                task_params.get('ref_stm'),
                task_params.get('hyp_stm'),
                task_params.get('source_lang'),
                task_params.get('target_lang'),
                task_params.get('translate_direct') or task_params.get('translation_direction'),
                normalize=normalize
            )
        elif task_type == 'tcpwer':
            return calculate_tcpwer(
                task_params.get('ref_stm'),
                task_params.get('hyp_stm'),
                task_params.get('source_lang'),
                task_params.get('target_lang'),
                task_params.get('translate_direct') or task_params.get('translation_direction'),
                task_params.get('collar', 0.0),
                normalize=normalize
            )
        elif task_type == 'stm_wer':
            return calculate_stm_wer(
                task_params.get('ref_stm'),
                task_params.get('hyp_stm'),
                task_params.get('source_lang'),
                task_params.get('target_lang'),
                task_params.get('translate_direct') or task_params.get('translation_direction'),
                normalize=normalize
            )
        elif task_type == 'der':
            from .der_calculator import calculate_der
            return calculate_der(
                task_params.get('rttm_ref'),
                task_params.get('stm_ref'),
                task_params.get('rttm_res'),
                task_params.get('stm_res'),
                task_params.get('source_lang'),
                task_params.get('target_lang'),
                task_params.get('translate_direct') or task_params.get('translation_direction'),
                task_params.get('collar', 0.5),
                task_params.get('skip_overlap', False),
                normalize=normalize
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
                    print(f"Worker: Starting task {task['task_id']} (Type: {task_type})")
                    ConcurrencyManager.increment(task_type)
                    TaskModel.update_task_status(task['task_id'], 'processing', started_at=datetime.now().isoformat())
                    threading.Thread(target=TaskService._run_task_wrapper, args=(task,), daemon=True).start()
                
            time.sleep(1)

    @staticmethod
    @limit_task_concurrency
    def _run_task_wrapper(task):
        TaskService._run_task(task)

    @staticmethod
    def _run_task(task):
        task_id = task['task_id']
        task_type = task['task_type']
        task_params = task.get('task_params', {})

        import time
        time.sleep(50)

        try:
            result = TaskService.calculate(task_type, task_params)
            
            TaskModel.update_task_status(
                task_id, 
                'completed', 
                completed_at=datetime.now().isoformat(),
                result=result
            )
        except Exception as e:
            TaskModel.update_task_status(
                task_id, 
                'failed', 
                completed_at=datetime.now().isoformat(),
                error_msg=str(e)
            )
