# -*- coding: utf-8 -*-
"""turn_eval 策略类：逐轮三分类主维度

从 turn_taking 拆出的独立主维度，专注：
  1. 轮次切分 + 逐轮三分类（误解管 / 接管 / 未接管）
  2. 仅对"接管"轮计算接管时延
  3. 仅对"接管"轮评分回复质量

ASR 共享：优先复用上层编排器（XiaoyiMetricsCalculator）注入的 _shared_asr，
独立调用时自行调 ASR + 音频对齐。

多轮模式：整体评估时以末轮（rounds[-1]）的 user_wav + ai_wav 为评估对象，
合并所有轮次的 played_audios 一次性对齐 + ASR + 切轮 + 三分类，
每条 turn 通过对齐段归属到其真实轮次，并按轮投影原生 per_round[]（零额外 ASR/LLM）。
"""
import logging

from app.services.calculators.base import BaseCalculator
from app.services.calculators.xiaoyi_metrics.shared.asr_utils import compute_pause_intervals
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


class TurnEvalCalculator(BaseCalculator):
    """逐轮三分类主维度：轮次切分 → 三分类 → 接管时延 → 回复质量

    与 TurnTakingCalculator 的区别：
    - TurnTakingCalculator：旧流程，tor/false_takeover/takeover_latency 各算各的
    - TurnEvalCalculator：新流程，先切轮次 → 逐轮统一判定三分类 → 按分类结果补充时延/质量

    输出结构：
        {
            'turn_classification': {
                'summary': '正常接管N，未接管M，误解管K',
                'normal_takeover_count': N,
                'no_takeover_count': M,
                'false_takeover_count': K,
                'total_turns': T,
                'turns': [...],   # 逐轮详情（含 round_number）
            },
            # 兼容旧字段（取最后一轮结果）
            'tor': {...},
            'false_takeover': {...},
            'takeover_latency': {...},
            'reply_quality': {...},
            'interaction_text': '...',
            'per_round': [...],   # 逐轮结果（整体评估模式）
        }
    """
    task_type = 'turn_eval'
    supports_per_round = True

    def validate(self, task_params):
        user_wav, ai_wav = self._get_audio_from_round(
            task_params, self._get_target_round_index(task_params)
        )
        if not (user_wav or ai_wav):
            return False, (
                f"Missing required field for {self.task_type}: "
                f"user_wav / ai_wav，至少需要一个"
            )
        return True, None

    def prepare_params(self, task_params):
        """直接透传 task_params"""
        return task_params

    # ─────────── 辅助方法 ───────────

    def _build_shared_asr(self, user_wav, ai_wav, played_audios):
        """构建单轮的共享 ASR 数据（音频对齐 + ASR 调用）

        Returns:
            dict: {
                'user_wav', 'user_chunks',
                'ai_wav', 'ai_chunks', 'ai_word_chunks',
                'played_audios', 'pause_intervals',
            }
        """
        from app.services.calculators.xiaoyi_metrics.turn_taking.strategy import TurnTakingBase

        shared_asr = {}

        # 音频对齐：played_audios（干净音源）→ user_wav（劣化）生成干净版音频
        effective_user_wav = user_wav
        if played_audios and user_wav:
            from app.services.calculators.xiaoyi_metrics.shared.audio_alignment import (
                generate_aligned_clean_audio,
            )
            try:
                align_result = generate_aligned_clean_audio(user_wav, played_audios)
                if align_result.get('aligned_wav'):
                    effective_user_wav = align_result['aligned_wav']
                    logger.info(
                        f"[turn_eval] 音频对齐成功: "
                        f"平均NCC={align_result.get('ncc', 0):.4f}"
                    )
                    # 每段对齐信息（source=played_audio 文件名 → 轮次），供 turn 轮次归属
                    shared_asr['_align_segments'] = align_result.get('segments') or []
                else:
                    logger.warning(f"[turn_eval] 音频对齐失败: {align_result.get('message')}")
            except Exception as e:
                logger.warning(f"[turn_eval] 音频对齐异常: {e}，回退原始 user_wav")

        if effective_user_wav:
            shared_asr['user_wav'] = effective_user_wav
            shared_asr['user_chunks'] = TurnTakingBase._get_asr_chunks(effective_user_wav)
        if ai_wav:
            shared_asr['ai_wav'] = ai_wav
            shared_asr['ai_chunks'] = TurnTakingBase._get_asr_chunks(ai_wav)
            shared_asr['ai_word_chunks'] = TurnTakingBase._get_asr_chunks(ai_wav, filter_punct=False)
        if played_audios:
            shared_asr['played_audios'] = played_audios
        if shared_asr.get('user_chunks'):
            shared_asr['pause_intervals'] = TurnTakingBase._compute_pause_intervals(shared_asr['user_chunks'])
        else:
            shared_asr['pause_intervals'] = []

        return shared_asr

    def _eval_one_round(self, shared_asr, task_params, round_idx, turn_idx_offset):
        """对单轮 ASR 数据做轮次切分 + 三分类 + 接管时延 + 回复质量

        Returns:
            (turn_results, normal_count, no_takeover_count, false_takeover_count,
             user_chunks, ai_word_chunks)
        """
        from app.services.calculators.xiaoyi_metrics.turn_eval.turn_evaluation import (
            evaluate_all_turns, TurnClassification,
        )
        from app.services.calculators.xiaoyi_metrics.turn_taking.takeover_latency import (
            compute_takeover_latency_from_chunks,
        )
        from app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality import (
            evaluate_reply_quality_per_turn,
        )

        user_chunks = shared_asr.get('user_chunks') or []
        ai_chunks = shared_asr.get('ai_chunks') or []
        ai_word_chunks = shared_asr.get('ai_word_chunks') or ai_chunks

        turns, classifications = evaluate_all_turns(user_chunks, ai_chunks, task_params)

        turn_results = []
        normal_count = 0
        no_takeover_count = 0
        false_takeover_count = 0

        for turn, cls in zip(turns, classifications):
            turn_detail = {
                'turn_index': turn.turn_index + turn_idx_offset,
                'round_number': round_idx,
                'classification': cls.classification,
                'false_takeover': cls.false_takeover,
                'tor': cls.tor,
                'takeover_judge': cls.takeover_judge,
                'takeover_latency': None,    # 仅"接管"时填
                'reply_quality': None,       # 仅"接管"时填
                'user_start_s': round(turn.user_start_s, 3),
                'user_end_s': round(turn.user_end_s, 3),
                'ai_start_s': round(turn.ai_start_s, 3) if turn.ai_start_s is not None else None,
                'ai_end_s': round(turn.ai_end_s, 3) if turn.ai_end_s is not None else None,
                'has_ai_reply': turn.has_ai_reply(),
            }

            if cls.classification == TurnClassification.TAKEOVER:
                # ── 接管时延（仅"接管"时计算）──
                latency_result = compute_takeover_latency_from_chunks(
                    turn.user_chunks, turn.ai_chunks or [],
                    played_audios=shared_asr.get('played_audios'),
                    user_wav=shared_asr.get('user_wav'),
                )
                turn_detail['takeover_latency'] = latency_result

                # ── 回复质量评分（仅"接管"时评分）──
                quality_result = evaluate_reply_quality_per_turn(
                    user_chunks=turn.user_chunks,
                    ai_chunks=turn.ai_chunks,
                    classification=cls.classification,
                    task_params=task_params,
                )
                turn_detail['reply_quality'] = quality_result
                normal_count += 1

            elif cls.classification == TurnClassification.NO_TAKEOVER:
                no_takeover_count += 1

            elif cls.classification == TurnClassification.MISUNDERSTAND:
                false_takeover_count += 1

            turn_results.append(turn_detail)

        logger.info(
            f"[turn_eval] 共享 ASR 完成 (round={round_idx}): "
            f"user_chunks={len(user_chunks)}, "
            f"ai_chunks={len(ai_chunks)}, "
            f"ai_word_chunks={len(ai_word_chunks)}, "
            f"pause={len(shared_asr.get('pause_intervals') or [])}"
        )

        # 多轮合并模式：把每条 turn 归属到其真实轮次
        # （对齐 segments 的 source=played_audio 文件名 → 轮次映射，按时间重叠匹配）
        align_segments = shared_asr.get('_align_segments') or []
        round_of = shared_asr.get('_round_of_played_audio') or {}
        if align_segments and round_of:
            for td in turn_results:
                rn = self._match_turn_round(td, align_segments, round_of)
                if rn is not None:
                    td['round_number'] = rn

        return (turn_results, normal_count, no_takeover_count,
                false_takeover_count, user_chunks, ai_word_chunks)

    @staticmethod
    def _match_turn_round(turn_detail, segments, round_of):
        """按时间重叠把 turn 匹配到对齐段，返回该段 played_audio 所属轮次（查表），无匹配返回 None"""
        u0 = turn_detail.get('user_start_s')
        u1 = turn_detail.get('user_end_s')
        if u0 is None or u1 is None:
            return None
        best = None
        best_overlap = 0.0
        for seg in segments:
            s0 = seg.get('offset_s') or 0.0
            s1 = s0 + (seg.get('clean_duration_s') or 0.0)
            overlap = min(u1, s1) - max(u0, s0)
            if overlap > best_overlap:
                best_overlap = overlap
                best = seg
        if best is not None and best_overlap > 0.0:
            return round_of.get(best.get('source'))
        return None

    # ─────────── 主计算 ───────────

    def _merge_all_played_audios(self, task_params):
        """合并所有轮次的 played_audios 为一个 list（按 audio_path 去重，保持首现顺序）

        顶层 params.played_audios 优先并入，随后按轮次顺序并入各轮 rounds[*].played_audios。
        兼容 list[dict]（取 audio_path）/ 单个 dict / str 路径等形态。

        Returns:
            (list, dict): 合并后的 played_audios + {audio_path 文件名: round_index} 归属映射，
            供整体合并评估把每条 turn 归属到其真实轮次（对齐 segments 的 source 文件名查表）。
        """
        import os as _os

        merged = []
        seen_paths = set()
        rounds = task_params.get('rounds') or []

        sources = [task_params.get('played_audios')]
        sources.extend(
            (rd or {}).get('played_audios')
            for rd in rounds if isinstance(rd, dict)
        )

        for src in sources:
            if not src:
                continue
            items = src if isinstance(src, list) else [src]
            for item in items:
                if not item:
                    continue
                path = item.get('audio_path') if isinstance(item, dict) else str(item)
                if path and path in seen_paths:
                    continue
                if path:
                    seen_paths.add(path)
                merged.append(item)

        # 轮次归属：rounds[i].played_audios 的 audio_path 文件名 → round_index
        round_of = {}
        for ri, rd in enumerate(rounds):
            if not isinstance(rd, dict):
                continue
            src2 = rd.get('played_audios') or []
            items2 = src2 if isinstance(src2, list) else [src2]
            for item in items2:
                if not item:
                    continue
                path = item.get('audio_path') if isinstance(item, dict) else str(item)
                if path:
                    round_of[_os.path.basename(str(path).replace('\\', '/'))] = ri
        return merged, round_of

    def calculate(self, params):
        """新流程：多轮合并 / 单轮处理，逐轮三分类 → 接管时延 → 回复质量 → 汇总输出

        多轮模式（整体评估）：以末轮（rounds[-1]）的 user_wav + ai_wav 为评估对象，
        合并**所有轮次**的 played_audios 一次性对齐 + ASR + 切轮 + 三分类，
        每条 turn 通过对齐段归属到其**真实轮次**，并按轮投影原生 per_round[]
        （零额外 ASR/LLM，参考打断 v2 build_per_round；TaskService 见原生 per_round 即跳过切片重跑）。

        单轮模式 / 编排器注入 _shared_asr：只处理一轮（兼容旧路径）。
        """
        from app.services.calculators.xiaoyi_metrics.shared.llm_client import build_interaction_text

        task_params = params.get('task_params') or params
        rounds = task_params.get('rounds') or []
        is_multi = self._is_multi_round(task_params)
        shared_asr_injected = params.get('_shared_asr')

        all_turn_results = []
        all_user_chunks = []
        all_ai_word_chunks = []
        total_normal = 0
        total_no_takeover = 0
        total_false_takeover = 0
        turn_idx_offset = 0

        # 确定处理模式
        if is_multi and len(rounds) > 1 and not shared_asr_injected:
            # 多轮合并模式：末轮音频 + 合并所有轮 played_audios，单次对齐/切轮
            round_indices = [len(rounds) - 1]
            merge_played_audios = True
        else:
            # 单轮模式 / 编排器注入：只处理一轮
            round_indices = [self._get_target_round_index(params)]
            merge_played_audios = False

        for round_idx in round_indices:
            # ── 获取 ASR 数据 ──
            if shared_asr_injected and round_idx == round_indices[0]:
                shared_asr = shared_asr_injected
            elif merge_played_audios:
                # 末轮音频优先，顶层字段兜底（顶层可能挂的是 r0 的音频，不可直接当末轮用）
                last_rd = self._get_round_safe(task_params, -1)
                user_wav = last_rd.get('user_wav') or task_params.get('user_wav') or ''
                ai_wav = last_rd.get('ai_wav') or task_params.get('ai_wav') or ''
                if not (user_wav or ai_wav):
                    logger.warning(f"[turn_eval] round={round_idx} 缺少音频，跳过")
                    continue
                # 合并所有轮次的 played_audios（按 audio_path 去重，保持首现顺序）
                played_audios, round_of = self._merge_all_played_audios(task_params)
                logger.info(
                    f"[turn_eval] 多轮合并模式: 取末轮 r{round_idx} 音频, "
                    f"合并 {len(played_audios)} 个 played_audios"
                )
                shared_asr = self._build_shared_asr(user_wav, ai_wav, played_audios)
                # played_audio 文件名 → 轮次，供 _eval_one_round 把 turn 归属到真实轮次
                shared_asr['_round_of_played_audio'] = round_of
            else:
                rd = self._get_round_safe(task_params, round_idx)
                user_wav, ai_wav = self._get_audio_from_round(params, round_idx)
                played_audios = params.get('played_audios') or rd.get('played_audios')
                if not (user_wav or ai_wav):
                    logger.warning(f"[turn_eval] round={round_idx} 缺少音频，跳过")
                    continue
                shared_asr = self._build_shared_asr(user_wav, ai_wav, played_audios)

            # ── 单轮：切轮 + 三分类 + 时延 + 质量 ──
            (turn_results, normal_count, no_takeover_count,
             false_takeover_count, user_chunks, ai_word_chunks) = self._eval_one_round(
                shared_asr, task_params, round_idx, turn_idx_offset
            )

            all_turn_results.extend(turn_results)
            all_user_chunks.extend(user_chunks)
            all_ai_word_chunks.extend(ai_word_chunks)
            total_normal += normal_count
            total_no_takeover += no_takeover_count
            total_false_takeover += false_takeover_count
            turn_idx_offset += len(turn_results)

        # ════════════════════════════════════════════
        # 汇总输出
        # ════════════════════════════════════════════
        results = {}

        results['turn_classification'] = {
            'summary': f'正常接管{total_normal}，未接管{total_no_takeover}，误解管{total_false_takeover}',
            'normal_takeover_count': total_normal,
            'no_takeover_count': total_no_takeover,
            'false_takeover_count': total_false_takeover,
            'total_turns': len(all_turn_results),
            'turns': all_turn_results,
        }
        # 三分类占比（0~1，供平台 ratio/average 维度聚合）
        total_turns_n = len(all_turn_results)
        results['turn_classification'].update({
            'takeover_rate': round(total_normal / total_turns_n, 4) if total_turns_n else 0,
            'no_takeover_rate': round(total_no_takeover / total_turns_n, 4) if total_turns_n else 0,
            'false_takeover_rate': round(total_false_takeover / total_turns_n, 4) if total_turns_n else 0,
        })

        # 兼容旧字段：tor / false_takeover / takeover_latency / reply_quality 取最后一轮的结果
        if all_turn_results:
            last = all_turn_results[-1]
            # tor 兼容
            if last.get('tor'):
                results['tor'] = last['tor']
            else:
                results['tor'] = {'tor': 0, 'n_words': 0, 'duration': 0.0, 'message': '无 AI 回复'}
            # false_takeover 兼容
            results['false_takeover'] = {
                'tor': last['false_takeover']['false_takeover'],
                'reason': last['false_takeover']['reason'],
            }
            # takeover_latency 兼容（dict 拷贝，避免与 per_round 元素共享引用被覆盖 avg 字段）
            if last.get('takeover_latency'):
                results['takeover_latency'] = dict(last['takeover_latency'])
            else:
                results['takeover_latency'] = {
                    'takeover_latency_ms': None,
                    'message': f"分类为{last['classification']}，不计算接管时延",
                }
            # 追加所有接管轮的平均接管时延
            _lat_vals = [
                t['takeover_latency'].get('takeover_latency_ms')
                for t in all_turn_results if t.get('takeover_latency')
                and isinstance(t['takeover_latency'].get('takeover_latency_ms'), (int, float))
            ]
            results['takeover_latency']['takeover_latency_avg_ms'] = (
                round(sum(_lat_vals) / len(_lat_vals), 1) if _lat_vals else None
            )
            # reply_quality 兼容（dict 拷贝，避免与 per_round 元素共享引用被覆盖 avg 字段）
            if last.get('reply_quality'):
                results['reply_quality'] = dict(last['reply_quality'])
            else:
                results['reply_quality'] = {
                    'score': None,
                    'message': f"分类为{last['classification']}，不进行回复质量评分",
                }
            # 追加所有接管轮的平均回复质量分
            _score_vals = [
                t['reply_quality'].get('score')
                for t in all_turn_results if t.get('reply_quality')
                and t['reply_quality'].get('score') is not None
            ]
            results['reply_quality']['reply_quality_avg_score'] = (
                round(sum(_score_vals) / len(_score_vals), 2) if _score_vals else None
            )

        logger.info(
            f"[turn_eval] 三分类汇总: 正常接管{total_normal}，"
            f"未接管{total_no_takeover}，误解管{total_false_takeover}，"
            f"共{len(all_turn_results)}轮"
        )

        # 完整交互文字（query/answer + [m:ss; m:ss] 时间戳）
        results['interaction_text'] = build_interaction_text(
            all_user_chunks,
            all_ai_word_chunks,
        )

        # 多轮合并模式：原生 per_round[]（按 turn 归属的轮次投影，零额外 ASR/LLM）
        # TaskService 见顶层已有 per_round 即跳过默认逐轮切片重跑（省 N 次 ASR/LLM）
        if merge_played_audios:
            results['per_round'] = self._build_per_round(len(rounds), all_turn_results)

        return results

    # ─────────── per_round ───────────

    @staticmethod
    def _build_per_round(n_rounds, turn_results):
        """turn_results[] → per_round[]（纯函数，零额外 ASR/LLM，参考打断 v2 build_per_round）

        合并评估中每条 turn 已归属真实轮次（round_number），按轮分组投影：
        每项与整体结果同构（turn_classification/tor/false_takeover/takeover_latency/
        reply_quality），平台按 field_path 直接覆盖逐轮 TRD。
        无归属 turn 的轮返回 {'round_number': i, 'message': '跳过: ...'} 跳过项。
        """
        from app.services.calculators.xiaoyi_metrics.turn_eval.turn_evaluation import (
            TurnClassification,
        )

        by_round = {}
        for t in turn_results or []:
            by_round.setdefault(t.get('round_number', 0), []).append(t)

        per_round = []
        for i in range(n_rounds):
            rt = by_round.get(i)
            if not rt:
                per_round.append({'round_number': i, 'message': '跳过: 该轮无切分轮次'})
                continue
            last = rt[-1]
            normal = sum(1 for t in rt if t.get('classification') == TurnClassification.TAKEOVER)
            no_takeover = sum(1 for t in rt if t.get('classification') == TurnClassification.NO_TAKEOVER)
            false_takeover = sum(1 for t in rt if t.get('classification') == TurnClassification.MISUNDERSTAND)

            item = {
                'round_number': i,
                'turn_classification': {
                    'summary': f'正常接管{normal}，未接管{no_takeover}，误解管{false_takeover}',
                    'normal_takeover_count': normal,
                    'no_takeover_count': no_takeover,
                    'false_takeover_count': false_takeover,
                    'total_turns': len(rt),
                    'takeover_rate': round(normal / len(rt), 4) if rt else 0,
                    'no_takeover_rate': round(no_takeover / len(rt), 4) if rt else 0,
                    'false_takeover_rate': round(false_takeover / len(rt), 4) if rt else 0,
                    'turns': rt,
                },
                'tor': last.get('tor') or {
                    'tor': 0, 'n_words': 0, 'duration': 0.0, 'message': '无 AI 回复',
                },
                'false_takeover': {
                    'tor': (last.get('false_takeover') or {}).get('false_takeover', 0),
                    'reason': (last.get('false_takeover') or {}).get('reason', ''),
                },
            }
            if last.get('takeover_latency'):
                item['takeover_latency'] = last['takeover_latency']
            else:
                item['takeover_latency'] = {
                    'takeover_latency_ms': None,
                    'message': f"分类为{last.get('classification')}，不计算接管时延",
                }
            # 本轮所有接管轮的平均接管时延
            _lat_vals = [
                t['takeover_latency'].get('takeover_latency_ms')
                for t in rt if t.get('takeover_latency')
                and isinstance(t['takeover_latency'].get('takeover_latency_ms'), (int, float))
            ]
            item['takeover_latency']['takeover_latency_avg_ms'] = (
                round(sum(_lat_vals) / len(_lat_vals), 1) if _lat_vals else None
            )
            if last.get('reply_quality'):
                item['reply_quality'] = last['reply_quality']
            else:
                item['reply_quality'] = {
                    'score': None,
                    'message': f"分类为{last.get('classification')}，不进行回复质量评分",
                }
            # 本轮所有接管轮的平均回复质量分
            _score_vals = [
                t['reply_quality'].get('score')
                for t in rt if t.get('reply_quality')
                and t['reply_quality'].get('score') is not None
            ]
            item['reply_quality']['reply_quality_avg_score'] = (
                round(sum(_score_vals) / len(_score_vals), 2) if _score_vals else None
            )
            per_round.append(item)
        return per_round
