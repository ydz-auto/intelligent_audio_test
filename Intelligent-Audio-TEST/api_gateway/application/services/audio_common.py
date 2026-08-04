import os
import time
import shutil
import logging
from api_gateway.config.config import Config
from pydub import AudioSegment

logger = logging.getLogger(__name__)


def retry_file_operation(func, *args, **kwargs):
    max_retries = 5
    retry_delay = 0.2
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (PermissionError, OSError) as e:
            if i == max_retries - 1:
                raise
            time.sleep(retry_delay)


def safe_makedirs(dir_path):
    if os.path.exists(dir_path):
        return
    max_retries = 3
    for i in range(max_retries):
        try:
            os.makedirs(dir_path, exist_ok=True)
            return
        except (PermissionError, OSError) as e:
            if i == max_retries - 1:
                raise
            time.sleep(0.2)


def safe_rmtree(path):
    if not os.path.exists(path):
        return

    def on_error(func, path, exc_info):
        import stat
        try:
            os.chmod(path, stat.S_IWUSR)
            func(path)
        except:
            pass

    try:
        retry_file_operation(shutil.rmtree, path, onerror=on_error)
    except:
        time.sleep(0.5)
        shutil.rmtree(path, ignore_errors=True)


def get_relative_path(file_path):
    if '/' in file_path and not os.path.isabs(file_path):
        return file_path
    static_base_path = Config.STATIC_BASE_PATH if hasattr(Config, 'STATIC_BASE_PATH') else None
    if not static_base_path:
        return file_path
    normalized_file_path = file_path.replace('\\', '/')
    normalized_static_path = static_base_path.replace('\\', '/')
    static_index = normalized_file_path.find(normalized_static_path)
    if static_index != -1:
        relative_path = normalized_file_path[static_index + len(normalized_static_path):]
        while relative_path.startswith('/'):
            relative_path = relative_path[1:]
        return relative_path
    return file_path


def _read_wav_header(file_path):
    """读取 WAV 文件头的采样率和位深（不依赖 ffmpeg/pydub）"""
    import wave
    with wave.open(file_path, 'rb') as wf:
        return wf.getframerate(), wf.getsampwidth() * 8


def convert_to_wav(file_path):
    """
    将音频转换为WAV格式（不进行归一化，增益调整在播放时实时进行）
    :param file_path: 原始音频文件路径
    :return: 转换后的WAV文件路径
    """
    file_path = os.path.normpath(file_path)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    audio_seg = AudioSegment.from_file(file_path)

    original_sample_rate = audio_seg.frame_rate
    original_channels = audio_seg.channels
    original_bits_per_sample = audio_seg.frame_width * 8

    directory = os.path.dirname(file_path)
    filename = os.path.splitext(os.path.basename(file_path))[0]
    new_wav_path = os.path.join(directory, f"{filename}.wav")

    codec_map = {
        16: 'pcm_s16le',
        24: 'pcm_s24le',
        32: 'pcm_s32le'
    }
    codec = codec_map.get(original_bits_per_sample, 'pcm_s16le')

    audio_seg.export(
        new_wav_path,
        format='wav',
        parameters=['-ar', str(int(original_sample_rate)),
                   '-ac', str(original_channels),
                   '-acodec', codec]
    )

    new_filename = f"{filename}.wav"
    return new_wav_path, new_filename, original_sample_rate, original_bits_per_sample
