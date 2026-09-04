"""BaseCalculator：模板方法基类。

子类需实现 validate()、prepare_params()、calculate()。
validate() 用于在 API 层拦截参数缺失，返回 (is_valid, error_msg)。
prepare_params() 默认走通用 _prepare_params，子类可覆写。

参数模式说明：
  - 单轮模式：task_params['round_number'] 有值（0/1/2...），取 rounds[round_number]
  - 多轮模式：task_params['round_number'] 不存在，遍历所有 rounds 或取最后一轮

公共方法（round_number 语义）：
  _is_multi_round        : round_number 不存在 → 多轮
  _get_target_round_index: round_number 有值则取它，否则 -1（末轮）
  _get_round_safe        : 安全取 rounds[index]，支持负索引
  _get_audio_from_round  : 从指定轮取双路音频（顶层优先）
  _iter_rounds           : 遍历轮次，yield (index, round_dict)
  _aggregate_results     : 聚合多轮结果：数值取平均，非数值取最后一轮
  _unwrap_value          : 解包 {'text': '...'} 格式
  _collect_flat_from_rounds: 从多轮按 key 收集各轮值拼接（wer/der 用）
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

    # ─────────── 单轮/多轮公共方法（round_number 语义）───────────

    @staticmethod
    def _is_multi_round(task_params):
        """判断是否为多轮模式：round_number 不存在 → 多轮"""
        return (task_params or {}).get('round_number') is None

    @staticmethod
    def _get_target_round_index(task_params):
        """获取目标轮次索引

        单轮：round_number（0-indexed）
        多轮：-1（最后一轮）
        """
        rn = (task_params or {}).get('round_number')
        if rn is not None:
            return rn
        return -1

    @staticmethod
    def _get_round_safe(task_params, index):
        """安全获取 rounds[index]，越界或不存在返回 {}

        支持负索引（-1 = 末轮）。
        """
        rounds = (task_params or {}).get('rounds')
        if not (rounds and isinstance(rounds, list)):
            return {}
        idx = index if index >= 0 else len(rounds) + index
        if 0 <= idx < len(rounds) and isinstance(rounds[idx], dict):
            return rounds[idx]
        return {}

    @classmethod
    def _get_audio_from_round(cls, task_params, index):
        """从指定轮次取双路音频（顶层优先）

        Returns:
            (user_wav, ai_wav)
        """
        rd = cls._get_round_safe(task_params, index)
        user_wav = task_params.get('user_wav') or rd.get('user_wav') or ''
        ai_wav = task_params.get('ai_wav') or rd.get('ai_wav') or ''
        return user_wav, ai_wav

    @staticmethod
    def _iter_rounds(task_params):
        """遍历轮次，yield (round_index, round_dict)

        单轮：只 yield (round_number, rounds[round_number])
        多轮：yield 每一轮
        """
        rounds = (task_params or {}).get('rounds')
        if not (rounds and isinstance(rounds, list)):
            return
        rn = (task_params or {}).get('round_number')
        if rn is not None:
            if 0 <= rn < len(rounds) and isinstance(rounds[rn], dict):
                yield rn, rounds[rn]
        else:
            for i, rd in enumerate(rounds):
                if isinstance(rd, dict):
                    yield i, rd

    @staticmethod
    def _aggregate_results(per_round_results, agg_keys=None):
        """聚合多轮结果：数值字段取平均，非数值取最后一轮

        Args:
            per_round_results: [{...}, {...}, ...] 每轮结果
            agg_keys: 需要取平均的数值字段名列表，为 None 则自动检测
        """
        if not per_round_results:
            return {}
        if len(per_round_results) == 1:
            return dict(per_round_results[0])

        # 取最后一轮作为基础
        result = dict(per_round_results[-1])
        # 数值字段取平均
        first = per_round_results[0]
        for k, v in first.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals = [r.get(k) for r in per_round_results if r.get(k) is not None]
                if vals:
                    result[k] = round(sum(vals) / len(vals), 3)
        result['n_rounds'] = len(per_round_results)
        result['per_round'] = per_round_results
        return result

    @staticmethod
    def _unwrap_value(val):
        """提取参数值：{'text': '...', 'json': [...]} 格式取 text，否则原样返回"""
        if isinstance(val, dict) and 'text' in val:
            return val['text']
        return val

    @staticmethod
    def _avg(values):
        """取平均，保留 3 位小数；过滤非数值项，空列表返回 None"""
        vals = [v for v in (values or []) if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if not vals:
            return None
        return round(sum(vals) / len(vals), 3)

    # ─────────── 扁平字段收集（wer/der 多轮拼接用）───────────

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
