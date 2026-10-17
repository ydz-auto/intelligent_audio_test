"""Full word ASR refusal judge: configured round IDs, no audio attachments."""
import json
import math
from pathlib import Path


def build_packet(user_chunks, model_chunks, configured_rounds):
    words = []
    for prefix, speaker, chunks in [('U', 'query', user_chunks), ('M', 'answer', model_chunks)]:
        for i, chunk in enumerate(chunks or []):
            start, end = chunk['timestamp']
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end)) or end < start:
                raise ValueError('Invalid word timestamps')
            words.append(dict(word_id=f'{prefix}{i:04d}', speaker=speaker,
                              text=str(chunk.get('text') or ''), start=start, end=end))
    rounds, parent = [], None
    for i, rd in enumerate(configured_rounds):
        number = rd['configured_round_number']
        rid = f'round_{number}'
        reject = rd['evaluate_rejection']
        if not reject:
            parent = rid
        rounds.append(dict(round_id=rid, sequence=i + 1, configured_round_number=number,
            role='rejection' if reject else 'intent', role_source='platform_config',
            evaluate_rejection=reject, parent_intent_round_id=parent if reject else None,
            script_text=rd.get('script_text'), asr_hint=None))
    if len({r['round_id'] for r in rounds}) != len(rounds):
        raise ValueError('Duplicate configured round numbers')
    return dict(round_inventory=dict(source='platform_config', configuration_complete=True,
        configured_round_count=len(rounds)), all_rounds=rounds,
        full_word_timeline=sorted(words, key=lambda w: (w['start'], w['end'], w['word_id'])))


def judge(packet, call, model, max_tokens, temperature):
    system = Path(__file__).with_name('rejection_rounds_prompt.txt').read_text(encoding='utf-8-sig')
    response = call(model=model, system_message=system,
        prompt=json.dumps(packet, ensure_ascii=False, separators=(',', ':')),
        max_tokens=max_tokens, temperature=temperature,
        log_context={'dimension': 'reject_judge_rounds_v3'})
    content = response.get('content', '').strip()
    if content.startswith('```'):
        content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    parsed = json.loads(content)
    rows = parsed.get('round_details')
    expected = packet['all_rounds']
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError('Missing or extra configured rounds')
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError('Invalid round object')
    if [r.get('round_id') for r in rows] != [r['round_id'] for r in expected]:
        raise ValueError('Round IDs changed, duplicated, reordered or missing')
    words = {w['word_id']: w for w in packet['full_word_timeline']}
    for row, config in zip(rows, expected):
        for field in ('sequence', 'configured_round_number', 'role', 'evaluate_rejection', 'parent_intent_round_id'):
            if row.get(field) != config[field]:
                raise ValueError('Changed configured round field: ' + field)
        if row.get('alignment_status') not in ('matched', 'partial', 'ambiguous', 'not_found', 'source_mismatch'):
            raise ValueError('Invalid alignment status')
        if row.get('evaluation_status') not in ('evaluated', 'not_applicable', 'unjudgeable'):
            raise ValueError('Invalid evaluation status')
        if row.get('timing') not in ('静默', '回复过程中', None) or row.get('behavior') not in ('恢复', '回应', '不确定询问', '无关回复', '静默', None):
            raise ValueError('Invalid judgment labels')
        if not row.get('reason') or not row.get('alignment_reason'):
            raise ValueError('Missing evidence reason')
        for key in ('user_start_word_id', 'user_end_word_id'):
            wid = row.get(key)
            if wid is not None and (wid not in words or words[wid]['speaker'] != 'query'):
                raise ValueError('Invalid user word ID')
        a, b = row.get('user_start_word_id'), row.get('user_end_word_id')
        if a and b and words[a]['start'] > words[b]['start']:
            raise ValueError('Reversed user word range')
        if any(wid not in words for wid in row.get('evidence_word_ids', [])):
            raise ValueError('Invented evidence word ID')
        if not config['evaluate_rejection']:
            if row['evaluation_status'] != 'not_applicable' or row.get('behavior') is not None or row.get('timing') is not None:
                raise ValueError('Normal intent round was scored')
        elif row['evaluation_status'] == 'evaluated':
            if row['alignment_status'] not in ('matched', 'partial') or not a or not b or row.get('timing') is None or row.get('behavior') is None:
                raise ValueError('Insufficient evidence for evaluated round')
        elif row['evaluation_status'] != 'unjudgeable' or row.get('behavior') is not None:
            raise ValueError('Unjudgeable rejection round must retain null behavior')
    return rows, response
