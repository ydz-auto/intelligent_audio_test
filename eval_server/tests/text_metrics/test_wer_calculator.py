# -*- coding: utf-8 -*-
"""文本转写指标单元测试：WER 编辑距离 / 中英文分词 / 中英分项 WER。

由旧脚本 tests/test_wer.py 改写为 pytest 断言（原文件为 __main__ 手工脚本）。
"""
from app.services.calculators.wer.wer_calculator import (
    levenshtein_distance, split_text, calculate_wer,
)


def _wer(ref, hyp, **kw):
    """按策略层签名调用 calculate_wer（source_lang/target_lang/translate_direct 可省略）。"""
    return calculate_wer(ref, hyp, None, None, None, **kw)


# ─────────── Levenshtein 编辑距离 ───────────

def test_levenshtein_identical():
    assert levenshtein_distance('abc', 'abc') == 0


def test_levenshtein_insert_delete_replace():
    assert levenshtein_distance('kitten', 'sitting') == 3  # k→s / e→i / +g
    assert levenshtein_distance('abc', '') == 3
    assert levenshtein_distance('', 'abc') == 3


# ─────────── 中英文分词 ───────────

def test_split_text_zh_and_en():
    chars, zh, en = split_text('这是一个测试text文本')
    # 中文逐字、英文整词
    assert ''.join(chars) == '这是一个测试text文本'
    assert zh == ['这', '是', '一', '个', '测', '试', '文', '本']
    assert en == ['text']


def test_split_text_merges_consecutive_en_words():
    chars, zh, en = split_text('hello world测试')
    assert ''.join(chars) == 'helloworld测试'
    assert en == ['hello', 'world']
    assert zh == ['测', '试']


# ─────────── 总/中/英 WER ───────────

def test_wer_zh_en_split():
    """中文删字、英文删词分别计入 wer_zh / wer_en。"""
    result = _wer('这是一个测试测试文本text', '这是一个测试文本text')
    # 词表：中文逐字(10) + 英文整词(1) = 11；缺 '测','试' 2 字 → 总 WER = 2/11
    assert result['wer'] == round(2 / 11, 4)
    assert result['wer_zh'] == round(2 / 10, 4)  # 中文错 2/10
    assert result['wer_en'] == 0.0


def test_wer_perfect_match_is_zero():
    result = _wer('今天天气很好', '今天天气很好')
    assert result['wer'] == 0.0
    assert result['wer_zh'] == 0.0
    assert result['wer_en'] == 0.0


def test_wer_empty_reference_guards_division_by_zero():
    result = _wer('', '有一些输出')
    assert result['wer'] == 0.0
    assert result['wer_zh'] == 0.0
    assert result['wer_en'] == 0.0


def test_wer_normalize_option():
    """normalize=True 时先做文本正则化（连续空白折叠）。"""
    result = _wer('今天 天气  很好', '今天 天气 很好', normalize=True)
    assert result['wer'] == 0.0
