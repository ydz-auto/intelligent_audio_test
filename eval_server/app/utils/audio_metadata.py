"""Read recording coverage without ASR or waveform inference."""
import io
import wave

from app.utils.audio_source import exists, read_bytes

# 读 wav 头所需字节数（RIFF + fmt + data chunk 头，常规 WAV 足够；
# 超长头文件会回退到 soundfile 读取，二者都不支持时返回 duration_error）
_HEADER_BYTES = 64 * 1024
_FALLBACK_BYTES = 1024 * 1024


def audio_metadata(wav_path, asr_status='unknown'):
    result = {'audio_duration_s': None, 'duration_source': None,
              'asr_status': asr_status, 'voice_activity_status': 'not_measured'}
    if not wav_path or not exists(wav_path):
        result['duration_error'] = 'audio_file_missing'
        return result
    try:
        with wave.open(io.BytesIO(read_bytes(wav_path, limit=_HEADER_BYTES)), 'rb') as audio:
            rate = audio.getframerate()
            if rate <= 0:
                raise ValueError('Invalid sample rate')
            result.update(audio_duration_s=audio.getnframes()/rate, duration_source='wav_header')
    except Exception:
        # Float WAV and WAV extensible are supported by soundfile when installed.
        try:
            import soundfile
            info = soundfile.info(io.BytesIO(read_bytes(wav_path, limit=_FALLBACK_BYTES)))
            result.update(audio_duration_s=info.frames/info.samplerate, duration_source='audio_header')
        except Exception:
            result['duration_error'] = 'audio_header_unreadable'
    return result
