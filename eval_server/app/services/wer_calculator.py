import re
import numpy as np
import json

try:
    import meeteval
    MEETEVAL_AVAILABLE = True
except ImportError:
    MEETEVAL_AVAILABLE = False

from ..utils.normalizer import normalize_text, normalize_stm_text, normalize_rttm_speaker

def levenshtein_distance(ref, hyp):
    ref_len = len(ref)
    hyp_len = len(hyp)
    
    dp = np.zeros((ref_len + 1, hyp_len + 1), dtype=int)
    
    for i in range(ref_len + 1):
        dp[i][0] = i
    for j in range(hyp_len + 1):
        dp[0][j] = j
    
    for i in range(1, ref_len + 1):
        for j in range(1, hyp_len + 1):
            if ref[i-1] == hyp[j-1]:
                cost = 0
            else:
                cost = 1
            dp[i][j] = min(dp[i-1][j] + 1, dp[i][j-1] + 1, dp[i-1][j-1] + cost)
    
    return dp[ref_len][hyp_len]

def split_sentences(text):
    sentence_endings = re.compile(r'[。.!?]')
    
    sentences = []
    start = 0
    
    for match in sentence_endings.finditer(text):
        sentence = text[start:match.end()].strip()
        if sentence:
            sentences.append(sentence)
        start = match.end()
    
    last_sentence = text[start:].strip()
    if last_sentence:
        sentences.append(last_sentence)
    
    return sentences

def split_text(text):
    zh_pattern = re.compile(r'[\u4e00-\u9fa5]')
    en_pattern = re.compile(r'[a-zA-Z]')
    num_pattern = re.compile(r'[0-9]')
    
    chars = []
    zh_chars = []
    en_chars = []
    num_chars = []
    
    i = 0
    while i < len(text):
        char = text[i]
        if zh_pattern.match(char):
            chars.append(char)
            zh_chars.append(char)
            i += 1
        elif en_pattern.match(char):
            word = ''
            while i < len(text) and en_pattern.match(text[i]):
                word += text[i]
                i += 1
            chars.append(word)
            en_chars.append(word)
        elif num_pattern.match(char):
            chars.append(char)
            num_chars.append(char)
            i += 1
        else:
            i += 1
    
    if not chars and text:
        chars = [text]
    
    return chars, zh_chars, en_chars

def parse_stm_from_json(stm_data, normalize=False):
    """
    从 JSON 格式解析 STM 内容

    支持两种 JSON 格式:
    1. {"text": "stm content string", "json": "[...]"}
    2. 直接传入 STM 字符串

    Args:
        stm_data: JSON对象 或 STM 字符串
        normalize: 是否在转换时对文本进行正则化（仅对 json 格式有效）

    Returns:
        str: STM 格式字符串
    """
    if not stm_data:
        return ""

    if isinstance(stm_data, dict):
        if 'text' in stm_data:
            text_content = stm_data['text']
            if normalize:
                text_content = normalize_text(text_content)
            return text_content
        elif 'json' in stm_data:
            json_data = stm_data['json']
            if isinstance(json_data, str):
                json_data = json.loads(json_data)

            lines = []
            for item in json_data:
                file_id = item.get('file_id', 'unknown')
                channel = item.get('channel', '1')
                speaker = item.get('speaker', 'unknown')
                start = item.get('start', 0.0)
                end = item.get('end', 0.0)
                text = item.get('text', '')

                if normalize:
                    text = normalize_text(text)

                line = f"{file_id} {channel} {speaker} {start} {end} <o> {text}"
                lines.append(line)

            return '\n'.join(lines)

    if isinstance(stm_data, str):
        return stm_data

    return str(stm_data)


def parse_stm_string_to_json(stm_content):
    """
    将 STM 字符串解析为 JSON 列表

    Args:
        stm_content (str): STM 格式字符串

    Returns:
        list: JSON 列表，每个元素包含 file_id, channel, speaker, start, end, text
    """
    if not stm_content:
        return []

    json_list = []
    for line in stm_content.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith(';'):
            continue
        parts = line.split()
        if len(parts) >= 6:
            file_id = parts[0]
            channel = parts[1]
            speaker = parts[2]
            start = float(parts[3])
            end = float(parts[4])
            text = ' '.join(parts[5:])

            json_list.append({
                'file_id': file_id,
                'channel': channel,
                'speaker': speaker,
                'start': start,
                'end': end,
                'text': text
            })

    return json_list


def normalize_stm_session_id(stm_content, ref_stm_content=None):
    """
    统一 STM 内容中的 session_id

    Args:
        stm_content (str): 要处理的 STM 内容
        ref_stm_content (str): 参考 STM 内容，用于提取目标 session_id

    Returns:
        str: 统一后的 STM 内容
    """
    if not stm_content:
        return stm_content

    target_session_id = None
    if ref_stm_content:
        lines = ref_stm_content.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith(';'):
                parts = line.split()
                if len(parts) >= 1:
                    target_session_id = parts[0]
                    break

    if not target_session_id:
        lines = stm_content.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith(';'):
                parts = line.split()
                if len(parts) >= 1:
                    target_session_id = parts[0]
                    break

    if not target_session_id:
        return stm_content

    normalized_lines = []
    for line in stm_content.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith(';'):
            normalized_lines.append(line)
            continue

        parts = line.split()
        if len(parts) >= 6:
            parts[0] = target_session_id
            normalized_lines.append(' '.join(parts))
        else:
            normalized_lines.append(line)

    return '\n'.join(normalized_lines)


def parse_rttm_from_json(rttm_data):
    """
    从 JSON 格式解析 RTTM 内容

    支持两种 JSON 格式:
    1. {"text": "rttm content string", "json": "[...]"}
    2. 直接传入 RTTM 字符串

    Args:
        rttm_data: JSON对象 或 RTTM 字符串

    Returns:
        str: RTTM 格式字符串
    """
    if not rttm_data:
        return ""

    if isinstance(rttm_data, dict):
        if 'text' in rttm_data:
            return rttm_data['text']
        elif 'json' in rttm_data:
            json_data = rttm_data['json']
            if isinstance(json_data, str):
                json_data = json.loads(json_data)

            lines = []
            for item in json_data:
                speaker = item.get('speaker', 'unknown')
                start = item.get('start', 0.0)
                duration = item.get('duration', 0.0)

                line = f"SPEAKER unknown 1 {start} {duration} <NA> <NA> {speaker} <NA>"
                lines.append(line)

            return '\n'.join(lines)

    if isinstance(rttm_data, str):
        return rttm_data

    return str(rttm_data)


def parse_asr_result_from_json(asr_data):
    """
    从 ASR 结果 JSON 解析文本内容

    Args:
        asr_data: ASR JSON 数据

    Returns:
        str: 文本内容
    """
    if not asr_data:
        return ""

    if isinstance(asr_data, str):
        try:
            asr_data = json.loads(asr_data)
        except:
            return asr_data

    if isinstance(asr_data, list):
        texts = []
        for item in asr_data:
            if isinstance(item, dict):
                text = item.get('text', '')
                if text:
                    texts.append(text)
        return ' '.join(texts)

    if isinstance(asr_data, dict):
        if 'text' in asr_data:
            return asr_data['text']

    return str(asr_data)


def calculate_wer(ref_text, hyp_text, source_lang, target_lang, translate_direct, normalize=False):
    if normalize:
        ref_text = normalize_text(ref_text)
        hyp_text = normalize_text(hyp_text)

    if MEETEVAL_AVAILABLE:
        try:
            wer_result = meeteval.wer.wer.siso.siso_word_error_rate(
                reference=ref_text,
                hypothesis=hyp_text
            )
            
            ref_chars, ref_zh, ref_en = split_text(ref_text)
            hyp_chars, hyp_zh, hyp_en = split_text(hyp_text)
            
            zh_errors = levenshtein_distance(ref_zh, hyp_zh)
            zh_wer = zh_errors / len(ref_zh) if len(ref_zh) > 0 else 0.0
            
            en_errors = levenshtein_distance(ref_en, hyp_en)
            en_wer = en_errors / len(ref_en) if len(ref_en) > 0 else 0.0
            
            error_rate = float(wer_result.error_rate) if wer_result.error_rate is not None else None
            
            return {
                'wer': round(error_rate, 4) if error_rate is not None else None,
                'wer_zh': round(zh_wer, 4),
                'wer_en': round(en_wer, 4),
                'errors': wer_result.errors,
                'length': wer_result.length,
                'insertions': wer_result.insertions,
                'deletions': wer_result.deletions,
                'substitutions': wer_result.substitutions,
                'source_lang': source_lang,
                'target_lang': target_lang,
                'translate_direct': translate_direct
            }
        except Exception as e:
            pass
    
    ref_chars, ref_zh, ref_en = split_text(ref_text)
    hyp_chars, hyp_zh, hyp_en = split_text(hyp_text)
    
    total_errors = levenshtein_distance(ref_chars, hyp_chars)
    total_wer = total_errors / len(ref_chars) if len(ref_chars) > 0 else 0.0
    
    zh_errors = levenshtein_distance(ref_zh, hyp_zh)
    zh_wer = zh_errors / len(ref_zh) if len(ref_zh) > 0 else 0.0
    
    en_errors = levenshtein_distance(ref_en, hyp_en)
    en_wer = en_errors / len(ref_en) if len(ref_en) > 0 else 0.0
    
    return {
        'wer': round(total_wer, 4),
        'wer_zh': round(zh_wer, 4),
        'wer_en': round(en_wer, 4),
        'source_lang': source_lang,
        'target_lang': target_lang,
        'translate_direct': translate_direct
    }


def calculate_ser(ref_text, hyp_text, source_lang, target_lang, translate_direct, normalize=False):
    if normalize:
        ref_text = normalize_text(ref_text)
        hyp_text = normalize_text(hyp_text)

    ref_sentences = split_sentences(ref_text)
    hyp_sentences = split_sentences(hyp_text)
    
    total_sentences = len(ref_sentences)
    error_sentences = 0
    
    for i in range(max(total_sentences, len(hyp_sentences))):
        if i < len(ref_sentences) and i < len(hyp_sentences):
            ref_sent = ref_sentences[i]
            hyp_sent = hyp_sentences[i]
            
            sent_wer = calculate_wer(ref_sent, hyp_sent, source_lang, target_lang, translate_direct, normalize=False)
            if sent_wer['wer'] > 0:
                error_sentences += 1
        else:
            error_sentences += 1
    
    ser = error_sentences / total_sentences if total_sentences > 0 else 0.0
    
    return {
        'ser': round(ser, 4),
        'total_sentences': total_sentences,
        'error_sentences': error_sentences,
        'source_lang': source_lang,
        'target_lang': target_lang,
        'translate_direct': translate_direct
    }


def calculate_cpwer(ref_stm, hyp_stm, source_lang, target_lang, translate_direct, normalize=False):
    if not MEETEVAL_AVAILABLE:
        return {
            'cpwer': None,
            'error': 'meeteval library not installed',
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct
        }

    try:
        if isinstance(ref_stm, dict):
            ref_stm = parse_stm_from_json(ref_stm, normalize=normalize)
        elif isinstance(ref_stm, str) and normalize:
            ref_json = parse_stm_string_to_json(ref_stm)
            ref_stm = parse_stm_from_json({'json': ref_json}, normalize=True)

        if isinstance(hyp_stm, dict):
            hyp_stm = parse_stm_from_json(hyp_stm, normalize=normalize)
        elif isinstance(hyp_stm, str) and normalize:
            hyp_json = parse_stm_string_to_json(hyp_stm)
            hyp_stm = parse_stm_from_json({'json': hyp_json}, normalize=True)

        if isinstance(ref_stm, str):
            ref_stm = normalize_stm_session_id(ref_stm)
        if isinstance(hyp_stm, str):
            hyp_stm = normalize_stm_session_id(hyp_stm, ref_stm)

        ref_data = meeteval.io.STM.parse(ref_stm)
        hyp_data = meeteval.io.STM.parse(hyp_stm)
        
        wer_result = meeteval.wer.cpwer(ref_data, hyp_data)
        
        combined = meeteval.wer.combine_error_rates(wer_result)
        
        error_rate = float(combined.error_rate) if combined.error_rate is not None else None
        
        return {
            'cpwer': round(error_rate, 4) if error_rate is not None else None,
            'errors': combined.errors,
            'length': combined.length,
            'insertions': combined.insertions,
            'deletions': combined.deletions,
            'substitutions': combined.substitutions,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct
        }
    except Exception as e:
        return {
            'cpwer': None,
            'error': str(e),
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct
        }


def calculate_tcpwer(ref_stm, hyp_stm, source_lang, target_lang, translate_direct, collar=0.0, normalize=False):
    if not MEETEVAL_AVAILABLE:
        return {
            'tcpwer': None,
            'error': 'meeteval library not installed',
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct
        }

    try:
        if isinstance(ref_stm, dict):
            ref_stm = parse_stm_from_json(ref_stm, normalize=normalize)
        elif isinstance(ref_stm, str) and normalize:
            ref_json = parse_stm_string_to_json(ref_stm)
            ref_stm = parse_stm_from_json({'json': ref_json}, normalize=True)

        if isinstance(hyp_stm, dict):
            hyp_stm = parse_stm_from_json(hyp_stm, normalize=normalize)
        elif isinstance(hyp_stm, str) and normalize:
            hyp_json = parse_stm_string_to_json(hyp_stm)
            hyp_stm = parse_stm_from_json({'json': hyp_json}, normalize=True)

        if isinstance(ref_stm, str):
            ref_stm = normalize_stm_session_id(ref_stm)
        if isinstance(hyp_stm, str):
            hyp_stm = normalize_stm_session_id(hyp_stm, ref_stm)

        from meeteval.wer.wer import time_constrained
        wer_result = time_constrained.tcp_word_error_rate([ref_stm], [hyp_stm], collar=collar)
        
        error_rate = float(wer_result.error_rate) if wer_result.error_rate is not None else None
        
        return {
            'tcpwer': round(error_rate, 4) if error_rate is not None else None,
            'errors': wer_result.errors,
            'length': wer_result.length,
            'insertions': wer_result.insertions,
            'deletions': wer_result.deletions,
            'substitutions': wer_result.substitutions,
            'collar': collar,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct
        }
    except Exception as e:
        return {
            'tcpwer': None,
            'error': str(e),
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct
        }


def calculate_stm_wer(ref_stm, hyp_stm, source_lang, target_lang, translate_direct, normalize=False):
    if not MEETEVAL_AVAILABLE:
        return {
            'stm_wer': None,
            'error': 'meeteval library not installed',
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct
        }

    try:
        if isinstance(ref_stm, dict):
            ref_stm = parse_stm_from_json(ref_stm, normalize=normalize)
        elif isinstance(ref_stm, str) and normalize:
            ref_json = parse_stm_string_to_json(ref_stm)
            ref_stm = parse_stm_from_json({'json': ref_json}, normalize=True)

        if isinstance(hyp_stm, dict):
            hyp_stm = parse_stm_from_json(hyp_stm, normalize=normalize)
        elif isinstance(hyp_stm, str) and normalize:
            hyp_json = parse_stm_string_to_json(hyp_stm)
            hyp_stm = parse_stm_from_json({'json': hyp_json}, normalize=True)

        if isinstance(ref_stm, str):
            ref_stm = normalize_stm_session_id(ref_stm)
        if isinstance(hyp_stm, str):
            hyp_stm = normalize_stm_session_id(hyp_stm, ref_stm)

        from meeteval.wer.wer import cp
        wer_result = cp.cp_word_error_rate([ref_stm], [hyp_stm])
        
        error_rate = float(wer_result.error_rate) if wer_result.error_rate is not None else None
        
        return {
            'stm_wer': round(error_rate, 4) if error_rate is not None else None,
            'errors': wer_result.errors,
            'length': wer_result.length,
            'insertions': wer_result.insertions,
            'deletions': wer_result.deletions,
            'substitutions': wer_result.substitutions,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct
        }
    except Exception as e:
        return {
            'stm_wer': None,
            'error': str(e),
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct
        }


def calculate_multi_round_wer(
    rounds: list,
    source_lang: str = 'zh',
    target_lang: str = 'en',
    normalize: bool = True,
) -> dict:
    """
    Multi-round WER aggregation.

    Args:
        rounds: List of per-round data, each with 'reference' and 'hypothesis' keys.
        source_lang: Source language code.
        target_lang: Target language code.
        normalize: Whether to normalize text before computing.

    Returns:
        Aggregated WER result with per-round breakdown.
    """
    per_round = []
    total_errors = 0
    total_length = 0

    for idx, round_data in enumerate(rounds):
        ref = round_data.get('reference', '')
        hyp = round_data.get('hypothesis', '')

        result = calculate_wer(
            ref_text=ref,
            hyp_text=hyp,
            source_lang=source_lang,
            target_lang=target_lang,
            translate_direct=None,
            normalize=normalize,
        )

        round_info = {
            'round': idx,
            'wer': result.get('wer'),
            'errors': result.get('errors', 0),
            'length': result.get('length', 0),
            'insertions': result.get('insertions', 0),
            'deletions': result.get('deletions', 0),
            'substitutions': result.get('substitutions', 0),
        }
        per_round.append(round_info)

        total_errors += round_info['errors']
        total_length += round_info['length']

    weighted_wer = total_errors / total_length if total_length > 0 else 0
    simple_wer = sum(
        (r['wer'] for r in per_round if r['wer'] is not None), 0
    ) / len(per_round) if per_round else 0

    return {
        'wer': round(weighted_wer, 4),
        'per_round': per_round,
        'aggregated': {
            'total_errors': total_errors,
            'total_length': total_length,
            'weighted_wer': round(weighted_wer, 4),
            'simple_wer': round(simple_wer, 4),
            'round_count': len(per_round),
        },
        'source_lang': source_lang,
        'target_lang': target_lang,
    }
