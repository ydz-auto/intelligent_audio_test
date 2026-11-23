import copy,json
from pathlib import Path
import pytest
from app.services.calculators.xiaoyi_metrics.turn_eval import full_timeline_judge as f
from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator
from app.services.calculators.xiaoyi_metrics.turn_taking.strategy import TurnTakingBase
from app.services.calculators.xiaoyi_metrics.shared.constants import AsrStatus


def _patch_asr(monkeypatch, path_map):
    """同时打桩普通 ASR 与带状态 ASR（turn_eval 走带状态入口）。"""
    def asr(path, **kwargs):
        chunks = path_map.get(path)
        return chunks

    def asr_with_status(path, **kwargs):
        chunks = asr(path, **kwargs)
        return chunks, (AsrStatus.OK if chunks else AsrStatus.EMPTY)

    monkeypatch.setattr(TurnTakingBase, '_get_asr_chunks', staticmethod(asr))
    monkeypatch.setattr(TurnTakingBase, '_get_asr_chunks_with_status', staticmethod(asr_with_status))

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


def test_backchannel_rate_counts_case_once():
    packet={'full_word_timeline':[
        {'word_id':'M00000','speaker':'model','text':'嗯','start':1.0,'end':1.2},
        {'word_id':'M00001','speaker':'model','text':'好','start':2.0,'end':2.2},
    ]}
    turns=[
        {'turn_index':0,'round_number':0,'classification':f.BACKCHANNEL_LABEL,
         'response_start_word_id':'M00000','response_end_word_id':'M00000',
         'user_start_s':0.5,'user_end_s':1.5},
        {'turn_index':1,'round_number':1,'classification':f.BACKCHANNEL_LABEL,
         'response_start_word_id':'M00001','response_end_word_id':'M00001',
         'user_start_s':1.5,'user_end_s':2.5},
    ]
    feedback=f.collect_backchannel_feedback(packet,turns)
    assert feedback['backchannel_turn_count']==2
    assert feedback['backchannel_case_count']==1
    assert feedback['total_cases']==1
    assert feedback['backchannel_rate']==1

    result={'turn_classification':{'backchannel_count':2},'reasons':{}}
    f.apply_backchannel_case_metrics(result,turns,feedback)
    assert result['turn_classification']['backchannel_case_count']==1
    assert result['turn_classification']['backchannel_case_total']==1
    assert result['turn_classification']['backchannel_rate']==1
    assert '命中1个用例 / 总用例数1个' in result['reasons']['backchannel_rate']


def test_backchannel_form_limit_rejects_long_feedback():
    def packet_and_row(user_words, model_words):
        packet=f.build_input(user_words, model_words, [{'query':'用户正在表达'}])
        model_ids=[w['word_id'] for w in packet['full_word_timeline'] if w['speaker']=='model']
        row={
            'round_number':0,
            'user_start_word_id':'U00000',
            'user_end_word_id':f"U{len(user_words)-1:05d}",
            'response_start_word_id':model_ids[0],
            'response_end_word_id':model_ids[-1],
            'classification':f.BACKCHANNEL_LABEL,
            'has_backchannel':True,
            'alignment_reason':'用户仍在表达',
            'response_start_reason':'模型短反馈与用户语音重叠',
            'reason':'仅短反馈，无实质回答',
            'false_takeover_triggers':[],
        }
        return packet,{'rounds':[row]}

    # 6个中文字符以内，符合新形式标准。
    packet,parsed=packet_and_row(
        [{'text':'我','timestamp':[0.0,0.4]},{'text':'在说','timestamp':[0.4,1.5]}],
        [{'text':'明白','timestamp':[0.8,1.0]}],
    )
    turns=f.validate_and_derive(packet,parsed)
    assert turns[0]['classification']==f.BACKCHANNEL_LABEL

    # 超过6个中文字符且超过1.5秒，不能作为整轮backchannel。
    packet,parsed=packet_and_row(
        [{'text':'我','timestamp':[0.0,0.5]},{'text':'在说','timestamp':[0.5,3.0]}],
        [{'text':'明白了你的意思','timestamp':[0.8,2.5]}],
    )
    with pytest.raises(ValueError,match='Backchannel must be'):
        f.validate_and_derive(packet,parsed)


def test_truncated_substantive_takeover_cannot_use_backchannel_label():
    # 语义/接管判定由 full_timeline LLM 依据 prompt 完成；
    # 本地只校验形式，不能把“片段短”本身当作接管证据。
    packet=f.build_input(
        [{'text':'我想问问怎么安排','timestamp':[0.0,3.0]}],
        [{'text':'建议你可以先','timestamp':[1.0,1.4]}],
        [{'query':'我想问问怎么安排'}],
    )
    parsed={'rounds':[{
        'round_number':0,
        'user_start_word_id':'U00000',
        'user_end_word_id':'U00000',
        'response_start_word_id':'M00000',
        'response_end_word_id':'M00000',
        'classification':f.BACKCHANNEL_LABEL,
        'has_backchannel':True,
        'alignment_reason':'用户仍在表达',
        'response_start_reason':'模型短片段与用户语音重叠',
        'reason':'片段较短，判定为短反馈',
        'false_takeover_triggers':[],
    }]}
    turns=f.validate_and_derive(packet,parsed)
    assert turns[0]['classification']==f.BACKCHANNEL_LABEL


def test_backchannel_can_coexist_with_normal_takeover_and_project_by_round():
    packet=f.build_input(
        [{'text':'你','timestamp':[0.0,0.3]},{'text':'好','timestamp':[0.3,1.0]}],
        [{'text':'嗯','timestamp':[0.5,0.7]},{'text':'建议这样','timestamp':[1.1,1.8]}],
        [{'query':'给我建议'}],
    )
    parsed={'rounds':[{
        'round_number':0,'user_start_word_id':'U00000','user_end_word_id':'U00001',
        'response_start_word_id':'M00000','response_end_word_id':'M00001',
        'substantive_response_start_word_id':'M00001',
        'classification':'接管','has_backchannel':True,
        'alignment_reason':'用户完整表达请求','response_start_reason':'模型先嗯后给出建议',
        'reason':'先短反馈后给出实质建议','false_takeover_triggers':[],
        'reply_quality':{'score':4,'reason':'给出了建议'},
    }]}
    turns=f.validate_and_derive(packet,parsed)
    assert turns[0]['classification']=='接管'
    assert turns[0]['has_backchannel'] is True
    assert turns[0]['takeover_latency']['takeover_latency_ms']==100.0
    assert turns[0]['takeover_latency']['ai_first_word_start_ms']==1100.0
    assert turns[0]['takeover_latency']['latency_start_word_id']=='M00001'
    assert turns[0]['takeover_latency']['backchannel_start_ms']==500.0
    assert turns[0]['takeover_latency']['backchannel_start_word_id']=='M00000'
    feedback=f.collect_backchannel_feedback(packet,turns)
    assert feedback['backchannel_turn_count']==1
    assert feedback['backchannel_case_count']==1

    per_round=TurnEvalCalculator._build_per_round(2,[
        dict(turns[0],round_number=0),
        dict(turns[0],round_number=1,turn_index=2,classification='未接管',has_backchannel=False),
    ])
    assert per_round[0]['turn_classification']['has_backchannel'] is True
    assert per_round[1]['turn_classification']['has_backchannel'] is False


def test_quick_response_after_user_end_sets_latency_start_but_is_not_backchannel():
    packet=f.build_input(
        [{'text':'给我建议','timestamp':[0.0,1.0]}],
        [
            {'text':'嗯','timestamp':[0.2,0.3]},
            {'text':'好的','timestamp':[1.2,1.4]},
            {'text':'建议这样','timestamp':[1.6,2.0]},
        ],
        [{'query':'给我建议'}],
    )
    parsed={'rounds':[{
        'round_number':0,'user_start_word_id':'U00000','user_end_word_id':'U00000',
        'response_start_word_id':'M00000','response_end_word_id':'M00002',
        'quick_response_start_word_id':'M00001',
        'substantive_response_start_word_id':'M00002',
        'classification':'接管','has_backchannel':True,
        'alignment_reason':'用户完整表达请求',
        'response_start_reason':'用户说话期间有重叠backchannel，用户说完后先快回复再给出建议',
        'reason':'针对完整请求给出实质建议','false_takeover_triggers':[],
        'reply_quality':{'score':4,'reason':'给出了建议'},
    }]}
    turns=f.validate_and_derive(packet,parsed)
    assert turns[0]['has_backchannel'] is True
    assert turns[0]['quick_response_start_word_id']=='M00001'
    assert turns[0]['substantive_response_start_word_id']=='M00002'
    assert turns[0]['takeover_latency']['latency_start_kind']=='quick_response'
    assert turns[0]['takeover_latency']['latency_start_word_id']=='M00001'
    assert turns[0]['takeover_latency']['takeover_latency_ms']==200.0
    assert turns[0]['takeover_latency']['backchannel_start_word_id']=='M00000'


def test_whole_case_bypasses_local_segmentation_and_projects_contract(example,monkeypatch):
    data,rounds,_,parsed=example
    _patch_asr(monkeypatch, {'raw_user.wav': data['user'], 'raw_model.wav': data['model']})
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
    _patch_asr(monkeypatch, {'raw_user.wav': data['user'], 'raw_model.wav': data['model']})
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

    def asr_with_status(path, **kwargs):
        chunks = asr(path, **kwargs)
        return chunks, (AsrStatus.OK if chunks else AsrStatus.EMPTY)

    monkeypatch.setattr(audio_alignment, 'generate_aligned_clean_audio', align)
    monkeypatch.setattr(TurnTakingBase, '_get_asr_chunks', staticmethod(asr))
    monkeypatch.setattr(TurnTakingBase, '_get_asr_chunks_with_status', staticmethod(asr_with_status))

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
    _patch_asr(monkeypatch, {'raw_user.wav': data['user'], 'raw_model.wav': data['model']})
    monkeypatch.setattr(f,'judge',lambda p,params:(f.validate_and_derive(p,parsed),1))
    result=TurnEvalCalculator().calculate({'task_params':{'rounds':rounds}})
    tc=result['turn_classification']
    assert (tc['normal_takeover_count'],tc['false_takeover_count'],tc['no_takeover_count'])==(1,1,1)
    assert result['per_round'][0]['reply_quality']['score'] is None
    assert result['per_round'][2]['takeover_latency']['takeover_latency_ms'] is None
    assert result['takeover_latency']['takeover_latency_avg_ms']==tc['turns'][1]['takeover_latency']['takeover_latency_ms']


def test_confirmed_silent_model_asr_is_allowed_but_missing_or_failed_is_rejected():
    user=[{'text':'你','timestamp':[0.0,0.4]}]
    rounds=[{'query':'你叫什么'}]
    packet=f.build_input(user,[],rounds,AsrStatus.EMPTY)
    assert packet['model_asr']=={'status':'empty','word_count':0}
    with pytest.raises(ValueError,match='ai_wav missing'):
        f.build_input(user,[],rounds,AsrStatus.FILE_MISSING)
    with pytest.raises(ValueError,match='ASR call failed'):
        f.build_input(user,[],rounds,AsrStatus.FAILED)
    with pytest.raises(ValueError,match='Model ASR absent'):
        f.build_input(user,[],rounds)


def test_confirmed_silence_coerces_llm_rows_to_no_takeover():
    user=[{'text':'你','timestamp':[0.0,0.3]},{'text':'叫什么','timestamp':[0.3,1.0]}]
    packet=f.build_input(user,[],[{'query':'你叫什么'}],AsrStatus.EMPTY)
    llm_row={
        'round_number':0,'user_start_word_id':'U00000','user_end_word_id':'U00001',
        'response_start_word_id':'M00000','response_end_word_id':'M00000',
        'classification':'接管','has_backchannel':True,
        'alignment_reason':'用户完整提问','response_start_reason':'模型作答','reason':'模型回答了问题',
        'reply_quality':{'score':5,'reason':'完整回答'},
    }
    content=json.dumps({'rounds':[llm_row]},ensure_ascii=False)
    turns,_=f.judge(packet,{'model':'offline'},call=lambda **kw:{'content':content,'tokens_used':1})
    assert turns[0]['classification']=='未接管'
    assert turns[0]['has_ai_reply'] is False
    assert turns[0]['has_backchannel'] is False
    assert turns[0]['false_takeover']['false_takeover']==0
    assert turns[0]['response_start_word_id'] is None


def test_silent_model_projects_no_takeover_rates(monkeypatch):
    user=[{'text':'你','timestamp':[0.0,0.4]},{'text':'叫什么','timestamp':[0.4,1.2]}]
    rounds=[{'query':'你叫什么','user_wav':'raw_user.wav','ai_wav':'raw_model.wav'}]
    _patch_asr(monkeypatch,{'raw_user.wav':user,'raw_model.wav':[]})

    def judge(packet,params):
        parsed={'rounds':[{
            'round_number':0,'user_start_word_id':'U00000','user_end_word_id':'U00001',
            'classification':'未接管','has_backchannel':False,
            'alignment_reason':'用户完整提问','response_start_reason':'无可确认的本轮回应首词',
            'reason':'模型通道ASR成功但整段无模型词','false_takeover_triggers':[],
        }]}
        return f.validate_and_derive(packet,parsed),1

    monkeypatch.setattr(f,'judge',judge)
    result=TurnEvalCalculator().calculate({'task_params':{'rounds':rounds}})
    tc=result['turn_classification']
    assert tc['no_takeover_count']==1
    assert tc['no_takeover_rate']==1.0
    assert tc['takeover_rate']==0
    assert tc['total_turns']==1
