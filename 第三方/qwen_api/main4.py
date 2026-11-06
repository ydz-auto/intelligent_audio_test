import os
import time
import base64
import asyncio
import json
import websockets
import pyaudio
import queue
import threading
import logging
import wave
from typing import List, Dict, Tuple, Optional
import glob

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("file_translate.log"),
        logging.StreamHandler()
    ]
)


class FileTranslateClient:
    def __init__(self, api_key: str, target_language: str = "en", voice: str = "Cherry"):
        if not api_key:
            raise ValueError("API key cannot be empty.")

        self.api_key = api_key
        self.target_language = target_language
        self.voice = voice
        self.ws = None
        self.api_url = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen3-livetranslate-flash-realtime"

        # 音频配置（匹配API要求）
        self.sample_rate = 16000
        self.chunk_size = 1600
        self.audio_format = pyaudio.paInt16
        self.channels = 1

        # 状态管理
        self.is_connected = False
        self.audio_playback_queue = queue.Queue()
        self.pyaudio_instance = pyaudio.PyAudio()

        # 结果收集
        self.current_asr = []
        self.current_translate = []
        self.timestamps = {
            "asr_first_char": None,
            "asr_last_char": None,
            "translate_first_char": None,
            "translate_last_char": None,
            "tts_first_char": None,
            "tts_last_char": None
        }
        self.task_start_time = 0

        # 输出目录
        self.TRANSLATE_AUDIO_DIR = "./translate_audio_qwen"
        self.TEXT_OUTPUT_DIR = "./qwen_fanyi_text"
        self.SUMMARY_FILE = "./output_qwen.txt"
        self.LATENCY_FILE = "./latency_stats_qwen.txt"
        self._create_output_dirs()

        # 汇总数据
        self.all_summary = []
        self.all_latency = []

    def _create_output_dirs(self):
        """创建输出目录"""
        for dir_path in [self.TRANSLATE_AUDIO_DIR, self.TEXT_OUTPUT_DIR]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                logging.info(f"创建输出目录：{dir_path}")

    async def connect(self):
        """建立WebSocket连接"""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            self.ws = await websockets.connect(self.api_url, additional_headers=headers)
            self.is_connected = True
            logging.info(f"成功连接到服务端: {self.api_url}")
            await self.configure_session()
        except Exception as e:
            logging.error(f"连接失败: {e}")
            self.is_connected = False
            raise

    async def configure_session(self):
        """配置翻译会话"""
        config = {
            "event_id": f"event_{int(time.time() * 1000)}",
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "voice": self.voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "translation": {
                    "language": self.target_language
                }
            }
        }
        logging.debug(f"发送会话配置: {json.dumps(config, indent=2, ensure_ascii=False)}")
        await self.ws.send(json.dumps(config))

    async def send_audio_chunk(self, audio_data: bytes):
        """发送音频块到服务端"""
        if not self.is_connected:
            return

        event = {
            "event_id": f"event_{int(time.time() * 1000)}",
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio_data).decode()
        }
        logging.debug(f"发送音频数据块，长度: {len(audio_data)}字节")
        await self.ws.send(json.dumps(event))

    def _audio_player_task(self, output_file: str):
        """处理音频播放和保存"""
        stream = self.pyaudio_instance.open(
            format=self.audio_format,
            channels=self.channels,
            rate=self.sample_rate,
            output=True,
            frames_per_buffer=self.chunk_size,
        )

        # 准备保存音频
        wf = wave.open(output_file, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.pyaudio_instance.get_sample_size(self.audio_format))
        wf.setframerate(self.sample_rate)

        try:
            while self.is_connected or not self.audio_playback_queue.empty():
                try:
                    audio_chunk = self.audio_playback_queue.get(timeout=0.1)
                    if audio_chunk is None:
                        break
                    # 播放并保存音频
                    stream.write(audio_chunk)
                    wf.writeframes(audio_chunk)
                    self.audio_playback_queue.task_done()

                    # 记录TTS首字时间
                    if self.timestamps["tts_first_char"] is None:
                        self.timestamps["tts_first_char"] = time.time() * 1000
                    self.timestamps["tts_last_char"] = time.time() * 1000

                except queue.Empty:
                    continue
        finally:
            stream.stop_stream()
            stream.close()
            wf.close()
            logging.debug("音频播放和保存完成")

    def start_audio_player(self, output_file: str):
        """启动音频播放和保存线程"""
        player_thread = threading.Thread(
            target=self._audio_player_task,
            args=(output_file,),
            daemon=True
        )
        player_thread.start()
        return player_thread

    async def handle_server_messages(self):
        """处理服务端消息并收集结果"""
        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get("type")
                logging.debug(f"收到事件: {event_type}")

                # 处理ASR结果
                if event_type == "response.audio_transcript.delta":
                    text = event.get("transcript", "")
                    if text:
                        self.current_asr.append(text)
                        # 记录ASR首字时间
                        if self.timestamps["asr_first_char"] is None:
                            self.timestamps["asr_first_char"] = time.time() * 1000
                        self.timestamps["asr_last_char"] = time.time() * 1000

                # 处理翻译文本
                elif event_type == "response.text.delta":
                    text = event.get("text", "")
                    if text:
                        self.current_translate.append(text)
                        # 记录翻译首字时间
                        if self.timestamps["translate_first_char"] is None:
                            self.timestamps["translate_first_char"] = time.time() * 1000
                        self.timestamps["translate_last_char"] = time.time() * 1000

                # 处理TTS音频
                elif event_type == "response.audio.delta":
                    audio_b64 = event.get("delta", "")
                    if audio_b64:
                        audio_data = base64.b64decode(audio_b64)
                        self.audio_playback_queue.put(audio_data)

                # 处理完成事件
                elif event_type in ["response.done", "response.audio_transcript.done", "response.text.done"]:
                    logging.debug(f"收到完成事件: {event_type}")

        except websockets.exceptions.ConnectionClosed as e:
            logging.warning(f"连接已关闭: {e}")
            self.is_connected = False
        except Exception as e:
            logging.error(f"消息处理错误: {e}", exc_info=True)
            self.is_connected = False

    def _read_audio_file(self, file_path: str) -> Tuple[bytes, float]:
        """读取音频文件并转换为所需格式"""
        try:
            with wave.open(file_path, 'rb') as wf:
                # 检查音频参数
                if (wf.getframerate() != self.sample_rate or
                        wf.getnchannels() != self.channels or
                        wf.getsampwidth() != 2):  # 16位
                    raise ValueError(f"音频格式不符合要求: {file_path}")

                frames = wf.readframes(wf.getnframes())
                duration = wf.getnframes() / wf.getframerate()
                return frames, duration
        except Exception as e:
            logging.error(f"读取音频文件失败 {file_path}: {e}")
            raise

    async def process_audio_file(self, file_path: str) -> Optional[Tuple[Dict, Dict]]:
        """处理单个音频文件"""
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        logging.info(f"\n===== 开始处理: {file_path} =====")

        # 初始化结果收集器
        self.current_asr = []
        self.current_translate = []
        self.timestamps = {k: None for k in self.timestamps.keys()}
        self.task_start_time = time.time() * 1000  # 毫秒级

        # 准备输出文件
        tts_output_path = os.path.join(self.TRANSLATE_AUDIO_DIR, f"{base_name}_fanyi_qwen.wav")
        asr_output_path = os.path.join(self.TEXT_OUTPUT_DIR, f"{base_name}_asr_qwen.txt")
        translate_output_path = os.path.join(self.TEXT_OUTPUT_DIR, f"{base_name}_fanyi_qwen.txt")

        try:
            # 1. 读取音频文件
            audio_data, duration = self._read_audio_file(file_path)
            logging.info(f"音频时长: {duration:.2f}秒, 大小: {len(audio_data)}字节")

            # 2. 建立连接
            await self.connect()

            # 3. 启动音频处理线程
            player_thread = self.start_audio_player(tts_output_path)

            # 4. 启动消息处理协程
            message_task = asyncio.create_task(self.handle_server_messages())

            # 5. 分块发送音频
            chunk_count = len(audio_data) // self.chunk_size
            for i in range(chunk_count):
                start = i * self.chunk_size
                end = start + self.chunk_size
                chunk = audio_data[start:end]
                await self.send_audio_chunk(chunk)
                # 控制发送速度，模拟实时流
                await asyncio.sleep(0.1)

            # 处理剩余数据
            if len(audio_data) % self.chunk_size != 0:
                await self.send_audio_chunk(audio_data[chunk_count * self.chunk_size:])

            # 等待处理完成
            await asyncio.sleep(duration + 2)  # 等待额外时间确保处理完成

            # 6. 关闭连接
            await self.close()
            player_thread.join()

            # 7. 保存文本结果
            asr_text = ''.join(self.current_asr)
            translate_text = ''.join(self.current_translate)

            with open(asr_output_path, 'w', encoding='utf-8') as f:
                f.write(asr_text)
            with open(translate_output_path, 'w', encoding='utf-8') as f:
                f.write(translate_text)

            logging.info(f"ASR结果: {asr_text}")
            logging.info(f"翻译结果: {translate_text}")

            # 8. 计算时延
            latency = self._calculate_latency()
            logging.info(f"时延统计: {latency}")

            # 9. 构建汇总数据
            summary = {
                "audio_path": file_path,
                "asr_text": asr_text,
                "translate_text": translate_text,
                "lang_pair": f"zh2{self.target_language}"
            }

            return summary, latency

        except Exception as e:
            logging.error(f"处理文件 {file_path} 失败: {e}", exc_info=True)
            return None, None

    def _calculate_latency(self) -> Dict:
        """计算各项时延（毫秒）"""
        base_time = self.task_start_time
        latency = {}

        # 计算各项时延
        for key, value in self.timestamps.items():
            if value is not None:
                latency[key] = round(value - base_time, 2)
            else:
                latency[key] = 0.0

        return {
            "asr_first_ms": latency["asr_first_char"],
            "asr_last_ms": latency["asr_last_char"],
            "translate_first_ms": latency["translate_first_char"],
            "translate_last_ms": latency["translate_last_char"],
            "tts_first_ms": latency["tts_first_char"],
            "tts_last_ms": latency["tts_last_char"]
        }

    async def close(self):
        """关闭连接和资源"""
        self.is_connected = False
        if self.ws:
            await self.ws.close()
            logging.info("WebSocket连接已关闭")

        # 发送音频播放结束信号
        self.audio_playback_queue.put(None)
        self.pyaudio_instance.terminate()

    async def batch_process(self, input_dir: str):
        """批量处理文件夹中的所有音频文件"""
        # 获取所有wav文件
        audio_files = glob.glob(os.path.join(input_dir, "*.wav"))
        logging.info(f"找到 {len(audio_files)} 个音频文件")

        for idx, file in enumerate(audio_files, 1):
            summary, latency = await self.process_audio_file(file)
            if summary and latency:
                self.all_summary.append(summary)
                self.all_latency.append({
                    "audio_filename": os.path.basename(file),
                    **latency
                })
            logging.info(f"完成 {idx}/{len(audio_files)} 个文件处理")

        # 保存汇总结果
        self._save_summary()
        self._save_latency_stats()

        logging.info("所有文件处理完成")

    def _save_summary(self):
        """保存汇总结果"""
        with open(self.SUMMARY_FILE, "w", encoding="utf-8") as f:
            f.write("音频文件路径\tASR结果\t翻译结果\t语言对\t\n")
            for item in self.all_summary:
                line = f"{item['audio_path']}\t{item['asr_text']}\t{item['translate_text']}\t{item['lang_pair']}\t\n"
                f.write(line)
        logging.info(f"汇总结果已保存到 {self.SUMMARY_FILE}")

    def _save_latency_stats(self):
        """保存时延统计"""
        with open(self.LATENCY_FILE, "w", encoding="utf-8") as f:
            headers = [
                "音频文件名", "ASR首字时延(ms)", "ASR尾字时延(ms)",
                "翻译首字时延(ms)", "翻译尾字时延(ms)",
                "TTS首字时延(ms)", "TTS尾字时延(ms)"
            ]
            f.write("\t".join(headers) + "\n")

            for item in self.all_latency:
                line = [
                    item["audio_filename"],
                    str(item["asr_first_ms"]),
                    str(item["asr_last_ms"]),
                    str(item["translate_first_ms"]),
                    str(item["translate_last_ms"]),
                    str(item["tts_first_ms"]),
                    str(item["tts_last_ms"])
                ]
                f.write("\t".join(line) + "\n")

            # 计算平均值
            if self.all_latency:
                f.write("\n===== 时延平均值 =====" + "\n")
                avg_keys = [
                    "asr_first_ms", "asr_last_ms",
                    "translate_first_ms", "translate_last_ms",
                    "tts_first_ms", "tts_last_ms"
                ]
                avg_names = [
                    "ASR首字时延平均值", "ASR尾字时延平均值",
                    "翻译首字时延平均值", "翻译尾字时延平均值",
                    "TTS首字时延平均值", "TTS尾字时延平均值"
                ]

                for key, name in zip(avg_keys, avg_names):
                    avg = round(sum(item[key] for item in self.all_latency) / len(self.all_latency), 2)
                    f.write(f"{name}: {avg} ms\n")

        logging.info(f"时延统计已保存到 {self.LATENCY_FILE}")


# 使用示例
if __name__ == "__main__":

    api_key = "sk-d561b5b16c47456ab1a0eedd0359e910"
    TARGET_LANGUAGE = "en"  # 目标语言
    input_dir = r"C:\S2TT_test\ast_python_client\ast_python"  # 音频文件目录

    client = FileTranslateClient(api_key=api_key, target_language="en")

    try:
        asyncio.run(client.batch_process(input_dir))
    except Exception as e:
        logging.critical(f"程序运行失败: {e}", exc_info=True)