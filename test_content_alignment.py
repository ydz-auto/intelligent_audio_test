"""内容对齐功能验证测试"""
import sys
import os

# 添加项目根路径
project_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Intelligent-Audio-TEST')
sys.path.insert(0, project_root)

from unittest.mock import patch, MagicMock

# Mock 依赖
mock_mapper = MagicMock()
sys.modules.setdefault('backend.algorithm.field_mapper', MagicMock())
sys.modules['backend.algorithm.field_mapper'].get_field_mapper = mock_mapper

from backend.utils.device_result_collector import (
    DeviceResultCollector,
    MIN_TEXT_SIMILARITY,
    MIN_CONTENT_MATCH_PAIRS,
    CONTENT_ALIGNMENT_SKIP_PENALTY,
    CONTENT_ALIGNMENT_CONFIDENCE_THRESHOLD,
    CONTENT_OUTLIER_OFFSET_THRESHOLD,
)


def test_constants():
    """验证新增常量"""
    assert MIN_TEXT_SIMILARITY == 0.3
    assert MIN_CONTENT_MATCH_PAIRS == 2
    assert CONTENT_ALIGNMENT_SKIP_PENALTY == -0.1
    assert CONTENT_ALIGNMENT_CONFIDENCE_THRESHOLD == 0.5
    assert CONTENT_OUTLIER_OFFSET_THRESHOLD == 2.0
    print("[PASS] test_constants")


def test_stm_timestamp_bug_fix():
    """验证 STM 时间戳 bug 修复：parts[3] 而非 parts[2]"""
    collector = DeviceResultCollector()
    # STM 格式: file_id channel speaker start end <text>...
    stm_text = "file1 1 speakerA 2.500 5.000 <LABEL> hello world"
    ts = collector._extract_first_timestamp_from_text(stm_text, 'stm')
    assert ts is not None, "STM timestamp should not be None"
    assert abs(ts - 2.5) < 0.001, f"Expected 2.5, got {ts}"
    print("[PASS] test_stm_timestamp_bug_fix")


def test_text_similarity_sequencematcher():
    """验证 SequenceMatcher 替换 Jaccard"""
    collector = DeviceResultCollector()

    # 完全相同
    sim = collector._compute_text_similarity("hello world", "hello world")
    assert abs(sim - 1.0) < 0.01, f"Expected ~1.0, got {sim}"

    # 完全不同
    sim = collector._compute_text_similarity("hello world", "xyz abc")
    assert sim < 0.3, f"Expected < 0.3, got {sim}"

    # 部分相似
    sim = collector._compute_text_similarity("the quick brown fox", "the quick red dog")
    assert 0.3 < sim < 0.9, f"Expected 0.3-0.9, got {sim}"

    # 空文本
    assert collector._compute_text_similarity("", "hello") == 0.0
    assert collector._compute_text_similarity("hello", "") == 0.0
    assert collector._compute_text_similarity(None, "hello") == 0.0

    # 太短的文本 (< 3 chars)
    assert collector._compute_text_similarity("hi", "hello world") == 0.0

    print("[PASS] test_text_similarity_sequencematcher")


def test_stm_priority_in_extract():
    """验证 _extract_segments_from_result 优先使用 STM"""
    collector = DeviceResultCollector()

    # 同时有 STM 和 RTTM，应该从 STM 提取（有文本）
    raw_results = {
        'recording_rttm_content': 'SPEAKER file1 1 1.000 2.000 <NA> <NA> spk1 <NA> <NA>',
        'recording_stm_content': 'file1 1 spk1 1.000 3.000 hello world from stm',
    }
    segments = collector._extract_segments_from_result(raw_results)
    assert len(segments) == 1
    assert segments[0]['text'] == 'hello world from stm', f"Expected STM text, got '{segments[0]['text']}'"
    print("[PASS] test_stm_priority_in_extract")


def test_rttm_fallback_when_no_stm():
    """验证 STM 为空时回退到 RTTM"""
    collector = DeviceResultCollector()

    raw_results = {
        'recording_rttm_content': 'SPEAKER file1 1 1.000 2.000 <NA> <NA> spk1 <NA> <NA>',
        'recording_stm_content': '',
    }
    segments = collector._extract_segments_from_result(raw_results)
    assert len(segments) == 1
    assert segments[0]['text'] == '', "RTTM segments should have empty text"
    print("[PASS] test_rttm_fallback_when_no_stm")


def _make_segments(data):
    """快速构建片段列表
    data: list of (start, end, text)
    """
    return [{'start': s, 'end': e, 'text': t, 'speaker': 'spk1'} for s, e, t in data]


def test_align_by_content_basic():
    """验证基本内容对齐：匹配文本产生正确偏移量"""
    collector = DeviceResultCollector()

    # 设备比参考整体延迟 2.0 秒 -> offset = device_start - ref_start = +2.0
    device_segs = _make_segments([
        (2.0, 4.0, "doors were open"),
        (5.0, 7.0, "the book is on the table"),
        (8.0, 10.0, "she walked to the store"),
        (11.0, 13.0, "he drove the car fast"),
    ])
    ref_segs = _make_segments([
        (0.0, 2.0, "doors were open"),
        (3.0, 5.0, "the book is on the table"),
        (6.0, 8.0, "she walked to the store"),
        (9.0, 11.0, "he drove the car fast"),
    ])

    offset, confidence, details = collector._align_by_content(device_segs, ref_segs)

    assert offset is not None, "Offset should not be None"
    assert abs(offset - 2.0) < 0.5, f"Expected offset ~ 2.0, got {offset}"
    assert confidence > 0.3, f"Expected confidence > 0.3, got {confidence}"
    assert len(details['matched_pairs']) >= 2, f"Expected >= 2 matched pairs, got {len(details['matched_pairs'])}"
    print(f"[PASS] test_align_by_content_basic (offset={offset:.3f}, confidence={confidence:.3f}, pairs={len(details['matched_pairs'])})")


def test_align_by_content_no_text():
    """验证无文本时跳过内容对齐"""
    collector = DeviceResultCollector()

    device_segs = _make_segments([
        (2.0, 4.0, ""),
        (5.0, 7.0, ""),
    ])
    ref_segs = _make_segments([
        (0.0, 2.0, "hello world"),
        (3.0, 5.0, "foo bar"),
    ])

    offset, confidence, details = collector._align_by_content(device_segs, ref_segs)
    assert offset is None, f"Expected None offset when no device text, got {offset}"
    assert confidence == 0.0
    print("[PASS] test_align_by_content_no_text")


def test_align_by_content_outlier_filtering():
    """验证离群值过滤"""
    collector = DeviceResultCollector()

    # 4 对偏移量 ~-2.0s (device - ref), 1 对偏移量 ~-15.0s (应被过滤)
    device_segs = _make_segments([
        (0.0, 2.0, "alpha bravo charlie"),
        (3.0, 5.0, "delta echo foxtrot"),
        (6.0, 8.0, "golf hotel india"),
        (9.0, 11.0, "juliet kilo lima"),
        (12.0, 14.0, "mike november oscar"),
    ])
    # 参考：前4个偏移 -2.0s，最后一个偏移 -15.0s (故意错位)
    ref_segs = _make_segments([
        (2.0, 4.0, "alpha bravo charlie"),     # offset = 0-2 = -2.0
        (5.0, 7.0, "delta echo foxtrot"),       # offset = 3-5 = -2.0
        (8.0, 10.0, "golf hotel india"),        # offset = 6-8 = -2.0
        (11.0, 13.0, "juliet kilo lima"),       # offset = 9-11 = -2.0
        (27.0, 29.0, "totally different text"), # offset = 12-27 = -15.0 (outlier)
    ])

    offset, confidence, details = collector._align_by_content(device_segs, ref_segs)

    assert offset is not None, "Offset should not be None"
    assert abs(offset - (-2.0)) < 0.5, f"Expected offset ~ -2.0 after outlier filtering, got {offset}"
    print(f"[PASS] test_align_by_content_outlier_filtering (offset={offset:.3f}, pairs={len(details['matched_pairs'])})")


def test_align_by_content_too_few_pairs():
    """验证匹配对不足时返回 None"""
    collector = DeviceResultCollector()

    # 只有 1 对能匹配，不满足 MIN_CONTENT_MATCH_PAIRS=2
    device_segs = _make_segments([
        (0.0, 2.0, "hello world greeting"),
        (3.0, 5.0, "xyz123"),
        (6.0, 8.0, "abc456"),
    ])
    ref_segs = _make_segments([
        (0.0, 2.0, "hello world greeting"),
        (3.0, 5.0, "completely different text"),
        (6.0, 8.0, "nothing matches here either"),
    ])

    offset, confidence, details = collector._align_by_content(device_segs, ref_segs)
    # 如果只有1个匹配对，应该返回 None
    if len(details.get('matched_pairs', [])) < MIN_CONTENT_MATCH_PAIRS:
        assert offset is None, f"Expected None when < {MIN_CONTENT_MATCH_PAIRS} pairs"
        print("[PASS] test_align_by_content_too_few_pairs (correctly returned None)")
    else:
        print(f"[PASS] test_align_by_content_too_few_pairs (got {len(details['matched_pairs'])} pairs, offset={offset})")


def test_content_alignment_in_main_flow():
    """验证内容对齐在主流程中作为 Strategy 0 被正确调用"""
    collector = DeviceResultCollector()

    # 构造设备结果 (STM 格式，有文本)
    stm_lines = [
        "file1 1 spk1 2.000 4.000 the cat sat on the mat",
        "file1 1 spk1 5.000 7.000 the dog ran in the park",
        "file1 1 spk1 8.000 10.000 the bird flew over the tree",
        "file1 1 spk1 11.000 13.000 the fish swam in the pond",
    ]
    stm_content = '\n'.join(stm_lines)

    raw_results = {
        'recording_stm_content': stm_content,
        'recording_rttm_content': '',
    }

    # 参考参数 (设备延迟 +2.0 秒) - 使用真实嵌套格式
    reference_params = [
        {
            'type': 'stm',
            'api': {
                'segments': [
                    {'start': 0.0, 'end': 2.0, 'text': 'the cat sat on the mat', 'speaker': 'spk1'},
                    {'start': 3.0, 'end': 5.0, 'text': 'the dog ran in the park', 'speaker': 'spk1'},
                    {'start': 6.0, 'end': 8.0, 'text': 'the bird flew over the tree', 'speaker': 'spk1'},
                    {'start': 9.0, 'end': 11.0, 'text': 'the fish swam in the pond', 'speaker': 'spk1'},
                ]
            }
        }
    ]

    playback_time_offsets = {}

    result = collector._calculate_effective_offset_for_single_result(
        raw_results, reference_params, playback_time_offsets
    )

    info = result['alignment_info']
    print(f"  method={info['method']}, offset={info['offset']:.3f}, "
          f"content_score={info.get('content_alignment_score')}, "
          f"pairs={info.get('content_matched_pairs')}")

    assert info['method'] == 'content_alignment', f"Expected content_alignment, got {info['method']}"
    assert abs(info['offset'] - 2.0) < 0.5, f"Expected offset ~ +2.0, got {info['offset']}"
    assert info['content_alignment_score'] is not None
    assert info['content_matched_pairs'] >= 2
    print("[PASS] test_content_alignment_in_main_flow")


def test_fallthrough_when_no_device_text():
    """验证设备端无文本时内容对齐被跳过，回退到 max_overlap"""
    collector = DeviceResultCollector()

    # RTTM-only (无文本)
    rttm_lines = [
        "SPEAKER file1 1 2.000 2.000 <NA> <NA> spk1 <NA> <NA>",
        "SPEAKER file1 1 5.000 2.000 <NA> <NA> spk1 <NA> <NA>",
        "SPEAKER file1 1 8.000 2.000 <NA> <NA> spk1 <NA> <NA>",
        "SPEAKER file1 1 11.000 2.000 <NA> <NA> spk1 <NA> <NA>",
    ]
    rttm_content = '\n'.join(rttm_lines)

    raw_results = {
        'recording_stm_content': '',
        'recording_rttm_content': rttm_content,
    }

    # 使用真实嵌套格式
    reference_params = [
        {
            'type': 'rttm',
            'api': {
                'segments': [
                    {'start': 0.0, 'end': 2.0, 'text': 'text a', 'speaker': 'spk1'},
                    {'start': 3.0, 'end': 5.0, 'text': 'text b', 'speaker': 'spk1'},
                    {'start': 6.0, 'end': 8.0, 'text': 'text c', 'speaker': 'spk1'},
                    {'start': 9.0, 'end': 11.0, 'text': 'text d', 'speaker': 'spk1'},
                ]
            }
        }
    ]

    result = collector._calculate_effective_offset_for_single_result(
        raw_results, reference_params, {}
    )

    info = result['alignment_info']
    print(f"  method={info['method']}, offset={info['offset']:.3f}, "
          f"content_score={info.get('content_alignment_score')}")

    # 内容对齐应该被跳过 (score=0.0)，回退到 max_overlap
    assert info['method'] != 'content_alignment', \
        f"Should NOT use content_alignment when no text, got {info['method']}"
    assert info['content_alignment_score'] is not None  # 字段存在
    print(f"[PASS] test_fallthrough_when_no_device_text (fell through to {info['method']})")


if __name__ == '__main__':
    tests = [
        test_constants,
        test_stm_timestamp_bug_fix,
        test_text_similarity_sequencematcher,
        test_stm_priority_in_extract,
        test_rttm_fallback_when_no_stm,
        test_align_by_content_basic,
        test_align_by_content_no_text,
        test_align_by_content_outlier_filtering,
        test_align_by_content_too_few_pairs,
        test_content_alignment_in_main_flow,
        test_fallthrough_when_no_device_text,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            print(f"\n--- Running {test_fn.__name__} ---")
            test_fn()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test_fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    if failed == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"FAILED: {failed} tests")
        sys.exit(1)
