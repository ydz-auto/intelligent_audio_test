import json
import pytest
from app.services.calculators.xiaoyi_metrics.env_judge import env_judge as m

@pytest.fixture
def setup(monkeypatch):
    calls=[]
    monkeypatch.setattr(m.os.path,'isfile',lambda p:bool(p))
    monkeypatch.setattr(m,'get_llm_config',lambda:{})
    monkeypatch.setattr(m,'get_asr_text',lambda p:'完全不同的措辞')
    monkeypatch.setattr(m,'_resolve_played_audio_path',lambda p:'reference.wav' if p else None)
    monkeypatch.setattr(m,'_calculate_response_latency',lambda *a:{'response_latency_ms':1250.0,'user_question_end_ms':2000.0,'model_first_word_start_ms':3250.0,'message':'OK'})
    def judge(**kw):
        calls.append(kw)
        return {'content':json.dumps({'understand_correct':True,'score':5,'reason':'语义正确'}),'tokens_used':1}
    monkeypatch.setattr(m,'call_llm_api',judge)
    return calls

def run():
    return m.evaluate_env_judge(ai_wav='ai.wav',user_wav='user.wav',correctAnswer='abcdefghijk',played_audios=[{'audio_path':'reference.wav'}],model='offline-test',env_type=True)

def test_low_overlap_does_not_override_judge_or_skip_latency(setup):
    r=run()
    assert r['text_similarity']==0
    assert len(setup)==1 and r['understand_correct'] is True and r['score']==5
    assert r['response_latency_ms']==1250
    assert r['ai_answer']=='完全不同的措辞'

def test_incorrect_answer_still_has_latency(setup,monkeypatch):
    monkeypatch.setattr(m,'call_llm_api',lambda **kw:{'content':json.dumps({'understand_correct':False,'score':1,'reason':'错误'})})
    r=run()
    assert r['understand_correct'] is False and r['response_latency_ms']==1250

@pytest.mark.parametrize('failure',['transport','json'])
def test_judge_failure_keeps_computed_latency(setup,monkeypatch,failure):
    def judge(**kw):
        if failure=='transport':raise RuntimeError('offline failure')
        return {'content':'invalid JSON'}
    monkeypatch.setattr(m,'call_llm_api',judge)
    r=run()
    assert r['response_latency_ms']==1250 and r['understand_correct'] is None
    assert '失败' in r['message']

def test_latency_failure_does_not_skip_judge(setup,monkeypatch):
    def timing(*a):raise RuntimeError('missing boundary')
    monkeypatch.setattr(m,'_calculate_response_latency',timing)
    r=run()
    assert len(setup)==1 and r['understand_correct'] is True
    assert r['response_latency_ms'] is None and 'missing boundary' in r['latency_message']

def test_missing_reference_keeps_scoring(setup,monkeypatch):
    monkeypatch.setattr(m,'_resolve_played_audio_path',lambda p:None)
    r=run()
    assert r['understand_correct'] is True and r['response_latency_ms'] is None
    assert 'no played_audios' in r['latency_message']


@pytest.mark.parametrize('env_type',[True,False])
def test_prompt_uses_audio_as_primary_evidence(env_type):
    prompt=m.build_env_judge_prompt('辅助参考', 'semantic' if env_type else 'non_semantic', model_output_text='')
    assert '音频为主要依据' in prompt
    assert '不能因ASR为空' in prompt
    assert '仅以' not in prompt
    assert '未获得ASR转写' in prompt
    assert '参考答案是正确答案' in prompt
    assert '辅助参考，可能存在转写误差' not in prompt


def test_asr_failure_still_sends_audio_to_judge(setup,monkeypatch):
    def broken_asr(*args): raise RuntimeError('ASR unavailable')
    monkeypatch.setattr(m,'get_asr_text',broken_asr)
    result=run()
    assert result['understand_correct'] is True
    assert setup[0]['file_paths']==['ai.wav']
    assert result['ai_answer']==''
