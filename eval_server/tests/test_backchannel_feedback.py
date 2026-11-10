import numpy as np

from app.services.calculators.xiaoyi_metrics.shared.audio_alignment import highpass_filter_audio
from app.services.calculators.xiaoyi_metrics.turn_eval.full_timeline_judge import (
    apply_backchannel_classification,
)
from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator


def test_backchannel_during_user_speech_overrides_turn_classification():
    packet = {
        'full_word_timeline': [
            {'word_id': 'U00000', 'speaker': 'user', 'text': '我', 'start': 1.0, 'end': 1.2},
            {'word_id': 'U00001', 'speaker': 'user', 'text': '说', 'start': 4.0, 'end': 4.2},
            {'word_id': 'M00000', 'speaker': 'model', 'text': '嗯', 'start': 2.2, 'end': 2.5},
        ],
    }
    turns = [{
        'turn_index': 1,
        'round_number': 0,
        'classification': '接管',
        'user_start_s': 1.0,
        'user_end_s': 4.2,
    }]

    turns, summary = apply_backchannel_classification(packet, turns)

    assert turns[0]['classification'] == '主动反馈-backchannel'
    assert turns[0]['llm_classification'] == '接管'
    assert summary['backchannel_turn_count'] == 1
    assert summary['backchannel_rate'] == 1.0


def test_substantive_early_reply_is_not_backchannel():
    packet = {
        'full_word_timeline': [
            {'word_id': 'U00000', 'speaker': 'user', 'text': '后', 'start': 1.0, 'end': 1.2},
            {'word_id': 'M00000', 'speaker': 'model', 'text': '上', 'start': 1.1, 'end': 1.3},
        ],
    }
    turns = [{
        'turn_index': 1,
        'round_number': 0,
        'classification': '误接管',
        'user_start_s': 1.0,
        'user_end_s': 2.0,
    }]

    turns, summary = apply_backchannel_classification(packet, turns)

    assert turns[0]['classification'] == '误接管'
    assert summary['backchannel_turn_count'] == 0


def test_backchannel_rate_projects_into_per_round():
    turns = [{
        'turn_index': 1,
        'round_number': 0,
        'classification': '主动反馈-backchannel',
        'user_start_s': 1.0,
        'user_end_s': 2.0,
        'ai_start_s': None,
        'ai_end_s': None,
        'false_takeover': {'false_takeover': 0, 'reason': ''},
        'takeover_latency': None,
        'reply_quality': None,
    }]

    result = TurnEvalCalculator._build_per_round(1, turns)[0]
    classification = result['turn_classification']

    assert classification['backchannel_count'] == 1
    assert classification['backchannel_rate'] == 1.0
    assert '主动反馈-backchannel1' in classification['summary']


def test_highpass_filter_removes_dc_component():
    audio = np.ones(16000, dtype=np.float64)
    filtered = highpass_filter_audio(audio, sr=16000, cutoff=80, order=4)

    assert filtered.shape == audio.shape
    assert abs(float(np.mean(filtered))) < 1e-6
