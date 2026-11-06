import os
import asyncio
import logging
import traceback  # 补充导入
from pathlib import Path
from typing import List, Dict  # 补充导入
from livetranslate_client import LiveTranslateClient

# 配置logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 全局配置
OUTPUT_AUDIO_DIR = r"C:\S2TT\Test_out\qwen_translated_audio\口音\zh\北方"  # 翻译后音频保存目录
OUTPUT_TEXT_DIR = r"C:\S2TT\Test_out\qwen_single_txt_results\口音\zh\北方"  # 文本结果保存目录
OUTPUT_SUMMARY_FILE = r"C:\S2TT\Test_out\qwen_txt\口音\output_qwen_北方.txt"  # 汇总文本文件
OUTPUT_LATENCY_FILE = r"C:\S2TT\Test_out\qwen_txt\口音\latency_stats_qwen_北方.txt"  # 时延统计文件

# 支持的音频后缀
SUPPORTED_AUDIO_EXT = [".wav", ".pcm"]


def init_directories():
    """初始化输出目录"""
    for dir_path in [OUTPUT_AUDIO_DIR, OUTPUT_TEXT_DIR]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"初始化目录: {dir_path}")


def get_audio_files(input_dir: str) -> List[str]:
    """获取目录下所有支持的音频文件"""
    if not os.path.isdir(input_dir):
        raise NotADirectoryError(f"输入路径不是目录: {input_dir}")

    audio_files = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            file_ext = os.path.splitext(file)[1].lower()
            if file_ext in SUPPORTED_AUDIO_EXT:
                audio_files.append(os.path.abspath(os.path.join(root, file)))

    if not audio_files:
        logger.warning(f"目录下未找到支持的音频文件: {input_dir}")
    else:
        logger.info(f"找到{len(audio_files)}个音频文件待处理")
    return audio_files


def save_text_results(audio_basename: str, asr_text: str, translation_text: str):
    """保存单个文件的ASR文本和翻译文本"""
    # 保存ASR文本
    asr_path = os.path.join(OUTPUT_TEXT_DIR, f"{audio_basename}_asr_qwen.txt")
    with open(asr_path, 'w', encoding='utf-8') as f:
        f.write(asr_text)
    logger.info(f"ASR文本已保存: {asr_path}")

    # 保存翻译文本
    translate_path = os.path.join(OUTPUT_TEXT_DIR, f"{audio_basename}_fanyi_qwen.txt")
    with open(translate_path, 'w', encoding='utf-8') as f:
        f.write(translation_text)
    logger.info(f"翻译文本已保存: {translate_path}")


def append_summary_line(audio_path: str, asr_text: str, translation_text: str, src_lang: str = "zh",
                        tgt_lang: str = "en"):
    """追加一行到汇总文件"""
    # 处理文本中的制表符和换行符（避免破坏TSV格式）
    asr_text = asr_text.replace('\t', ' ').replace('\n', ' ')
    translation_text = translation_text.replace('\t', ' ').replace('\n', ' ')
    line = f"{audio_path}\t{asr_text}\t{translation_text}\t{src_lang}2{tgt_lang}\t\n"

    with open(OUTPUT_SUMMARY_FILE, 'a', encoding='utf-8') as f:
        f.write(line)
    logger.info(f"已追加到汇总文件: {OUTPUT_SUMMARY_FILE}")


def save_latency_stats(audio_path: str, latency_stats: Dict):
    """保存单个文件的时延统计到文件"""
    # 第一次写入时添加表头
    if not os.path.exists(OUTPUT_LATENCY_FILE):
        headers = [
            "音频文件路径", "ASR首字时延(秒)", "ASR尾字时延(秒)",
            "翻译首字时延(秒)", "翻译尾字时延(秒)", "TTS首字时延(秒)", "TTS尾字时延(秒)"
        ]
        with open(OUTPUT_LATENCY_FILE, 'w', encoding='utf-8') as f:
            f.write('\t'.join(headers) + '\n')

    # 写入数据
    data = [
        audio_path,
        str(latency_stats["asr_first_latency"]),
        str(latency_stats["asr_last_latency"]),
        str(latency_stats["translation_first_latency"]),
        str(latency_stats["translation_last_latency"]),
        str(latency_stats["tts_first_latency"]),
        str(latency_stats["tts_last_latency"])
    ]
    with open(OUTPUT_LATENCY_FILE, 'a', encoding='utf-8') as f:
        f.write('\t'.join(data) + '\n')
    logger.info(f"时延统计已保存: {OUTPUT_LATENCY_FILE}")


async def process_batch_audio(input_dir: str, api_key: str, target_language: str, voice: str, audio_enabled: bool):
    """批量处理目录下的音频文件"""
    # 初始化
    init_directories()
    audio_files = get_audio_files(input_dir)
    if not audio_files:
        return

    # 创建客户端实例
    client = LiveTranslateClient(
        api_key=api_key,
        target_language=target_language,
        voice=voice,
        audio_enabled=audio_enabled
    )

    # 遍历处理每个音频文件
    for idx, audio_path in enumerate(audio_files, 1):
        logger.info(f"\n{'=' * 50} 处理第{idx}/{len(audio_files)}个文件 {'=' * 50}")
        logger.info(f"当前文件: {audio_path}")

        try:
            # 处理单个文件
            asr_text, translation_text, tts_chunks, latency_stats = await client.process_single_audio(audio_path)

            # 生成文件名（不含后缀）
            audio_filename = os.path.basename(audio_path)
            audio_basename = os.path.splitext(audio_filename)[0]

            # 保存文本结果
            save_text_results(audio_basename, asr_text, translation_text)

            # 追加到汇总文件
            append_summary_line(audio_path, asr_text, translation_text, src_lang="zh", tgt_lang=target_language)

            # 保存TTS音频（如果启用）
            if audio_enabled and tts_chunks:
                audio_output_path = os.path.join(OUTPUT_AUDIO_DIR, f"{audio_basename}_fanyi_qwen.wav")
                client.save_tts_audio(tts_chunks, audio_output_path)

            # 保存时延统计
            save_latency_stats(audio_path, latency_stats)

            logger.info(f"第{idx}个文件处理成功！")

        except Exception as e:
            logger.error(f"第{idx}个文件处理失败: {e}")
            traceback.print_exc()
            continue

    logger.info(f"\n{'=' * 50} 所有文件处理完成 {'=' * 50}")
    logger.info(f"翻译音频保存目录: {os.path.abspath(OUTPUT_AUDIO_DIR)}")
    logger.info(f"文本结果保存目录: {os.path.abspath(OUTPUT_TEXT_DIR)}")
    logger.info(f"汇总文件: {os.path.abspath(OUTPUT_SUMMARY_FILE)}")
    logger.info(f"时延统计文件: {os.path.abspath(OUTPUT_LATENCY_FILE)}")


def get_user_config():
    """获取用户配置"""
    # 输入目录
    input_dir = r"C:\S2TT\Test_dataset\口音\zh\北方"
    while not os.path.isdir(input_dir):
        logger.error("目录不存在，请重新输入")
        input_dir = input("请输入音频文件所在目录路径: ").strip()

    # 模式选择
    print("\n请选择模式:")
    print("1. 语音+文本 [默认] | 2. 仅文本")
    mode_choice = "1"
    audio_enabled = (mode_choice != "2")

    # 目标语言选择
    if audio_enabled:
        lang_map = {
            "1": "en", "2": "zh", "3": "ru", "4": "fr", "5": "de", "6": "pt",
            "7": "es", "8": "it", "9": "ko", "10": "ja", "11": "yue"
        }
        print("\n请选择翻译目标语言 (音频+文本 模式):")
        print(
            "1. 英语 | 2. 中文 | 3. 俄语 | 4. 法语 | 5. 德语 | 6. 葡萄牙语 | 7. 西班牙语 | 8. 意大利语 | 9. 韩语 | 10. 日语 | 11. 粤语")
    else:
        lang_map = {
            "1": "en", "2": "zh", "3": "ru", "4": "fr", "5": "de", "6": "pt", "7": "es", "8": "it",
            "9": "id", "10": "ko", "11": "ja", "12": "vi", "13": "th", "14": "ar",
            "15": "yue", "16": "hi", "17": "el", "18": "tr"
        }
        print("\n请选择翻译目标语言 (仅文本 模式):")
        print(
            "1. 英语 | 2. 中文 | 3. 俄语 | 4. 法语 | 5. 德语 | 6. 葡萄牙语 | 7. 西班牙语 | 8. 意大利语 | 9. 印尼语 | 10. 韩语 | 11. 日语 | 12. 越南语 | 13. 泰语 | 14. 阿拉伯语 | 15. 粤语 | 16. 印地语 | 17. 希腊语 | 18. 土耳其语")

    choice = "2"
    target_language = lang_map.get(choice, next(iter(lang_map.values())))

    # 语音选择（仅音频模式）
    voice = "Cherry"
    if audio_enabled:
        print("\n请选择语音合成声音:")
        voice_map = {"1": "Cherry", "2": "Nofish", "3": "Sunny", "4": "Jada", "5": "Dylan", "6": "Peter", "7": "Eric",
                     "8": "Kiki"}
        print(
            "1. Cherry (女声) [默认] | 2. Nofish (男声) | 3. 晴儿 Sunny (四川女声) | 4. 阿珍 Jada (上海女声) | 5. 晓东 Dylan (北京男声) | 6. 李彼得 Peter (天津男声) | 7. 程川 Eric (四川男声) | 8. 阿清 Kiki (粤语女声)")
        voice_choice = "1"
        voice = voice_map.get(voice_choice, "Cherry")

    return input_dir, target_language, voice, audio_enabled


def print_banner():
    print("=" * 60)
    print("  基于通义千问 qwen3-livetranslate-flash-realtime - 批量音频翻译工具")
    print("=" * 60 + "\n")


async def main():
    print_banner()

    # 获取API密钥
    api_key = "sk-d561b5b16c47456ab1a0eedd0359e910"
    if not api_key:
        logger.error("请设置环境变量 DASHSCOPE_API_KEY")
        logger.error("  例如: export DASHSCOPE_API_KEY='your_api_key_here' (Linux/Mac)")
        logger.error("  例如: set DASHSCOPE_API_KEY='your_api_key_here' (Windows CMD)")
        logger.error("  例如: $env:DASHSCOPE_API_KEY='your_api_key_here' (Windows PowerShell)")
        return

    # 获取用户配置
    input_dir, target_language, voice, audio_enabled = get_user_config()
    print("\n" + "=" * 30 + " 配置摘要 " + "=" * 30)
    print(f"输入目录: {input_dir}")
    print(f"目标语言: {target_language}")
    print(f"输出模式: {'语音+文本' if audio_enabled else '仅文本'}")
    if audio_enabled:
        print(f"合成声音: {voice}")
    print("=" * 60 + "\n")

    # 开始批量处理
    try:
        await process_batch_audio(input_dir, api_key, target_language, voice, audio_enabled)
    except KeyboardInterrupt:
        logger.info("\n用户中断，程序退出")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())