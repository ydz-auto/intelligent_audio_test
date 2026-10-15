import importlib.util
import copy
import unittest
import sys
import json
from unittest.mock import patch
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
if not (PROJECT/'app').is_dir(): PROJECT=Path('D:/work/20260630/eval_server')
FILE=PROJECT/'app/services/calculators/xiaoyi_metrics/interruptibility/full_timeline_judge.py'
spec=importlib.util.spec_from_file_location('full_judge',FILE)
j=importlib.util.module_from_spec(spec);spec.loader.exec_module(j)

class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.packet=j.build_input([{'text':'停','timestamp':[1,2]}],
            [{'text':'旧','timestamp':[1.1,1.5]},{'text':'好','timestamp':[1.999,2.2]}],
            [{'round':1,'role':'打断','query':'停'}])
        self.raw={'round_details':[{'round':1,'behavior':'回复','behavior_reason':'好是承接语',
            'alignment':{'status':'matched','reason':'实际停','user_start_word_id':'U0000',
             'user_end_word_id':'U0000','start_boundary_valid':True,'end_boundary_valid':True},
            'response_start_word_id':'M0001','last_old_content_word_id':'M0000'}]}
    def test_real_negative_one_is_not_missing(self):
        r=j.validate_and_derive(self.packet,self.raw)
        self.assertIsNone(r['aggregate']['reply_latency']['avg_ms'])
        self.assertEqual(r['aggregate']['reply_latency']['valid_count'],1)
    def test_round_missing_or_duplicate_rejected(self):
        self.raw['round_details']*=2
        with self.assertRaises(ValueError):j.validate_and_derive(self.packet,self.raw)
    def test_fabricated_id_rejected(self):
        self.raw['round_details'][0]['response_start_word_id']='M9999'
        with self.assertRaises(ValueError):j.validate_and_derive(self.packet,self.raw)
    def test_partial_end_not_timed(self):
        self.raw['round_details'][0]['alignment']['end_boundary_valid']=False
        self.assertIsNone(j.validate_and_derive(self.packet,self.raw)['round_details'][0]['timing']['reply_latency_ms'])
    def test_aggregate_claim_recomputed(self):
        self.raw['aggregate']={'total_rounds':300}
        r=j.validate_and_derive(self.packet,self.raw)
        self.assertEqual(r['aggregate']['total_rounds'],1)
        self.assertFalse(r['validation']['llm_aggregate_matches'])
    def test_stopped_without_confirmation(self):
        self.packet['scheduled_rounds'][0]['role']='停止'
        self.packet['full_word_timeline']=self.packet['full_word_timeline'][:2]
        row=self.raw['round_details'][0];row['response_start_word_id']=None
        row['stop_review']={'stop_status':'stopped','stop_reason':'停止旧内容',
             'last_original_content_word_id':'M0000'}
        r=j.validate_and_derive(self.packet,self.raw)['round_details'][0]
        self.assertTrue(r['stop_complied'])
        self.assertEqual(r['stop_review']['original_content_stop_latency_ms'],500)
        self.assertIsNone(r['stop_review']['confirmation_reply_latency_ms'])
    def test_not_stopped_has_no_success_stop_latency(self):
        self.packet['scheduled_rounds'][0]['role']='停止'
        row=self.raw['round_details'][0];row['behavior']='恢复';row['response_start_word_id']=None
        row['stop_review']={'stop_status':'not_stopped','stop_reason':'持续讲旧内容'}
        r=j.validate_and_derive(self.packet,self.raw)['round_details'][0]
        self.assertFalse(r['stop_complied'])
        self.assertIsNone(r['stop_review']['original_content_stop_latency_ms'])
    def test_input_has_no_local_round_slice(self):
        self.assertNotIn('window',self.packet['scheduled_rounds'][0])
        self.assertNotIn('model_words',self.packet['scheduled_rounds'][0])
    def test_wrong_speaker_reference_rejected(self):
        self.raw['round_details'][0]['response_start_word_id']='U0000'
        with self.assertRaises(ValueError):j.validate_and_derive(self.packet,self.raw)
    def test_resume_role_excluded_from_ordinary_aggregate(self):
        self.packet['scheduled_rounds'][0]['role']='恢复原话题'
        self.raw['round_details'][0].update(behavior='',topic_resumed=True)
        result=j.validate_and_derive(self.packet,self.raw)
        self.assertEqual(result['aggregate']['ordinary_rounds'],0)
        self.assertEqual(result['aggregate']['resume_rounds'],1)
        self.assertEqual(result['aggregate']['round_reply_latencies'],[])
    def test_waiting_claim_with_later_speech_rejected(self):
        self.packet['scheduled_rounds'][0]['role']='停止'
        self.packet['scheduled_rounds'].append({'round':2,'role':'打断','script_text':'继续'})
        self.packet['full_word_timeline'] += [dict(word_id='U0001',speaker='query',text='继续',start=5,end=6),
            dict(word_id='M0002',speaker='answer',text='又说',start=3,end=4)]
        row=self.raw['round_details'][0]
        row['stop_review']={'stop_status':'stopped','stop_reason':'好后等待',
            'confirmation_start_word_id':'M0001','last_confirmation_word_id':'M0001',
            'last_original_content_word_id':'M0000'}
        second=copy.deepcopy(row);second.update(round=2,behavior=None,response_start_word_id=None,last_old_content_word_id=None)
        second['alignment'].update(status='not_found',user_start_word_id='U0001',user_end_word_id='U0001')
        self.raw['round_details'].append(second)
        with self.assertRaises(ValueError):j.validate_and_derive(self.packet,self.raw)
    def test_adapter_preserves_same_round_timing_in_legacy_projection(self):
        rm_path=FILE.with_name('round_metrics.py')
        rm_spec=importlib.util.spec_from_file_location('round_metrics_test',rm_path)
        rm=importlib.util.module_from_spec(rm_spec);rm_spec.loader.exec_module(rm)
        packet=self.packet
        normalized=j.validate_and_derive(packet,self.raw)
        normalized.update(model='test',tokens_used=1)
        source={'user_segments':[{'words':[{'text':'停','timestamp':[1,2]}]}],
                'model_segments':[{'words':[{'text':'旧','timestamp':[1.1,1.5]},{'text':'好','timestamp':[1.999,2.2]}]}]}
        module_name='app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics'
        with patch.dict(sys.modules,{module_name:rm}),patch.object(j,'judge_full_timeline',return_value=normalized) as remote:
            result=j.attach_full_timeline(source,[{'round':1,'role':'打断','query':'停'}],{}, {})
        self.assertEqual(remote.call_count,1)
        self.assertIsNone(result['reply_latency_avg_ms'])
        self.assertEqual(result['round_details'][0]['reply_latency_ms'],-1)
        self.assertEqual(rm.build_per_round(2,result['round_details'])[1]['interruption']['reply_latency_avg_ms'],-1)
    def test_unknown_gate_does_not_leak_claimed_score_or_valid_start(self):
        self.raw['round_details'][0]['alignment']['status']='ambiguous'
        self.raw['round_details'][0]['score']={'overall':5}
        r=j.validate_and_derive(self.packet,self.raw)['round_details'][0]
        self.assertIsNone(r['behavior'])
        self.assertIsNone(r['response_start_word_id'])
        self.assertNotIn('score',r)
        self.assertEqual(r['llm_behavior_claim'],'回复')
    def test_schema_embeds_stop_and_resume_fields_without_extra_rows(self):
        self.packet['scheduled_rounds']=[dict(round=1,role='停止',script_text='停'),
                                         dict(round=2,role='恢复原话题',script_text='继续')]
        schema=j.build_output_schema(self.packet)
        self.assertEqual(len(schema['round_details']),2)
        self.assertIn('stop_review',schema['round_details'][0])
        self.assertNotIn('topic_resumed',schema['round_details'][0])
        self.assertIn('topic_resumed',schema['round_details'][1])
        self.assertEqual(schema['aggregate']['total_rounds'],2)
    def test_string_fragments_in_round_array_are_rejected(self):
        self.raw['round_details'].append('topic_resumed:true')
        with self.assertRaisesRegex(ValueError,'non-object'):
            j.validate_and_derive(self.packet,self.raw)

def test_real_calculator_dispatches_once_and_projects_same_negative_latency():
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import InterruptionMetricsCalculator
    raw={'round_details':[dict(round=1,behavior='回复',behavior_reason='好是承接',
        alignment=dict(status='matched',reason='实际换话题',user_start_word_id='U0000',
            user_end_word_id='U0000',start_boundary_valid=True,end_boundary_valid=True),
        response_start_word_id='M0001',last_old_content_word_id='M0000')]}
    params=dict(user_asr=[dict(text='换话题',timestamp=[1,2])],
        model_asr=[dict(text='旧',timestamp=[1.1,1.5]),dict(text='好',timestamp=[1.999,2.2])],
        interruption_rounds=[1],rounds=[dict(is_interruption=True,query='初始'),dict(query='换话题')])
    with patch('app.services.calculators.xiaoyi_metrics.shared.llm_client.call_llm',
               return_value=dict(content=json.dumps(raw,ensure_ascii=False),tokens_used=1)) as remote:
        result=InterruptionMetricsCalculator().run(params)
    assert remote.call_count==1
    packet=json.loads(remote.call_args.kwargs['prompt'])
    assert len(packet['full_word_timeline'])==3
    assert 'window' not in packet['scheduled_rounds'][0]
    assert result['interruption']['reply_latency_avg_ms'] is None
    assert 'aggregate' not in result['interruption']
    assert 'full_timeline_evaluation' not in result['interruption']
    assert set(result) == {'interruption', 'per_round'}
    assert result['interruption']['round_details'][0]['reply_latency_ms']==-1
    assert result['per_round'][1]['interruption']['reply_latency_avg_ms']==-1


if __name__=='__main__':unittest.main()
