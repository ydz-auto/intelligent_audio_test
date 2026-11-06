import asyncio
import os
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
from ast_demo_zh2en import Config, translate_v4, ProcessResult

# ---------------- 日志配置（控制台+文件双输出）----------------
def setup_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  # 日志级别：INFO及以上
    logger.handlers.clear()  # 清除默认处理器

    # 1. 控制台处理器
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 2. 文件处理器（按大小轮转）
    log_dir = "logs_seed2"
    log_file = Path(log_dir) / "audio_translate_log.txt"
    os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10*1024*1024,  # 单个文件最大10MB
        backupCount=5,  # 保留5个备份
        encoding="utf-8"  # 支持中文
    )
    file_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

# 初始化日志
setup_logger()

async def batch_translate(
    input_dir: str,
    api_config: Config,
    out_audio_dir: str = "translated_audio",
    output_txt_dir: str = None,
    final_output_txt: str = "output.txt",  # ASR+翻译结果文件
    latency_output_txt: str = "latency_stats.txt",  # 时延统计单独文件
    save_single_txt: bool = True,  # 是否保留单独的ASR/翻译TXT
    supported_audio_formats: tuple = (".wav", ".WAV", '.m4a')
):
    """
    批处理音频翻译：ASR+翻译+音频保存+结果拼接+时延单独保存
    - final_output_txt：ASR+翻译结果（格式：音频路径\tASR\t翻译\tzh2en\t）
    - latency_output_txt：时延统计（格式：音频路径\t请求时间\tASR首字时延\t...\t）
    """
    input_path = Path(input_dir)
    # 验证输入目录
    if not input_path.exists() or not input_path.is_dir():
        logging.error(f"输入文件夹不存在或非法：{input_dir}")
        return

    # 验证输出目录（单独TXT用）
    if save_single_txt and output_txt_dir:
        output_path = Path(output_txt_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        logging.info(f"单独文本结果保存目录：{output_path}")
    elif save_single_txt:
        output_path = input_path  # 单独TXT与音频同目录
        logging.info(f"单独文本结果与音频文件同目录保存")

    # 筛选支持的音频文件
    audio_files = [
        f for f in input_path.iterdir()
        if f.is_file() and f.suffix in supported_audio_formats
    ]
    if not audio_files:
        logging.warning(f"未在 {input_dir} 中找到支持的音频文件（格式：{supported_audio_formats}）")
        return

    logging.info(f"\n===== 共找到 {len(audio_files)} 个待处理音频文件 =====")

    # 关键：收集所有结果（用于批量保存）
    all_translate_results = []  # 存储ASR+翻译结果
    all_latency_results = []    # 存储时延统计结果

    # 逐个处理文件
    for idx, audio_file in enumerate(audio_files, start=1):
        audio_filename = audio_file.name
        audio_stem = audio_file.stem
        audio_abs_path = str(audio_file.absolute())  # 音频文件绝对路径
        logging.info(f"\n===== 处理第 {idx}/{len(audio_files)} 个文件：{audio_filename} =====")

        try:
            # 调用核心翻译函数
            result: ProcessResult = await translate_v4(
                conf=api_config,
                audio_path=str(audio_file),
                audio_filename=audio_filename,
                n=idx,
                out_audio_dir=out_audio_dir
            )

            # 1. （可选）保存单独的ASR/翻译TXT
            if save_single_txt:
                # 保存ASR结果（xxx_asr.txt）
                asr_txt_filename = f"{audio_stem}_asr_seed2.txt"
                asr_save_path = output_path / asr_txt_filename
                with open(asr_save_path, "w", encoding="utf-8") as f:
                    f.write(result.asr_text)
                logging.info(f"单独ASR结果已保存：{asr_save_path}")

                # 保存翻译结果（xxx_fanyi.txt）
                translate_txt_filename = f"{audio_stem}_fanyi_seed2.txt"
                translate_save_path = output_path / translate_txt_filename
                with open(translate_save_path, "w", encoding="utf-8") as f:
                    f.write(result.translated_text)
                logging.info(f"单独翻译结果已保存：{translate_save_path}")

            # 2. 收集ASR+翻译结果（用于output.txt）
            translate_row = {
                "audio_path": audio_abs_path,
                "asr_result": result.asr_text.replace("\t", " "),  # 替换制表符避免格式错乱
                "translate_result": result.translated_text.replace("\t", " "),
                "direction": "zh2en"
            }
            all_translate_results.append(translate_row)

            # 3. 收集时延统计结果（用于latency_stats.txt）
            latency_stats = result.latency_stats
            latency_row = {
                "audio_path": audio_abs_path,
                "audio_filename": audio_filename,
                "request_start_time": latency_stats.get("request_start_time", "无"),
                "asr_first_char_latency": latency_stats.get("asr_first_char_latency", "无"),
                "asr_last_char_latency": latency_stats.get("asr_last_char_latency", "无"),
                "translate_first_char_latency": latency_stats.get("translate_first_char_latency", "无"),
                "translate_last_char_latency": latency_stats.get("translate_last_char_latency", "无"),
                "tts_first_char_latency": latency_stats.get("tts_first_char_latency", "无"),
                "tts_last_char_latency": latency_stats.get("tts_last_char_latency", "无"),
                "error": latency_stats.get("error", "无")
            }
            all_latency_results.append(latency_row)

            # 4. 日志输出当前文件时延统计
            logging.info(f"\n【{audio_filename} 完整时延统计】")
            if latency_row["error"] != "无":
                logging.error(f"时延统计失败：{latency_row['error']}")
            else:
                logging.info(f"请求开始时间：{latency_row['request_start_time']}")
                logging.info(f"ASR首字时延：{latency_row['asr_first_char_latency']} 秒")
                logging.info(f"ASR尾字时延：{latency_row['asr_last_char_latency']} 秒")
                logging.info(f"翻译首字时延：{latency_row['translate_first_char_latency']} 秒")
                logging.info(f"翻译尾字时延：{latency_row['translate_last_char_latency']} 秒")
                logging.info(f"耳口差时延：{latency_row['tts_first_char_latency']} 秒")
                logging.info(f"TTS尾字时延：{latency_row['tts_last_char_latency']} 秒")

        except Exception as e:
            logging.error(f"处理文件 {audio_filename} 时发生异常：{str(e)}", exc_info=True)
            # 异常文件也记录结果（标记失败）
            # 异常-ASR+翻译结果
            error_translate_row = {
                "audio_path": audio_abs_path,
                "asr_result": "（处理失败）",
                "translate_result": "（处理失败）",
                "direction": "zh2en"
            }
            all_translate_results.append(error_translate_row)

            # 异常-时延结果
            error_latency_row = {
                "audio_path": audio_abs_path,
                "audio_filename": audio_filename,
                "request_start_time": "无",
                "asr_first_char_latency": "无",
                "asr_last_char_latency": "无",
                "translate_first_char_latency": "无",
                "translate_last_char_latency": "无",
                "tts_first_char_latency": "无",
                "tts_last_char_latency": "无",
                "error": f"文件处理异常：{str(e)}"
            }
            all_latency_results.append(error_latency_row)
            continue

    # 5. 保存ASR+翻译结果到 output.txt
    if all_translate_results:
        final_output_path = Path(final_output_txt)
        with open(final_output_path, "w", encoding="utf-8") as f:
            for row in all_translate_results:
                line = f"{row['audio_path']}\t{row['asr_result']}\t{row['translate_result']}\t{row['direction']}\t\n"
                f.write(line)
        logging.info(f"\nASR+翻译结果已保存到：{final_output_path.absolute()}")

    # 6. 单独保存时延统计到 latency_stats.txt（核心新增）
    if all_latency_results:
        latency_output_path = Path(latency_output_txt)
        with open(latency_output_path, "w", encoding="utf-8") as f:
            # 写入表头（可选，便于阅读）
            header = (
                "音频文件路径\t"
                "音频文件名\t"
                "请求开始时间\t"
                "ASR首字时延(秒)\t"
                "ASR尾字时延(秒)\t"
                "翻译首字时延(秒)\t"
                "翻译尾字时延(秒)\t"
                "耳口差时延(秒)\t"
                "TTS尾字时延(秒)\t"
                "错误信息\t\n"
            )
            f.write(header)
            # 写入每条时延数据
            for row in all_latency_results:
                line = (
                    f"{row['audio_path']}\t"
                    f"{row['audio_filename']}\t"
                    f"{row['request_start_time']}\t"
                    f"{row['asr_first_char_latency']}\t"
                    f"{row['asr_last_char_latency']}\t"
                    f"{row['translate_first_char_latency']}\t"
                    f"{row['translate_last_char_latency']}\t"
                    f"{row['tts_first_char_latency']}\t"
                    f"{row['tts_last_char_latency']}\t"
                    f"{row['error']}\t\n"
                )
                f.write(line)
        logging.info(f"时延统计结果已单独保存到：{latency_output_path.absolute()}")

    logging.info("\n===== 所有文件处理完毕！=====")
    logging.info(f"1. ASR+翻译结果：{final_output_txt}")
    logging.info(f"2. 时延统计结果：{latency_output_txt}")
    if save_single_txt:
        logging.info(f"3. 单独TXT结果：{output_txt_dir or '与音频同目录'}")

if __name__ == "__main__":
    # -------------------------- 核心配置（必须修改！）--------------------------
    SEED2_API_CONFIG = Config(
        ws_url="wss://openspeech.bytedance.com/api/v4/ast/v2/translate",
        app_key="4378424584",  # 替换为你的AppKey
        access_key="Yb4G8pIilf2EYymaFD1NHAhoyr7X-Gv9",  # 替换为你的AccessKey
        resource_id="volc.service_type.10053"  # 替换为分配的资源ID
    )

    # 目录配置（可自定义）
    INPUT_AUDIO_DIR = r"C:\S2TT\Test_dataset\1210test\zh"  # 输入：转换后的音频文件夹（16kHz/16bit/单通道）
    OUTPUT_AUDIO_DIR = r"C:\S2TT\Test_out\1210test-out\zh2en"  # 输出：翻译后的WAV音频
    OUTPUT_TXT_DIR = r"C:\S2TT\Test_out\1210test-out"  # 输出：单独的ASR/翻译TXT（可选）
    FINAL_OUTPUT_TXT = r"C:\S2TT\Test_out\seed2_txt\多信道测试集-八爪鱼\大会议室多信道测试集_4m\1210test.txt"        # ASR+翻译结果文件
    LATENCY_OUTPUT_TXT = r"C:\S2TT\Test_out\seed2_txt\多信道测试集-八爪鱼\大会议室多信道测试集_4m\1210test.txt"  # 时延统计单独文件
    SAVE_SINGLE_TXT = True  # 是否保留单独的TXT文件（False=仅保存2个汇总文件）

    # 运行批处理
    asyncio.run(batch_translate(
        input_dir=INPUT_AUDIO_DIR,
        api_config=SEED2_API_CONFIG,
        out_audio_dir=OUTPUT_AUDIO_DIR,
        output_txt_dir=OUTPUT_TXT_DIR,
        final_output_txt=FINAL_OUTPUT_TXT,
        latency_output_txt=LATENCY_OUTPUT_TXT,
        save_single_txt=SAVE_SINGLE_TXT
    ))