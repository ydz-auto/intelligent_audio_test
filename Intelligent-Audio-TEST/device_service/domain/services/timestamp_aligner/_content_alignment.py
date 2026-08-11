"""文本内容对齐（动态规划）方法"""

import difflib
import statistics
from shared.domain.ports.logging_port import log_not_emit
from .constants import (
    MAX_CANDIDATE_PAIRS,
    MIN_TEXT_SIMILARITY,
    MIN_CONTENT_MATCH_PAIRS,
    CONTENT_ALIGNMENT_SKIP_PENALTY,
    CONTENT_OUTLIER_OFFSET_THRESHOLD,
)


class ContentAlignmentMixin:
    """基于文本内容的对齐方法：相似度计算、候选配对、DP 对齐"""

    def _compute_text_similarity(self, text_a, text_b):
        """计算两个文本的相似度（SequenceMatcher 字符级序列匹配）

        Args:
            text_a: 文本A
            text_b: 文本B

        Returns:
            float: 相似度 (0.0-1.0)
        """
        if not text_a or not text_b:
            return 0.0

        text_a = text_a.strip().lower()
        text_b = text_b.strip().lower()

        if len(text_a) < 3 or len(text_b) < 3:
            return 0.0

        return difflib.SequenceMatcher(None, text_a, text_b).ratio()

    def _find_candidate_pairs_by_text(self, device_segments, ref_segments, min_similarity=0.3):
        """基于文本相似度找到候选匹配对

        Args:
            device_segments: 设备片段列表
            ref_segments: 参考片段列表
            min_similarity: 最小相似度阈值

        Returns:
            list: [(device_idx, ref_idx, similarity), ...]
        """
        candidates = []

        for i, d_seg in enumerate(device_segments):
            d_text = d_seg.get('text', '')
            if not d_text:
                continue

            for j, r_seg in enumerate(ref_segments):
                r_text = r_seg.get('text', '')
                if not r_text:
                    continue

                similarity = self._compute_text_similarity(d_text, r_text)
                if similarity >= min_similarity:
                    candidates.append((i, j, similarity))

        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates[:MAX_CANDIDATE_PAIRS]

    def _align_by_content(self, device_segments, ref_segments):
        """基于文本内容的动态规划对齐

        使用 SequenceMatcher 构建 N×M 相似度矩阵，通过 DP 找到最优的
        设备-参考片段配对路径，从匹配对的时间差中计算鲁棒的偏移量。

        Args:
            device_segments: 设备片段列表 (each has 'start', 'end', 'text')
            ref_segments: 参考片段列表 (each has 'start', 'end', 'text')

        Returns:
            tuple: (offset, confidence, details_dict)
                - offset: float or None (None if alignment failed)
                - confidence: float (0.0-1.0)
                - details_dict: {
                    'matched_pairs': [(dev_idx, ref_idx, similarity, offset)],
                    'skipped_device': int,
                    'skipped_ref': int,
                  }
        """
        empty_details = {'matched_pairs': [], 'skipped_device': 0, 'skipped_ref': 0}

        if not device_segments or not ref_segments:
            return None, 0.0, empty_details

        # 提取文本
        d_texts = [seg.get('text', '').strip() for seg in device_segments]
        r_texts = [seg.get('text', '').strip() for seg in ref_segments]

        if not any(d_texts) or not any(r_texts):
            return None, 0.0, empty_details

        N = len(device_segments)
        M = len(ref_segments)

        # DP 对齐
        sim, dp, traceback = self._build_dp_alignment(d_texts, r_texts, device_segments, ref_segments, N, M)

        # 回溯
        matched_pairs, skipped_device, skipped_ref = self._backtrace_dp(
            traceback, sim, device_segments, ref_segments, N, M
        )

        if len(matched_pairs) < MIN_CONTENT_MATCH_PAIRS:
            details = {'matched_pairs': matched_pairs, 'skipped_device': skipped_device, 'skipped_ref': skipped_ref}
            return None, 0.0, details

        # 计算偏移量和置信度
        return self._compute_offset_and_confidence(matched_pairs, skipped_device, skipped_ref, N)

    def _build_dp_alignment(self, d_texts, r_texts, device_segments, ref_segments, N, M):
        """构建 DP 对齐表"""
        sim = [[0.0] * M for _ in range(N)]
        for i in range(N):
            if not d_texts[i]:
                continue
            for j in range(M):
                if not r_texts[j]:
                    continue
                sim[i][j] = self._compute_text_similarity(d_texts[i], r_texts[j])

        dp = [[0.0] * (M + 1) for _ in range(N + 1)]
        traceback = [[''] * (M + 1) for _ in range(N + 1)]

        for i in range(1, N + 1):
            for j in range(1, M + 1):
                match_score = float('-inf')
                if sim[i - 1][j - 1] >= MIN_TEXT_SIMILARITY:
                    time_penalty = max(
                        -0.01 * abs(device_segments[i - 1]['start'] - ref_segments[j - 1]['start']),
                        -0.5
                    )
                    match_score = dp[i - 1][j - 1] + sim[i - 1][j - 1] + time_penalty

                skip_ref_score = dp[i][j - 1] + CONTENT_ALIGNMENT_SKIP_PENALTY
                skip_dev_score = dp[i - 1][j] + CONTENT_ALIGNMENT_SKIP_PENALTY

                best = max(match_score, skip_ref_score, skip_dev_score)
                dp[i][j] = best

                if best == match_score:
                    traceback[i][j] = 'match'
                elif best == skip_ref_score:
                    traceback[i][j] = 'skip_ref'
                else:
                    traceback[i][j] = 'skip_device'

        return sim, dp, traceback

    def _backtrace_dp(self, traceback, sim, device_segments, ref_segments, N, M):
        """回溯 DP 表恢复对齐路径"""
        matched_pairs = []
        skipped_device = 0
        skipped_ref = 0
        i, j = N, M
        while i > 0 and j > 0:
            action = traceback[i][j]
            if action == 'match':
                dev_idx = i - 1
                ref_idx = j - 1
                pair_offset = device_segments[dev_idx]['start'] - ref_segments[ref_idx]['start']
                matched_pairs.append((dev_idx, ref_idx, sim[dev_idx][ref_idx], pair_offset))
                i -= 1
                j -= 1
            elif action == 'skip_ref':
                skipped_ref += 1
                j -= 1
            elif action == 'skip_device':
                skipped_device += 1
                i -= 1
            else:
                break
        while i > 0:
            skipped_device += 1
            i -= 1
        while j > 0:
            skipped_ref += 1
            j -= 1
        matched_pairs.reverse()
        return matched_pairs, skipped_device, skipped_ref

    def _compute_offset_and_confidence(self, matched_pairs, skipped_device, skipped_ref, N):
        """从匹配对计算偏移量和置信度"""
        offsets = [p[3] for p in matched_pairs]
        median_offset = statistics.median(offsets)

        filtered_pairs = [
            p for p in matched_pairs
            if abs(p[3] - median_offset) <= CONTENT_OUTLIER_OFFSET_THRESHOLD
        ]

        if len(filtered_pairs) < MIN_CONTENT_MATCH_PAIRS:
            details = {'matched_pairs': matched_pairs, 'skipped_device': skipped_device, 'skipped_ref': skipped_ref}
            return None, 0.0, details

        final_offset = statistics.median([p[3] for p in filtered_pairs])

        avg_similarity = statistics.mean([p[2] for p in filtered_pairs])
        unique_device_matched = len(set(p[0] for p in filtered_pairs))
        device_coverage = unique_device_matched / N

        if len(filtered_pairs) >= 3:
            offset_stdev = statistics.stdev([p[3] for p in filtered_pairs])
            offset_consistency = max(0.0, 1.0 - offset_stdev / CONTENT_OUTLIER_OFFSET_THRESHOLD)
        else:
            offsets = [p[3] for p in filtered_pairs]
            offset_consistency = max(0.0, 1.0 - abs(offsets[0] - offsets[1]) / CONTENT_OUTLIER_OFFSET_THRESHOLD)

        confidence = avg_similarity * device_coverage * offset_consistency

        details = {
            'matched_pairs': filtered_pairs,
            'skipped_device': skipped_device,
            'skipped_ref': skipped_ref,
        }
        return final_offset, confidence, details
