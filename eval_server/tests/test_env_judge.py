# -*- coding: utf-8 -*-
"""环境理解裁判 env_judge 音频有效性拦截测试。

覆盖:
  - ai_wav 录音静音 / 无有效 ASR 文本 → 直接判失败，且不调用 LLM（防裁判幻觉打分）
  - 有语义场景 ASR 文本与参考内容关联度过低 → 直接判失败，且不调用 LLM
  - 关联度正常 → 走 LLM 裁判（mock）
  - 无语义场景不启用相关性兜底校验
  - _detect_silence 静音检测辅助函数
"""
import struct
import wave

import pytest

from app.services.calculators.xiaoyi_metrics.env_judge import env_judge as ej

FLIGHT_REF = '乘坐中国东方航空公司279次航班，日本航空公司5632次航班从上海前往。'
MOVIE_REF = ('县长上任得巧立名目，拉拢豪绅，交税捐款，他们交了，才能让百姓跟着交钱，'
             '得钱之后，豪绅的钱如数奉还，百姓的钱，三七分成。怎么才七成啊？'
             '七成是人家的，能得三成还得看黄四郎的脸色，谁的脸色？')
ASK_BACK = '刚才他们具体说了什么呀？是在聊工作安排还是生活中的趣事呢？可以多给点细节吗？我在这儿听着呢。'


def _make_wav(path, seconds=1, sr=16000, silent=True):
    """生成 int16 mono 的 wav：silent=True 全零（静音），否则为固定幅度方波。"""
    w = wave.open(str(path), 'wb')
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    if silent:
        frames = b'\x00\x00' * (sr * seconds)
    else:
        frames = struct.pack('<%dh' % (sr * seconds), *([1000] * (sr * seconds)))
    w.writeframes(frames)
    w.close()
    return str(path)


@pytest.fixture
def audio_pair(tmp_path):
    """返回 (silent_ai_wav, audible_ai_wav) 两个真实 wav 文件路径。"""
    silent = _make_wav(tmp_path / 'silent.wav', silent=True)
    audible = _make_wav(tmp_path / 'audible.wav', silent=False)
    return silent, audible


@pytest.fixture
def fake_llm(monkeypatch):
    """拦截 LLM 调用，记录是否被调用，返回固定 JSON。"""
    calls = []

    def fake(**kwargs):
        calls.append(kwargs.get('prompt', ''))
        return {'content': '{"understand_correct": true, "score": 4, "reason": "ok"}',
                'tokens_used': 1, 'input_token': 1, 'output_token': 1}

    monkeypatch.setattr(ej, 'call_llm_api', fake)
    return calls


def _run(monkeypatch, ai_wav, asr_text, ref, env_type=1, silent_result=None):
    """以给定 ASR 文本调用 evaluate_env_judge，mock 掉静音检测结果。"""
    monkeypatch.setattr(ej, 'get_asr_text', lambda w: asr_text)
    if silent_result is not None:
        monkeypatch.setattr(ej, '_detect_silence',
                            lambda w, rms_threshold=0.001: silent_result)
    return ej.evaluate_env_judge(
        user_wav=ai_wav, ai_wav=ai_wav, played_audios=None,
        correctAnswer=ref, env_type=env_type,
    )


def test_silent_audio_failed_without_llm(monkeypatch, audio_pair, fake_llm):
    """ai_wav 录音静音且 ASR 为空 → 直接判失败，不调用 LLM。"""
    silent, _ = audio_pair
    r = _run(monkeypatch, silent, '', FLIGHT_REF, env_type=1,
             silent_result={'is_silent': True, 'rms': 0.0, 'error': ''})
    assert r['understand_correct'] is False
    assert r['score'] == 1
    assert '静音' in r['message']
    assert fake_llm == []


def test_no_valid_asr_failed_without_llm(monkeypatch, audio_pair, fake_llm):
    """ASR 为空且音频无法判定静音（加载失败等）→ 判失败，不调用 LLM。"""
    silent, _ = audio_pair
    r = _run(monkeypatch, silent, '', FLIGHT_REF, env_type=1,
             silent_result={'is_silent': False, 'rms': None, 'error': 'x'})
    assert r['understand_correct'] is False
    assert r['score'] == 1
    assert '无有效 ASR 文本' in r['message']
    assert fake_llm == []


def test_low_similarity_failed_without_llm(monkeypatch, audio_pair, fake_llm):
    """有语义：ASR 文本与参考关联度过低（反问/闲聊）→ 直接判失败。"""
    silent, audible = audio_pair
    r = _run(monkeypatch, audible, ASK_BACK, MOVIE_REF, env_type=1)
    assert r['text_similarity'] < ej.TEXT_SIMILARITY_THRESHOLD
    assert r['understand_correct'] is False
    assert r['score'] == 1
    assert fake_llm == []


def test_normal_similarity_calls_llm(monkeypatch, audio_pair, fake_llm):
    """有语义：ASR 文本与参考关联度正常 → 走 LLM 裁判。"""
    silent, audible = audio_pair
    r = _run(monkeypatch, audible, '刚才广播说东航279次航班和日航5632次航班从上海出发', FLIGHT_REF, env_type=1)
    assert r['text_similarity'] >= ej.TEXT_SIMILARITY_THRESHOLD
    assert fake_llm, '关联度正常应调用 LLM'
    assert r['understand_correct'] is True


def test_non_semantic_skips_similarity_gate(monkeypatch, audio_pair, fake_llm):
    """无语义：不启用相关性兜底，text_similarity 保持 None。"""
    silent, audible = audio_pair
    r = _run(monkeypatch, audible, '有人在按门铃', '门铃声', env_type=0)
    assert r['text_similarity'] is None
    assert fake_llm, '无语义场景应走 LLM'
    assert r['understand_correct'] is True


def test_detect_silence_helper(audio_pair):
    """_detect_silence：全零 wav 判静音，有幅度 wav 判非静音。"""
    silent, audible = audio_pair
    assert ej._detect_silence(silent)['is_silent'] is True
    assert ej._detect_silence(audible)['is_silent'] is False
    assert ej._detect_silence(str(__import__('pathlib').Path('不存在.wav')))['is_silent'] is False
