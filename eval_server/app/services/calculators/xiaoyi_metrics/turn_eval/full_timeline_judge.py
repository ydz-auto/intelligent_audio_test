"""Full-case takeover judge: semantic boundaries remote, validation/arithmetic local."""
import copy
import json
import math
from pathlib import Path

LABELS = ('接管', '误接管', '未接管')


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
        if label == '未接管':
            if row.get('response_start_word_id') is not None or row.get('response_end_word_id') is not None:
                raise ValueError('No-takeover must not claim a reply span')
            mw = []
        else:
            mw, _, _ = span('model', row.get('response_start_word_id'), row.get('response_end_word_id'))
            if mw[0]['start'] < uw[0]['start']:
                raise ValueError('Reply predates this user turn')
        user_text = ''.join(w['text'] for w in uw)
        model_text = ''.join(w['text'] for w in mw)
        turn = dict(turn_index=len(turns) + 1, round_number=row['round_number'], classification=label,
                    user_start_s=uw[0]['start'], user_end_s=uw[-1]['end'], ai_start_s=mw[0]['start'] if mw else None,
                    ai_end_s=mw[-1]['end'] if mw else None, has_ai_reply=bool(mw),
                    false_takeover=dict(false_takeover=int(label == '误接管'), reason=row['reason'], evidence=dict(user_full_utterance=user_text)),
                    alignment=dict(user_start_word_id=uw[0]['word_id'], user_end_word_id=uw[-1]['word_id'], reason=row['alignment_reason']),
                    response_start_word_id=mw[0]['word_id'] if mw else None, response_end_word_id=mw[-1]['word_id'] if mw else None,
                    response_start_reason=row['response_start_reason'], tor=None, takeover_judge=None, takeover_latency=None, reply_quality=None)
        if label == '接管':
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


def judge(packet, task_params, call=None):
    from app.services.calculators.xiaoyi_metrics.shared.llm_client import call_llm, resolve_model
    call = call or call_llm
    prompt = Path(__file__).with_name('full_timeline_prompt.txt').read_text(encoding='utf-8')
    response = call(model=task_params.get('model') or resolve_model(dimension='turn_eval'), prompt=json.dumps(packet, ensure_ascii=False),
                    system_message=prompt, temperature=0, max_tokens=task_params.get('max_tokens') or 16000,
                    log_context={'dimension': 'turn_eval_full_timeline'})
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('Duplicate JSON key')
            result[k] = v
        return result
    parsed = json.loads(response.get('content', ''), object_pairs_hook=pairs)
    return validate_and_derive(packet, parsed), response.get('tokens_used', 0)


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
