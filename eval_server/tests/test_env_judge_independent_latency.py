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
    assert r['understand_correct'] is True and r['response_latency_ms']==1250


@pytest.mark.parametrize('env_type',[True,False])
def test_prompt_uses_audio_as_primary_evidence(env_type):
    prompt=m.build_env_judge_prompt('辅助参考', 'semantic' if env_type else 'non_semantic', model_output_text='')
    assert '音频为主要依据' in prompt
    assert '不能因ASR为空' in prompt
    assert '仅以' not in prompt
    assert '未获得ASR转写' in prompt
    assert '参考答案是正确答案' in prompt
    assert '辅助参考，可能存在转写误差' not in prompt


def test_asr_failure_is_evaluation_exception(setup,monkeypatch):
    def broken_asr(*args): raise RuntimeError('ASR unavailable')
    monkeypatch.setattr(m,'get_asr_text',broken_asr)
    result=run()
    assert result.get('is_success') is not False
    assert result['excluded_from_statistics'] is True
    assert not setup
    assert result['ai_answer']==''


@pytest.mark.parametrize('side',['user.wav','ai.wav'])
def test_empty_asr_is_exception_not_business_failure(setup,monkeypatch,side):
    monkeypatch.setattr(m,'get_asr_text',lambda path:'  ' if path==side else '有效文字')
    result=run()
    assert result.get('is_success') is not False and result['enabled'] is True
    assert result['excluded_from_statistics'] is True
    assert result['understand_correct'] is None and result['score'] is None
    assert '评估异常' in result['message'] and not setup


@pytest.mark.parametrize('latency',[-1,-2000,0])
def test_negative_latency_exception_zero_valid(setup,monkeypatch,latency):
    monkeypatch.setattr(m,'_calculate_response_latency',lambda *args:{'response_latency_ms':latency,'message':'OK'})
    result=run()
    if latency<0:
        assert result.get('is_success') is not False and not setup
        assert result['excluded_from_statistics'] is True
        assert result['raw_response_latency_ms']==latency
        assert result['response_latency_ms'] is None and result['score'] is None
    else:
        assert result['score']==5 and result['response_latency_ms']==0


@pytest.mark.parametrize('question_chunks',[[]])
def test_missing_actual_query_has_no_environment_end_fallback(monkeypatch,question_chunks):
    import numpy as np
    monkeypatch.setattr(m.os.path,'isfile',lambda p:True)
    monkeypatch.setattr(m,'_load_audio',lambda p:(1000,np.ones(5000)))
    monkeypatch.setattr(m,'_detect_speech_region',lambda *a:(0,1000))
    monkeypatch.setattr(m,'_coarse_to_fine_align',lambda *a:(0,1))
    monkeypatch.setattr(m,'get_asr_chunks',lambda p:question_chunks)
    result=m._calculate_response_latency('ref.wav','user.wav','ai.wav')
    if question_chunks:
        assert result.get('is_success') is not False
        assert '用户ASR有内容' in result['message']
    else:
        assert result['is_success'] is False
    assert result['user_question_end_ms'] is None


def test_early_reply_not_hidden_by_later_words(monkeypatch):
    import numpy as np
    monkeypatch.setattr(m.os.path,'isfile',lambda p:True)
    monkeypatch.setattr(m,'_load_audio',lambda p:(1000,np.ones(5000)))
    monkeypatch.setattr(m,'_detect_speech_region',lambda *a:(0,1000))
    monkeypatch.setattr(m,'_coarse_to_fine_align',lambda *a:(0,1))
    monkeypatch.setattr(m,'get_asr_chunks',lambda p: (
        [{'text':'问','timestamp':[2,3]}] if p=='user.wav' else
        [{'text':'答','timestamp':[2.5,2.8]},{'text':'尾','timestamp':[4,5]}]))
    result=m._calculate_response_latency('ref.wav','user.wav','ai.wav')
    assert result['is_success'] is False
    assert result['raw_response_latency_ms']==-500
    assert result['response_latency_ms'] is None


def test_earlier_round_exception_survives_later_valid_round(monkeypatch):
    from app.services.calculators.base import BaseCalculator
    from app.services.calculators.xiaoyi_metrics.env_judge.strategy import EnvJudgeCalculator
    monkeypatch.setattr(BaseCalculator,'_calculate_per_round',lambda *a:[
        {'is_success':False,'message':'评估异常：query ASR为空','score':None,'round_number':0},
        {'score':5,'round_number':1}])
    calc=EnvJudgeCalculator()
    calc._calculate_per_round({})
    assert calc._agg_result['is_success'] is False
    assert 'round=0' in calc._agg_result['message']


def test_excluded_case_completes_with_all_round_statistics_empty(monkeypatch):
    from app.services.calculators.base import BaseCalculator
    from app.services.calculators.xiaoyi_metrics.env_judge.strategy import EnvJudgeCalculator
    monkeypatch.setattr(BaseCalculator,'_calculate_per_round',lambda *a:[
        {'excluded_from_statistics':True,'message':'评估异常：query ASR为空','round_number':0},
        {'score':5,'understand_correct_pass':1,'response_latency_ms':100,'round_number':1}])
    calc=EnvJudgeCalculator()
    rows=calc._calculate_per_round({})
    assert calc._agg_result.get('is_success') is not False
    assert calc._agg_result['excluded_from_statistics'] is True
    assert all(r['score'] is None and r['understand_correct_pass'] is None
               and r['response_latency_ms'] is None for r in rows)


def test_hj001_wrong_audio_path_never_used_for_alignment(setup,monkeypatch):
    monkeypatch.setattr(m,'_calculate_response_latency',original_latency)
    monkeypatch.setattr(m,'_resolve_played_audio_path',lambda p:'HJ018.wav')
    def unexpected_load(path):
        raise AssertionError('wrong audio must not reach FFT')
    monkeypatch.setattr(m,'_load_audio',unexpected_load)
    monkeypatch.setattr(m,'get_asr_chunks',lambda p: (
        [{'text':'刚才是什么声音','timestamp':[60.41,61.735]}] if p=='user.wav'
        else [{'text':'嗯','timestamp':[64,64.3]}]))
    result=m.evaluate_env_judge(user_wav='user.wav',ai_wav='ai.wav',
        played_audios=[{'audio_name':'HJ001.wav','audio_path':'HJ018.wav'}],
        correctAnswer='键盘声',model='offline-test')
    assert len(setup)==1 and result['score']==5
    assert result.get('excluded_from_statistics') is not True
    assert result['response_latency_ms']==2265


def test_nonempty_query_with_unmatched_timing_keeps_content_scoring(setup,monkeypatch):
    monkeypatch.setattr(m,'_calculate_response_latency',lambda *a:{
        'response_latency_ms':None,
        'message':'时延不可计算：用户ASR有内容，但环境声定位与用户词时间不匹配'})
    result=run()
    assert result['score']==5 and result['understand_correct'] is True
    assert result.get('excluded_from_statistics') is not True
    assert result.get('is_success') is not False
    assert result['response_latency_ms'] is None


# Keep a reference before fixtures replace the latency function.
original_latency=m._calculate_response_latency


def test_navigation_and_earlier_reply_do_not_belong_to_question(monkeypatch):
    user=[{'text':'靠右侧行驶往苏州南通方向','timestamp':[4.73,10.315]},
          {'text':'刚刚说了什么内容','timestamp':[37.64,39.075]}]
    model=[{'text':'听起来你正在高速路上导航','timestamp':[12.35,20]},
           {'text':'刚刚是提示你先靠右侧行驶','timestamp':[40.31,47.375]}]
    monkeypatch.setattr(m,'get_asr_chunks',lambda p:user if p=='user' else model)
    result=m._calculate_response_latency(None,'user','model')
    assert result['user_question_text']=='刚刚说了什么内容'
    assert result['user_question_start_ms']==37640
    assert result['user_question_end_ms']==39075
    assert result['model_first_word_start_ms']==40310
    assert result['response_latency_ms']==1235


def test_real_early_reply_to_final_question_remains_negative(monkeypatch):
    user=[{'text':'导航播报','timestamp':[4,10]},
          {'text':'刚刚说了什么内容','timestamp':[37,39]}]
    model=[{'text':'之前的回答','timestamp':[12,20]},
           {'text':'提前回答','timestamp':[38,41]}]
    monkeypatch.setattr(m,'get_asr_chunks',lambda p:user if p=='user' else model)
    r=m._calculate_response_latency(None,'user','model')
    assert r['is_success'] is False and r['raw_response_latency_ms']==-1000


def test_mixed_single_chunk_does_not_fabricate_question_start(monkeypatch):
    monkeypatch.setattr(m,'get_asr_chunks',lambda p:[
        {'text':'导航播报刚刚说了什么内容','timestamp':[4,39]}])
    r=m._calculate_response_latency(None,'user','model')
    assert r['response_latency_ms'] is None and '同一ASR片段' in r['message']
