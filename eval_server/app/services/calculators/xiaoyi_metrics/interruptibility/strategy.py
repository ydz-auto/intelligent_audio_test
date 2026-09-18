# -*- coding: utf-8 -*-
"""interruptibility 策略类

打断指标计算：用户打断正在说话的小艺时，衡量小艺"停得下、恢复得来"。

单轮 vs 多轮区分：
  - round_number 有值（0/1/2...）→ 单轮评估，取 rounds[round_number]
  - round_number 不存在 → 多轮整体评估，取最后一轮

取参方式：
  单轮 → 取当前轮 user_wav/ai_wav（或已对齐的 user_asr/model_asr）
  多轮 → 取最后一轮双路音频/ASR（打断场景通常在最后一轮）

委托计算给 interruptibility.calculate_interruption_metrics 统一入口，
该入口内部完成 wav→ASR 与本地时序指标(compute_interruption_metrics)，
不调用任何 LLM；LLM 语义/行为/停止指令判定由 env_judge.interruption_judge 承担。

多轮语义：
  - 有效实际打断轮 = 平台传入的 interruption_rounds，或按 is_actual_interruption /
    is_interruption 的下一轮推导；末轮 dangling 标记不入分母
  - 主成功率 = 所有有效实际轮都成功才为 1，任一轮失败为 0
  - 失败率 = 失败轮数 / 有效实际轮数
  - round_latencies 逐轮返回时延明细，avg_* 为跨轮平均
  - first_recovery_latency_s 只取最后一个有效实际轮（前面轮次回复被截断）
"""
import logging
from app.services.calculators.base import BaseCalculator

logger = logging.getLogger(__name__)


class InterruptionMetricsCalculator(BaseCalculator):
    """打断指标：用户打断模型时，衡量"停得下、恢复得来"

    单轮：取当前轮双路音频
    多轮：取最后一轮双路音频算 1 次

    单轮/多轮公共方法（_is_multi_round / _get_target_round_index /
    _get_round_safe / _get_audio_from_round）由 BaseCalculator 统一提供。
    """
    task_type = 'interruption_metrics'
    supports_per_round = True

    # ─── Calculator 实现 ───

    @staticmethod
    def _actual_rounds(task_params):
        """有效实际打断轮：优先显式列表，其次 is_actual_interruption，再从 marker 下一轮推导。

        平台经 multipart 上传时 `interruption_rounds` 会是 JSON 字符串（如 '[1]'），
        轮内标记会是 'true'/'1' 之类字符串，统一交给 _derive_interruption_rounds 归一化。
        """
        from app.services.calculators.xiaoyi_metrics.interruptibility import (
            _derive_interruption_rounds,
        )

        params = task_params or {}
        if params.get('interruption_rounds') is None and not isinstance(params.get('rounds'), list):
            return None
        actual, _dangling = _derive_interruption_rounds(params)
        return actual

    def validate(self, task_params):
        rounds = task_params.get('rounds') or []
        actual_rounds = self._actual_rounds(task_params)
        if actual_rounds:
            for idx in actual_rounds:
                rd = self._get_round_safe(task_params, idx)
                if self._round_has_input(task_params, rd):
                    return True, None
            return False, f"Missing required field for {self.task_type}: actual interruption round audio/ASR"

        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        if self._round_has_input(task_params, rd):
            return True, None
        return False, f"Missing required field for {self.task_type}: user_wav/ai_wav or user_asr/model_asr"

    @staticmethod
    def _round_has_input(task_params, round_data):
        params = task_params or {}
        rd = round_data or {}
        return bool(
            (rd.get('user_wav') or params.get('user_wav') or rd.get('user_asr') or params.get('user_asr') or rd.get('user_chunks') or params.get('user_chunks'))
            and
            (rd.get('ai_wav') or params.get('ai_wav') or rd.get('model_asr') or params.get('model_asr') or rd.get('model_chunks') or params.get('model_chunks'))
        )

    def prepare_params(self, task_params):
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        rd = self._get_round_safe(task_params, idx)
        user_asr = task_params.get('user_asr') or task_params.get('user_chunks') or rd.get('user_asr') or rd.get('user_chunks')
        model_asr = task_params.get('model_asr') or task_params.get('model_chunks') or rd.get('model_asr') or rd.get('model_chunks')
        rounds = task_params.get('rounds') or []
        actual_rounds = self._actual_rounds(task_params)
        # round_number 是**用例级**轮索引；平台逐轮评估时 rounds 已被切成一片，
        # 因此判定"本轮是否实际打断轮"要用原始 round_number，取数才用钳制后的 idx。
        case_round = self._round_index(task_params.get('round_number'))
        is_actual_interruption = None
        if actual_rounds is not None:
            if not rounds:
                is_actual_interruption = bool(actual_rounds)
            elif case_round is not None:
                is_actual_interruption = case_round in actual_rounds
            else:
                is_actual_interruption = idx in actual_rounds
        return {
            'mode': 'single',
            'user_wav': user_wav,
            'ai_wav': ai_wav,
            'user_asr': user_asr,
            'model_asr': model_asr,
            'is_actual_interruption': is_actual_interruption,
            'interruption_rounds': actual_rounds,
            'task_params': task_params,
        }

    def run(self, task_params):
        """独立调用入口：结果包装为 {'interruption': result}"""
        params = self.prepare_params(task_params)
        result = self.calculate(params)
        return {'interruption': result}

    @staticmethod
    def _average(results, key):
        values = [r.get(key) for r in results]
        values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return round(sum(values) / len(values), 3) if values else None

    def _calculate_round(self, params, round_index, shared_asr=None):
        from app.services.calculators.xiaoyi_metrics.interruptibility import calculate_interruption_metrics

        source = params.get('task_params') or {}
        rounds = source.get('rounds') or []
        rd = rounds[round_index] if round_index < len(rounds) and isinstance(rounds[round_index], dict) else {}
        task_params = dict(source)
        task_params['round_number'] = round_index
        task_params['user_wav'] = rd.get('user_wav') or source.get('user_wav') or ''
        task_params['ai_wav'] = rd.get('ai_wav') or rd.get('model_wav') or source.get('ai_wav') or source.get('model_wav') or ''
        task_params['case_wav'] = rd.get('case_wav') or source.get('case_wav') or ''
        # 本轮干净音源(FFT 精修)：rd 级 played_audios 优先；多轮时不回退用例级，
        # 避免 rounds[-1] 提升出来的顶层值错配到别的轮
        task_params['played_audios'] = rd.get('played_audios') or (
            source.get('played_audios') if len(rounds) <= 1 else None)
        task_params['user_asr'] = (
            rd.get('user_asr')
            or rd.get('user_chunks')
            or source.get('user_asr')
            or source.get('user_chunks')
        )
        task_params['model_asr'] = (
            rd.get('model_asr')
            or rd.get('model_chunks')
            or source.get('model_asr')
            or source.get('model_chunks')
        )
        task_params['is_actual_interruption'] = True
        # 保留用例级有效实际轮列表：子调用据此判断本轮是否为最后一轮
        # （恢复首轮时延只评最后一个有效实际打断轮）
        task_params['interruption_rounds'] = list(params.get('interruption_rounds') or [round_index])
        task_params['stop_intent'] = source.get('stop_intent', False)
        if isinstance(source.get('stop_intent'), list) and round_index < len(source['stop_intent']):
            task_params['stop_intent'] = source['stop_intent'][round_index]
        task_params['stop_intent'] = rd.get('stop_intent', rd.get('is_stop_instruction', task_params['stop_intent']))

        child_params = {
            'user_wav': task_params.get('user_wav'),
            'ai_wav': task_params.get('ai_wav'),
            'task_params': task_params,
        }
        if shared_asr and shared_asr.get('user_wav') == task_params.get('user_wav') \
                and shared_asr.get('ai_wav') == task_params.get('ai_wav'):
            child_params['_shared_asr'] = shared_asr

        # Reuse the existing single-round path; only matching-source shared ASR is reused.
        single = self.prepare_params(task_params)
        single.update(child_params)
        single['is_actual_interruption'] = True
        # v2：用例级聚合统一调一次 LLM 出全轮行为，逐轮子计算不再单独判
        single['_skip_llm_judge'] = True
        return self.calculate_single(single)

    def calculate_single(self, params):
        from app.services.calculators.xiaoyi_metrics.interruptibility import calculate_interruption_metrics

        task_params = dict(params.get('task_params') or {})
        shared = params.get('_shared_asr') or {}
        if shared.get('user_chunks') and shared.get('user_wav') == params.get('user_wav') \
                and not task_params.get('user_asr'):
            task_params['user_asr'] = shared['user_chunks']
        if shared.get('ai_chunks') and shared.get('ai_wav') == params.get('ai_wav') \
                and not task_params.get('model_asr'):
            task_params['model_asr'] = shared['ai_chunks']
        if params.get('is_actual_interruption') is not None:
            task_params['is_actual_interruption'] = params['is_actual_interruption']
        result = calculate_interruption_metrics(task_params)

        # v2：单轮请求（平台逐轮评估/直调路径）也进程内直调 LLM 判本轮行为；
        # LLM 缺失/失败时保持 __init__ 已挂的降级字段
        timing = result.get('round_timing') or []
        if timing and not params.get('_skip_llm_judge'):
            from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
                build_round_block, chunks_from_segments, derive_case_type,
            )
            from app.services.calculators.xiaoyi_metrics.shared.llm_client import build_interaction_text

            rounds = task_params.get('rounds') or []
            ridx = timing[0].get('round')
            rd = self._rd(rounds, ridx) if isinstance(ridx, int) else {}
            if not rd and len(rounds) == 1:
                rd = self._rd(rounds, 0)  # 平台逐轮评估时 rounds 已切片
            case_info = derive_case_type(
                rounds, result.get('interruption_rounds') or [],
                result.get('dangling_interruption_rounds') or [],
                stop_intent=result.get('stop_intent'))
            interaction = build_interaction_text(
                chunks_from_segments(result.get('user_segments')),
                chunks_from_segments(result.get('model_segments')))
            self._judge_and_attach(result, [build_round_block(timing[0], result, rd)],
                                   interaction, task_params, timing, None, case_info,
                                   preserve_resume=True)
        return result

    @staticmethod
    def _rd(rounds, idx):
        if isinstance(rounds, list) and isinstance(idx, int) and 0 <= idx < len(rounds) \
                and isinstance(rounds[idx], dict):
            return rounds[idx]
        return {}

    def _judge_and_attach(self, result, blocks, interaction_text, task_params,
                          timing, resume_timing, case_info, preserve_resume=False):
        """进程内直调逐轮 LLM 五分类裁判，成功则重派生覆盖降级 spec 字段。"""
        from app.services.calculators.xiaoyi_metrics.env_judge.interruption_judge import (
            behaviors_from_judge, judge_interruption_rounds,
        )
        from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
            derive_round_metrics,
        )

        def _num(v):
            try:
                return float(v) if v not in (None, '') else None
            except (TypeError, ValueError):
                return None

        max_tokens = _num(task_params.get('max_tokens'))
        judge_result = judge_interruption_rounds(
            blocks, interaction_text,
            model=str(task_params.get('model') or ''),
            max_tokens=int(max_tokens) if max_tokens else None,
            temperature=_num(task_params.get('temperature')),
        )
        result['interaction_text'] = interaction_text or result.get('interaction_text')
        if not judge_result or not judge_result.get('enabled'):
            msg = (judge_result or {}).get('message') or ''
            if msg and msg != '无可判定轮次':
                base = result.get('message') or ''
                result['message'] = f'{base}；LLM 行为判定降级: {msg}' if base else f'LLM 行为判定降级: {msg}'
            return result

        behaviors = behaviors_from_judge(judge_result)
        if resume_timing is not None and behaviors:
            rb = next((b for b in behaviors if b.get('round') == resume_timing.get('round')), None)
            if rb is not None:
                resume_timing['score_overall'] = rb.get('score_overall')
        if behaviors is not None:
            spec = derive_round_metrics(timing, behaviors, case_info, resume_timing)
            if preserve_resume:
                # 单轮路径的恢复时延门控(is_last_actual)在 __init__ 已定，不覆盖
                spec['resume_first_reply_latency_ms'] = result.get('resume_first_reply_latency_ms')
            result.update(spec)
        result['llm_round_evaluations'] = judge_result.get('rounds') or []
        result['llm_judge_model'] = judge_result.get('model')
        result['tokens_used'] = judge_result.get('tokens_used', 0)
        return result

    def calculate(self, params):
        actual_rounds = params.get('interruption_rounds')
        source = params.get('task_params') or {}
        rounds = source.get('rounds') or []
        # Overall multi-round evaluation: calculate each valid actual round, then AND the binary results.
        if actual_rounds and rounds and isinstance(rounds, list) and params.get('mode') == 'single' \
                and source.get('round_number') is None:
            shared = params.get('_shared_asr') or {}
            round_results = [self._calculate_round(params, idx, shared) for idx in actual_rounds]
            if not round_results:
                return {'interruption_success_rate': 0, 'timing_success_rate': 0,
                        'interruption_rounds': list(actual_rounds), 'round_results': [],
                        'message': '无有效实际打断轮'}

            result = dict(round_results[-1])
            result['interruption_rounds'] = list(actual_rounds)
            result['round_results'] = [dict(r, round_number=idx)
                                       for idx, r in zip(actual_rounds, round_results)]
            result['per_event'] = [event for r in round_results for event in r.get('per_event', [])]
            result['round_latencies'] = [
                item for r in round_results for item in r.get('round_latencies', [])
            ]
            for key in ('n_events', 'n_user_segments', 'n_recovery_only', 'n_no_model_speech'):
                result[key] = sum((r.get(key) or 0) for r in round_results)
            for key in ('avg_stop_latency_s', 'avg_recovery_latency_s',
                        'avg_overlap_s', 'avg_silence_gap_s'):
                result[key] = self._average(round_results, key)
            result['interruption_success_rate'] = int(all(
                r.get('interruption_success_rate') == 1 for r in round_results
            ))
            # 失败率与成功率二值互补：多轮里只要有一轮失败，整例即算失败
            result['interruption_failure_rate'] = float(1 - result['interruption_success_rate'])
            # 只有最后一个有效实际打断轮的回复是完整的，其首轮恢复时延直接取末轮结果
            result['first_recovery_latency_s'] = round_results[-1].get('first_recovery_latency_s')
            # 目标事件时延同样以末个有效实际轮为准；avg_* 仍是跨轮平均
            for key in ('target_stop_latency_s', 'target_recovery_latency_s'):
                result[key] = round_results[-1].get(key)
            result['timing_success_rate'] = result['interruption_success_rate']
            result['stop_rate'] = int(all(r.get('stop_rate') == 1 for r in round_results))
            result['resume_rate'] = int(all(r.get('resume_rate') == 1 for r in round_results))

            # ── v2 spec：用例类型推导 + 逐轮时序聚合 + 恢复轮锚定 → 派生层出全部 spec 字段 ──
            from app.services.calculators.xiaoyi_metrics.interruptibility import _derive_interruption_rounds
            from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
                build_round_block, derive_case_type, derive_round_metrics,
            )

            _, dangling_rounds = _derive_interruption_rounds(source)
            case_info = derive_case_type(rounds, actual_rounds, dangling_rounds,
                                         stop_intent=source.get('stop_intent'))
            # 恢复轮即使被标为实际打断轮也不入时序聚合（避免与 resume 条目重复计数）
            _resume_set = set(case_info['resume_rounds'])
            timed_pairs = [(t, r) for r in round_results for t in r.get('round_timing', [])
                           if t.get('round') not in _resume_set]
            round_timing = [t for t, _ in timed_pairs]
            resume_timing = resume_result = None
            if case_info['resume_rounds']:
                resume_timing, resume_result = self._resume_round_timing(
                    params, case_info['resume_rounds'][0], round_results, shared)
            # 先出无行为的降级 spec（数量/评分 None、list 记 -1），LLM 成功后重派生覆盖
            spec = derive_round_metrics(round_timing, None, case_info, resume_timing)
            result.update(spec)
            result['round_timing'] = round_timing + ([resume_timing] if resume_timing else [])

            result['message'] = 'OK' if result['interruption_success_rate'] else '至少一个实际打断轮失败'
            if any(t.get('anchor_method') in ('none', 'overlap_heuristic') for t in round_timing):
                result['message'] += '；部分轮时序锚定降级(无FFT/驱动窗口)'

            # 逐轮 LLM 五分类裁判：整例一次调用（成本约束不变），失败自动保持降级字段
            blocks = [build_round_block(t, r, self._rd(rounds, t.get('round')))
                      for t, r in timed_pairs]
            if resume_timing is not None:
                blocks.append(build_round_block(
                    resume_timing, resume_result or {},
                    self._rd(rounds, resume_timing.get('round'))))
            self._judge_and_attach(
                result, blocks,
                self._interaction_text(rounds, actual_rounds, round_results),
                source, round_timing, resume_timing, case_info)
            return result

        return self.calculate_single(params)

    def _interaction_text(self, rounds, actual_rounds, round_results):
        """用例级交互文字时间线：case 共用录音=全局时间线；轮录音=逐轮分节拼轮号。"""
        from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
            chunks_from_segments,
        )
        from app.services.calculators.xiaoyi_metrics.shared.llm_client import build_interaction_text

        own_audio = any(
            self._rd(rounds, i).get('user_wav') or self._rd(rounds, i).get('ai_wav')
            or self._rd(rounds, i).get('user_asr') or self._rd(rounds, i).get('model_asr')
            for i in actual_rounds)
        if not own_audio and round_results:
            base = round_results[-1]
            return build_interaction_text(
                chunks_from_segments(base.get('user_segments')),
                chunks_from_segments(base.get('model_segments')))
        parts = []
        for idx, r in zip(actual_rounds, round_results):
            text = build_interaction_text(
                chunks_from_segments(r.get('user_segments')),
                chunks_from_segments(r.get('model_segments')))
            if text:
                parts.append(f'【第 {idx} 轮】\n{text}')
        return '\n'.join(parts)

    def _resume_round_timing(self, params, resume_idx, round_results, shared):
        """恢复轮时序锚定（恢复首轮内容时延）。

        轮录音模式：恢复轮有独立音频/ASR → 复用单轮计算（含 FFT 精修）；
        case 共用录音模式：在全局段上 FFT(played_audios)/驱动窗口定位恢复轮窗口。

        Returns:
            (timing_entry|None, round_result|None)：round_result 供 LLM 标注块取三段文本
        """
        from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
            _driver_window_overlap, extract_round_timing, locate_fft_window,
            round_latency_from_window,
        )

        source = params.get('task_params') or {}
        rounds = source.get('rounds') or []
        rd = self._rd(rounds, resume_idx)
        if rd.get('user_wav') or rd.get('ai_wav') or rd.get('user_asr') or rd.get('model_asr'):
            r = self._calculate_round(params, resume_idx, shared)
            return extract_round_timing(r, rd, resume_idx, role='resume'), r

        base = round_results[-1] if round_results else {}
        win = locate_fft_window(rd.get('played_audios') or rd.get('case_wav'), source.get('user_wav'))
        method = 'fft'
        if win is None:
            seg = _driver_window_overlap(rd, base.get('user_segments') or [])
            win = (seg[0], seg[1], None) if seg else None
            method = 'driver_window'
        if win is None:
            return None, None
        resp, reply = round_latency_from_window(win[0], win[1], base.get('model_segments') or [])
        return {'round': resume_idx, 'role': 'resume',
                'u_s': round(win[0], 3), 'u_e': round(win[1], 3),
                'anchor_method': method, 'response_latency_ms': resp,
                'reply_latency_ms': reply, 'stop_intent': False}, base
