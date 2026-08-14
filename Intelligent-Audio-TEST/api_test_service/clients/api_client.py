import time
import json
import os
import logging
import requests
try:
    import websocket
except ImportError:
    websocket = None

logger = logging.getLogger(__name__)


class APIClient:
    """
    统一的 API 调用客户端，支持 HTTP (GET/POST/...) 和 WebSocket (WS/WSS)
    """

    @staticmethod
    def call(endpoint, method='POST', headers=None, data=None, files=None, timeout=30, meta=None):
        """
        根据 endpoint 协议自动选择调用方式
        """
        if endpoint.startswith('ws://') or endpoint.startswith('wss://'):
            return APIClient._call_websocket(endpoint, data, headers, timeout, meta)
        else:
            return APIClient._call_http(endpoint, method, headers, data, files, timeout)

    @staticmethod
    def _call_http(endpoint, method='POST', headers=None, data=None, files=None, timeout=30):
        start_time = time.time()
        response_data = {
            "status_code": 0,
            "latency": 0,
            "raw_response": "",
            "json": {},
            "error": None
        }

        try:
            method = method.upper()
            if method == 'GET':
                resp = requests.get(endpoint, params=data, headers=headers, timeout=timeout)
            elif method == 'POST':
                if files:
                    resp = requests.post(endpoint, files=files, data=data, headers=headers, timeout=timeout)
                else:
                    resp = requests.post(endpoint, json=data, headers=headers, timeout=timeout)
            else:
                resp = requests.request(method, endpoint, json=data, headers=headers, timeout=timeout)

            response_data["latency"] = int((time.time() - start_time) * 1000)
            response_data["status_code"] = resp.status_code

            # 显式设置响应编码为UTF-8
            resp.encoding = 'utf-8'
            response_data["raw_response"] = resp.text

            try:
                response_data["json"] = resp.json()
            except Exception:
                logger.debug("解析HTTP响应JSON失败: endpoint=%s", endpoint, exc_info=True)

        except Exception as e:
            response_data["error"] = str(e)

        return response_data

    @staticmethod
    def _call_websocket(endpoint, data=None, headers=None, timeout=30, meta=None):
        if websocket is None:
            return {
                "status_code": 500,
                "latency": 0,
                "raw_response": "",
                "json": {},
                "error": "websocket-client 库未安装"
            }

        start_time = time.time()
        meta = meta or {}

        all_responses = []
        last_json = {}
        error = None
        max_retries = meta.get('max_retries', 2)
        retry_count = 0

        ws = None
        while retry_count <= max_retries:
            try:
                ws = websocket.create_connection(endpoint, timeout=timeout, header=headers)

                if data:
                    if isinstance(data, (dict, list)):
                        ws.send(json.dumps(data, ensure_ascii=False))
                    else:
                        ws.send(str(data))

                audio_path = meta.get('audio_path')
                stream_audio = meta.get('stream_audio', True)

                if stream_audio and audio_path and os.path.exists(audio_path):
                    chunk_size = meta.get('chunk_size', 4096)
                    with open(audio_path, 'rb') as f:
                        while True:
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            ws.send_binary(chunk)
                            sleep_time = meta.get('chunk_interval', 0.02)
                            if sleep_time > 0:
                                time.sleep(sleep_time)

                    eos_message = meta.get('eos_message')
                    if eos_message:
                        ws.send(json.dumps(eos_message, ensure_ascii=False) if isinstance(eos_message, dict) else str(eos_message))

                session_end_path = meta.get('session_end_mapping')

                ws.settimeout(meta.get('recv_timeout', 5))

                max_responses = meta.get('max_responses', 100)
                for _ in range(max_responses):
                    try:
                        msg = ws.recv()
                        if not msg: break

                        all_responses.append(msg)

                        try:
                            msg_json = json.loads(msg)
                            last_json = msg_json

                            if session_end_path:
                                if APIClient._extract_by_path(msg_json, session_end_path) is True:
                                    break
                        except Exception:
                            logger.debug("解析WebSocket消息JSON失败: endpoint=%s", endpoint, exc_info=True)
                    except websocket.WebSocketTimeoutException:
                        if all_responses:
                            break
                        retry_count += 1
                        if retry_count <= max_retries:
                            if ws:
                                ws.close()
                            ws = None
                            continue
                        break
                    except websocket.WebSocketConnectionClosedException:
                        if all_responses:
                            break
                        retry_count += 1
                        if retry_count <= max_retries:
                            if ws:
                                ws.close()
                            ws = None
                            continue
                        error = "WebSocket连接已关闭"
                        break
                    except Exception as e:
                        error = f"Recv error: {str(e)}"
                        break

                break

            except Exception as e:
                retry_count += 1
                if retry_count <= max_retries:
                    continue
                error = str(e)
            finally:
                if ws:
                    ws.close()
                    ws = None

        latency = int((time.time() - start_time) * 1000)

        return {
            "status_code": 200 if not error else 500,
            "latency": latency,
            "raw_response": "\n".join(all_responses) if all_responses else "",
            "json": last_json,
            "all_responses": all_responses,
            "error": error,
            "retry_count": retry_count
        }

    @staticmethod
    def _extract_by_path(data, path):
        """从字典中根据路径提取值"""
        if not path or not data: return None
        try:
            for key in path.split('.'):
                if isinstance(data, dict):
                    data = data.get(key)
                elif isinstance(data, list) and key.isdigit():
                    data = data[int(key)]
                else:
                    return None
            return data
        except:
            return None

api_client = APIClient()
