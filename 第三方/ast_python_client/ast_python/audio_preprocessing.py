import os
from pathlib import Path
import logging
import soundfile as sf
import librosa
import numpy as np

# 日志配置（显示处理进度和错误）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def batch_convert_audio(
    input_dir: str,
    output_dir: str = "converted_audio",
    target_sample_rate: int = 16000,  # 目标采样率：16kHz
    target_channels: int = 1,         # 目标声道：单通道
    supported_formats: tuple = ("wav", "mp3", "flac", "m4a", "ogg")  # 支持的输入格式
):
    """
    批处理音频格式转换：统一为16kHz、16bit、单通道WAV（纯Python实现，无ffmpeg依赖）
    """
    # 验证输入目录
    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        logging.error(f"输入文件夹不存在或非法：{input_dir}")
        return

    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    logging.info(f"输入文件夹：{input_dir}")
    logging.info(f"输出文件夹：{output_dir}")
    logging.info(f"目标格式：16kHz、16bit、单通道 WAV\n")

    # 筛选支持的音频文件
    audio_files = []
    for file in input_path.iterdir():
        if file.is_file() and file.suffix.lower()[1:] in supported_formats:
            audio_files.append(file)

    if not audio_files:
        logging.warning(f"未在输入文件夹中找到支持的音频文件（支持格式：{supported_formats}）")
        return

    logging.info(f"共找到 {len(audio_files)} 个待转换音频文件，开始处理...\n")

    # 逐个转换音频
    for idx, audio_file in enumerate(audio_files, start=1):
        file_name = audio_file.name
        file_stem = audio_file.stem
        file_suffix = audio_file.suffix.lower()

        logging.info(f"===== 处理第 {idx}/{len(audio_files)} 个文件：{file_name} =====")

        try:
            # 1. 读取音频（librosa自动处理解码，支持常见格式）
            # sr=None 表示保留原采样率，后续统一转换
            y, sr = librosa.load(str(audio_file), sr=None, mono=False)  # y: 音频数据，sr: 原采样率

            # 2. 转换声道（单通道）
            if y.ndim > 1:  # 多声道→单声道（取均值合并）
                y = librosa.to_mono(y)
                logging.debug(f"已转换声道：多通道→单通道")

            # 3. 转换采样率（16kHz）
            if sr != target_sample_rate:
                y = librosa.resample(y, orig_sr=sr, target_sr=target_sample_rate)
                logging.debug(f"已转换采样率：{sr}→{target_sample_rate}Hz")

            # 4. 转换位深（16bit）：librosa输出为float32（-1~1范围），需转为int16
            y_16bit = (y * 32767).astype(np.int16)  # 16bit的取值范围是 [-32768, 32767]

            # 5. 生成输出文件路径
            output_file_name = f"{file_stem}_converted.wav"
            output_file_path = output_path / output_file_name

            # 6. 导出为WAV（16bit、单通道、16kHz）
            sf.write(
                str(output_file_path),
                y_16bit,
                samplerate=target_sample_rate,
                subtype='PCM_16'  # 明确指定16bit PCM编码
            )

            logging.info(f"转换成功！输出文件：{output_file_path}\n")

        except Exception as e:
            logging.error(f"转换文件 {file_name} 失败：{str(e)}", exc_info=True)
            logging.info("跳过该文件，继续处理下一个...\n")
            continue

    logging.info("\n===== 所有文件处理完毕！=====")
    logging.info(f"转换后的音频文件已保存至：{output_dir}")
    logging.info("格式说明：16kHz采样率、16bit位深、单通道、WAV（PCM编码）")

if __name__ == "__main__":
    # 配置参数（和原脚本一致，无需修改）
    INPUT_AUDIO_DIR = r"C:\S2TT\Test_dataset\20251104测试集\领域测试集\构建_领域（英）"
    OUTPUT_AUDIO_DIR = r"C:\S2TT\Test_dataset\20251104测试集\领域测试集\en-16k"
    # 执行批量转换
    batch_convert_audio(
        input_dir=INPUT_AUDIO_DIR,
        output_dir=OUTPUT_AUDIO_DIR
    )