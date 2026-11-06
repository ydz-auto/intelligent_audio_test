import ast
import importlib.util
import pathlib
import tempfile
import unittest
import wave

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('audio_meta',ROOT/'app/utils/audio_metadata.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class AudioMetadataTests(unittest.TestCase):
    def test_header_duration_including_silence(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as tmp:
            path=pathlib.Path(tmp)/'silent.wav'
            with wave.open(str(path),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*24000)
            data=module.audio_metadata(path,'success')
            self.assertEqual(data['audio_duration_s'],1.5)
            self.assertEqual(data['voice_activity_status'],'not_measured')

    def test_missing_audio_does_not_invent_duration(self):
        data=module.audio_metadata('nonexistent_test.wav')
        self.assertIsNone(data['audio_duration_s'])
        self.assertEqual(data['asr_status'],'unknown')

    def test_parse_result_preserves_metadata_and_chunks(self):
        tree=ast.parse((ROOT/'app/utils/asr_adapter.py').read_text(encoding='utf8'))
        func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='parse_result')
        namespace={};exec(compile(ast.Module(body=[func],type_ignores=[]),'parse_result','exec'),namespace)
        chunks=[dict(text='好',timestamp=[1,1.2])]
        result=namespace['parse_result']([dict(text='好',chunks=chunks,audio_duration_s=5.0,asr_status='success')])
        self.assertEqual(result['chunks'],chunks)
        self.assertEqual(result['audio_duration_s'],5.0)
        self.assertEqual(result['asr_status'],'success')

if __name__=='__main__':unittest.main()
