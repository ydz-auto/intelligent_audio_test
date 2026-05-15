import time
import json
import os
import requests
try:
    import websocket
except ImportError:
    websocket = None

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
            except:
                pass
                
        except Exception as e:
            response_data["error"] = str(e)
            
        return response_data

    @staticmethod
    def _call_websocket(endpoint, data=None, headers=None, timeout=30, meta=None):
        """
        WebSocket 流式调用逻辑
        """
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
        
        # 用于存储流式响应过程中的所有消息
        all_responses = []
        last_json = {}
        error = None
        
        ws = None
        try:
            # 建立连接
            ws = websocket.create_connection(endpoint, timeout=timeout, header=headers)
            
            # 1. 发送初始配置数据 (JSON)
            if data:
                if isinstance(data, (dict, list)):
                    ws.send(json.dumps(data, ensure_ascii=False))
                else:
                    ws.send(str(data))
            
            # 2. 如果配置了流式发送音频文件
            audio_path = meta.get('audio_path')
            stream_audio = meta.get('stream_audio', True) # 默认开启流式发送
            
            if stream_audio and audio_path and os.path.exists(audio_path):
                chunk_size = meta.get('chunk_size', 4096)
                with open(audio_path, 'rb') as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        ws.send_binary(chunk)
                        # 控制发送速率，模拟真实流式
                        sleep_time = meta.get('chunk_interval', 0.02)
                        if sleep_time > 0:
                            time.sleep(sleep_time)
                
                # 发送结束标志 (如果 API 需要)
                eos_message = meta.get('eos_message')
                if eos_message:
                    ws.send(json.dumps(eos_message, ensure_ascii=False) if isinstance(eos_message, dict) else str(eos_message))

            # 3. 持续接收响应直到会话结束或超时
            # 使用 session_end_mapping 来判断是否结束 (由 APIDriver 传递或在此解析)
            session_end_path = meta.get('session_end_mapping')
            
            ws.settimeout(meta.get('recv_timeout', 5)) # 接收单条消息的超时
            
            max_responses = meta.get('max_responses', 100)
            for _ in range(max_responses):
                try:
                    msg = ws.recv()
                    if not msg: break
                    
                    all_responses.append(msg)
                    
                    # 尝试解析 JSON 并检查结束标志
                    try:
                        msg_json = json.loads(msg)
                        last_json = msg_json
                        
                        # 如果配置了结束标志路径，则检查
                        if session_end_path:
                            if APIClient._extract_by_path(msg_json, session_end_path) is True:
                                break
                    except:
                        pass
                except websocket.WebSocketTimeoutException:
                    # 如果超时了还没有收到结束标志，可能是发送完了或者网络延迟
                    break
                except Exception as e:
                    error = f"Recv error: {str(e)}"
                    break
                    
        except Exception as e:
            error = str(e)
        finally:
            if ws:
                ws.close()
                
        latency = int((time.time() - start_time) * 1000)
        
        return {
            "status_code": 200 if not error else 500,
            "latency": latency,
            "raw_response": "\n".join(all_responses) if all_responses else "",
            "json": last_json, # 返回最后一条响应的 JSON 作为主要参考
            "all_responses": all_responses, # 返回所有原始响应供后续聚合
            "error": error
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
