# -*- coding: utf-8 -*-
"""env_judge.py
环境理解裁判：判断模型对环境音内容的理解是否正确 + 计算用户询问到模型回复的时延

两个子维度:
  - 无语义脚本 (non_semantic): 环境声为噪声(门铃/电话/地铁广播等)，
    用户询问"刚刚是什么声音"，比较ai_wav回答与correctAnswer
  - 有语义脚本 (semantic): 环境声含语义内容(新闻/广播/电视等)，
    用户询问"刚刚电视说了什么"，比较ai_wav回答与correctAnswer

输入:
    user_wav      — 用户通道音频(含环境声 + 用户询问)
    ai_wav        — 模型回复音频
    play_audio    — 原始环境声音频(干净音源)
    correctAnswer — 正确答案(字符串)

输出:
    understand_correct: bool (模型理解是否正确)
    response_latency_ms: float (用户询问到模型回复的时延，ms)
    score: int (1-5 LLM评分)
    reason: str (判定理由)
"""
import json
import os
import logging
from typing import Any, Dict, Optional

import numpy as np
from scipy.signal import resample_poly

from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    call_llm as call_llm_api,
    parse_json,
    get_asr_text,
    get_asr_chunks,
    get_llm_config,
    resolve_model,
)
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)
from app.services.calculators.xiaoyi_metrics.env_judge.env_response_latency import (
    _load_audio,
    _detect_speech_region,
    _coarse_to_fine_align,
    _resolve_played_audio_path,
)

logger = logging.getLogger(__name__)


# ─────────── 场景定义 ───────────
# 有语义场景：环境声含可识别的语音内容
ENVIRONMENT_SCENES = {
    '新闻广播': '环境中出现新闻播报内容，包含时事新闻、社会事件、体育赛事等可识别的新闻信息。',
    '公共广播': '环境中出现公共交通或场所广播，如地铁站台广播、机场航班广播、商场通知等结构化播报内容。',
    '电视节目': '环境中出现电视或电台节目的音频，包含主持人对话、访谈、纪录片旁白等节目内容。',
    '讲座演讲': '环境中出现演讲、讲座或课堂等场景的可识别语音内容，包含知识性或观点性信息。',
    '广告通知': '环境中出现广告播报或通知公告，包含促销信息、安全提醒、活动通知等内容。',
    '背景人声': '环境中出现可识别的背景人声对话或朗读内容，区别于目标用户的直接交互语音。',
}

# 无语义场景：环境声为噪声/非语音声音
NON_SEMANTIC_SOUND_TYPES = {
    '门铃': '门铃声、按铃声，通常为电子或机械门铃发出的提示音。',
    '电话': '电话铃声、手机铃声，包括传统座机和现代手机的来电提示音。',
    '警报': '警报声、警笛声，如火警报警器、汽车警报、防空警报等。',
    '动物': '动物叫声，如狗叫、猫叫、鸟鸣等自然环境中的动物声音。',
    '交通工具': '交通工具声音，如汽车喇叭、火车经过、飞机引擎等。',
    '厨房': '厨房声音，如微波炉提示音、水壶烧开、油锅烹饪等。',
    '钟表': '钟表报时声、闹钟声、整点敲钟声等。',
    '音乐': '音乐声、乐器演奏声，如钢琴、吉他、背景音乐等。',
    '自然': '自然环境声，如雷声、雨声、风声、水流声等。',
    '其他': '其他可识别的非语音环境声音。',
}

# ─── 有语义评分标准 ───
SCORING_CRITERIA = """- 5分（完全一致）：模型输出内容与参考内容文本高度相关且完全一致，准确理解并完整正确地引用了参考内容中的全部关键信息，无遗漏、无错误、无臆造内容。模型对环境音内容的理解精准，在相关性、一致性、完整性三个维度均表现优异，输出与参考内容在语义和信息层面高度吻合。
- 4分（基本一致）：模型输出内容与参考内容文本基本相关，理解并引用了大部分关键信息，存在少量遗漏或细微偏差，但不影响对环境音核心内容的整体理解。模型在相关性上表现良好，一致性和完整性略有不足，仅在细节层面略有出入。
- 3分（部分一致）：模型输出内容与参考内容文本部分相关，理解了部分信息但遗漏了重要内容，或存在一定程度的理解偏差，部分信息不够准确。模型在相关性上有一定表现，但一致性和完整性存在明显不足，核心信息有缺失或部分错误。
- 2分（弱相关）：模型输出内容与参考内容文本关联较弱，仅捕捉到少量或边缘信息，未理解参考内容的核心主旨，存在明显偏差或错误。模型在相关性、一致性、完整性三个维度均表现较差，输出与参考内容仅有表层或零散关联，关键信息大量缺失。
- 1分（无关）：模型输出内容与参考内容文本完全无关或严重不一致，未理解或错误理解参考内容，输出了与参考内容毫无关联的信息或完全臆造的内容。模型在相关性、一致性、完整性三个维度均无有效表现，未表现出对环境音内容的任何有效理解。"""

# ─── 无语义评分标准 ───
NON_SEMANTIC_SCORING_CRITERIA = """- 5分（完全正确）：模型准确识别出环境声音的类型/来源，与参考答案完全一致，描述精准无误差。
- 4分（基本正确）：模型识别出的声音类型与参考答案基本一致，虽表述方式略有不同但核心判断正确，如参考答案为"门铃声"模型回答"有人在按门铃"。
- 3分（部分正确）：模型识别出了部分特征但不够准确，或给出了模糊/宽泛的描述，如参考答案为"电话铃声"模型回答"有什么在响"。
- 2分（错误判断）：模型对声音类型的判断与参考答案明显不符，如参考答案为"狗叫"模型回答"警报声"。
- 1分（完全错误）：模型完全未能识别环境声音，回答与参考答案无关，或表示没听到任何声音。"""


# ─────────── prompt 构建 ───────────
def build_env_judge_prompt(correct_answer: str, script_type: str = 'semantic') -> str:
    """构建环境理解判定 prompt

    Args:
        correct_answer: 环境音参考内容文本（正确答案）
        script_type: 'non_semantic'(无语义) 或 'semantic'(有语义)
    """
    if script_type == 'non_semantic':
        return _build_non_semantic_prompt(correct_answer)
    return _build_semantic_prompt(correct_answer)


def _task_type_to_script_type(task_type) -> str:
    """将输入参数 task_type 映射为 script_type

    task_type=0 或 '0' → 'non_semantic'（无语义）
    task_type=1 或 '1' → 'semantic'（有语义）
    """
    if isinstance(task_type, str):
        task_type = task_type.strip()
    if task_type in (0, '0', 'non_semantic'):
        return 'non_semantic'
    return 'semantic'


def _build_non_semantic_prompt(correct_answer: str) -> str:
    """无语义脚本 prompt：判断模型是否正确识别了环境声音类型"""
    sound_type_blocks = []
    for i, (key, definition) in enumerate(NON_SEMANTIC_SOUND_TYPES.items(), 1):
        sound_type_blocks.append(f"类型{i} — {key}\n  {definition}")
    sound_types_text = '\n\n'.join(sound_type_blocks)

    return f"""你是语音对话能力的裁判专家。你将收到【模型输出音频】以及下方【环境声音参考答案】。

在环境理解-无语义场景中，用户所处的环境中出现了一段环境声音（如门铃、电话、警报等非语音噪声）。用户会询问"刚刚是什么声音"之类的问题，模型需要正确识别并描述该环境声音的类型。

请结合模型输出音频和参考答案，判断模型是否正确识别了环境声音的类型。

═══════════════════════════════════════
【评分标准】（1-5分，仅可给出1至5的正数整数）
═══════════════════════════════════════

{NON_SEMANTIC_SCORING_CRITERIA}

评分维度说明：
- 准确性：模型识别的声音类型是否与参考答案一致。
- 描述质量：模型对声音的描述是否具体、清晰，而非模糊笼统。

═══════════════════════════════════════
【环境声音参考答案】
═══════════════════════════════════════

{correct_answer}

═══════════════════════════════════════
【声音类型参考】（常见环境声音类型）
═══════════════════════════════════════

{sound_types_text}

═══════════════════════════════════════
【评估步骤】
═══════════════════════════════════════

1. 从模型输出音频中提取模型实际输出的语音内容。
2. 将模型识别的声音类型与【环境声音参考答案】进行比对。
3. 评估模型是否正确识别了声音类型，描述是否准确。
4. 根据评分标准给出1-5的整数评分。
5. 评分4分及以上 → understand_correct = true；评分3分及以下 → understand_correct = false。

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "understand_correct": true,
  "score": 5,
  "reason": "简短判定理由"
}}

其中：
- understand_correct 必须是 true 或 false，表示模型是否正确识别了环境声音
- score 必须是 1 至 5 的正数整数，分数越高表示模型对环境声音的识别越准确
- reason 为简短判定理由，需说明：模型识别出的声音类型是什么，与参考答案是否一致，有何偏差"""


def _build_semantic_prompt(correct_answer: str) -> str:
    """有语义脚本 prompt：判断模型是否正确理解了环境音内容"""
    scene_blocks = []
    for i, (key, definition) in enumerate(ENVIRONMENT_SCENES.items(), 1):
        scene_blocks.append(f"场景{i} — {key}\n  {definition}")
    scenes_text = '\n\n'.join(scene_blocks)

    return f"""你是语音对话能力的裁判专家。你将收到【模型输出音频】以及下方【环境音参考内容文本】。

在环境理解-有语义场景中，用户在交互过程中所处环境内存在可识别的环境音内容（如新闻广播、公共播报等）。模型需要对环境音内容进行感知和理解，并在输出中体现出对环境音内容的正确理解。下方【环境音参考内容文本】即为环境音中实际包含的内容文本，作为评估模型理解准确性的参考标准。

请结合模型输出音频和参考内容文本，对模型输出内容与环境音参考内容的相关性、一致性和完整性进行综合评估，判断模型是否正确理解了环境音内容。

═══════════════════════════════════════
【评分标准】（1-5分，仅可给出1至5的正数整数）
═══════════════════════════════════════

{SCORING_CRITERIA}

评分维度说明：
- 相关性：模型输出内容是否与环境音参考内容文本在主题和语义上相关联，是否围绕参考内容中的信息展开。
- 一致性：模型输出内容中引用或转述的环境音信息是否与参考内容文本一致，是否存在错误、偏差或臆造。
- 完整性：模型输出内容是否覆盖了参考内容文本中的全部关键信息，是否存在信息遗漏或缺失，对环境音内容的理解是否全面。

═══════════════════════════════════════
【环境音参考内容文本】
═══════════════════════════════════════

{correct_answer}

═══════════════════════════════════════
【场景定义】（环境音内容类型参考）
═══════════════════════════════════════

{scenes_text}

═══════════════════════════════════════
【评估步骤】
═══════════════════════════════════════

1. 从模型输出音频中提取模型实际输出的语音内容。
2. 将模型输出内容与【环境音参考内容文本】进行逐项比对，识别模型理解并引用了哪些关键信息。
3. 评估模型输出内容与参考内容的相关性（是否围绕参考内容展开）、一致性（信息是否准确、无臆造）和完整性（关键信息是否全面覆盖、无遗漏）。
4. 综合相关性、一致性、完整性三个维度的表现，根据评分标准给出1-5的整数评分。
5. 评分4分及以上 → understand_correct = true；评分3分及以下 → understand_correct = false。

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "understand_correct": true,
  "score": 5,
  "reason": "简短判定理由"
}}

其中：
- understand_correct 必须是 true 或 false，表示模型是否正确理解了环境音内容
- score 必须是 1 至 5 的正数整数（1、2、3、4、5），分数越高表示模型对环境音内容的理解越准确、越完整
- reason 为简短判定理由，需说明：模型输出中包含了参考内容的哪些关键信息、遗漏或错误了哪些信息，以及相关性、一致性、完整性三个维度的具体表现，综合分析后为何给出该分数"""


# ─────────── 时延计算 ───────────
def _calculate_response_latency(play_audio, user_wav, ai_wav):
    """计算用户询问到模型回复的时延

    1. 用 FFT 互相关在 user_wav 中定位环境声(play_audio)的起止时间
    2. 从 user_wav ASR chunks 中找到环境声后的用户询问，获取其结束时间
    3. 从 ai_wav ASR chunks 中找到模型首字时间
    4. 时延 = 模型首字时间 - 用户询问结束时间
    """
    result: Dict[str, Any] = {
        'response_latency_ms': None,
        'env_sound_start_ms': None,
        'env_sound_end_ms': None,
        'user_question_end_ms': None,
        'model_first_word_start_ms': None,
        'ncc': None,
        'message': '',
    }

    # 解析 play_audio 路径
    played_audio_path = _resolve_played_audio_path(play_audio)
    if not played_audio_path or not os.path.isfile(played_audio_path):
        result['message'] = f'play_audio 文件不存在: {play_audio!r}'
        logger.error(result['message'])
        return result

    if not user_wav or not os.path.isfile(user_wav):
        result['message'] = f'user_wav 文件不存在: {user_wav!r}'
        logger.error(result['message'])
        return result

    if not ai_wav or not os.path.isfile(ai_wav):
        result['message'] = f'ai_wav 文件不存在: {ai_wav!r}'
        logger.error(result['message'])
        return result

    # 1. FFT 互相关定位环境声在 user_wav 中的起止时间
    try:
        sr_clean, clean = _load_audio(played_audio_path)
        sr_user, user_audio = _load_audio(user_wav)
        if sr_clean != sr_user:
            clean = resample_poly(clean, sr_user, sr_clean)
        start, end = _detect_speech_region(clean, sr_user)
        clean_speech = clean[start:end]
        if len(clean_speech) < 1:
            result['message'] = '环境声有效语料区间为空，无法对齐'
            logger.error(result['message'])
            return result
        offset, ncc = _coarse_to_fine_align(clean_speech, user_audio)
        env_sound_start_s = offset / sr_user
        env_sound_end_s = (offset + len(clean_speech)) / sr_user
    except Exception as exc:
        logger.exception('[env_judge] 音频对齐失败')
        result['message'] = f'音频对齐失败: {exc}'
        return result

    result['env_sound_start_ms'] = round(env_sound_start_s * 1000.0, 1)
    result['env_sound_end_ms'] = round(env_sound_end_s * 1000.0, 1)
    result['ncc'] = round(ncc, 4)

    logger.info(
        f'[env_judge] 环境声定位: start={result["env_sound_start_ms"]}ms '
        f'end={result["env_sound_end_ms"]}ms ncc={result["ncc"]}'
    )

    # 2. 从 user_wav ASR 中找到环境声后的用户询问
    user_chunks = get_asr_chunks(user_wav)
    if user_chunks:
        user_speech_after_env = [
            c for c in user_chunks
            if isinstance(c, dict) and c.get('timestamp')
            and c['timestamp'][0] is not None
            and c['timestamp'][1] is not None
            and c['timestamp'][0] >= env_sound_end_s
        ]
        if user_speech_after_env:
            user_question_end_s = max(c['timestamp'][1] for c in user_speech_after_env)
        else:
            # 没找到用户询问，用环境声结束时间作为近似
            user_question_end_s = env_sound_end_s
    else:
        user_question_end_s = env_sound_end_s

    result['user_question_end_ms'] = round(user_question_end_s * 1000.0, 1)

    # 3. 从 ai_wav ASR 中找到模型首字
    ai_chunks = get_asr_chunks(ai_wav)
    if not ai_chunks:
        result['message'] = 'ai_wav ASR chunks 为空，无法获取模型首字时间戳'
        logger.error(result['message'])
        return result

    valid_chunks = [
        c for c in ai_chunks
        if isinstance(c, dict) and c.get('timestamp')
        and c['timestamp'][0] is not None
        and c['timestamp'][0] >= user_question_end_s
    ]

    if not valid_chunks:
        # 如果没有找到用户询问后的模型首字，取所有 ai chunks 的第一个
        valid_chunks = [
            c for c in ai_chunks
            if isinstance(c, dict) and c.get('timestamp')
            and c['timestamp'][0] is not None
        ]

    if not valid_chunks:
        result['message'] = 'ai_wav ASR chunks 中无有效时间戳'
        logger.error(result['message'])
        return result

    model_first_word_start_s = min(c['timestamp'][0] for c in valid_chunks)
    result['model_first_word_start_ms'] = round(model_first_word_start_s * 1000.0, 1)

    # 4. 时延 = 模型首字时间 - 用户询问结束时间
    result['response_latency_ms'] = round(
        result['model_first_word_start_ms'] - result['user_question_end_ms'], 1
    )
    result['message'] = 'OK'

    logger.info(
        f'[env_judge] 回复时延: {result["response_latency_ms"]}ms '
        f'(model_first_word={result["model_first_word_start_ms"]}ms - '
        f'user_question_end={result["user_question_end_ms"]}ms)'
    )

    return result


# ─────────── 主入口 ───────────
def evaluate_env_judge(
    user_wav: str,
    ai_wav: str,
    play_audio: str,
    correctAnswer: str,
    task_type=0,
    model: str = '',
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """环境理解裁判

    判断模型对环境音内容的理解是否正确 + 计算用户询问到模型回复的时延

    Args:
        user_wav:      用户通道音频路径(含环境声 + 用户询问)
        ai_wav:        模型回复音频路径
        play_audio:    原始环境声音频路径(干净音源)
        correctAnswer: 正确答案(字符串)
        task_type:     脚本类型: 0=无语义(non_semantic), 1=有语义(semantic)
        model:         LLM 模型名(空则按维度配置解析)
        max_tokens:    LLM max_tokens
        temperature:   LLM temperature

    Returns:
        dict: {understand_correct, score, reason, response_latency_ms, ...}
    """
    script_type = _task_type_to_script_type(task_type)

    llm_config = get_llm_config()
    if not model:
        model = resolve_model(dimension='env_judge')
    if not max_tokens:
        max_tokens = llm_config.get('max_tokens', LLM_DEFAULT_MAX_TOKENS)
    if temperature is None:
        temperature = llm_config.get('temperature', LLM_DEFAULT_TEMPERATURE)

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'user_wav': user_wav,
        'ai_wav': ai_wav,
        'play_audio': play_audio,
        'correctAnswer': correctAnswer,
        'task_type': task_type,
        'script_type': script_type,
        'understand_correct': None,
        'understand_correct_pass': None,
        'score': None,
        'reason': '',
        'ai_answer': '',
        'response_latency_ms': None,
        'env_sound_start_ms': None,
        'env_sound_end_ms': None,
        'user_question_end_ms': None,
        'model_first_word_start_ms': None,
        'ncc': None,
        'tokens_used': 0,
        'input_token': 0,
        'output_token': 0,
        'message': '',
    }

    # ─── 1. LLM 判定 True/False ───
    if not ai_wav or not os.path.isfile(ai_wav):
        result['message'] = f'模型回复音频(ai_wav)不存在或路径无效: ai_wav={ai_wav!r}'
        result['enabled'] = False
        logger.error(f'[env_judge] {result["message"]}')
        return result

    # 从 ai_wav 提取 ASR 文本（供参考）
    answer_text = get_asr_text(ai_wav)
    result['ai_answer'] = answer_text

    # 构建 prompt
    prompt = build_env_judge_prompt(correctAnswer, script_type)

    try:
        response = call_llm_api(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            file_paths=[ai_wav],  # 发送模型回复音频给多模态 LLM
            log_context={'dimension': 'env_judge', 'script_type': script_type},
        )
    except Exception as e:
        result['message'] = f'LLM 调用失败: {e}'
        result['enabled'] = False
        logger.error(f'[env_judge] LLM 调用失败: {e}')
        return result

    result['tokens_used'] = response.get('tokens_used', 0)
    result['input_token'] = response.get('input_token', 0)
    result['output_token'] = response.get('output_token', 0)

    parsed = parse_json(response['content'])
    if not parsed:
        result['message'] = 'LLM 输出解析失败'
        logger.error(f'[env_judge] LLM 输出解析失败: {response["content"][:200]}')
        return result

    # 解析 understand_correct（兼容 bool / str）
    uc = parsed.get('understand_correct')
    if isinstance(uc, str):
        uc = uc.strip().lower() == 'true'
    result['understand_correct'] = uc
    result['understand_correct_pass'] = 1 if uc else (0 if uc is not None else None)

    result['score'] = parsed.get('score')
    result['reason'] = parsed.get('reason', '')

    # ─── 2. 计算时延 ───
    latency_result = _calculate_response_latency(play_audio, user_wav, ai_wav)
    result['response_latency_ms'] = latency_result.get('response_latency_ms')
    result['env_sound_start_ms'] = latency_result.get('env_sound_start_ms')
    result['env_sound_end_ms'] = latency_result.get('env_sound_end_ms')
    result['user_question_end_ms'] = latency_result.get('user_question_end_ms')
    result['model_first_word_start_ms'] = latency_result.get('model_first_word_start_ms')
    result['ncc'] = latency_result.get('ncc')

    if not result['message']:
        latency_msg = latency_result.get('message', '')
        result['message'] = latency_msg if latency_msg else 'OK'

    logger.info(
        f'[env_judge] '
        f'model={model} script_type={script_type} '
        f'understand_correct={result["understand_correct"]} '
        f'score={result["score"]} '
        f'latency={result["response_latency_ms"]}ms '
        f'tokens={result["tokens_used"]}'
    )
    return result


if __name__ == '__main__':
    import argparse
    from pathlib import Path

    # 独立运行时加载 eval_server/.env
    _env_path = Path(__file__).resolve().parents[4] / '.env'
    if _env_path.exists():
        with open(_env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser(
        description='环境理解裁判：判断模型对环境音内容的理解是否正确 + 计算回复时延'
    )
    parser.add_argument('user_wav', help='用户通道音频路径(含环境声+用户询问)')
    parser.add_argument('ai_wav', help='模型回复音频路径')
    parser.add_argument('play_audio', help='原始环境声音频路径(干净音源)')
    parser.add_argument('--correct_answer', default='', help='正确答案(字符串)')
    parser.add_argument('--task_type', type=int, default=0,
                        choices=[0, 1],
                        help='脚本类型: 0=无语义(non_semantic), 1=有语义(semantic)')
    args = parser.parse_args()

    r = evaluate_env_judge(
        user_wav=args.user_wav,
        ai_wav=args.ai_wav,
        play_audio=args.play_audio,
        correctAnswer=args.correct_answer,
        task_type=args.task_type,
    )

    print('=' * 60)
    print(f'模型: {r["model"]}')
    print(f'task_type: {r["task_type"]} → script_type: {r["script_type"]}')
    print(f'tokens: {r["tokens_used"]} (in={r["input_token"]}, out={r["output_token"]})')
    print(f'message: {r["message"]}')
    print('-' * 60)
    print(f'  正确答案: {r["correctAnswer"]}')
    print(f'  模型回答(ASR): {r["ai_answer"]}')
    print(f'  理解正确: {r["understand_correct"]}')
    print(f'  评分: {r["score"]}')
    print(f'  理由: {r["reason"]}')
    print(f'  回复时延: {r["response_latency_ms"]}ms')
    print(f'  环境声起止: {r["env_sound_start_ms"]}ms - {r["env_sound_end_ms"]}ms')
    print(f'  用户询问结束: {r["user_question_end_ms"]}ms')
    print(f'  模型首字: {r["model_first_word_start_ms"]}ms')
    print(f'  NCC: {r["ncc"]}')
    print('=' * 60)
    print(json.dumps(r, ensure_ascii=False, indent=2))
