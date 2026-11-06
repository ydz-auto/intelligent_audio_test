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
    played_audios — 本轮被播放音频(经 case_config→audios 映射取用，取首位为原始环境声)
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
from difflib import SequenceMatcher
from typing import Any, Dict, Optional

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
def build_env_judge_prompt(correct_answer: str, script_type: str = 'semantic',
                           model_output_text: str = '') -> str:
    """以音频为实际回答证据、ASR辅助识别，将回答与正确答案比较。"""
    if script_type == 'non_semantic':
        return _build_non_semantic_prompt(correct_answer, model_output_text)
    return _build_semantic_prompt(correct_answer, model_output_text)


def _env_type_to_script_type(env_type) -> str:
    """将输入参数 env_type 映射为 script_type

    env_type=false/0/'0' → 'non_semantic'（无语义）
    env_type=true/1/'1'  → 'semantic'（有语义）
    """
    if isinstance(env_type, str):
        env_type = env_type.strip().lower()
    if env_type in (0, '0', False, 'false', 'non_semantic'):
        return 'non_semantic'
    return 'semantic'


def _build_non_semantic_prompt(correct_answer: str, model_output_text: str = '') -> str:
    """无语义脚本 prompt：判断模型是否正确识别了环境声音类型"""
    sound_type_blocks = []
    for i, (key, definition) in enumerate(NON_SEMANTIC_SOUND_TYPES.items(), 1):
        sound_type_blocks.append(f"类型{i} — {key}\n  {definition}")
    sound_types_text = '\n\n'.join(sound_type_blocks)

    output_block = (
        f'{model_output_text}'
        if model_output_text.strip()
        else '（未获得ASR转写：请直接依据音频判断，不代表模型未回复）'
    )

    return f"""你是语音对话能力的裁判专家。你将收到【模型输出音频】以及下方【环境声音参考答案】。

在环境理解-无语义场景中，用户所处的环境中出现了一段环境声音（如门铃、电话、警报等非语音噪声）。用户会询问"刚刚是什么声音"之类的问题，模型需要正确识别并描述该环境声音的类型。

请结合模型输出音频和参考答案，判断模型是否正确识别了环境声音的类型。

【证据优先级】以提供的模型输出音频为主要依据，先听辨模型实际说了什么，ASR转写仅辅助识别实际回答；环境声音参考答案是正确答案，必须将实际回答与其比较，不因措辞不同直接判错。ASR可能漏字、误识别或为空；与音频冲突时以音频中可确认的实际发言为准，不能因ASR为空就认定模型未回复或直接判1分。区分模型发言与混入的环境声、噪声，严禁把参考答案当作模型实际输出。只有音频能够确认静音或没有有效模型发言时，才按未回复评分；无法可靠听辨时，在reason中明确证据不足，不虚构回答。

═══════════════════════════════════════
【模型输出内容（ASR 转写）】
═══════════════════════════════════════

{output_block}

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

1. 先听模型输出音频，识别模型实际发言；ASR仅用于辅助定位和理解，不能代替音频。结合参考内容判断，reason应说明音频证据及必要的ASR差异；不要将参考内容当成实际输出。
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


def _build_semantic_prompt(correct_answer: str, model_output_text: str = '') -> str:
    """有语义脚本 prompt：判断模型是否正确理解了环境音内容"""
    scene_blocks = []
    for i, (key, definition) in enumerate(ENVIRONMENT_SCENES.items(), 1):
        scene_blocks.append(f"场景{i} — {key}\n  {definition}")
    scenes_text = '\n\n'.join(scene_blocks)

    output_block = (
        f'{model_output_text}'
        if model_output_text.strip()
        else '（未获得ASR转写：请直接依据音频判断，不代表模型未回复）'
    )

    return f"""你是语音对话能力的裁判专家。你将收到【模型输出音频】以及下方【环境音参考内容文本】。

在环境理解-有语义场景中，用户在交互过程中所处环境内存在可识别的环境音内容（如新闻广播、公共播报等）。模型需要对环境音内容进行感知和理解，并在输出中体现出对环境音内容的正确理解。下方【环境音参考内容文本】是给定的正确答案，作为内容正确性的评判标准；允许同义表达，不要求模型逐字复述。

请结合模型输出音频和参考内容文本，对模型输出内容与环境音参考内容的相关性、一致性和完整性进行综合评估，判断模型是否正确理解了环境音内容。

【证据优先级】以提供的模型输出音频为主要依据，先听辨模型实际说了什么，ASR转写仅辅助识别实际回答；环境声音参考答案是正确答案，必须将实际回答与其比较，不因措辞不同直接判错。ASR可能漏字、误识别或为空；与音频冲突时以音频中可确认的实际发言为准，不能因ASR为空就认定模型未回复或直接判1分。区分模型发言与混入的环境声、噪声，严禁把参考答案当作模型实际输出。只有音频能够确认静音或没有有效模型发言时，才按未回复评分；无法可靠听辨时，在reason中明确证据不足，不虚构回答。

═══════════════════════════════════════
【模型输出内容（ASR 转写）】
═══════════════════════════════════════

{output_block}

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

1. 先听模型输出音频，识别模型实际发言；ASR仅用于辅助定位和理解，不能代替音频。结合参考内容判断，reason应说明音频证据及必要的ASR差异；不要将参考内容当成实际输出。
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
def _calculate_response_latency(played_audios, user_wav, ai_wav):
    """当前轮用户实际ASR末词到模型新回复首词；环境声定位不参与问句过滤。"""
    import math
    import re
    import unicodedata

    result = dict(response_latency_ms=None, env_sound_start_ms=None,
                  env_sound_end_ms=None, user_question_end_ms=None,
                  model_first_word_start_ms=None, ncc=None, message='')

    def valid_words(chunks):
        words = []
        for chunk in chunks or []:
            if not isinstance(chunk, dict):
                continue
            text = str(chunk.get('text') or '')
            ts = chunk.get('timestamp')
            if not any(not c.isspace() and not unicodedata.category(c).startswith(('P', 'Z')) for c in text):
                continue
            if (not isinstance(ts, (list, tuple)) or len(ts) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (float, int))
                           or not math.isfinite(v) for v in ts)
                    or ts[0] < 0 or ts[1] < ts[0]):
                raise ValueError('ASR字词时间戳无效，不能计算时延')
            words.append(chunk)
        return sorted(words, key=lambda c: (c['timestamp'][0], c['timestamp'][1]))

    user_words = valid_words(get_asr_chunks(user_wav))
    if not user_words:
        result.update(is_success=False, message='评估异常：query ASR为空')
        return result
    # 本维度用户通道包含环境播报和随后的询问。优先定位实际ASR中
    # “刚才/刚刚…什么”等询问，不把前面的环境播报视作用户问题。
    # 保留字符到chunk的映射，既支持中文逐字，也支持整词/整句chunk。
    text = ''.join(c['text'] for c in user_words)
    anchors = list(re.finditer(r'(?:刚才|刚刚|方才|刚)(?=[^。！？?]*(?:什么|啥|哪))', text))
    if anchors:
        offset = anchors[-1].start()
        consumed = 0
        first = 0
        for index, chunk in enumerate(user_words):
            if consumed + len(chunk['text']) > offset:
                first = index
                break
            consumed += len(chunk['text'])
        question_words = user_words[first:]
        # 起点落在整句chunk内部时没有可靠词级起点，不能借用整句开头。
        if consumed != offset:
            result['message'] = '时延不可计算：问句与环境播报位于同一ASR片段，缺少问句起点时间'
            return result
    else:
        # 无询问锚点时，仅接受单段实际输入；多段混合输入不自动猜轮。
        if any(b['timestamp'][0] - a['timestamp'][1] > 1.5
               for a, b in zip(user_words, user_words[1:])):
            result['message'] = '时延不可计算：用户通道含多段内容，无法可靠定位实际询问'
            return result
        question_words = user_words
    question_start = question_words[0]['timestamp'][0]
    question_end = max(c['timestamp'][1] for c in question_words)
    result['user_question_start_ms'] = round(question_start * 1000, 1)
    result['user_question_text'] = ''.join(c['text'] for c in question_words)
    result['user_question_end_ms'] = round(question_end * 1000, 1)
    model_words = valid_words(get_asr_chunks(ai_wav))
    if not model_words:
        result.update(is_success=False, message='评估异常：模型回复ASR为空')
        return result
    # 累积录音可能含问句开始之前的模型发言，不能把它当作本轮回复。
    # 不要求模型开始晚于问句末词，否则会掩盖真实负时延。
    # 按停顿分组后选新的发言起点，不能截取提问前已开始的旧回答中间词。
    utterances = []
    for word in model_words:
        if not utterances or word['timestamp'][0] - utterances[-1][-1]['timestamp'][1] > 1.5:
            utterances.append([])
        utterances[-1].append(word)
    responses = [group[0] for group in utterances
                 if group[0]['timestamp'][0] >= question_start]
    if not responses:
        result['message'] = '时延不可计算：当前问句开始后无可确认的模型回复词'
        return result
    model_start = responses[0]['timestamp'][0]
    result['model_first_word_start_ms'] = round(model_start * 1000, 1)
    latency = round((model_start - question_end) * 1000, 1)
    if latency < 0:
        result.update(is_success=False, raw_response_latency_ms=latency,
                      message='评估异常：响应时延为负值')
        return result
    result.update(response_latency_ms=latency,
                  message='OK：模型回复首词开始时间减去当前轮用户ASR末词结束时间')
    logger.info('[env_judge] 问句=%s 起止=%s–%sms 回复首词=%sms 时延=%sms',
                result['user_question_text'], result['user_question_start_ms'],
                result['user_question_end_ms'], result['model_first_word_start_ms'], latency)
    return result


# ─────────── 主入口 ───────────
def evaluate_env_judge(
    user_wav: str,
    ai_wav: str,
    played_audios: str,
    correctAnswer: str,
    env_type=0,
    model: str = '',
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """环境理解裁判

    判断模型对环境音内容的理解是否正确 + 计算用户询问到模型回复的时延

    Args:
        user_wav:      用户通道音频路径(含环境声 + 用户询问)
        ai_wav:        模型回复音频路径
        played_audios: 本轮被播放音频（列表/JSON/路径，取首位为原始环境声）
        correctAnswer: 正确答案(字符串)
        env_type:      脚本类型: false/0=无语义(non_semantic), true/1=有语义(semantic)
        model:         LLM 模型名(空则按维度配置解析)
        max_tokens:    LLM max_tokens
        temperature:   LLM temperature

    Returns:
        dict: {understand_correct, score, reason, response_latency_ms, ...}
    """
    script_type = _env_type_to_script_type(env_type)

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
        'played_audios': played_audios,
        'correctAnswer': correctAnswer,
        'env_type': env_type,
        'script_type': script_type,
        'understand_correct': None,
        'understand_correct_pass': None,
        'score': None,
        'reason': '',
        'ai_answer': '',
        'text_similarity': None,
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

    def evaluation_error(message):
        # 数据异常属于已完成但无有效统计值，不触发任务failed。
        result.update(enabled=True, excluded_from_statistics=True,
                      exclusion_reason=message,
                      understand_correct=None, understand_correct_pass=None,
                      score=None, response_latency_ms=None,
                      reason='评估异常：' + message, message='评估异常：' + message)
        return result

    try:
        query_text = get_asr_text(user_wav) if user_wav and os.path.isfile(user_wav) else ''
    except Exception as exc:
        return evaluation_error(f'query ASR获取失败: {exc}')
    result['query_asr'] = query_text or ''
    if not result['query_asr'].strip():
        return evaluation_error('query ASR为空')

    # ─── 1. LLM 判定 True/False ───
    if not ai_wav or not os.path.isfile(ai_wav):
        return evaluation_error(f'模型回复音频为空或不存在: ai_wav={ai_wav!r}')

    # 从 ai_wav 提取 ASR 文本（供参考）
    try:
        answer_text = get_asr_text(ai_wav) or ''
    except Exception as exc:
        return evaluation_error(f'模型回复ASR获取失败: {exc}')
    result['ai_answer'] = answer_text
    if not answer_text.strip():
        return evaluation_error('模型回复ASR为空')

    # Text overlap is diagnostic only; semantic correctness belongs to the judge.
    if script_type == 'semantic' and answer_text.strip():
        result['text_similarity'] = round(
            SequenceMatcher(None, answer_text, correctAnswer).ratio(), 4
        )

    # Timing is independent of content scoring and judge transport/JSON failures.
    # Keep its status separate so a missing timestamp cannot mask a scoring failure.
    try:
        latency_result = _calculate_response_latency(played_audios, user_wav, ai_wav)
        for key in ('response_latency_ms', 'env_sound_start_ms', 'env_sound_end_ms',
                    'user_question_end_ms', 'user_question_start_ms', 'user_question_text',
                    'model_first_word_start_ms', 'ncc'):
            result[key] = latency_result.get(key)
        result['latency_message'] = latency_result.get('message') or 'OK'
        if latency_result.get('is_success') is False:
            result['raw_response_latency_ms'] = latency_result.get('raw_response_latency_ms')
            return evaluation_error(result['latency_message'].removeprefix('评估异常：'))
        if result['response_latency_ms'] is not None and result['response_latency_ms'] < 0:
            result['raw_response_latency_ms'] = result['response_latency_ms']
            result['response_latency_ms'] = None
            return evaluation_error('响应时延为负值')
    except Exception as exc:
        logger.exception('[env_judge] latency calculation failed')
        result['latency_message'] = f'时延计算失败: {exc}'

    # Audio is primary evidence; the transcript is an optional aid.
    prompt = build_env_judge_prompt(correctAnswer, script_type,
                                    model_output_text=answer_text)

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
        result['is_success'] = False
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
    result['message'] = result.get('latency_message') or 'OK'

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
    parser.add_argument('played_audios', help='本轮被播放音频路径/JSON(取首位为原始环境声)')
    parser.add_argument('--correct_answer', default='', help='正确答案(字符串)')
    parser.add_argument('--env_type', type=int, default=0,
                        choices=[0, 1],
                        help='脚本类型: 0=无语义(non_semantic), 1=有语义(semantic)')
    args = parser.parse_args()

    r = evaluate_env_judge(
        user_wav=args.user_wav,
        ai_wav=args.ai_wav,
        played_audios=args.played_audios,
        correctAnswer=args.correct_answer,
        env_type=args.env_type,
    )

    print('=' * 60)
    print(f'模型: {r["model"]}')
    print(f'env_type: {r["env_type"]} → script_type: {r["script_type"]}')
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
