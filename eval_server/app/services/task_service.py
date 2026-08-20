import threading
import time
from datetime import datetime
from ..models.task import TaskModel
from .wer_calculator import calculate_wer, calculate_ser, calculate_cpwer, calculate_tcpwer, calculate_stm_wer
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

        if task_type in TaskService.CALCULATORS:
            calculator = TaskService.CALCULATORS[task_type]
            return calculator(task_params)

        p = TaskService._prepare_params(task_params, task_type)

        if task_type == 'wer':
            return calculate_wer(
                p['asr_ref'], p['asr_hyp'],
                p['source_lang'], p['target_lang'], p['translate_direct'],
                normalize=p['normalize'],
            )
        elif task_type == 'ser':
            return calculate_ser(
                p['asr_ref'], p['asr_hyp'],
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
                **jp['extra_kwargs'],
            )
        elif task_type == 'turn_taking':
            from .xiaoyi_metrics.turn_taking import calculate_xiaoyi_metrics
            return calculate_xiaoyi_metrics(task_params)
        elif task_type == 'interruption_metrics':
            from .xiaoyi_metrics.turn_taking import calculate_interruption_metrics
            return calculate_interruption_metrics(task_params)
        elif task_type == 'non_interactive_latency':
            from .xiaoyi_metrics.rejection_scene_awareness.non_interactive_latency import compute_non_interactive_latency
            _rounds = task_params.get('rounds') or []
            _r0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}
            user_asr = task_params.get('user_asr') or task_params.get('user_chunks') or _r0.get('user_asr') or _r0.get('user_chunks')
            model_asr = task_params.get('model_asr') or task_params.get('model_chunks') or _r0.get('model_asr') or _r0.get('model_chunks')
            kwargs = {}
            gap = task_params.get('seg_merge_gap_s') or _r0.get('seg_merge_gap_s')
            if gap is not None:
                kwargs['seg_merge_gap_s'] = gap
            tsi = task_params.get('target_segment_index') or _r0.get('target_segment_index')
            if tsi is not None:
                kwargs['target_segment_index'] = tsi
            # 回退：user_asr/model_asr 为空时用 user_wav/ai_wav 调 ASR
            if not user_asr:
                user_wav = task_params.get('user_wav') or _r0.get('user_wav')
                if user_wav:
                    from .xiaoyi_metrics.turn_taking import _get_asr_chunks
                    user_asr = _get_asr_chunks(user_wav)
            if not model_asr:
                ai_wav = task_params.get('ai_wav') or _r0.get('ai_wav')
                if ai_wav:
                    from .xiaoyi_metrics.turn_taking import _get_asr_chunks
                    model_asr = _get_asr_chunks(ai_wav)
            # 两者都为空时返回带说明的空结果
            if not user_asr and not model_asr:
                return {
                    'score': 0,
                    'message': 'user_asr 和 model_asr 均为空（body_template 未包含 wav/asr 字段），跳过非交互意图时延计算',
                    'n_rounds': 0,
                    'per_round': [],
                    'avg_latency_s': None,
                }
            _nil_result = compute_non_interactive_latency(user_asr, model_asr, **kwargs)
            return {
                'stop_latency_s': _nil_result.get('stop_latency_s'),
                'recovery_latency_s': _nil_result.get('recovery_latency_s'),
                'user_segment': _nil_result.get('user_segment'),
                'model_active_segment': _nil_result.get('model_active_segment'),
                'model_recovery_segment': _nil_result.get('model_recovery_segment'),
                'message': _nil_result.get('message', ''),
            }
        elif task_type == 'noise_latency':
            from .xiaoyi_metrics.rejection_scene_awareness.noise_latency import compute_noise_latency
            _rounds = task_params.get('rounds') or []
            _r0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}
            # 多组噪声时取第二轮的 start_ms/end_ms（第一轮为初始交互）
            _r_noise = _rounds[1] if (isinstance(_rounds, list) and len(_rounds) > 1 and isinstance(_rounds[1], dict)) else _r0
            model_asr = task_params.get('model_asr') or task_params.get('model_chunks') or _r0.get('model_asr') or _r0.get('model_chunks')
            start_ms = _r_noise.get('start_ms')
            end_ms = _r_noise.get('end_ms')
            pcm_first_ms = task_params.get('pcm_first_ms') or _r0.get('pcm_first_ms') or _r_noise.get('pcm_first_ms')
            kwargs = {}
            gap = task_params.get('seg_merge_gap_s') or _r0.get('seg_merge_gap_s')
            if gap is not None:
                kwargs['seg_merge_gap_s'] = gap
            # 回退：model_asr 为空时用 ai_wav 调 ASR
            if not model_asr:
                ai_wav = task_params.get('ai_wav') or _r0.get('ai_wav')
                if ai_wav:
                    from .xiaoyi_metrics.turn_taking import _get_asr_chunks
                    model_asr = _get_asr_chunks(ai_wav)
                    if model_asr is None:
                        model_asr = {'text': '', 'chunks': []}
            # pcm_first_ms 为空时返回带说明的空结果（驱动未输出，无法做时间对齐）
            if not pcm_first_ms:
                return {
                    'score': 0,
                    'message': 'pcm_first_ms 为空（设备驱动未输出 PCM 创建时刻），无法做噪声↔模型时间轴对齐，跳过噪声打断时延计算',
                    'n_model_segments': 0,
                    'has_model_reply': False,
                    'pause_latency_s': None,
                    'recovery_latency_s': None,
                }
            _nl_result = compute_noise_latency(
                model_asr,
                start_ms,
                end_ms,
                pcm_first_ms,
                **kwargs,
            )
            return {
                'stop_latency_s': _nl_result.get('stop_latency_s'),
                'recovery_latency_s': _nl_result.get('recovery_latency_s'),
                'model_active_segment': _nl_result.get('model_active_segment'),
                'model_recovery_segment': _nl_result.get('model_recovery_segment'),
                'message': _nl_result.get('message', ''),
            }
        elif task_type == 'env_judge':
            from .xiaoyi_metrics.env_judge.env_judge import evaluate_env_judge
            _rounds = task_params.get('rounds') or []
            _r0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}
            video_path = task_params.get('video_path') or task_params.get('record_file') or _r0.get('video_path') or _r0.get('record_file')
            env_type = task_params.get('env_type') or _r0.get('env_type') or ''
            model = task_params.get('model') or _r0.get('model') or ''
            max_tokens = task_params.get('max_tokens') or _r0.get('max_tokens') or 4096
            temperature = task_params.get('temperature') or _r0.get('temperature') or 0.1
            return evaluate_env_judge(
                video_path,
                task_type=task_params.get('task_type', 'env_judge'),
                env_type=env_type,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
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
    """模块级函数，供 ThreadPoolExecutor 调用。
    线程池中运行，直接调用即可，无需子进程日志初始化。"""
    return TaskService.calculate(task_type, task_params)
