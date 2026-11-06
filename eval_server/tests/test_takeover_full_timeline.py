import copy,json
from pathlib import Path
import pytest
from app.services.calculators.xiaoyi_metrics.turn_eval import full_timeline_judge as f
from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator
from app.services.calculators.xiaoyi_metrics.turn_taking.strategy import TurnTakingBase

@pytest.fixture
def example():
    data=json.loads((Path(__file__).parent/'fixtures/turn_eval_jg0211_words.json').read_text(encoding='utf-8'))
    rounds=[{'query':q,'user_wav':'raw_user.wav','ai_wav':'raw_model.wav'} for q in ['你叫什么','你多大了','你是男的女的']]
    packet=f.build_input(data['user'],data['model'],rounds)
    rows=[]
    for i,(a,b,lo,hi) in enumerate([(0,3,6,20),(4,7,26,45),(8,13,54,70)]):
        ids=[w['word_id'] for w in packet['full_word_timeline'] if w['speaker']=='model' and lo<=w['start']<hi]
        rows.append(dict(round_number=i,user_start_word_id=f'U{a:05d}',user_end_word_id=f'U{b:05d}',response_start_word_id=ids[0],response_end_word_id=ids[-1],classification='接管',reason='用户本轮完整提问后模型作答',alignment_reason='下一问题首词不属于本轮',response_start_reason='对应本轮实际回答首词',reply_quality={'score':4,'reason':'回应问题'}))
    return data,rounds,packet,{'rounds':rows}

def test_real_jg0211_word_ranges_are_disjoint(example):
    _,_,packet,parsed=example
    ts=f.validate_and_derive(packet,parsed)
    assert [t['false_takeover']['evidence']['user_full_utterance'] for t in ts]==['你叫什么','你多大了','你是男的女的']
    assert ts[0]['user_end_s']<6 and ts[1]['user_start_s']>24
    assert ts[0]['takeover_latency']['takeover_latency_ms']==round((ts[0]['ai_start_s']-ts[0]['user_end_s'])*1000,1)

@pytest.mark.parametrize('kind',['overlap_user','overlap_model','unknown_id','missing_round','reverse_rounds','unknown_class','invalid_score','bool_round'])
def test_bad_judge_output_is_rejected(example,kind):
    _,_,packet,p=example;p=copy.deepcopy(p)
    if kind=='overlap_user':p['rounds'][0]['user_end_word_id']='U00004'
    if kind=='overlap_model':p['rounds'][1]['response_start_word_id']=p['rounds'][0]['response_start_word_id']
    if kind=='unknown_id':p['rounds'][0]['user_end_word_id']='M99999'
    if kind=='missing_round':p['rounds'].pop()
    if kind=='reverse_rounds':p['rounds'].reverse()
    if kind=='unknown_class':p['rounds'][0]['classification']=None
    if kind=='invalid_score':p['rounds'][0]['reply_quality']['score']=False
    if kind=='bool_round':p['rounds'][0]['round_number']=False
    with pytest.raises(ValueError):f.validate_and_derive(packet,p)

def test_input_does_not_use_script_to_invent_words():
    with pytest.raises(ValueError):f.build_input([],[],[{'query':'你叫什么'}])
    with pytest.raises(ValueError):f.build_input([{'text':'你','timestamp':[1,2]}],[],[{'query':'你叫什么'}])

def test_whole_case_bypasses_local_segmentation_and_projects_contract(example,monkeypatch):
    data,rounds,_,parsed=example
    def asr(path,**kwargs):return data['user'] if path=='raw_user.wav' else data['model']
    monkeypatch.setattr(TurnTakingBase,'_get_asr_chunks',staticmethod(asr))
    monkeypatch.setattr(f,'judge',lambda packet,params:(f.validate_and_derive(packet,parsed),123))
    calc=TurnEvalCalculator()
    monkeypatch.setattr(calc,'_eval_one_round',lambda *a,**kw:pytest.fail('old segmentation used'))
    result=calc.calculate({'task_params':{'rounds':rounds}})
    assert result['evaluation_mode']=='full_timeline'
    assert result['turn_classification']['normal_takeover_count']==3
    assert result['turn_classification']['total_turns']==3
    assert len(result['per_round'])==3 and result['per_round_native'] is True
    assert len(result['full_timeline_input']['full_word_timeline'])==len(data['user'])+len(data['model'])
    result['per_round'][0]['turn_classification']['turns'][0]['classification']='changed'
    assert result['turn_classification']['turns'][0]['classification']=='接管'

def test_invalid_full_case_does_not_fallback(example,monkeypatch):
    data,rounds,_,_=example
    monkeypatch.setattr(TurnTakingBase,'_get_asr_chunks',staticmethod(lambda path,**kw:data['user'] if 'user' in path else data['model']))
    def invalid(*args):raise ValueError('word overlap')
    monkeypatch.setattr(f,'judge',invalid)
    with pytest.raises(ValueError,match='word overlap'):TurnEvalCalculator().calculate({'task_params':{'rounds':rounds}})


@pytest.mark.parametrize('alignment', ['aligned', 'low_confidence', 'failed', 'exception'])
def test_full_case_uses_aligned_user_asr_with_safe_fallback(example, monkeypatch, alignment):
    from app.services.calculators.xiaoyi_metrics.shared import audio_alignment
    data, rounds, _, parsed = example
    rounds[0]['played_audios'] = [{'audio_path': 'first.wav'}]
    rounds[1]['played_audios'] = [{'audio_path': 'second.wav'}]
    calls = []

    def align(path, sources):
        assert path == 'raw_user.wav'
        assert sources == [{'audio_path': 'first.wav'}, {'audio_path': 'second.wav'}]
        if alignment == 'exception':
            raise RuntimeError('alignment unavailable')
        return {'aligned_wav': None if alignment == 'failed' else 'aligned_user.wav',
                'ncc': 0.1 if alignment == 'low_confidence' else 0.9}

    def asr(path, **kwargs):
        calls.append((path, kwargs))
        if path == 'raw_model.wav':
            return data['model']
        expected = 'aligned_user.wav' if alignment == 'aligned' else 'raw_user.wav'
        assert path == expected
        return data['user']

    monkeypatch.setattr(audio_alignment, 'generate_aligned_clean_audio', align)
    monkeypatch.setattr(TurnTakingBase, '_get_asr_chunks', staticmethod(asr))

    def judge(packet, params):
        user_words = [w for w in packet['full_word_timeline'] if w['speaker'] == 'user']
        assert [w['text'] for w in user_words] == [w['text'] for w in data['user']]
        assert [w['start'] for w in user_words] == [w['timestamp'][0] for w in data['user']]
        return f.validate_and_derive(packet, parsed), 1

    monkeypatch.setattr(f, 'judge', judge)
    result = TurnEvalCalculator().calculate({'task_params': {'rounds': rounds}})
    assert result['turn_classification']['normal_takeover_count'] == 3
    assert ('raw_model.wav', {'filter_punct': False}) in calls

def test_duplicate_json_is_rejected(example):
    _,_,packet,_=example
    with pytest.raises(ValueError,match='Duplicate JSON key'):
        f.judge(packet,{'model':'offline'},call=lambda **kw:{'content':'{"rounds":[],"rounds":[]}'})


def test_tail_repair_recovers_broken_json():
    # 模型真实坏输出：多一个 } / 缺闭合 + 夹带垃圾字符 / 直接截断 / 尾逗号
    cases = [
        ('{"rounds":[]}}', {'rounds': []}),
        ('{"rounds":[{"round_number":0}]}箍', {'rounds': [{'round_number': 0}]}),
        ('{"rounds":[{"round_number":0}', {'rounds': [{'round_number': 0}]}),
        ('{"rounds":[],}', {'rounds': []}),  # 尾逗号
    ]
    for raw, expected in cases:
        parsed, info = f._parse_judge_content(raw)
        assert parsed == expected, raw
        assert info['repaired'] is True
    # 围栏剥离不算“修复”，repaired 保持 False
    parsed, info = f._parse_judge_content('```json\n{"rounds":[]}\n```')
    assert parsed == {'rounds': []} and info['repaired'] is False
    # 重复键仍然严格拒绝，不得被修复蒙混
    with pytest.raises(ValueError, match='Duplicate JSON key'):
        f._parse_judge_content('{"rounds":[],"rounds":[]}')
    # 纯垃圾无法修复，原样抛错
    with pytest.raises(json.JSONDecodeError):
        f._parse_judge_content('not json at all')


def test_broken_tail_passes_judge_with_repair(example):
    _,_,packet,parsed=example
    good=json.dumps(parsed,ensure_ascii=False)
    def broken(*args,**kw):
        # 第 1 次语义错误（不可修复）→ 触发重试；第 2 次坏尾部靠修复救回
        if kw.get('log_context',{}).get('output_attempt')==1:
            return {'content':good.replace('"接管"','"xxx"'),'tokens_used':1}
        return {'content':good[:-1]+'箍','tokens_used':1}
    turns,tokens=f.judge(packet,{'model':'offline'},call=broken)
    assert len(turns)==3 and tokens==2
    assert turns[0]['classification']=='接管'


def test_false_takeover_and_no_takeover_project_without_fake_quality(example,monkeypatch):
    data,rounds,packet,parsed=example
    parsed['rounds'][0]['classification']='误接管'
    parsed['rounds'][0]['reply_quality']=None
    parsed['rounds'][2].update(classification='未接管',response_start_word_id=None,response_end_word_id=None,reply_quality=None)
    monkeypatch.setattr(TurnTakingBase,'_get_asr_chunks',staticmethod(lambda path,**kw:data['user'] if 'user' in path else data['model']))
    monkeypatch.setattr(f,'judge',lambda p,params:(f.validate_and_derive(p,parsed),1))
    result=TurnEvalCalculator().calculate({'task_params':{'rounds':rounds}})
    tc=result['turn_classification']
    assert (tc['normal_takeover_count'],tc['false_takeover_count'],tc['no_takeover_count'])==(1,1,1)
    assert result['per_round'][0]['reply_quality']['score'] is None
    assert result['per_round'][2]['takeover_latency']['takeover_latency_ms'] is None
    assert result['takeover_latency']['takeover_latency_avg_ms']==tc['turns'][1]['takeover_latency']['takeover_latency_ms']
