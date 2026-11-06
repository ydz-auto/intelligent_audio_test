import os
import time
import base64
import asyncio
import json
import websockets
import pyaudio
import queue
import threading
import traceback
import logging  # 导入日志模块

# 配置日志（如果需要在模块内单独配置，否则可依赖外部配置）
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class LiveTranslateClient:
    def __init__(self, api_key: str, target_language: str = "en", voice: str | None = "Cherry", *,
                 audio_enabled: bool = True):
        if not api_key:
            raise ValueError("API key cannot be empty.")

        self.api_key = api_key
        self.target_language = target_language
        self.audio_enabled = audio_enabled
        self.voice = voice if audio_enabled else "Cherry"
        self.ws = None
        self.api_url = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen3-livetranslate-flash-realtime"

        # 音频输入配置 (来自麦克风)
        self.input_rate = 16000
        self.input_chunk = 1600
        self.input_format = pyaudio.paInt16
        self.input_channels = 1

        # 音频输出配置 (用于播放)
        self.output_rate = 24000
        self.output_chunk = 2400
        self.output_format = pyaudio.paInt16
        self.output_channels = 1

        # 状态管理
        self.is_connected = False
        self.audio_player_thread = None
        self.audio_playback_queue = queue.Queue()
        self.pyaudio_instance = pyaudio.PyAudio()

    async def connect(self):
        """建立到翻译服务的 WebSocket 连接。"""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            self.ws = await websockets.connect(self.api_url, additional_headers=headers)
            self.is_connected = True
            logging.info(f"成功连接到服务端: {self.api_url}")  # 替换print为info日志
            await self.configure_session()
        except Exception as e:
            logging.error(f"连接失败: {e}")  # 替换print为error日志
            self.is_connected = False
            raise

    async def configure_session(self):
        """配置翻译会话，设置目标语言、声音等。"""
        config = {
            "event_id": f"event_{int(time.time() * 1000)}",
            "type": "session.update",
            "session": {
                # 'modalities' 控制输出类型。
                # ["text", "audio"]: 同时返回翻译文本和合成音频（推荐）。
                # ["text"]: 仅返回翻译文本。
                "modalities": ["text", "audio"] if self.audio_enabled else ["text"],
                **({"voice": self.voice} if self.audio_enabled and self.voice else {}),
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "translation": {
                    "language": self.target_language
                }
            }
        }
        logging.debug(f"发送会话配置: {json.dumps(config, indent=2, ensure_ascii=False)}")  # 替换print为debug日志
        await self.ws.send(json.dumps(config))

    async def send_audio_chunk(self, audio_data: bytes):
        """将音频数据块编码并发送到服务端。"""
        if not self.is_connected:
            return

        event = {
            "event_id": f"event_{int(time.time() * 1000)}",
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio_data).decode()
        }
        logging.debug(f"发送音频数据块事件: {event['event_id']}")  # 新增debug日志
        await self.ws.send(json.dumps(event))

    async def send_image_frame(self, image_bytes: bytes, *, event_id: str | None = None):
        # 将图像数据发送到服务端
        if not self.is_connected:
            return

        if not image_bytes:
            raise ValueError("image_bytes 不能为空")

        # 编码为 Base64
        image_b64 = base64.b64encode(image_bytes).decode()

        event = {
            "event_id": event_id or f"event_{int(time.time() * 1000)}",
            "type": "input_image_buffer.append",
            "image": image_b64,
        }
        logging.debug(f"发送图像帧事件: {event['event_id']}")  # 新增debug日志
        await self.ws.send(json.dumps(event))

    def _audio_player_task(self):
        stream = self.pyaudio_instance.open(
            format=self.output_format,
            channels=self.output_channels,
            rate=self.output_rate,
            output=True,
            frames_per_buffer=self.output_chunk,
        )
        try:
            while self.is_connected or not self.audio_playback_queue.empty():
                try:
                    audio_chunk = self.audio_playback_queue.get(timeout=0.1)
                    if audio_chunk is None:  # 结束信号
                        break
                    stream.write(audio_chunk)
                    self.audio_playback_queue.task_done()
                    logging.debug(f"播放音频块，长度: {len(audio_chunk)}字节")  # 新增debug日志
                except queue.Empty:
                    continue
        finally:
            stream.stop_stream()
            stream.close()
            logging.debug("音频播放流已关闭")  # 新增debug日志

    def start_audio_player(self):
        """启动音频播放线程（仅当启用音频输出时）。"""
        if not self.audio_enabled:
            return
        if self.audio_player_thread is None or not self.audio_player_thread.is_alive():
            self.audio_player_thread = threading.Thread(target=self._audio_player_task, daemon=True)
            self.audio_player_thread.start()
            logging.debug("音频播放线程已启动")  # 新增debug日志

    async def handle_server_messages(self, on_text_received):
        """循环处理来自服务端的消息。"""
        try:
            async for message in self.ws:
                # 打印原始消息内容（DEBUG级别）
                logging.debug(f"收到服务端原始消息: {message}")
                event = json.loads(message)
                event_type = event.get("type")

                if event_type == "response.audio_transcript.delta":
                    text = event.get("transcript", "")
                    logging.debug(f"收到ASR增量文本: {text} (事件类型: {event_type})")  # 详细debug日志
                    if text and on_text_received:
                        on_text_received(text)

                elif event_type == "response.audio.delta" and self.audio_enabled:
                    audio_b64 = event.get("delta", "")
                    logging.debug(
                        f"收到TTS音频块 (事件类型: {event_type}, 长度: {len(audio_b64)}Base64字符)")  # 详细debug日志
                    if audio_b64:
                        audio_data = base64.b64decode(audio_b64)
                        self.audio_playback_queue.put(audio_data)

                elif event_type == "response.done":
                    logging.info("一轮响应完成。")  # 替换print为info日志
                    usage = event.get("response", {}).get("usage", {})
                    if usage:
                        logging.debug(
                            f"Token 使用情况: {json.dumps(usage, indent=2, ensure_ascii=False)}")  # 替换print为debug日志

                elif event_type == "response.audio_transcript.done":
                    logging.info("翻译文本完成。")  # 替换print为info日志
                    text = event.get("transcript", "")
                    if text:
                        logging.debug(f"翻译文本: {text}")  # 替换print为debug日志

                elif event_type == "response.text.done":
                    logging.info("翻译文本完成。")  # 替换print为info日志
                    text = event.get("text", "")
                    if text:
                        logging.debug(f"翻译文本: {text}")  # 替换print为debug日志

                else:
                    logging.debug(
                        f"收到未处理的事件类型: {event_type}，事件内容: {json.dumps(event, ensure_ascii=False)}")  # 未处理事件日志

        except websockets.exceptions.ConnectionClosed as e:
            logging.warning(f"连接已关闭: {e}")  # 替换print为warning日志
            self.is_connected = False
        except Exception as e:
            logging.error(f"消息处理时发生未知错误: {e}", exc_info=True)  # 替换print为error日志，增加堆栈信息
            self.is_connected = False

    async def start_microphone_streaming(self):
        """从麦克风捕获音频并流式传输到服务端。"""
        stream = self.pyaudio_instance.open(
            format=self.input_format,
            channels=self.input_channels,
            rate=self.input_rate,
            input=True,
            frames_per_buffer=self.input_chunk
        )
        logging.info("麦克风已启动，请开始说话...")  # 替换print为info日志
        try:
            while self.is_connected:
                audio_chunk = await asyncio.get_event_loop().run_in_executor(
                    None, stream.read, self.input_chunk
                )
                await self.send_audio_chunk(audio_chunk)
                logging.debug(f"发送麦克风音频块，长度: {len(audio_chunk)}字节")  # 新增debug日志
        finally:
            stream.stop_stream()
            stream.close()
            logging.debug("麦克风音频流已关闭")  # 新增debug日志

    async def close(self):
        """优雅地关闭连接和资源。"""
        self.is_connected = False
        if self.ws:
            await self.ws.close()
            logging.info("WebSocket 连接已关闭。")  # 替换print为info日志

        if self.audio_player_thread:
            self.audio_playback_queue.put(None)  # 发送结束信号
            self.audio_player_thread.join(timeout=1)
            logging.info("音频播放线程已停止。")  # 替换print为info日志

        self.pyaudio_instance.terminate()
        logging.info("PyAudio 实例已释放。")  # 替换print为info日志