import copy
import importlib.util
import json
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'app/services/calculators/xiaoyi_metrics/env_judge'
spec = importlib.util.spec_from_file_location('round_judge', root/'rejection_rounds_v3.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class RoundJudgeTests(unittest.TestCase):
    def setUp(self):
        self.packet = mod.build_packet([{'text':'问题','timestamp':[1,2]}, {'text':'嗯','timestamp':[4,5]}],
            [{'text':'回答','timestamp':[3,6]}], [
                dict(configured_round_number=0,is_reject=False),
                dict(configured_round_number=7,is_reject=True)])
        self.rows=[]
        for config in self.packet['all_rounds']:
            reject=config['evaluate_rejection']
            self.rows.append(dict(config,alignment_status='matched',alignment_reason='ASR对齐',
                user_start_word_id='U0001' if reject else 'U0000',
                user_end_word_id='U0001' if reject else 'U0000',
                evaluation_status='evaluated' if reject else 'not_applicable',
                timing='回复过程中' if reject else None,behavior='恢复' if reject else None,
                evidence_word_ids=['M0000'],reason='同一原任务继续输出'))

    def run_judge(self,rows):
        def call(**kw):
            self.assertNotIn('file_paths',kw)
            self.assertEqual(json.loads(kw['prompt']),self.packet)
            return {'content':json.dumps({'round_details':rows},ensure_ascii=False)}
        return mod.judge(self.packet,call,'mock',8192,0)

    def test_original_numbers_and_no_audio(self):
        rows,_=self.run_judge(self.rows)
        self.assertEqual([r['configured_round_number'] for r in rows],[0,7])
        self.assertEqual(rows[1]['parent_intent_round_id'],'round_0')

    def test_missing_round_rejected(self):
        with self.assertRaises(ValueError): self.run_judge(self.rows[1:])

    def test_wrong_word_rejected(self):
        self.rows[1]['evidence_word_ids']=['M9999']
        with self.assertRaises(ValueError): self.run_judge(self.rows)

    def test_intent_cannot_be_scored(self):
        self.rows[0]['behavior']='回应'
        with self.assertRaises(ValueError): self.run_judge(self.rows)

    def test_unknown_keeps_round(self):
        self.rows[1].update(evaluation_status='unjudgeable',behavior=None,timing=None,
            alignment_status='not_found',user_start_word_id=None,user_end_word_id=None)
        rows,_=self.run_judge(self.rows)
        self.assertEqual(rows[1]['configured_round_number'],7)
        self.assertIsNone(rows[1]['behavior'])

    def test_renumbering_rejected(self):
        self.rows[1]['configured_round_number']=1
        with self.assertRaises(ValueError): self.run_judge(self.rows)

    def test_true_cannot_be_skipped_as_normal_intent(self):
        self.rows[1].update(evaluation_status='not_applicable',behavior=None,timing=None)
        with self.assertRaises(ValueError): self.run_judge(self.rows)

    def test_llm_cannot_change_is_reject(self):
        self.rows[1]['is_reject']=False
        with self.assertRaises(ValueError): self.run_judge(self.rows)

    def test_false_is_not_reclassified_by_question_text(self):
        self.assertIs(self.packet['all_rounds'][0]['is_reject'],False)
        self.assertEqual(self.packet['all_rounds'][0]['role'],'intent')
        self.assertEqual(self.run_judge(self.rows)[0][0]['evaluation_status'],'not_applicable')

    def test_string_flag_in_llm_output_rejected(self):
        self.rows[1]['is_reject']='true'
        with self.assertRaises(ValueError): self.run_judge(self.rows)

if __name__=='__main__': unittest.main()
