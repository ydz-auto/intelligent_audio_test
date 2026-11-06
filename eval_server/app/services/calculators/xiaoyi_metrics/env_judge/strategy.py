# -*- coding: utf-8 -*-
"""env_judge 策略类

环境理解裁判：通过 env_type 输入参数区分无语义/有语义场景
  - env_type=false/0 → non_semantic（无语义：环境声为噪声，判断声音类型识别）
  - env_type=true/1  → semantic（有语义：环境声含语义内容，判断内容理解）

  - 主音频：ai_wav（模型回复，被判定对象）
  - 用户侧：user_wav（用户通道音频，含环境声+用户询问）
  - 环境声：played_audios（本轮被播放音频，FFT互相关定位）
  - 正确答案：correctAnswer（参考内容文本）
  - LLM 配置：model / max_tokens / temperature
"""
import logging
import os
from app.services.calculators.base import BaseCalculator
from app.services.calculators.xiaoyi_metrics.shared.llm_client import get_llm_config
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

# 0/1 字段：多轮聚合时求和得到数量，再除以总拒识轮次得到占比
_SUM_FIELDS = (
    'rate_success', 'rate_inquiry', 'rate_failure',
    'success_silent_recover', 'success_reply_recover',
    'inquiry_silent', 'inquiry_reply',
    'failure_silent_respond', 'failure_reply_respond',
    'failure_silent_irrelevant', 'failure_reply_irrelevant',
    'failure_reply_silent',
)
# count 字典字段：多轮聚合时合并累加
_COUNT_DICT_FIELDS = ('rate_success_count', 'rate_inquiry_count', 'rate_failure_count')

logger = logging.getLogger(__name__)


class _BaseEnvJudgeCalculator(BaseCalculator):
    """环境理解裁判公共基类

    单轮/多轮公共方法（_get_target_round_index / _get_round_safe /
    _iter_rounds / _aggregate_results）由 BaseCalculator 统一提供。
    """

    @staticmethod
    def _extract_llm_config(task_params, rd):
        """提取 LLM 配置参数

        model / max_tokens / temperature 缺省时回退到 config.LLM_JUDGE。
        """
        llm_config = get_llm_config()
        return {
            'model': task_params.get('model') or rd.get('model') or '',
            'max_tokens': int(task_params.get('max_tokens') or rd.get('max_tokens') or llm_config.get('max_tokens', LLM_DEFAULT_MAX_TOKENS)),
            'temperature': float(task_params.get('temperature') or rd.get('temperature') or llm_config.get('temperature', LLM_DEFAULT_TEMPERATURE)),
        }


class EnvJudgeCalculator(_BaseEnvJudgeCalculator):
    """环境理解裁判：判断模型对环境音内容的理解是否正确 + 计算用户询问到模型回复的时延

    通过 env_type 输入参数区分无语义/有语义：
      env_type=false/0 → non_semantic（无语义：环境声为噪声，判断声音类型识别）
      env_type=true/1  → semantic（有语义：环境声含语义内容，判断内容理解）
    输入：user_wav, ai_wav, played_audios, correctAnswer, env_type
    输出：understand_correct (True/False), response_latency_ms, score, reason
    """
    task_type = 'env_judge'
    supports_per_round = True

    def _calculate_per_round(self, task_params):
        self._agg_result = None
        results = super()._calculate_per_round(task_params)
        failed = [r for r in results if r.get('is_success') is False
                  or r.get('excluded_from_statistics') is True]
        if failed:
            self._agg_result = dict(failed[0])
            self._agg_result['message'] = '; '.join(
                f"round={r.get('round_number')}: {r.get('message')}" for r in failed)
            if any(r.get('excluded_from_statistics') for r in failed):
                self._agg_result.update(excluded_from_statistics=True,
                                        understand_correct=None, understand_correct_pass=None,
                                        score=None, response_latency_ms=None)
                # 整条用例排除，避免正常轮经per_round回填后仍进入报告统计。
                for row in results:
                    for key in ('understand_correct', 'understand_correct_pass',
                                'score', 'response_latency_ms'):
                        row[key] = None
                    row['excluded_from_statistics'] = True
        return results

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        has_ai = task_params.get('ai_wav') or rd.get('ai_wav')
        has_user = task_params.get('user_wav') or rd.get('user_wav')
        has_answer = task_params.get('correctAnswer') or rd.get('correctAnswer')
        if not has_ai:
            return False, f"Missing required field for {self.task_type}: ai_wav"
        if not has_user:
            return False, f"Missing required field for {self.task_type}: user_wav"
        if not has_answer:
            return False, f"Missing required field for {self.task_type}: correctAnswer"
        # played_audios 可选：缺失时跳过时延计算，仅做 LLM 评判
        return True, None

    def prepare_params(self, task_params):
        """提取环境理解裁判所需参数"""
        rounds = task_params.get('rounds') or []
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        llm_config = self._extract_llm_config(task_params, rd)

        return {
            'mode': 'single',
            'rounds': rounds,
            'ai_wav': task_params.get('ai_wav') or rd.get('ai_wav') or '',
            'user_wav': task_params.get('user_wav') or rd.get('user_wav') or '',
            'played_audios': task_params.get('played_audios') or rd.get('played_audios') or '',
            'correctAnswer': task_params.get('correctAnswer') or rd.get('correctAnswer') or '',
            'env_type': task_params.get('env_type', rd.get('env_type', 0)),
            **llm_config,
        }

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.env_judge import evaluate_env_judge

        return evaluate_env_judge(
            user_wav=params['user_wav'],
            ai_wav=params['ai_wav'],
            played_audios=params['played_audios'],
            correctAnswer=params['correctAnswer'],
            env_type=params.get('env_type', 0),
            model=params.get('model', ''),
            max_tokens=params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS),
            temperature=params.get('temperature', LLM_DEFAULT_TEMPERATURE),
        )


class RejectionJudgeCalculator(_BaseEnvJudgeCalculator):
    """拒识裁判：评估模型在拒识场景（非意图交互内容出现时）下的行为表现

    裁判 LLM 直接听取 ai_wav + user_wav 音频，判断模型行为类别（五选一），
    再由代码根据 timing + behavior 计算 rate 评级。

    输入：ai_wav, user_wav, is_single_round, timing, model, max_tokens, temperature
    输出：evaluations, behavior_*(5个0/1字段), rate, rate_*(3个0/1字段),
          rate_*_count(3组分组统计字典)
    """
    task_type = 'reject_judge'
    supports_per_round = True

    # 单轮也走逐轮聚合：只有 1 个拒识轮（rounds<2）时同样输出
    # n_ 前缀数量字段（n_rate_* / n_子维度）与 n_reject_rounds，
    # 避免单轮场景主维度/子维度 field_path 提取为 None。
    min_rounds_for_aggregate = 1
    aggregate_overall_only = False

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        has_ai = task_params.get('ai_wav') or rd.get('ai_wav')
        if not has_ai:
            return False, f"Missing required field for {self.task_type}: ai_wav"
        return True, None

    def prepare_params(self, task_params):
        """提取拒识裁判所需参数"""
        rounds = task_params.get('rounds') or []
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        llm_config = self._extract_llm_config(task_params, rd)

        is_single_round = rd.get('is_single_round', task_params.get('is_single_round', False))
        if isinstance(is_single_round, str):
            is_single_round = is_single_round.strip().lower() in ('true', '1', 'yes')

        timing = rd.get('timing', task_params.get('timing', '静默'))

        return {
            'mode': 'single',
            'rounds': rounds,
            'ai_wav': task_params.get('ai_wav') or rd.get('ai_wav') or '',
            'user_wav': task_params.get('user_wav') or rd.get('user_wav') or '',
            'is_single_round': is_single_round,
            'timing': timing,
            'prev_active_end': task_params.get('prev_active_end'),
            'active_segments': task_params.get('active_segments'),
            **llm_config,
        }

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.rejection_judge import evaluate_rejection_judge

        return evaluate_rejection_judge(
            ai_wav=params['ai_wav'],
            user_wav=params.get('user_wav', ''),
            is_single_round=params.get('is_single_round', False),
            timing=params.get('timing', '静默'),
            model=params.get('model', ''),
            max_tokens=params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS),
            temperature=params.get('temperature', LLM_DEFAULT_TEMPERATURE),
            prev_active_end=params.get('prev_active_end'),
            active_segments=params.get('active_segments'),
        )

    def _is_reject_round(self, task_params, rd=None):
        """归一化判断目标轮是否参与拒识评估（is_reject）

        rd 为轮次字典；缺省时按 round_number 定位目标轮。
        缺失默认 True（兼容旧请求），字符串 'true'/'1'/'yes' 视为 True。
        """
        if rd is None:
            idx = self._get_target_round_index(task_params)
            rd = self._get_round_safe(task_params, idx)
        is_reject = (rd or {}).get('is_reject', (task_params or {}).get('is_reject', True))
        if isinstance(is_reject, str):
            is_reject = is_reject.strip().lower() in ('true', '1', 'yes')
        return bool(is_reject)

    @staticmethod
    def _user_active_segments(user_wav: str):
        """用户侧波形活跃段 [[start_s, end_s], ...]；无音频/检测失败返回 []。

        用于逐轮窗口化：round_i 音频是累积的，新增干扰从上一轮覆盖终点
        之后寻找，避免重复评估更早轮次内容。结果会被 calculator 与
        evaluate_rejection_judge 复用，避免同一文件重复能量扫描。
        """
        if not user_wav or not os.path.isfile(user_wav):
            return []
        try:
            from app.services.calculators.xiaoyi_metrics.env_judge.rejection_judge import (
                get_active_segments,
            )
            return get_active_segments(user_wav) or []
        except Exception as e:
            logger.warning(f'[_user_active_segments] {user_wav} 检测失败: {e}')
            return []

    @staticmethod
    def _is_round_failed(result):
        """判定单个拒识轮评估是否失败（LLM 调用失败/输出解析失败/显式失败标记）。

        失败轮仍计入 n_reject_rounds（拒识轮计数），但不会归入成功/询问/失败任何分子，
        若放任不管会把占比分母撑大导致三率之和 < 100%，故整例判定评估失败。
        """
        if not isinstance(result, dict) or not result:
            return True
        msg = str(result.get('message') or '')
        if 'LLM 调用失败' in msg or 'LLM 输出解析失败' in msg:
            return True
        if result.get('enabled') is False or result.get('is_success') is False:
            return True
        return False

    def run(self, task_params):
        """覆写：is_reject=false 跳过；整体评估走文本模态全时间线评判（原生 per_round）。"""
        # 多轮整体评估：只要任一配置轮 is_reject=true 就继续（_run_overall_text 内部只评拒识轮、
        # 非拒识轮留跳过占位）；仅当全部轮 is_reject=false 才整例跳过。
        # 不能用 _is_reject_round(task_params)（多轮时按目标轮=最后一轮取数）——最后一轮为
        # 意图轮(is_reject=false)但前面有拒识轮时会把整例误判为跳过，整体 TRD 为空而逐轮切片
        # 照常评估，导致整体/逐轮数据不一致，报告主/子维度口径错乱。
        if self._is_multi_round(task_params):
            rounds = (task_params or {}).get('rounds') or []
            if not any(isinstance(rd, dict) and self._is_reject_round(task_params, rd) for rd in rounds):
                return {
                    'enabled': True,
                    'message': '跳过: 非拒识轮(is_reject=false)',
                    'rate': None,
                }
        elif not self._is_reject_round(task_params):
            return {
                'enabled': True,
                'message': '跳过: 非拒识轮(is_reject=false)',
                'rate': None,
            }
        # 整体评估（round_number 不存在）：最终轮双路 wav → ASR 全时间线 →
        # 轮次切分（参考打断）→ 一次 LLM 逐轮判定 timing/behavior/reason（文本模态，不再用配置 timing）
        if self._is_multi_round(task_params):
            return self._run_overall_text(task_params)
        return super().run(task_params)

    def _run_overall_text(self, task_params):
        """整体评估（文本模态）：返回原生 per_round[] + 聚合顶层结果。

        task_service 检测到 result['per_round'] 为列表（原生投影）直接返回，
        不再走 _calculate_per_round 逐轮音频重跑，保证逐轮口径与整体一次判定一致。
        """
        from app.services.calculators.xiaoyi_metrics.env_judge.rejection_judge import (
            evaluate_rejection_judge_text,
        )
        rounds = (task_params or {}).get('rounds') or []
        per_round = []
        # 无任何拒识轮 → 全部跳过占位（不调 LLM、不产出指标）
        if not any(isinstance(rd, dict) and self._is_reject_round(task_params, rd) for rd in rounds):
            for i, rd in enumerate(rounds):
                per_round.append({
                    'round_number': self._per_round_number(task_params, rd, i),
                    'message': '跳过: 非拒识轮(is_reject=false)',
                })
            return {
                'enabled': True,
                'message': '跳过: 非拒识轮(is_reject=false)',
                'rate': None,
                'per_round': per_round,
            }

        # 最终轮（累积）音频：只取最大的双路 wav
        last = rounds[-1] if isinstance(rounds[-1], dict) else {}
        user_wav = last.get('user_wav') or ''
        ai_wav = last.get('ai_wav') or ''
        llm_config = self._extract_llm_config(task_params, last)
        first = rounds[0] if rounds and isinstance(rounds[0], dict) else {}
        has_intent = not self._is_reject_round(task_params, first)
        # 明确传递原始轮号及全部轮角色；不再依赖ASR停顿切段后顺序映射。
        configured_rounds = []
        for i, rd in enumerate(rounds):
            if not isinstance(rd, dict):
                continue
            configured_rounds.append({
                'configured_round_number': self._per_round_number(task_params, rd, i),
                'is_reject': self._is_reject_round(task_params, rd),
                'script_text': rd.get('query') if isinstance(rd.get('query'), str) else None,
            })
        judged = evaluate_rejection_judge_text(
            user_wav=user_wav, ai_wav=ai_wav,
            model=llm_config['model'],
            # 文本裁判一次处理整条时间线，输出轮次判定，放宽 max_tokens 防截断
            max_tokens=max(int(llm_config['max_tokens'] or 0), 8192),
            temperature=llm_config['temperature'], has_intent=has_intent,
            configured_rounds=configured_rounds,
        )
        judged_items = sorted(judged.get('rounds') or [], key=lambda j: j.get('round', 0))

        # 逐轮映射到配置轮序：第 k 个拒识配置轮 ← 第 k 段干扰判定
        reject_results = []
        reject_ord = 1
        for i, rd in enumerate(rounds):
            if not isinstance(rd, dict):
                continue
            rn = self._per_round_number(task_params, rd, i)
            if not self._is_reject_round(task_params, rd):
                per_round.append({
                    'round_number': rn, 'message': '跳过: 非拒识轮(is_reject=false)'})
                continue
            j = next((x for x in judged_items if x.get('round') == reject_ord), None)
            reject_ord += 1
            if j is None:
                per_round.append({
                    'round_number': rn,
                    'message': '未检测到对应拒识干扰(无文本段)，不计入统计',
                })
                continue
            if j.get('evaluation_status') == 'unjudgeable':
                per_round.append({'round_number': rn, 'rate': None,
                                  'evaluation_status': 'unjudgeable',
                                  'round_id': j.get('round_id'),
                                  'message': j.get('message'), 'reason': j.get('reason')})
                continue
            item = dict(j)
            item['round_number'] = rn
            for field in _SUM_FIELDS:
                item.setdefault(f'n_{field}', 1 if item.get(field) else 0)
            per_round.append(item)
            reject_results.append(item)

        n_reject_rounds = len(reject_results)
        if not reject_results:
            return {
                'enabled': True,
                'message': ('所有拒识轮不可判定' if any(r.get('evaluation_status') == 'unjudgeable' for r in per_round) else judged.get('message') or '未检测到拒识干扰'),
                'rate': None,
                'per_round': per_round,
                'round_alignment': judged.get('round_alignment', []),
                'audio_info': judged.get('audio_info', {}),
                'prompt_version': judged.get('prompt_version', ''),
                'n_unjudgeable_rounds': sum(r.get('evaluation_status') == 'unjudgeable' for r in per_round),
            }

        # 聚合（与 _calculate_per_round 同构：数量 + 占比 + count 合并）
        agg = dict(reject_results[-1])
        agg.pop('round_number', None)
        agg['n_reject_rounds'] = n_reject_rounds
        for field in _SUM_FIELDS:
            vals = [r.get(field, 0) for r in reject_results if r.get(field) is not None]
            count = sum(vals)
            agg[f'n_{field}'] = count
            agg[field] = round(count / n_reject_rounds, 3) if n_reject_rounds else 0
        # 整体 rate 按成功/失败轮数重算（与 _calculate_per_round 同构，不再继承末轮单轮 rate）
        # 注意：不在此设置 is_success —— 基础设施把 is_success=False 视为"评估内部失败"并丢弃结果，
        # 拒识失败是合法评估结论，只通过 rate 字段表达
        n_succ = agg.get('n_rate_success', 0) or 0
        n_fail = agg.get('n_rate_failure', 0) or 0
        agg['rate'] = '拒识成功' if n_succ > n_fail else '拒识失败'
        for dict_field in _COUNT_DICT_FIELDS:
            merged = {}
            for r in reject_results:
                d = r.get(dict_field, {})
                if isinstance(d, dict):
                    for k, v in d.items():
                        merged[k] = merged.get(k, 0) + (v if isinstance(v, (int, float)) else 0)
            agg[dict_field] = merged
        agg['tokens_used'] = sum(r.get('tokens_used', 0) for r in reject_results)
        agg['input_token'] = sum(r.get('input_token', 0) for r in reject_results)
        agg['output_token'] = sum(r.get('output_token', 0) for r in reject_results)
        agg['model'] = judged.get('model', '')
        agg['round_alignment'] = judged.get('round_alignment', [])
        agg['audio_info'] = judged.get('audio_info', {})
        agg['prompt_version'] = judged.get('prompt_version', '')
        agg['n_unjudgeable_rounds'] = sum(r.get('evaluation_status') == 'unjudgeable' for r in per_round)
        agg['message'] = judged.get('message') or 'OK'
        agg['per_round'] = per_round
        logger.info(
            f'[reject_judge] 文本整体评估: n_reject_rounds={n_reject_rounds} '
            f'配置拒识轮数={sum(1 for rd in rounds if isinstance(rd, dict) and self._is_reject_round(task_params, rd))} '
            f'user_wav={os.path.basename(user_wav) if user_wav else "无"} '
            f'success={agg.get("n_rate_success", 0)} '
            f'inquiry={agg.get("n_rate_inquiry", 0)} '
            f'failure={agg.get("n_rate_failure", 0)}'
        )
        return agg

    def _calculate_per_round(self, task_params):
        """逐轮切片计算 + 多轮聚合

        与 BaseCalculator 默认实现的区别：
        1. is_reject=false 的轮次不参与统计，per_round 中保留跳过项
           （{"round_number": i, "message": "跳过: 非拒识轮(is_reject=false)"}，
            per_round 数组长度与 rounds 一致，平台按 round_number 字段定位，不依赖下标）
        2. 每轮结果补充 n_ 前缀数量字段（与整体结果同构），平台据此
           process_group_dimension_results 解析并覆盖/创建逐轮 TRD
        3. 聚合时 0/1 字段求和得到数量，再除以拒识总轮次得到占比
        4. count 字典合并累加

        Returns:
            list: per_round 结果列表（task_service 会赋值到 result['per_round']）
            聚合结果通过 self._agg_result 传递，task_service 检测后覆盖顶层 result
        """
        rounds = (task_params or {}).get('rounds') or []
        per_round = []
        reject_results = []  # 仅有效拒识轮结果，用于聚合
        n_reject_rounds = 0
        failed_rounds = []   # 评估失败的拒识轮（round_number），任一存在则整例判定评估失败
        prev_active_end = 0.0  # 上一轮用户侧波形活跃段覆盖终点，用于本轮窗口化
        round_active = {}      # 每轮用户侧活跃段缓存（一次能量扫描，calculator/evaluate 复用）

        for i in range(len(rounds)):
            rd = rounds[i] if isinstance(rounds[i], dict) else {}
            # 本轮用户侧波形活跃段（能量检测，一次扫描缓存复用）
            segs_i = round_active.get(i)
            if segs_i is None:
                segs_i = self._user_active_segments((rd or {}).get('user_wav') or '')
                round_active[i] = segs_i
            next_coverage = max((e for _, e in segs_i), default=None) if segs_i else None

            # 跳过 is_reject=false 的轮次（非拒识轮不参与统计，per_round 保留跳过项）
            if not self._is_reject_round(task_params, rd):
                # 非拒识轮：填充占位项，保证 per_round 数组长度与 rounds 一致
                per_round.append({
                    'round_number': self._per_round_number(task_params, rd, i),
                    'message': '跳过: 非拒识轮(is_reject=false)',
                })
                if next_coverage is not None:
                    prev_active_end = next_coverage
                continue

            single = dict(task_params)
            single['round_number'] = i
            # 清空顶层轮次相关字段
            for k in self._TOP_LEVEL_ROUND_FIELDS:
                single.pop(k, None)
            # 注入该轮音频字段
            for k in self._AUDIO_FIELD_NAMES:
                if rd.get(k):
                    single[k] = rd[k]
            # 累积音频窗口化：本轮新增干扰从上一轮覆盖终点之后寻找；活跃段复用，避免重复扫描
            single['prev_active_end'] = prev_active_end
            single['active_segments'] = segs_i
            try:
                result = self.run(single)
            except Exception as e:
                logger.warning(f"[_calculate_per_round] round={i} 失败: {e}")
                result = {}
            # 逐轮评估（round_number 有值）时 rounds 被切成单轮，本地下标 i 不代表用例级轮号，
            # 必须用请求级 round_number 打号，否则该轮结果被标成 0，平台落库到 round 0 的 TRD
            result['round_number'] = self._per_round_number(task_params, rd, i)
            # 与整体结果同构：单轮也输出 n_ 前缀数量字段（0/1），
            # 平台按维度 field_path（如 n_rate_success / n_success_silent_recover）提取逐轮 TRD
            for field in _SUM_FIELDS:
                result.setdefault(f'n_{field}', 1 if result.get(field) else 0)
            # 更新覆盖终点（供下一轮窗口化）
            if next_coverage is not None:
                prev_active_end = next_coverage

            # ─── 新增: 干扰可判定性 + timing 一致性校验 ───
            # timing 由 LLM 基于「干扰发生时模型是否在说话」判定（静默/回复过程中）；
            # 干扰不可判定（被降噪抹掉等）或判定结果与配置 timing 不一致 → 该轮不计入统计（保留明细并标记）
            if result.get('undetectable'):
                result['excluded'] = True
                per_round.append(result)
                continue

            judged_timing = str(result.get('judged_timing', '') or '').strip()
            config_timing = str(rd.get('timing') or task_params.get('timing') or '静默').strip()
            if judged_timing and config_timing and judged_timing != config_timing:
                result['timing_mismatch'] = True
                result['excluded'] = True
                result['message'] = (
                    f'timing不匹配: 模型判定={judged_timing}, 配置={config_timing}, 该轮不计入统计'
                )
                per_round.append(result)
                continue

            n_reject_rounds += 1
            per_round.append(result)
            reject_results.append(result)
            # 检测该轮是否评估失败（LLM 调用失败/输出解析失败等）：任一失败 → 整例判定评估失败
            if self._is_round_failed(result):
                failed_rounds.append(i)

        # 聚合（仅统计有效拒识轮结果，跳过占位项）
        if not reject_results:
            self._agg_result = None
            return per_round

        # 以最后一个有效拒识轮为基底，剥离逐轮残留字段（round_number），
        # 保证整体结果顶层不含轮次字段（round_number 只属于 per_round 元素）
        agg = dict(reject_results[-1])
        agg.pop('round_number', None)
        agg['n_reject_rounds'] = n_reject_rounds

        # 0/1 字段求和 → 数量（n_ 前缀），再算占比
        for field in _SUM_FIELDS:
            vals = [r.get(field, 0) for r in reject_results if r.get(field) is not None]
            count = sum(vals)
            agg[f'n_{field}'] = count
            agg[field] = round(count / n_reject_rounds, 3) if n_reject_rounds else 0

        # 整体 rate 按成功/失败轮数重算（成功 > 失败 → 拒识成功，否则拒识失败；
        # 不再继承最后一轮的单轮 rate，避免 1成1询1败等分布被末轮结果带偏）
        # 注意：不在此设置 is_success —— 基础设施把 is_success=False 视为"评估内部失败"并丢弃结果，
        # 拒识失败是合法评估结论，只通过 rate 字段表达
        n_succ = agg.get('n_rate_success', 0) or 0
        n_fail = agg.get('n_rate_failure', 0) or 0
        agg['rate'] = '拒识成功' if n_succ > n_fail else '拒识失败'

        # count 字典合并累加（rate_success_count / rate_inquiry_count / rate_failure_count）
        for dict_field in _COUNT_DICT_FIELDS:
            merged = {}
            for r in reject_results:
                d = r.get(dict_field, {})
                if isinstance(d, dict):
                    for k, v in d.items():
                        merged[k] = merged.get(k, 0) + (v if isinstance(v, (int, float)) else 0)
            agg[dict_field] = merged

        # token 求和
        agg['tokens_used'] = sum(r.get('tokens_used', 0) for r in reject_results)
        agg['input_token'] = sum(r.get('input_token', 0) for r in reject_results)
        agg['output_token'] = sum(r.get('output_token', 0) for r in reject_results)

        # ═══ 整例失败判定 ═══
        # 任一拒识轮评估失败（LLM 调用失败/输出解析失败等）→ 整例判定为评估失败。
        # 失败轮已计入 n_reject_rounds 但不会归入任何分子，若照常输出会把占比分母撑大，
        # 导致 成功/询问/失败 三率之和 < 100%；因此整体标记失败并清空统计字段，
        # 平台侧见 message 含 'LLM 调用失败' 即整例剔除（不参与分子/分母）。
        if failed_rounds:
            agg['enabled'] = False
            agg['is_success'] = False
            agg['message'] = (
                f'LLM 调用失败: 拒识轮评估失败，整例判定评估失败'
                f'（失败轮次: {failed_rounds}）'
            )
            for field in _SUM_FIELDS:
                agg.pop(f'n_{field}', None)
            agg.pop('n_reject_rounds', None)
            for dict_field in _COUNT_DICT_FIELDS:
                agg.pop(dict_field, None)
            logger.warning(
                f'[reject_judge] 整例判定评估失败: 失败拒识轮 {failed_rounds}, '
                f'n_reject_rounds={n_reject_rounds}（已清空占比统计）'
            )

        logger.info(
            f'[reject_judge] 多轮聚合: n_reject_rounds={n_reject_rounds} '
            f'success={agg.get("n_rate_success", 0)} '
            f'inquiry={agg.get("n_rate_inquiry", 0)} '
            f'failure={agg.get("n_rate_failure", 0)}'
        )

        self._agg_result = agg
        return per_round
