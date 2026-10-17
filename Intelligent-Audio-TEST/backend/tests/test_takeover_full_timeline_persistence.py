"""Isolated SQLite regression for the full-timeline save contract (no production DB)."""
import copy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pytest
from sqlalchemy import create_engine,Column,Integer,Float,String,JSON
from sqlalchemy.orm import declarative_base,Session
from backend.services.evaluation import takeover_persistence as m
Base=declarative_base()
class Row(Base):
    __tablename__='rounds'
    id=Column(Integer,primary_key=True);test_result_id=Column(Integer);dimension_id=Column(Integer);round_number=Column(Integer)
    algorithm_type=Column(String);dimension_value=Column(Float);score=Column(Float);status=Column(String);evaluation_status=Column(String);error_message=Column(String)
    api_raw_response=Column(JSON);api_request_body=Column(JSON)
class Result(Base):
    __tablename__='results'
    id=Column(Integer,primary_key=True);algorithm_type=Column(String);result_data=Column(JSON);result_data_path=Column(String)
class Parser:
    def parse_dimension_result(self,payload,dim):
        value=payload
        for part in dim['path'].split('.'):value=value.get(part) if isinstance(value,dict) else None
        return value,value

def output(n=2,false=False):
    turns=[dict(round_number=i,classification='误接管' if false else '接管',takeover_latency=None if false else {'takeover_latency_ms':100},reply_quality=None if false else {'score':4}) for i in range(n)]
    count=0 if false else n;tc=dict(summary='new',turns=turns,total_turns=n,normal_takeover_count=count,no_takeover_count=0,false_takeover_count=n-count)
    per=[dict(round_number=i,turn_classification=dict(turns=[copy.deepcopy(t)],normal_takeover_count=0 if false else 1),takeover_latency={'takeover_latency_avg_ms':None if false else 100}) for i,t in enumerate(turns)]
    return dict(evaluation_mode='full_timeline',per_round_native=True,turn_classification=tc,per_round=per,full_timeline_input={'full_word_timeline':[{'word_id':'U0','text':'新'}],'scheduled_rounds':[{'round_number':i} for i in range(n)]},takeover_latency={'takeover_latency_ms':None if false else 100},reply_quality={'score':None if false else 4})
@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(m,'TestResultDimension',Row)
    from backend.utils.common import result_data_store
    monkeypatch.setattr(result_data_store,'load_full_result_data',lambda data,path:data)
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as s:
        r=Result(id=1,algorithm_type='voice_llm',result_data={'evaluation_data':{'tc_turns':['old'],'other':7,'llm_round_evaluations':['KEEP_INTERRUPTION']},'algorithm_results':[{'param_code':'record_file','value':'keep'}]},result_data_path='old-file')
        s.add(r);s.add_all([Row(test_result_id=1,dimension_id=1,round_number=None),Row(test_result_id=1,dimension_id=2,round_number=None),Row(test_result_id=1,dimension_id=2,round_number=9,dimension_value=999)])
        s.commit()
        group=[({'id':1,'name':'接管率','path':'turn_classification.normal_takeover_count','output_params':[{'field_path':'turn_classification.normal_takeover_count','param_code':'count','output_role':'main'}]},1),({'id':2,'name':'时延','path':'takeover_latency.takeover_latency_avg_ms','output_params':[]},2)]
        yield s,r,group

def test_repeated_save_replaces_nulls_and_removes_old_rounds(env):
    s,r,g=env;m.persist(Parser(),s,r,output(),g,{});s.commit()
    m.persist(Parser(),s,r,output(1,True),g,{});s.commit();s.expire_all()
    assert r.result_data_path is None
    assert r.result_data['evaluation_data']['other']==7
    assert r.result_data['evaluation_data']['llm_round_evaluations']==['KEEP_INTERRUPTION']
    assert r.result_data['evaluation_data']['te_reply_quality_score'] is None
    assert len(r.result_data['evaluation_data']['tc_turns'])==1
    assert all(x.round_number in [None,0] for x in s.query(Row).all())
    assert all(x.dimension_value is None for x in s.query(Row).filter(Row.dimension_id==2))
    assert any(a.get('value')=='keep' for a in r.result_data['algorithm_results'])

def test_failure_clears_success_snapshot(env):
    s,r,g=env;m.persist(Parser(),s,r,output(),g,{});s.commit();m.invalidate(s,r,g,'failed');s.commit();s.expire_all()
    assert r.result_data['turn_eval_evaluation']['status']=='failed'
    assert 'tc_turns' not in r.result_data['evaluation_data']
    assert all(x.dimension_value is None and x.evaluation_status=='failed' for x in s.query(Row))

def test_invalid_projection_is_rejected_without_commit(env):
    s,r,g=env;p=output();p['per_round'][0]['turn_classification']['turns'][0]['classification']='误接管'
    with pytest.raises(ValueError,match='Projected turn'):m.persist(Parser(),s,r,p,g,{})
    s.rollback();assert r.result_data_path=='old-file'

def test_duplicate_old_rows_are_collapsed(env):
    s,r,g=env;s.add_all([Row(test_result_id=1,dimension_id=2,round_number=0,dimension_value=999),Row(test_result_id=1,dimension_id=2,round_number=0,dimension_value=888)]);s.commit()
    m.persist(Parser(),s,r,output(),g,{});s.commit()
    assert s.query(Row).filter(Row.dimension_id==2,Row.round_number==0).count()==1
