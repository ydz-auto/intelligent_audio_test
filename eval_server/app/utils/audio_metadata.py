"""Read recording coverage without ASR or waveform inference."""
import os
import wave


def audio_metadata(wav_path, asr_status='unknown'):
    result = {'audio_duration_s': None, 'duration_source': None,
              'asr_status': asr_status, 'voice_activity_status': 'not_measured'}
    if not wav_path or not os.path.isfile(wav_path):
        result['duration_error'] = 'audio_file_missing'
        return result
    try:
        with wave.open(str(wav_path), 'rb') as audio:
            rate = audio.getframerate()
            if rate <= 0:
                raise ValueError('Invalid sample rate')
            result.update(audio_duration_s=audio.getnframes()/rate, duration_source='wav_header')
    except Exception:
        # Float WAV and WAV extensible are supported by soundfile when installed.
        try:
            import soundfile
            info = soundfile.info(str(wav_path))
            result.update(audio_duration_s=info.frames/info.samplerate, duration_source='audio_header')
        except Exception:
            result['duration_error'] = 'audio_header_unreadable'
    return result
