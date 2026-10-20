import unittest

from asr_server.word_timestamps import paraformer_chunks


class WordTimestampsTests(unittest.TestCase):
    def test_bmi_word_timing_keeps_tail_and_boundaries(self):
        text = '体脂率怎么算？不是是BMI怎么算？'
        ts = [[i * 100, (i + 1) * 100] for i in range(13)]
        chunks = paraformer_chunks(text, ts)
        self.assertEqual(''.join(c['text'] for c in chunks), '体脂率怎么算不是是BMI怎么算')
        self.assertEqual(chunks[9], {'text': 'BMI', 'timestamp': [0.9, 1.0]})
        self.assertEqual([c['text'] for c in chunks[-3:]], list('怎么算'))
        self.assertEqual(chunks[-1]['timestamp'], [1.2, 1.3])

    def test_actual_character_timing_is_not_merged(self):
        chunks = paraformer_chunks('BMI怎么算？', [[i, i + 1] for i in range(6)])
        self.assertEqual([c['text'] for c in chunks], list('BMI怎么算'))

    def test_chinese_punctuation_and_spaces(self):
        chunks = paraformer_chunks(' 好，的！ ', [[0, 100], [200, 300]])
        self.assertEqual([c['text'] for c in chunks], ['好', '的'])

    def test_missing_intervals_fail_instead_of_silent_truncation(self):
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            paraformer_chunks('BMI怎么算', [[0, 100]])

    def test_extra_intervals_and_invalid_values_fail(self):
        for text, ts in [('好', [[0, 1], [2, 3]]), ('好', [[2, 1]]),
                         ('好', [[0, float('nan')]])]:
            with self.subTest(ts=ts), self.assertRaises(ValueError):
                paraformer_chunks(text, ts)

    def test_empty_audio(self):
        self.assertEqual(paraformer_chunks('', []), [])


if __name__ == '__main__':
    unittest.main()
