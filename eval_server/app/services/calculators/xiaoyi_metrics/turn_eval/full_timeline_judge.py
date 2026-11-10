"""Full-case takeover judge: semantic boundaries remote, validation/arithmetic local."""
import copy
import json
import logging
import math
from pathlib import Path

LABELS = ('接管', '误接管', '未接管', '误接管-正常接管', '误接管-未接管')
FALSE_TAKEOVER_LABELS = ('误接管', '误接管-正常接管', '误接管-未接管')


def build_input(user_chunks, model_chunks, rounds):
    words = []
    for prefix, speaker, chunks in [('U', 'user', user_chunks), ('M', 'model', model_chunks)]:
        for i, chunk in enumerate(chunks or []):
            ts = chunk.get('timestamp')
            if not isinstance(ts, (list, tuple)) or len(ts) != 2:
                raise ValueError('Missing ASR word interval')
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in ts) or ts[1] < ts[0]:
                raise ValueError('Invalid ASR word interval')
            words.append(dict(word_id=f'{prefix}{i:05d}', speaker=speaker, text=str(chunk.get('text') or ''), start=ts[0], end=ts[1]))
    if not any(w['speaker'] == 'model' for w in words):
        raise ValueError('Model ASR absent; absence alone cannot prove silence')
    if not any(w['speaker'] == 'user' for w in words):
        raise ValueError('User ASR missing; cannot align scheduled questions')
    scheduled = []
    for i, rd in enumerate(rounds):
        q = rd.get('query') or ''
        if isinstance(q, dict):
            q = q.get('text') or ''
        scheduled.append(dict(round_number=i, script_text=str(q)))
    if not scheduled:
        raise ValueError('Scheduled rounds required')
    return dict(full_word_timeline=sorted(words, key=lambda w: (w['start'], w['end'], w['word_id'])), scheduled_rounds=scheduled)


def validate_and_derive(packet, parsed):
    if not isinstance(parsed, dict) or not isinstance(parsed.get('rounds'), list):
        raise ValueError('Judge must return rounds array')
    rows = parsed['rounds']
    if any(not isinstance(r, dict) or type(r.get('round_number')) is not int for r in rows):
        raise ValueError('Round number must be an integer')
    expected = [r['round_number'] for r in packet['scheduled_rounds']]
    if [r.get('round_number') for r in rows if isinstance(r, dict)] != expected or len(rows) != len(expected):
        raise ValueError('Missing, duplicated or reordered scheduled round')
    streams = {s: sorted([w for w in packet['full_word_timeline'] if w['speaker'] == s], key=lambda w: (w['start'], w['end'], w['word_id'])) for s in ('user', 'model')}
    positions = {s: {w['word_id']: i for i, w in enumerate(ws)} for s, ws in streams.items()}
    used = {'user': set(), 'model': set()}
    last_user = -1
    turns = []
    trigger_ranges = []
    for row in rows:
        label = row.get('classification')
        if label not in LABELS:
            raise ValueError('Uncertain classification; do not convert missing evidence to success')
        for key in ('reason', 'alignment_reason', 'response_start_reason'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError('Per-round evidence reasons required: ' + key)

        def span(speaker, first, last):
            if first not in positions[speaker] or last not in positions[speaker]:
                raise ValueError('Unknown word ID / wrong speaker')
            a, b = positions[speaker][first], positions[speaker][last]
            if b < a:
                raise ValueError('Reversed word span')
            ws = streams[speaker][a:b + 1]
            ids = {w['word_id'] for w in ws}
            if used[speaker] & ids:
                raise ValueError('Cross-round word reuse: ' + speaker)
            used[speaker].update(ids)
            return ws, a, b

        uw, ua, ub = span('user', row.get('user_start_word_id'), row.get('user_end_word_id'))
        if ua <= last_user:
            raise ValueError('User rounds must be ordered and disjoint')
        last_user = ub
        if label in ('未接管', '误接管-未接管'):
            if row.get('response_start_word_id') is not None or row.get('response_end_word_id') is not None:
                raise ValueError('No-takeover must not claim a reply span')
            mw = []
            if label == '误接管-未接管':
                span('model', row.get('false_takeover_start_word_id'), row.get('false_takeover_end_word_id'))
        else:
            mw, _, _ = span('model', row.get('response_start_word_id'), row.get('response_end_word_id'))
            if mw[0]['start'] < uw[0]['start']:
                raise ValueError('Reply predates this user turn')
            if label == '误接管-正常接管':
                span('model', row.get('false_takeover_start_word_id'), row.get('false_takeover_end_word_id'))
        triggers = row.get('false_takeover_triggers')
        if label in FALSE_TAKEOVER_LABELS:
            if not isinstance(triggers, list) or not triggers:
                raise ValueError('False takeover requires trigger events')
        elif triggers != []:
            raise ValueError('Non false-takeover rounds must have empty triggers')
        normalized_triggers = []
        for trigger in triggers or []:
            if not isinstance(trigger, dict):
                raise ValueError('Trigger must be an object')
            if not isinstance(trigger.get('reason'), str) or not trigger['reason'].strip():
                raise ValueError('Trigger reason required')
            first, last = trigger.get('start_word_id'), trigger.get('end_word_id')
            if first not in positions['model'] or last not in positions['model']:
                raise ValueError('Unknown model word ID / wrong speaker in trigger')
            a, b = positions['model'][first], positions['model'][last]
            if b < a:
                raise ValueError('Reversed trigger word span')
            trigger_range = (a, b)
            if any(not (b < x or a > y) for x, y in trigger_ranges):
                raise ValueError('Trigger spans must not overlap')
            if streams['model'][b]['end'] <= uw[0]['start']:
                raise ValueError('Trigger predates this user turn')
            trigger_ranges.append(trigger_range)
            normalized_triggers.append(dict(start_word_id=first, end_word_id=last, reason=trigger['reason'].strip()))
        if label in FALSE_TAKEOVER_LABELS and row.get('false_takeover_start_word_id') != normalized_triggers[0]['start_word_id']:
            raise ValueError('Initial false takeover must match first trigger')
        user_text = ''.join(w['text'] for w in uw)
        model_text = ''.join(w['text'] for w in mw)
        turn = dict(turn_index=len(turns) + 1, round_number=row['round_number'], classification=label,
                    user_start_s=uw[0]['start'], user_end_s=uw[-1]['end'], ai_start_s=mw[0]['start'] if mw else None,
                    ai_end_s=mw[-1]['end'] if mw else None, has_ai_reply=bool(mw),
                    false_takeover=dict(false_takeover=int(label in FALSE_TAKEOVER_LABELS), reason=row['reason'], evidence=dict(user_full_utterance=user_text)),
                    alignment=dict(user_start_word_id=uw[0]['word_id'], user_end_word_id=uw[-1]['word_id'], reason=row['alignment_reason']),
                    false_takeover_triggers=normalized_triggers, false_takeover_trigger_count=len(normalized_triggers),
                    result=f'{label}；误接管次数{len(normalized_triggers)}',
                    response_start_word_id=mw[0]['word_id'] if mw else None, response_end_word_id=mw[-1]['word_id'] if mw else None,
                    response_start_reason=row['response_start_reason'], tor=None, takeover_judge=None, takeover_latency=None, reply_quality=None)
        if label in ('接管', '误接管-正常接管'):
            quality = row.get('reply_quality')
            if not isinstance(quality, dict) or isinstance(quality.get('score'), bool) or not isinstance(quality.get('score'), int) or not 1 <= quality['score'] <= 5 or not isinstance(quality.get('reason'), str) or not quality['reason'].strip():
                raise ValueError('Normal takeover requires quality score 1..5 and reason')
            latency = round((mw[0]['start'] - uw[-1]['end']) * 1000, 1)
            turn.update(tor=dict(tor=1, n_words=len(mw), duration=round(mw[-1]['end']-mw[0]['start'], 3), hit_words=[dict(text=w['text'], timestamp=[w['start'], w['end']]) for w in mw], message='OK'),
                        takeover_judge=dict(takeover=1, reason=row['reason']),
                        takeover_latency=dict(takeover_latency_ms=latency, user_last_word_end_ms=uw[-1]['end']*1000, ai_first_word_start_ms=mw[0]['start']*1000, message='word ASR: model first start minus user last end'),
                        reply_quality=dict(copy.deepcopy(quality), user_text=user_text, ai_text=model_text, message='OK'))
        turns.append(turn)
    return turns


_LOGGER = logging.getLogger(__name__)
_CLOSERS = {'{': '}', '[': ']'}


class TurnEvalOutputError(ValueError):
    """Invalid output after bounded retries; raw evidence is kept off platform data."""

    def __init__(self, message, attempts):
        super().__init__(message)
        self.attempts = attempts


def _remove_trailing_commas(content):
    """Remove only commas before ]/} outside JSON strings; never alter values."""
    output, in_string, escaped, removed = [], False, False, 0
    for index, char in enumerate(content):
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == ',':
            following = index + 1
            while following < len(content) and content[following] in ' \t\r\n':
                following += 1
            if following < len(content) and content[following] in ']}':
                removed += 1
                continue
        output.append(char)
    return ''.join(output), removed


def _repair_tail(content):
    """保守修复 JSON 尾部括号错误（仅严格解析失败后的兜底）。

    只处理结构层，绝不改动键、值、字符串内容：
    - 丢弃栈顶不匹配的多余闭合符（模型多写的 } / ]）
    - 丢弃根对象已闭合之后的尾部垃圾字符
    - 结尾缺闭合符时按括号平衡补上缺失的 ] / }

    修复产物仍必须通过 validate_and_derive 的严格语义复核，
    因此无法靠补括号蒙混任何编造内容。无法修复时返回 (None, False)。
    """
    out, stack, in_string, escaped, root_closed = [], [], False, False, False
    for ch in content:
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
        elif ch in '{[':
            stack.append(ch)
            out.append(ch)
        elif ch in '}]':
            expected = _CLOSERS.get(stack[-1]) if stack else None
            if expected == ch:
                stack.pop()
                out.append(ch)
                if not stack:
                    root_closed = True
            elif root_closed:
                continue  # 根对象已闭合，之后全是垃圾，丢弃
            else:
                continue  # 栈顶不匹配的多余闭合符，丢弃
        elif root_closed:
            continue
        else:
            out.append(ch)
    cleaned = ''.join(out)
    if stack:
        # 尾部可能夹带非 JSON 垃圾字符：从后往前去掉，再按平衡补闭合符
        end = len(cleaned)
        while end > 0 and cleaned[end - 1] not in '}"])0123456789':
            end -= 1
        cleaned = cleaned[:end] + ''.join(_CLOSERS[ch] for ch in reversed(stack))
    if cleaned == content:
        return None, False
    return cleaned, True


def _parse_judge_content(content):
    """解析 LLM 输出为 dict；优先严格解析，失败时依次做保守修复：
    去围栏 → 去尾逗号 → 尾部括号配平。修复不臆造键、ID、轮次、引号或内容。
    """
    if not isinstance(content, str):
        raise ValueError('Judge content must be a JSON string')
    content = content.strip()
    if content.startswith('```') and content.endswith('```') and '\n' in content:
        first, rest = content.split('\n', 1)
        if first.strip().lower() in ('```', '```json'):
            content = rest.rsplit('```', 1)[0].strip()

    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('Duplicate JSON key: ' + k)
            result[k] = v
        return result

    def reject_constant(value):
        raise ValueError('Non-finite JSON constant: ' + value)

    def load(value):
        parsed = json.loads(value, object_pairs_hook=pairs, parse_constant=reject_constant)
        if not isinstance(parsed, dict):
            raise ValueError('Judge JSON root must be an object')
        return parsed

    try:
        return load(content), dict(repaired=False, removed_trailing_commas=0, tail_repaired=False)
    except json.JSONDecodeError:
        repaired, removed = _remove_trailing_commas(content)
        if removed:
            try:
                return load(repaired), dict(repaired=True, removed_trailing_commas=removed, tail_repaired=False)
            except (json.JSONDecodeError, ValueError):
                pass
        cleaned, changed = _repair_tail(content)
        if changed:
            try:
                return load(cleaned), dict(repaired=True, removed_trailing_commas=0, tail_repaired=True)
            except (json.JSONDecodeError, ValueError):
                pass
        raise


def judge(packet, task_params, call=None):
    from app.services.calculators.xiaoyi_metrics.shared.llm_client import call_llm, resolve_model
    call = call or call_llm
    base_prompt = Path(__file__).with_name('full_timeline_prompt.txt').read_text(encoding='utf-8')
    request = json.dumps(packet, ensure_ascii=False)
    attempts, tokens_used = [], 0
    for attempt in range(2):
        attempt_prompt = base_prompt
        if attempt:
            attempt_prompt += ('\n【输出校验重试】上次输出未通过解析或轮次/词ID校验。'
                '请根据同一输入重新输出完整严格JSON，不要解释、不要尾逗号、不要重复键，'
                'rounds只能包含全部完整的轮对象，禁止追加字符串或补充对象。'
                '结尾括号必须与开头完全配平：不多、不少、不截断，也不要夹带无关字符。'
                '不要为了通过校验虚构词ID、轮次或边界。')
        response = call(model=task_params.get('model') or resolve_model(dimension='turn_eval'),
                        prompt=request, system_message=attempt_prompt, temperature=0,
                        max_tokens=task_params.get('max_tokens') or 16000,
                        log_context={'dimension': 'turn_eval_full_timeline', 'output_attempt': attempt + 1})
        tokens_used += response.get('tokens_used', 0) or 0
        content = response.get('content', '')
        record = dict(attempt=attempt + 1, raw_content=content)
        attempts.append(record)
        try:
            parsed, parse_info = _parse_judge_content(content)
            record.update(parse_info)
            turns = validate_and_derive(packet, parsed)
        except ValueError as exc:
            record.update(validation_passed=False, error=str(exc))
            _LOGGER.warning('[turn_eval] output attempt %s failed: %s', attempt + 1, exc)
            if attempt == 0:
                continue
            raise TurnEvalOutputError(
                'Turn eval output invalid after 2 attempts: ' + str(exc), attempts) from exc
        record['validation_passed'] = True
        if parse_info['repaired']:
            _LOGGER.warning('[turn_eval] repaired LLM output: trailing_commas=%s tail_repaired=%s',
                            parse_info.get('removed_trailing_commas', 0), parse_info.get('tail_repaired', False))
        return turns, tokens_used


def evaluate(calculator, task_params):
    from app.services.calculators.xiaoyi_metrics.shared.llm_client import build_interaction_text
    rounds = task_params.get('rounds') or []
    last = rounds[-1]
    # Align all played sources to the cumulative user recording before ASR.
    # Keep the full timeline; semantic round boundaries still belong to the LLM.
    played_audios, _ = calculator._merge_all_played_audios(task_params)
    shared = calculator._build_shared_asr(
        last.get('user_wav') or task_params.get('user_wav') or '',
        last.get('ai_wav') or task_params.get('ai_wav') or '',
        played_audios,
    )
    user = shared.get('user_chunks') or []
    model = shared.get('ai_word_chunks') or []
    packet = build_input(user, model, rounds)
    turns, tokens = judge(packet, task_params)
    # Reuse the existing pure projection contract, not the old segmentation/classifier.
    per_round = calculator._build_per_round(len(rounds), copy.deepcopy(turns))
    merged = copy.deepcopy(turns)
    for row in merged:
        row['round_number'] = 0
    result = calculator._build_per_round(1, merged)[0]
    result.pop('round_number', None)
    result['turn_classification']['turns'] = turns
    result.update(per_round=per_round, per_round_native=True, interaction_text=build_interaction_text(user, model),
                  full_timeline_input=packet, llm_round_evaluations=copy.deepcopy(turns), tokens_used=tokens, evaluation_mode='full_timeline', message='OK')
    return result
