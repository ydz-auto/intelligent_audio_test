"""BaseCalculator：模板方法基类。

子类需实现 validate()、prepare_params()、calculate()。
validate() 用于在 API 层拦截参数缺失，返回 (is_valid, error_msg)。
prepare_params() 默认走通用 _prepare_params，子类可覆写。

参数模式说明：
  - 单轮模式：task_params 顶层直接存放各字段（asr_ref / asr_hyp / answer 等）
  - 多轮模式：task_params['rounds'] 是 list[dict]，每轮含同名字段

子类通过覆写 prepare_params 实现各自的单轮/多轮取参逻辑。
公共方法 _is_multi_round / _get_round0 / _collect_flat_from_rounds /
_collect_audio_from_rounds / _collect_scalar_from_rounds 供子类复用。
"""


class BaseCalculator:
    """策略基类：run() 为模板方法，子类实现 validate() + calculate()。

    用法：
        class WerCalculator(BaseCalculator):
            task_type = 'wer'
            def validate(self, task_params):
                if not task_params.get('asr_ref') and 'rounds' not in task_params:
                    return False, "Missing required fields: asr_ref, asr_hyp"
                return True, None
            def calculate(self, params):
                return calculate_wer(params['asr_ref'], ...)
    """

    task_type: str = ''

    def run(self, task_params):
        """模板方法：prepare_params -> calculate"""
        params = self.prepare_params(task_params)
        return self.calculate(params)

    def validate(self, task_params):
        """参数校验：返回 (is_valid, error_msg)。

        子类应覆写此方法，检查必填字段是否齐全。
        """
        return True, None

    def prepare_params(self, task_params):
        """默认实现：使用 TaskService._prepare_params 提取通用字段。

        子类可覆写此方法，实现任务特定的参数提取。
        """
        # 延迟导入避免循环依赖
        from app.services.task_service import TaskService
        return TaskService._prepare_params(task_params, self.task_type)

    def calculate(self, params):
        """子类必须实现：接收 prepare_params 的返回值，执行计算。"""
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 calculate()")

    # ─────────── 单轮/多轮公共提取方法 ───────────

    @staticmethod
    def _is_multi_round(task_params):
        """判断是否为多轮模式：task_params['rounds'] 非空 list"""
        rounds = (task_params or {}).get('rounds')
        return bool(rounds and isinstance(rounds, list) and len(rounds) > 0)

    @staticmethod
    def _get_round0(task_params):
        """获取 rounds[0]（首轮），不存在时返回空 dict"""
        rounds = (task_params or {}).get('rounds')
        if rounds and isinstance(rounds, list) and len(rounds) > 0:
            r0 = rounds[0]
            return r0 if isinstance(r0, dict) else {}
        return {}

    @staticmethod
    def _get_round(task_params, index):
        """获取 rounds[index]，不存在时返回空 dict"""
        rounds = (task_params or {}).get('rounds')
        if rounds and isinstance(rounds, list) and 0 <= index < len(rounds):
            r = rounds[index]
            return r if isinstance(r, dict) else {}
        return {}

    @staticmethod
    def _get_round_or_last(task_params):
        """获取 rounds[-1]（末轮），不存在时返回空 dict。

        用于 api.py 字段提升逻辑对应的取值方式：
        单轮取 rounds[0]，多轮取 rounds[-1]。
        """
        rounds = (task_params or {}).get('rounds')
        if rounds and isinstance(rounds, list) and len(rounds) > 0:
            r = rounds[-1]
            return r if isinstance(r, dict) else {}
        return {}

    @staticmethod
    def _unwrap_value(val):
        """提取参数值：{'text': '...', 'json': [...]} 格式取 text，否则原样返回"""
        if isinstance(val, dict) and 'text' in val:
            return val['text']
        return val

    @staticmethod
    def _collect_flat_from_rounds(task_params, keys, separator='\n'):
        """从多轮 rounds 中按 key 收集各轮值，用 separator 拼接成单条字符串。

        单轮模式下直接从顶层取值。

        自动解包 {'text': '...'} 格式，过滤空值。

        Args:
            task_params: 原始参数
            keys: 需收集的字段名列表
            separator: 拼接符，默认 \\n

        Returns:
            dict: {key: 拼接后的字符串或 None}
        """
        task_params = task_params or {}
        result = {}

        rounds = task_params.get('rounds')
        if rounds and isinstance(rounds, list):
            for k in keys:
                values = []
                for rd in rounds:
                    if not isinstance(rd, dict):
                        continue
                    v = rd.get(k)
                    if v is None:
                        continue
                    if isinstance(v, dict) and 'text' in v:
                        v = v['text']
                    if v != '' and v is not None:
                        values.append(str(v))
                result[k] = separator.join(values) if values else None
        else:
            for k in keys:
                v = task_params.get(k)
                if isinstance(v, dict) and 'text' in v:
                    v = v['text']
                result[k] = v

        return result

    @staticmethod
    def _collect_audio_from_rounds(task_params, keys):
        """从多轮 rounds 中按 key 收集音频文件路径列表。

        与 _collect_flat_from_rounds 不同：音频路径不拼接，而是返回 list，
        供逐轮 ASR / LLM 处理。单轮模式下返回单元素 list 或空 list。

        Args:
            task_params: 原始参数
            keys: 需收集的字段名列表（如 ['ai_wav', 'user_wav']）

        Returns:
            dict: {key: [path1, path2, ...] 或 []}
        """
        task_params = task_params or {}
        result = {}

        rounds = task_params.get('rounds')
        if rounds and isinstance(rounds, list):
            for k in keys:
                paths = []
                for rd in rounds:
                    if not isinstance(rd, dict):
                        continue
                    v = rd.get(k)
                    if isinstance(v, dict) and 'text' in v:
                        v = v['text']
                    if v and v != '':
                        paths.append(str(v))
                result[k] = paths
        else:
            for k in keys:
                v = task_params.get(k)
                if isinstance(v, dict) and 'text' in v:
                    v = v['text']
                result[k] = [str(v)] if v and v != '' else []

        return result

    @staticmethod
    def _collect_scalar_from_rounds(task_params, keys):
        """从多轮 rounds 中按 key 收集标量值（数字/字符串），返回 list。

        单轮模式下从顶层取值，返回单元素 list 或空 list。

        Args:
            task_params: 原始参数
            keys: 需收集的字段名列表（如 ['start_ms', 'end_ms']）

        Returns:
            dict: {key: [val1, val2, ...] 或 []}
        """
        task_params = task_params or {}
        result = {}

        rounds = task_params.get('rounds')
        if rounds and isinstance(rounds, list):
            for k in keys:
                values = []
                for rd in rounds:
                    if not isinstance(rd, dict):
                        continue
                    v = rd.get(k)
                    if v is not None and v != '':
                        values.append(v)
                result[k] = values
        else:
            for k in keys:
                v = task_params.get(k)
                if v is not None and v != '':
                    result[k] = [v]
                else:
                    result[k] = []

        return result

    @staticmethod
    def _pick_field(task_params, key, default=None, round_index=0):
        """从顶层或 rounds[round_index] 取单个字段值（顶层优先）。

        Args:
            task_params: 原始参数
            key: 字段名
            default: 缺省值
            round_index: rounds 的轮次索引，默认 0（首轮）

        Returns:
            字段值或 default
        """
        task_params = task_params or {}
        val = task_params.get(key)
        if val is not None:
            return val
        r = BaseCalculator._get_round(task_params, round_index)
        val = r.get(key)
        return val if val is not None else default
