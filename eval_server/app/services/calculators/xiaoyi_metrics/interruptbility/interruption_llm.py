# -*- coding: utf-8 -*-
"""
interruption_llm.py
打断指标的大模型评估（LLM 全量评估）

在 calculate_interruption_metrics 算完时序指标后，把三项主指标(打断成功率/停止时延/恢复时延)
交给 LLM 计算，同时判断 AI 是否被打断、AI 对打断语句的反应，以及对整条用例的恢复质量
(coherence/relevance/adaptability，用例级单值)打分。仅在 enable_llm_eval=True 且配置了
LLM_JUDGE_API_KEY 时触发；LLM 失败则由调用方回退本地时序计算(compute_interruption_metrics)。

定位打断边界优先听随附音频做字词级 ASR(本地字词级 ASR 时间戳不可靠)；音频不可用回落段级 ASR。
AI 侧用本地段级 ASR 作参考；用户侧用本地段级 ASR(原样，不去日文)作参考。
多模态音频(各轮 ai_wav/user_wav)随附，裁尾部静音后发送(偏移 0，时间戳不变)。

数据来源：调用方传入的 rounds 文本结构，每轮 {query, answer, user_wav, ai_wav...}，
顶层可选 original_topic。注意用户 PCM 里可能说了两段及以上的话(多次开口)。

设计原则：
    - LLM 输出逐轮 JSON 数组，Python 做聚合(不让 LLM 算平均)
    - 每个指标都带简短 reason
    - LLM 输出严格 JSON；先 json.loads，失败用正则兜底
    - _call_llm_json/_parse_json/_BEHAVIOR_LABELS 等也供 false_takeover 复用
"""
import json
import logging
import os
import re
import struct
import tempfile
import wave
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

LLM_DEFAULT_TIMEOUT = 120
LLM_DEFAULT_TEMPERATURE = 0.1
LLM_DEFAULT_MAX_TOKENS = 1024

# 行为分类的合法取值（5 类，与 env_judge.interruption_judge 对齐）
# 回应=直接回复用户指令/回到原话题请求；恢复=未明确回应但自然续上原话题/交互主线；
# 询问=追问澄清确认；无关回复=有回复但与意图无关(含说穿/未停/恢复失败)；沉默或无视=无有效回复/无视指令
_BEHAVIOR_LABELS = ['回应', '恢复', '询问', '无关回复', '沉默或无视']


# ─────────── LLM 调用 ───────────
def _call_llm_json(prompt: str, model: str,
                   max_tokens: int = LLM_DEFAULT_MAX_TOKENS,
                   temperature: float = LLM_DEFAULT_TEMPERATURE) -> Dict[str, Any]:
    """调用 OpenAI 兼容的 LLM，返回 content 文本。

    复用 config.LLM_JUDGE（api_base_url/api_key/timeout）。未配置抛 ValueError。
    """
    from app.config import config

    llm_config = getattr(config, 'LLM_JUDGE', {})
    api_base = llm_config.get('api_base_url', '')
    api_key = llm_config.get('api_key', '')
    timeout = llm_config.get('timeout', LLM_DEFAULT_TIMEOUT)

    if not api_base or not api_key:
        raise ValueError(
            'LLM 评估未配置：请在 eval_server 设置 LLM_JUDGE_API_BASE 与 LLM_JUDGE_API_KEY'
        )

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': 'You are a precise dialog evaluator.'},
            {'role': 'user', 'content': prompt},
        ],
        'max_tokens': max_tokens,
        'temperature': temperature,
        'response_format': {'type': 'json_object'},
    }

    with httpx.Client(trust_env=False, timeout=timeout) as client:
        response = client.post(
            f'{api_base.rstrip("/")}/chat/completions',
            headers=headers,
            json=payload,
        )

    response.raise_for_status()
    data = response.json()
    content = data['choices'][0]['message']['content']
    tokens_used = data.get('usage', {}).get('total_tokens', 0)
    return {'content': content, 'tokens_used': tokens_used}


def _parse_json(content: str) -> Optional[dict]:
    """解析 LLM 输出为 dict。先 json.loads，失败用正则兜底，再失败返回 None。"""
    if not content:
        return None
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r'\{.*\}', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _unwrap_value(val: Any) -> str:
    """解包 {'text': '...'} 格式（与 task_service._unwrap_value 一致）"""
    if isinstance(val, dict) and 'text' in val:
        return val['text']
    return val


def _avg(values: List[float]) -> Optional[float]:
    """取平均，保留 3 位小数；空列表返回 None"""
    values = [v for v in values if isinstance(v, (int, float))]
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _score_field(parsed: dict, key: str) -> Optional[float]:
    """从 parsed 中取数值分；非数值返回 None"""
    v = parsed.get(key)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except (ValueError, TypeError):
            return None
    return None


def _normalize_behavior(raw: Any, summary: Dict[str, int]) -> tuple:
    """把 LLM 输出的 behavior 归一到合法 5 类标签，命中则给 summary 计数 +1。

    返回 (归一后标签, 是否命中合法标签)。未命中返回 (原值, False) 不计数。
    """
    behavior = str(raw or '').strip()
    if behavior in summary:
        summary[behavior] += 1
        return behavior, True
    # 子串/近义映射：LLM 偶有"回应了""沉默"等变体
    for label in _BEHAVIOR_LABELS:
        if label in behavior:
            summary[label] += 1
            return label, True
    return behavior, False


# ═════════════════════════════════════════════════════════════════════════════
# LLM 全量评估：success_rate / stop_latency / recovery_latency / 是否被打断 / 反应
# 三项主指标改为 LLM 计算，用户/AI 侧用本地段级 ASR 作参考，字词级定位优先听随附音频；
# 文本时间戳 + 音频多模态；用户 PCM 里可能说了两段及以上的话。
# ═════════════════════════════════════════════════════════════════════════════

# 音频总大小守卫：原始字节上限(base64≈4/3)，超过则丢弃音频只发文本
_LLM_AUDIO_MAX_BYTES = 12 * 1024 * 1024  # ≈12MB 原始 → ≈16MB base64

# 尾部静音裁剪阈值(16bit 幅度)；用于把长录音压小再发 gemini，偏移保持 0(只裁尾)时间戳不变
_TRIM_AMP_THRESHOLD = 300
_TRIM_FRAME_MS = 20
_TRIM_TAIL_MS = 300


def _trim_wav_tail(wav_path: str) -> str:
    """裁掉 wav 尾部静音到临时文件，返回临时路径；失败/无需裁返回原路径。

    只裁尾部(偏移 0)，时间戳不变；用于把 165s 全录音(语音仅~60s)压到几 MB 再发 gemini。
    """
    try:
        with wave.open(wav_path, 'rb') as w:
            p = w.getparams()
            frames = w.readframes(w.getnframes())
        nchan, sw, sr = p.nchannels, p.sampwidth, p.framerate
        bytes_per_sample = sw * nchan
        frame_bytes = int(sr * _TRIM_FRAME_MS / 1000) * bytes_per_sample
        if frame_bytes == 0:
            frame_bytes = bytes_per_sample
        n = len(frames)
        if n < frame_bytes:
            return wav_path
        pos = n
        last_voice = 0
        while pos > 0:
            start = max(0, pos - frame_bytes)
            chunk = frames[start:pos]
            max_amp = 0
            if sw == 2:
                cnt = len(chunk) // 2
                for i in range(cnt):
                    v = abs(struct.unpack_from('<h', chunk, i * 2)[0])
                    if v > max_amp:
                        max_amp = v
                        if max_amp > _TRIM_AMP_THRESHOLD:
                            break
            elif sw == 1:
                for b in chunk:
                    v = abs(b - 128)
                    if v > max_amp:
                        max_amp = v
                        if max_amp > _TRIM_AMP_THRESHOLD:
                            break
            else:
                return wav_path  # 未知位深不裁
            if max_amp > _TRIM_AMP_THRESHOLD:
                last_voice = pos
                break
            pos = start
        if last_voice == 0:
            return wav_path  # 全静音或未找到语音，不裁
        tail = int(sr * _TRIM_TAIL_MS / 1000) * bytes_per_sample
        end = min(n, last_voice + tail)
        trimmed = frames[:end]
        fd, tmp = tempfile.mkstemp(suffix='_trimmed.wav')
        with os.fdopen(fd, 'wb'):
            pass
        with wave.open(tmp, 'wb') as w:
            w.setparams(p)
            w.writeframes(trimmed)
        return tmp
    except Exception as e:
        logger.warning(f"[interruption_llm_full] trim wav tail 失败 {wav_path}: {e}")
        return wav_path


def _fmt_chunks(chunks: Any, limit: int = 600) -> str:
    """把 chunks 格式成 `text[start,end] text[start,end]` 形式，供 prompt 引用时间戳。"""
    if not chunks:
        return '(无)'
    if isinstance(chunks, dict):
        chunks = chunks.get('chunks') or []
    parts: List[str] = []
    for c in (chunks or [])[:limit]:
        if not isinstance(c, dict):
            continue
        t = str(c.get('text', ''))
        ts = c.get('timestamp')
        if isinstance(ts, (list, tuple)) and len(ts) >= 2 and ts[0] is not None and ts[1] is not None:
            try:
                parts.append(f'{t}[{float(ts[0]):.2f},{float(ts[1]):.2f}]')
            except (TypeError, ValueError):
                parts.append(t)
        else:
            parts.append(t)
    return ' '.join(parts) if parts else '(无)'


def _num(v: Any) -> Optional[float]:
    """转数值(秒)，3 位小数；非数值返回 None。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 3)
    if isinstance(v, str):
        try:
            return round(float(v.strip()), 3)
        except (ValueError, TypeError):
            return None
    return None


def _seg(v: Any) -> Optional[List[float]]:
    """[起, 止] 秒，3 位小数。"""
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        try:
            return [round(float(v[0]), 3), round(float(v[1]), 3)]
        except (TypeError, ValueError):
            return None
    return None


def _to_bool(v: Any) -> bool:
    """str 感知的布尔解析：multipart 上传时 is_return_to_topic 等会变 str('false'/'true')。
    bool('false')=True 是 bug，这里按内容判：'false'/'0'/'no'/'否'→False，其余 truthy→True。
    """
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    if s in ('false', '0', 'no', '否', 'off', ''):
        return False
    return True


def _build_interruption_full_prompt(rounds: List[Dict[str, Any]],
                                    user_asr_ref_pr: List[Any],
                                    ai_word_chunks_pr: List[Any],
                                    original_topic: str = '') -> str:
    """构建多轮打断全量评估 prompt。

    用户/AI 侧均给段级 ASR 时间戳作参考；字词级定位优先由 gemini 听随附音频自己产出
    （本地字词级 ASR 时间戳不可靠，不喂）；音频不可用时回落到段级 ASR 时间戳。
    """
    topic_line = original_topic or '(未显式给出，可从对话推断)'
    blocks: List[str] = []
    for i, rd in enumerate(rounds, 1):
        if not isinstance(rd, dict):
            continue
        u = user_asr_ref_pr[i - 1] if i - 1 < len(user_asr_ref_pr) else None
        a = ai_word_chunks_pr[i - 1] if i - 1 < len(ai_word_chunks_pr) else None
        query = _unwrap_value(rd.get('query', '')) or ''
        answer = _unwrap_value(rd.get('answer', '')) or ''
        blocks.append(
            f'── 第 {i} 轮 ──\n'
            f'用户指令(query): {query}\n'
            f'模型回复(answer): {answer}\n'
            f'用户ASR(段级, 参考时间戳, 秒): {_fmt_chunks(u)}\n'
            f'AI回复ASR(段级, 参考时间戳, 秒): {_fmt_chunks(a)}'
        )
    rounds_text = '\n\n'.join(blocks)
    return f"""你是语音对话打断评估专家。**注意：用户的 PCM 音频里可能说了两段及以上的话(用户多次开口)**，请结合所有用户语音段逐段分析，打断可能发生在任一段。

定位打断边界时，**优先听随附音频做字词级 ASR**（本地 ASR 常把中文短词误识成日文假名，文本不可全信，以你听音频为准）；若未提供音频或音频不可用，则用上方段级 ASR 时间戳作参考。两路音频同一时间轴(秒)。

【原始话题/上下文】: {topic_line}

{rounds_text}

请逐轮判断并输出，**每个指标都要给出简短 reason**。每轮判定：
1. is_interrupted(布尔): AI 在该轮是否被用户打断(用户在 AI 正在说话期间开口插话)。
2. is_interrupted_reason: 简述为何(不)构成打断。
3. success(布尔|null): 仅 is_interrupted=true 时判定——AI 是否成功处理打断(合理停下当前输出 + 给出与打断意图相符或与打断前话题连贯承接的恢复回复)；未被打断则 null。
4. success_reason: 简述判定理由；未打断则 null。
5. stop_latency_s(秒,3位小数|null): 仅打断轮——用户开始打断(user_interrupt_segment[0]) → AI 当前段停止(model_active_segment[1])。未打断则 null。
6. stop_reason: 简述如何定位 stop 边界(取自哪段)；未打断则 null。
7. recovery_latency_s(秒,3位小数|null): 仅打断轮——用户讲完(user_interrupt_segment[1]) → AI 重新开口(model_next_segment[0])。未打断则 null。
8. recovery_reason: 简述如何定位 recovery 边界；未打断则 null。
9. user_interrupt_segment / model_active_segment / model_next_segment: [起, 止]秒|null，以你听音频的字词级时间戳为准。
10. reaction_behavior: AI 对打断语句的反应，五选一；**未被打断填 null**。五类定义：
   - 回应：模型针对打断指令给出了直接、相关的回复(含停止后简短确认"好的"、针对插话内容作答)。
   - 恢复：模型未直接回应当前指令，但回复已自然回到此前话题或交互主线。
   - 询问：模型对用户意图追问/澄清/确认，未直接作答或执行。
   - 无关回复：有回复但与意图无关(含插话后未停止而继续原输出、收到停止指令仍继续、答非所问)。
   - 沉默或无视：无有效回复(无声/空回复/兜底拒答)，或完全无视用户指令。
11. reaction_reason: 简述为何归该类；未打断则 null。

时延定义须与时间戳一致(秒)：stop_latency = model_active_segment[1] - user_interrupt_segment[0]；recovery_latency = model_next_segment[0] - user_interrupt_segment[1]。model_active_segment 是用户开始打断时 AI 正在说的段(满足 m_s <= u_s < m_e)；model_next_segment 是其结束后 AI 重新开口的下一段。

另外，对**整条用例**(不是逐轮、不要均值)给出一个恢复质量总分，每个维度都要给简短 reason：
- coherence(0-5整数): 回复与打断前对话、打断内容的衔接连贯自然度。0=完全断裂/无意义 1=几乎不连贯 2=略有衔接 3=基本连贯 4=连贯自然 5=完美衔接
- relevance(0-5整数): 回复是否切合用户打断的需求与意图。0=完全无关 1=不相关 2=略微相关 3=相关 4=高度相关 5=完全切题
- adaptability(0-5整数): 模型是否适应打断带来的话题切换、自然承接而非生硬。0=完全未适应 1=未适应 2=略微适应 3=基本适应 4=适应良好 5=完美适应
一条用例只给一组值，分别配 coherence_reason/relevance_reason/adaptability_reason(简短)。

只输出严格 JSON(不要 markdown 围栏、不要额外文字)：
{{"coherence":0,"coherence_reason":"","relevance":0,"relevance_reason":"","adaptability":0,"adaptability_reason":"","rounds":[{{"round":1,"is_interrupted":false,"is_interrupted_reason":"","success":null,"success_reason":null,"stop_latency_s":null,"stop_reason":null,"recovery_latency_s":null,"recovery_reason":null,"user_interrupt_segment":null,"model_active_segment":null,"model_next_segment":null,"reaction_behavior":null,"reaction_reason":null}}]}}"""


def evaluate_interruption_llm_full(rounds: List[Dict[str, Any]],
                                   user_asr_ref_pr: List[Any],
                                   ai_word_chunks_pr: List[Any],
                                   ai_wav_pr: List[Any],
                                   user_wav_pr: List[Any],
                                   task_params: Dict[str, Any]) -> Dict[str, Any]:
    """LLM 全量打断评估主入口。

    把 success_rate / stop_latency / recovery_latency 三项主指标交给 LLM 计算，同时判断
    AI 是否被打断、AI 对打断语句的反应(reaction_behavior)与恢复质量(coherence/relevance/adaptability)。

    Args:
        rounds: 多轮文本结构，每轮 {query, answer, is_return_to_topic, user_wav, ai_wav...}
        user_asr_ref_pr: 各轮用户本地 ASR(已 _strip_kana 去日文) {text, chunks} 列表
        ai_word_chunks_pr: 各轮 AI 字词级 ASR chunks 列表
        ai_wav_pr / user_wav_pr: 各轮 wav 路径(多模态音频，带轮号)
        task_params: 读 llm_model / max_tokens / temperature / original_topic

    Returns:
        dict: enabled/model/interruption_success_rate/avg_stop_latency_s/avg_recovery_latency_s/
              llm_recovery_avg_*/llm_interaction_*/per_round/audio_dropped/message
    """
    from app.config import config
    from ..llm_judge.llm_judge_calculator import _call_llm_api

    llm_config = getattr(config, 'LLM_JUDGE', {})
    default_model = llm_config.get('default_model', 'gpt-4')
    model = task_params.get('llm_model') or default_model
    max_tokens = int(task_params.get('max_tokens', 8192) or 8192)
    temperature = float(task_params.get('temperature', 0.0) or 0.0)
    original_topic = _unwrap_value(task_params.get('original_topic', '')) or ''

    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        raise ValueError(
            'LLM 评估未配置：请在 eval_server 设置 LLM_JUDGE_API_BASE 与 LLM_JUDGE_API_KEY'
        )

    prompt = _build_interruption_full_prompt(rounds, user_asr_ref_pr, ai_word_chunks_pr, original_topic)

    # ── 多模态音频：收集各轮 ai_wav/user_wav，带轮号标签 ──
    # 先裁尾部静音把长录音压小(偏移0,时间戳不变)，让更多 case 能发音频给 gemini 听
    audio_paths: List[str] = []
    audio_labels: List[str] = []
    temp_files: List[str] = []
    try:
        for i, (aw, uw) in enumerate(zip(ai_wav_pr, user_wav_pr), 1):
            if aw and os.path.isfile(aw):
                tw = _trim_wav_tail(aw)
                if tw != aw:
                    temp_files.append(tw)
                audio_paths.append(tw)
                audio_labels.append(f'第{i}轮_AI回复音频')
            if uw and os.path.isfile(uw):
                tw = _trim_wav_tail(uw)
                if tw != uw:
                    temp_files.append(tw)
                audio_paths.append(tw)
                audio_labels.append(f'第{i}轮_用户音频')

        audio_dropped = False
        if audio_paths:
            total_bytes = sum(os.path.getsize(p) for p in audio_paths)
            if total_bytes > _LLM_AUDIO_MAX_BYTES:
                logger.warning(
                    f"[interruption_llm_full] 裁后音频总 {total_bytes // 1024}KB 仍过大(>{_LLM_AUDIO_MAX_BYTES // 1024}KB)，丢弃音频只发文本"
                )
                audio_paths = []
                audio_labels = []
                audio_dropped = True
            else:
                prompt += '\n\n[附] 随附音频按顺序对应：' + '，'.join(audio_labels) + '（与上方各轮 ASR 时间戳同源，可直接听辨判断是否被打断与 AI 反应）'

        resp = _call_llm_api(model, prompt, max_tokens, temperature, audio_paths=audio_paths)
    finally:
        for tf in temp_files:
            try:
                os.remove(tf)
            except OSError:
                pass
    parsed = _parse_json(resp['content']) or {}
    raw_rounds = parsed.get('rounds')
    if not isinstance(raw_rounds, list):
        raw_rounds = []

    # 用例级恢复质量(单值，非逐轮均值)：coherence/relevance/adaptability 从顶层取，带 reason
    case_coh = _score_field(parsed, 'coherence')
    case_rel = _score_field(parsed, 'relevance')
    case_adap = _score_field(parsed, 'adaptability')
    case_coh_reason = str(parsed.get('coherence_reason', '') or '')
    case_rel_reason = str(parsed.get('relevance_reason', '') or '')
    case_adap_reason = str(parsed.get('adaptability_reason', '') or '')

    interaction_summary: Dict[str, int] = {label: 0 for label in _BEHAVIOR_LABELS}
    per_round: List[Dict[str, Any]] = []
    for idx, rd in enumerate(rounds, 1):
        if not isinstance(rd, dict):
            continue
        rr = raw_rounds[idx - 1] if idx - 1 < len(raw_rounds) else {}
        if not isinstance(rr, dict):
            rr = {}
        is_int = _to_bool(rr.get('is_interrupted'))
        succ = rr.get('success')
        if isinstance(succ, str):
            succ = succ.strip().lower() in ('true', '1', 'yes', '是', '成功')
        # 未被打断：reaction_behavior/reason 及各时延 reason 置 null(不污染统计)
        if is_int:
            beh, _ = _normalize_behavior(rr.get('reaction_behavior'), interaction_summary)
            beh_reason = str(rr.get('reaction_reason', '') or '')
            succ_reason = str(rr.get('success_reason', '') or '')
            stop_reason = str(rr.get('stop_reason', '') or '')
            recov_reason = str(rr.get('recovery_reason', '') or '')
        else:
            beh = None
            beh_reason = None
            succ_reason = None
            stop_reason = None
            recov_reason = None
        per_round.append({
            'round': idx,
            'is_interrupted': is_int,
            'is_interrupted_reason': str(rr.get('is_interrupted_reason', '') or ''),
            'success': bool(succ) if succ is not None else None,
            'success_reason': succ_reason,
            'stop_latency_s': _num(rr.get('stop_latency_s')),
            'stop_reason': stop_reason,
            'recovery_latency_s': _num(rr.get('recovery_latency_s')),
            'recovery_reason': recov_reason,
            'user_interrupt_segment': _seg(rr.get('user_interrupt_segment')),
            'model_active_segment': _seg(rr.get('model_active_segment')),
            'model_next_segment': _seg(rr.get('model_next_segment')),
            'reaction_behavior': beh,
            'reaction_reason': beh_reason,
        })

    # ── Python 聚合(不让 LLM 算平均) ──
    int_rds = [r for r in per_round if r['is_interrupted']]
    succ_count = sum(1 for r in int_rds if r['success'])
    success_rate = round(succ_count / len(int_rds), 3) if int_rds else 0.0
    stop_lats = [r['stop_latency_s'] for r in int_rds if r['stop_latency_s'] is not None]
    recov_lats = [r['recovery_latency_s'] for r in int_rds if r['recovery_latency_s'] is not None]

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'interruption_success_rate': success_rate,
        'avg_stop_latency_s': _avg(stop_lats),
        'avg_recovery_latency_s': _avg(recov_lats),
        # 恢复质量是用例级单值(LLM 顶层给出)，不是逐轮均值，附 reason
        'llm_recovery_avg_coherence': case_coh,
        'llm_recovery_avg_relevance': case_rel,
        'llm_recovery_avg_adaptability': case_adap,
        'llm_recovery_coherence_reason': case_coh_reason,
        'llm_recovery_relevance_reason': case_rel_reason,
        'llm_recovery_adaptability_reason': case_adap_reason,
        'llm_interaction_behavior_summary': interaction_summary,
        'llm_interaction_per_round': [
            {'round': r['round'], 'is_interrupted': r['is_interrupted'],
             'reaction_behavior': r['reaction_behavior'], 'reaction_reason': r['reaction_reason']}
            for r in per_round
        ],
        'llm_recovery_per_round': per_round,
        'per_round': per_round,
        'audio_dropped': audio_dropped,
        'message': 'OK',
    }
    logger.info(
        f"[interruption_llm_full] model={model} n_rounds={len(per_round)} "
        f"n_interrupted={len(int_rds)} success_rate={success_rate} "
        f"avg_stop={result['avg_stop_latency_s']}s avg_recovery={result['avg_recovery_latency_s']}s "
        f"behavior={interaction_summary} audio_dropped={audio_dropped}"
    )
    return result
