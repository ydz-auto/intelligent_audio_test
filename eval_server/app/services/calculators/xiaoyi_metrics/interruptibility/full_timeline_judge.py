"""Full-case word ASR judge. Semantic decisions are remote; arithmetic is local."""
import copy
import hashlib
import json
import logging
import math
import os
import threading
from pathlib import Path

LABELS = ('回复', '恢复', '询问', '无关', '静默')
try:
    _CONCURRENCY = max(1, int(os.environ.get('LLM_INTERRUPTION_FULL_TIMELINE_CONCURRENCY', '1')))
except ValueError:
    _CONCURRENCY = 1
_CALL_GATE = threading.BoundedSemaphore(_CONCURRENCY)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Non-finite ASR timestamp')
    return float(value)


def build_input(user_chunks, model_chunks, rounds, task='', case=''):
    words = []
    for prefix, speaker, chunks in [('U', 'query', user_chunks), ('M', 'answer', model_chunks)]:
        for index, chunk in enumerate(chunks or []):
            start, end = map(_number, chunk['timestamp'])
            if end < start:
                raise ValueError('Reversed ASR word interval')
            words.append(dict(word_id=f'{prefix}{index:04d}', speaker=speaker,
                              text=str(chunk.get('text') or ''), start=start, end=end))
    if not any(w['speaker'] == 'query' for w in words) or not any(w['speaker'] == 'answer' for w in words):
        raise ValueError('Full user/model word ASR required; absence is not silence evidence')
    scheduled = []
    for rd in rounds:
        role = rd.get('role', '打断')
        role = {'resume': '恢复原话题', '恢复': '恢复原话题', 'interruption': '打断'}.get(role, role)
        if role not in ('打断', '停止', '恢复原话题'):
            raise ValueError('Unsupported scheduled role')
        query = rd.get('script_text', rd.get('query', ''))
        if isinstance(query, dict):
            query = query.get('text', '')
        rid = rd['round']
        if isinstance(rid, bool) or not isinstance(rid, int):
            raise ValueError('Round must be integer')
        scheduled.append(dict(round=rid, role=role, script_text=str(query or '')))
    if len({r['round'] for r in scheduled}) != len(scheduled):
        raise ValueError('Duplicate scheduled round')
    return dict(task=str(task), case=str(case), full_word_timeline=sorted(
        words, key=lambda w: (w['start'], w['end'], w['word_id'])), scheduled_rounds=scheduled)


def _stats(values):
    valid = [v for v in values if v is not None]
    positive = [v for v in valid if v > 0]
    return dict(valid_count=len(valid), avg_ms=round(sum(positive)/len(positive), 1) if positive else None,
                min_ms=min(valid) if valid else None, max_ms=max(valid) if valid else None)


def aggregate_rows(rows):
    ordinary = [r for r in rows if r['role'] != '恢复原话题']
    resume = [r for r in rows if r['role'] == '恢复原话题']
    stops = [r for r in ordinary if r['role'] == '停止']
    counts = {label: sum(r['behavior'] == label for r in ordinary) for label in LABELS}
    counts['不可判定'] = sum(r['behavior'] is None for r in ordinary)
    result = dict(total_rounds=len(rows), ordinary_rounds=len(ordinary), resume_rounds=len(resume),
                  behavior_counts=counts, unknown_total=sum(r['behavior'] is None for r in rows),
                  source_mismatch_rounds=sum(r['alignment']['status'] == 'source_mismatch' for r in rows),
                  stop_compliance=dict(eligible=sum(r.get('stop_complied') is not None for r in stops),
                      complied=sum(r.get('stop_complied') is True for r in stops),
                      unknown=sum(r.get('stop_complied') is None for r in stops)),
                  resume_results=[dict(round_id=r['round_id'], topic_resumed=r.get('topic_resumed'),
                      reply_latency_ms=r['timing']['reply_latency_ms'], reason=r['behavior_reason']) for r in resume],
                  stop_results=[dict(round_id=r['round_id'], **r['stop_review']) for r in stops])
    for label in ('response', 'reply'):
        values = [r['timing'][label+'_latency_ms'] for r in ordinary]
        result['round_'+label+'_latencies'] = [dict(round_id=r['round_id'], value_ms=v) for r, v in zip(ordinary, values)]
        result[label+'_latency'] = _stats(values)
    return result


def validate_and_derive(packet, parsed):
    """Never guess/remap a missing round or trust LLM numeric fields."""
    raw = parsed.get('round_details')
    if not isinstance(raw, list):
        raise ValueError('round_details must be an array')
    if not all(isinstance(r, dict) for r in raw):
        raise ValueError('round_details contains non-object items (string fragments are forbidden)')
    expected = {r['round'] for r in packet['scheduled_rounds']}
    if any(isinstance(r.get('round'), bool) or not isinstance(r.get('round'), int) for r in raw):
        raise ValueError('Invalid returned round number')
    if len(raw) != len(expected) or {r['round'] for r in raw} != expected:
        raise ValueError('Returned rounds missing, duplicated, or renumbered')
    by_round = {r['round']: r for r in raw}
    words = {w['word_id']: w for w in packet['full_word_timeline']}
    def word(wid, speaker):
        if wid is None:
            return None
        if not isinstance(wid, str) or wid not in words or words[wid]['speaker'] != speaker:
            raise ValueError(f'Invalid {speaker} word ID: {wid}')
        return words[wid]
    def delta(a, b):
        return round((a-b)*1000, 1)
    rows = []
    for scheduled in packet['scheduled_rounds']:
        r = copy.deepcopy(by_round[scheduled['round']])
        r['llm_round_id_claim'] = r.get('round_id')
        r.update(round_id=f"{packet['task']}_{packet['case']}_r{scheduled['round']}",
                 role=scheduled['role'], task=packet['task'], case=packet['case'])
        behavior = r.get('behavior')
        if behavior not in LABELS+(None, '') or (behavior == '' and r['role'] != '恢复原话题'):
            raise ValueError('Invalid behavior for role')
        alignment = r.get('alignment')
        if not isinstance(alignment, dict) or alignment.get('status') not in ('matched', 'partial', 'ambiguous', 'not_found', 'source_mismatch'):
            raise ValueError('Missing alignment status')
        us = word(alignment.get('user_start_word_id'), 'query')
        ue = word(alignment.get('user_end_word_id'), 'query')
        if us and ue and ue['start'] < us['start']:
            raise ValueError('Reversed user word range')
        first = word(r.get('response_start_word_id'), 'answer')
        last_old = word(r.get('last_old_content_word_id'), 'answer')
        if first and (not us or first['start'] < us['start']):
            raise ValueError('Response precedes user input')
        if last_old and first and last_old['end'] > first['start']+0.001:
            raise ValueError('Old-content end exceeds response start')
        if not r.get('behavior_reason') or not alignment.get('reason'):
            raise ValueError('Missing semantic reason')
        if alignment['status'] in ('ambiguous', 'not_found', 'source_mismatch'):
            r['llm_behavior_claim'] = behavior
            r['llm_behavior_reason_claim'] = r['behavior_reason']
            r['behavior'] = behavior = None
            r['behavior_reason'] = '证据门控为不可判定：' + alignment['reason'] + '；模型原判理由：' + r['llm_behavior_reason_claim']
            r['llm_response_start_word_id_claim'] = r.get('response_start_word_id')
            r['response_start_word_id'] = None
            r['last_old_content_word_id'] = None
            r.pop('score', None)
        eligible = behavior in ('回复', '询问') or (r['role'] == '恢复原话题' and r.get('topic_resumed') is True and behavior is not None)
        timing = dict(response_latency_ms=None, reply_latency_ms=None,
                      first_response_from_user_start_ms=None)
        missing = '没有可靠实际输入或新回应，不计算成功回应时延。'
        timing.update(response_reason=missing, reply_reason=missing, first_response_reason=missing)
        if eligible and first and us and alignment.get('start_boundary_valid') is True:
            value = delta(first['start'], us['start'])
            timing['first_response_from_user_start_ms'] = value
            timing['first_response_reason'] = f"{first['word_id']}({first['start']})-{us['word_id']}({us['start']}) = {value}ms"
            stop = last_old['end'] if last_old and last_old['end'] > us['start'] else first['start']
            timing['response_latency_ms'] = max(0, delta(stop, us['start']))
            timing['response_reason'] = f"({stop}-{us['start']})*1000={timing['response_latency_ms']}ms；" + (
                f"旧内容末词{last_old['word_id']}“{last_old['text']}”的结束代理。" if last_old and last_old['end'] > us['start'] else '无用户开始后旧内容，这是等待新回应时长，不是旧内容停止延迟。')
            timing['reply_reason'] = '实际用户末词边界不可靠，不能用可见片段末词代替完整结束。'
            if ue and alignment.get('end_boundary_valid') is True:
                value = delta(first['start'], ue['end'])
                timing.update(reply_latency_ms=value, reply_reason=f"{first['word_id']}“{first['text']}”start={first['start']}；{ue['word_id']}“{ue['text']}”end={ue['end']}；差*1000={value}ms。负值保留。")
        r['llm_timing_claim'] = r.get('timing')
        r['timing'] = timing
        if behavior is None:
            r['stop_complied'] = None
            r['topic_resumed'] = None
        if r['role'] == '停止':
            sr = r.get('stop_review')
            if not isinstance(sr, dict) or sr.get('stop_status') not in ('stopped', 'not_stopped', 'unknown'):
                raise ValueError('Missing stop-specific result')
            sr = copy.deepcopy(sr)
            r['llm_stop_review_claim'] = copy.deepcopy(sr)
            confirmed = word(sr.get('confirmation_start_word_id'), 'answer')
            orig = word(sr.get('last_original_content_word_id'), 'answer')
            conf_end = word(sr.get('last_confirmation_word_id'), 'answer')
            r['stop_complied'] = {'stopped': True, 'not_stopped': False, 'unknown': None}[sr['stop_status']] if behavior is not None else None
            if not sr.get('stop_reason'):
                raise ValueError('Missing stop reason')
            sr.update(original_content_stop_latency_ms=None, confirmation_reply_latency_ms=None,
                      settled_after_confirmation_latency_ms=None, confirmation_duration_ms=None,
                      asr_no_output_gap_before_next_user_ms=None)
            sr['original_content_stop_reason'] = sr['settled_reason'] = '未确认持续停止，不将观察末词作为停止点。'
            sr['confirmation_reply_reason'] = '没有有效确认首词或用户末词。'
            if confirmed and ue and alignment.get('end_boundary_valid') is True:
                sr['confirmation_reply_latency_ms'] = delta(confirmed['start'], ue['end'])
                sr['confirmation_reply_reason'] = f"({confirmed['start']}-{ue['end']})*1000={sr['confirmation_reply_latency_ms']}ms；确认开始不等于停止。"
            later = [row for row in raw if row['round'] > r['round']]
            next_starts = [word(row.get('alignment', {}).get('user_start_word_id'), 'query') for row in later]
            until = min((w['start'] for w in next_starts if w), default=None)
            sr['observation_start_s'] = us['start'] if us else None
            sr['observation_end_s'] = until
            sr['observation_end_reason'] = f'下一次已对齐实际用户指令起点{until}s。' if until is not None else '后续用户指令未可靠对齐，观察终点未知。'
            if us and until is not None:
                if until <= us['start']:
                    raise ValueError('Stop observation boundary is non-monotonic')
                observed = [w for w in words.values() if w['speaker'] == 'answer' and w['end'] > us['start'] and w['start'] < until]
                sr['observation_span_ms'] = delta(until, us['start'])
                sr['observed_elapsed_to_last_model_word_ms'] = delta(min(max(w['end'] for w in observed), until), us['start']) if observed else 0
                endpoint = min(max(w['end'] for w in observed), until) if observed else us['start']
                sr['observed_elapsed_to_last_model_word_reason'] = f'观察截断于下一次用户指令{until}s，末词跨界时按观察终点截断；({endpoint}-{us["start"]})*1000={sr["observed_elapsed_to_last_model_word_ms"]}ms，仅为观察跨度，不是成功停止时延。'
                sr['observation_span_reason'] = f'({until}-{us["start"]})*1000={sr["observation_span_ms"]}ms。'
                if observed:
                    last_end = max(w['end'] for w in observed)
                    sr['asr_no_output_gap_before_next_user_ms'] = max(0, delta(until, last_end))
                    sr['asr_no_output_gap_before_next_user_reason'] = f'max(0,({until}-{last_end})*1000)={sr["asr_no_output_gap_before_next_user_ms"]}ms；仅为词间隔，不代表已遵从停止。'
            if confirmed and conf_end:
                if conf_end['end'] < confirmed['start']:
                    raise ValueError('Invalid confirmation duration')
                sr['confirmation_duration_ms'] = delta(conf_end['end'], confirmed['start'])
                sr['confirmation_duration_reason'] = f'({conf_end["end"]}-{confirmed["start"]})*1000={sr["confirmation_duration_ms"]}ms。'
            if r['stop_complied'] is True and us:
                if orig and orig['end'] < us['start']:
                    raise ValueError('Original-content stop word predates request')
                endpoint = orig['end'] if orig else us['start']
                if until is not None and endpoint > until:
                    raise ValueError('Stop point crosses next user instruction')
                sr['original_content_stop_latency_ms'] = max(0, delta(endpoint, us['start']))
                sr['original_content_stop_reason'] = f"({endpoint}-{us['start']})*1000={sr['original_content_stop_latency_ms']}ms；" + (f"原内容末词{orig['word_id']}。" if orig else '无打断后原内容，记0。')
                settle = conf_end or orig
                if conf_end and (not confirmed or conf_end['end'] < confirmed['start']):
                    raise ValueError('Invalid confirmation interval')
                if settle and until is not None and settle['end'] > until:
                    raise ValueError('Confirmation crosses next user instruction')
                if settle:
                    sr['settled_after_confirmation_latency_ms'] = max(0, delta(settle['end'], us['start']))
                    sr['settled_reason'] = f"{settle['word_id']}结束{settle['end']}；相对用户{us['start']}为{sr['settled_after_confirmation_latency_ms']}ms，ASR代理非物理停声。"
                if confirmed and conf_end:
                    sr['confirmation_duration_ms'] = delta(conf_end['end'], confirmed['start'])
                if until is not None and settle:
                    remaining = [w for w in words.values() if w['speaker'] == 'answer' and w['start'] >= settle['end'] and w['start'] < until]
                    if remaining:
                        raise ValueError('Claimed waiting interval contains later model words')
                    sr['asr_no_output_gap_before_next_user_ms'] = delta(until, settle['end'])
                    sr['asr_no_output_gap_before_next_user_reason'] = f'({until}-{settle["end"]})*1000={sr["asr_no_output_gap_before_next_user_ms"]}ms；确认结束后到下一实际用户指令。'
            sr['original_content_stop_latency_reason'] = sr['original_content_stop_reason']
            sr['confirmation_reply_latency_reason'] = sr['confirmation_reply_reason']
            sr['settled_after_confirmation_latency_reason'] = sr['settled_reason']
            r['stop_review'] = sr
        rows.append(r)
    aggregate = aggregate_rows(rows)
    claimed = parsed.get('aggregate')
    mismatches = []
    timing_mismatches = []
    for row in rows:
        claim = row.get('llm_timing_claim') or {}
        for key in ('response_latency_ms', 'reply_latency_ms', 'first_response_from_user_start_ms'):
            if claim.get(key) != row['timing'][key]:
                timing_mismatches.append(dict(round_id=row['round_id'], field=key,
                    llm_value=claim.get(key), local_value=row['timing'][key]))
    if isinstance(claimed, dict):
        for key in ('total_rounds', 'ordinary_rounds', 'resume_rounds', 'unknown_total',
                    'source_mismatch_rounds', 'behavior_counts', 'round_response_latencies',
                    'round_reply_latencies', 'response_latency', 'reply_latency', 'stop_compliance'):
            if claimed.get(key) != aggregate.get(key):
                mismatches.append(key)
    else:
        mismatches.append('aggregate_missing')
    return dict(round_details=rows, aggregate=aggregate, llm_aggregate_claim=claimed,
                validation=dict(passed=True, llm_aggregate_matches=not mismatches,
                                llm_aggregate_mismatches=mismatches, llm_timing_mismatches=timing_mismatches,
                                aggregation_source='local_same_round_details'))


def build_output_schema(packet):
    """Render the entire case skeleton, including role fields in their own row."""
    rows = []
    for scheduled in packet['scheduled_rounds']:
        row = dict(round_id=f"{packet['task']}_{packet['case']}_r{scheduled['round']}",
            round=scheduled['round'], role=scheduled['role'], behavior=None, behavior_reason='',
            alignment=dict(status='not_found', user_start_word_id=None, user_end_word_id=None,
                actual_text='', start_boundary_valid=False, end_boundary_valid=False, reason=''),
            response_start_word_id=None, response_start_reason='', last_old_content_word_id=None,
            last_old_content_reason='', timing=dict(response_latency_ms=None, response_reason='',
                reply_latency_ms=None, reply_reason='', first_response_from_user_start_ms=None,
                first_response_reason=''))
        if scheduled['role'] == '停止':
            row.update(stop_complied=None, stop_compliance_reason='', stop_review=dict(
                stop_status='unknown', observation_start_s=None, observation_end_s=None,
                observation_end_reason='', confirmation_start_word_id=None,
                last_original_content_word_id=None, last_confirmation_word_id=None, stop_reason='',
                original_content_stop_latency_ms=None, original_content_stop_reason='',
                confirmation_reply_latency_ms=None, confirmation_reply_reason='',
                settled_after_confirmation_latency_ms=None, settled_reason='',
                confirmation_duration_ms=None, confirmation_duration_reason='',
                asr_no_output_gap_before_next_user_ms=None, asr_no_output_gap_before_next_user_reason='',
                observed_elapsed_to_last_model_word_ms=None, observed_elapsed_to_last_model_word_reason='',
                observation_span_ms=None, observation_span_reason=''))
        if scheduled['role'] == '恢复原话题':
            row.update(topic_resumed=None, topic_resume_reason='')
        rows.append(row)
    return dict(task=packet['task'], case=packet['case'], round_details=rows, aggregate=aggregate_rows(rows))



_LOGGER = logging.getLogger(__name__)


class FullTimelineOutputError(ValueError):
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


def _parse_judge_content(content):
    if not isinstance(content, str):
        raise ValueError('Judge content must be a JSON string')
    content = content.strip()
    if content.startswith('```') and content.endswith('```') and '\n' in content:
        first, rest = content.split('\n', 1)
        if first.strip().lower() in ('```', '```json'):
            content = rest.rsplit('```', 1)[0].strip()

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate JSON key: ' + key)
            value[key] = item
        return value

    def reject_constant(value):
        raise ValueError('Non-finite JSON constant: ' + value)

    def load(value):
        parsed = json.loads(value, object_pairs_hook=unique_object, parse_constant=reject_constant)
        if not isinstance(parsed, dict):
            raise ValueError('Judge JSON root must be an object')
        return parsed

    try:
        return load(content), dict(repaired=False, removed_trailing_commas=0)
    except json.JSONDecodeError:
        repaired, removed = _remove_trailing_commas(content)
        if not removed:
            raise
        # Syntax repair cannot invent keys, IDs, rounds, quotes, or closing brackets.
        parsed = load(repaired)
        return parsed, dict(repaired=True, removed_trailing_commas=removed)


def judge_full_timeline(packet, model='', max_tokens=None, temperature=None, call=None):
    prompt = Path(__file__).with_name('full_timeline_prompt.txt').read_text(encoding='utf-8-sig')
    prompt = prompt.split('【输出结构】')[0]
    prompt += '\n【当前用例唯一输出骨架】\n保留这些轮号、轮ID及角色；必须逐轮实际判断并填写reason，不得照抄未知初始值。禁止把字段、JSON或自我修改备注作为字符串数组元素追加。停止指标仅放在该轮stop_review中；恢复标记放在该轮对象中。可评内容时在该轮添加score对象。\n'
    prompt += json.dumps(build_output_schema(packet), ensure_ascii=False, separators=(',', ':'))
    if call is None:
        from app.services.calculators.xiaoyi_metrics.shared.llm_client import call_llm, resolve_model
        call = call_llm
        model = resolve_model(model, dimension='interruption_judge')
    request = json.dumps(packet, ensure_ascii=False, separators=(',', ':'))
    attempts, tokens_used = [], 0
    for attempt in range(2):
        attempt_prompt = prompt
        if attempt:
            attempt_prompt += ('\n【输出校验重试】上次输出未通过解析或轮次/词ID校验。'
                '请根据同一输入重新输出完整严格JSON，不要解释、不要尾逗号、不要重复键，'
                'round_details只能包含本次骨架中完整的轮对象，禁止追加字符串或补充对象。'
                '不要为了通过校验虚构词ID、轮次或边界。')
        # Transport failures keep the existing shared client's network retry policy.
        with _CALL_GATE:
            response = call(model=model, prompt=request, system_message=attempt_prompt,
                            max_tokens=max_tokens or 16000, temperature=0 if temperature is None else temperature,
                            log_context={'dimension': 'interruption_full_timeline', 'output_attempt': attempt + 1})
        tokens_used += response.get('tokens_used', 0) or 0
        content = response.get('content', '')
        record = dict(attempt=attempt + 1, raw_content=content)
        attempts.append(record)
        try:
            parsed, parse_info = _parse_judge_content(content)
            record.update(parse_info)
            result = validate_and_derive(packet, parsed)
        except ValueError as exc:
            record.update(validation_passed=False, error=str(exc))
            _LOGGER.warning('[interruption] output attempt %s failed: %s', attempt + 1, exc)
            if attempt == 0:
                continue
            raise FullTimelineOutputError(
                'Full timeline output invalid after 2 attempts: ' + str(exc), attempts) from exc
        record['validation_passed'] = True
        if parse_info['repaired']:
            _LOGGER.warning('[interruption] removed %s trailing commas; business validation passed',
                            parse_info['removed_trailing_commas'])
        result.update(model=model, tokens_used=tokens_used,
                      input_sha256=hashlib.sha256(request.encode()).hexdigest(), raw_llm_result=parsed,
                      raw_llm_content=content, output_parse=parse_info, output_attempts=attempts)
        return result



def attach_full_timeline(calculator_result, blocks, task_params, case_info):
    """Adapt canonical results to existing metric and per_round contracts."""
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import chunks_from_segments, derive_round_metrics
    user = chunks_from_segments(calculator_result.get('user_segments'))
    model = chunks_from_segments(calculator_result.get('model_segments'))
    packet = build_input(user, model, blocks, task_params.get('task_id', ''), task_params.get('case_id', task_params.get('test_case_id', '')))
    judged = judge_full_timeline(packet, model=str(task_params.get('model') or ''),
        max_tokens=int(task_params['max_tokens']) if task_params.get('max_tokens') else None,
        temperature=float(task_params['temperature']) if task_params.get('temperature') is not None else None)
    # Keep the legacy platform envelope; canonical evidence stays in API audit files.
    wordmap = {w['word_id']: w for w in packet['full_word_timeline']}
    existing = {t['round']: t for t in calculator_result.get('round_timing', [])}
    blockmap = {b['round']: b for b in blocks}
    timings, behaviors, legacy_rows = [], [], []
    for r in judged['round_details']:
        score = r.get('score') if isinstance(r.get('score'), dict) else None
        t = dict(existing.get(r['round'], {}))
        alignment = r['alignment']
        start = wordmap.get(alignment.get('user_start_word_id'), {})
        end = wordmap.get(alignment.get('user_end_word_id'), {})
        first = wordmap.get(r.get('response_start_word_id'))
        words = blockmap.get(r['round'], {}).get('model_words', [])
        index = next((i for i, w in enumerate(words) if first and
            w.get('start') == first['start'] and w.get('end') == first['end'] and
            w.get('text') == first['text']), None)
        t.update(round=r['round'], role='resume' if r['role'] == '恢复原话题' else 'interruption',
            stop_intent=r['role'] == '停止', anchor_method='llm_full_word_timeline',
            u_s=start.get('start') if alignment.get('start_boundary_valid') else None,
            u_e=end.get('end') if alignment.get('end_boundary_valid') else None,
            response_latency_ms=r['timing']['response_latency_ms'],
            reply_latency_ms=r['timing']['reply_latency_ms'])
        if index is not None:
            t.update(latency_source='llm_interrupt_point', interrupt_index=index)
        if t['role'] == 'resume':
            t.update(score_overall=(score or {}).get('overall'), topic_resumed=r.get('topic_resumed'))
        reason = r['behavior_reason'] or ''
        reason += '；响应时延：' + str(r['timing'].get('response_reason') or '无有效边界')
        reason += '；回复时延：' + str(r['timing'].get('reply_reason') or '无有效边界')
        legacy = dict(round=r['round'], behavior=r['behavior'], behavior_reason=reason,
                      interrupt_index=index, score=score)
        if r['role'] == '停止': legacy['stop_complied'] = r.get('stop_complied')
        if r['role'] == '恢复原话题': legacy['topic_resumed'] = r.get('topic_resumed')
        legacy_rows.append(legacy)
        timings.append(t)
        behaviors.append(dict(legacy, score_overall=(score or {}).get('overall')))
    resume = next((t for t in timings if t['role'] == 'resume'), None)
    spec = derive_round_metrics([t for t in timings if t['role'] != 'resume'], behaviors, case_info, resume)
    for label in ('response', 'reply'):
        for stat in ('avg', 'min', 'max'):
            spec[f'{label}_latency_{stat}_ms'] = judged['aggregate'][label+'_latency'][stat+'_ms']
    calculator_result.update(spec, llm_round_evaluations=legacy_rows,
        llm_judge_model=judged['model'], round_timing=timings, tokens_used=judged['tokens_used'])
    return calculator_result
