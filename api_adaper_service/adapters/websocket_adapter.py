import websocket
import json
import time
from utils.logger import logger
from utils.config import config

class WebSocketAdapter:
    def __init__(self, vendor_config):
        self.ws_url = vendor_config['ws_url']
        self.connect_headers = vendor_config['connect_headers']
        self.frame_header_template = vendor_config['frame_header_template']
        self.result_parser = vendor_config['result_parser']
        
        # WebSocket instance
        self.ws = None
        
        # Callbacks
        self.callbacks = {
            'on_open': self._default_on_open,
            'on_message': self._default_on_message,
            'on_error': self._default_on_error,
            'on_close': self._default_on_close,
            'on_send': self._default_on_send
        }
        
        # Connection status
        self.connected = False
        self.connect_time = None
        
        # Config
        self.reconnect_max = config.get('websocket.reconnect_max', 5)
        self.connect_timeout = config.get('websocket.connect_timeout', 10)
        self.no_heartbeat = config.get('websocket.no_heartbeat', True)
        
        logger.info(f"WebSocket adapter initialized: url={self.ws_url}, no_heartbeat={self.no_heartbeat}")
    
    def _default_on_open(self, task_id, session_id):
        """Default on_open callback"""
        logger.info(f"WebSocket connected for task {task_id}, session_id: {session_id}")
    
    def _default_on_message(self, task_id, frame_seq, asr_text, trans_text, raw_message):
        """Default on_message callback"""
        logger.debug(f"Received message for task {task_id}, frame {frame_seq}: {asr_text[:20]}...")
    
    def _default_on_error(self, task_id, error):
        """Default on_error callback"""
        logger.error(f"WebSocket error for task {task_id}: {str(error)}")
    
    def _default_on_close(self, task_id, close_code, close_reason):
        """Default on_close callback"""
        logger.info(f"WebSocket closed for task {task_id}: code={close_code}, reason={close_reason}")
    
    def _default_on_send(self, task_id, frame_seq, frame_size):
        """Default on_send callback"""
        logger.debug(f"Sent frame {frame_seq} for task {task_id}, size={frame_size} bytes")
    
    def set_callback(self, callback_type, callback_func):
        """Set custom callback function"""
        if callback_type in self.callbacks:
            self.callbacks[callback_type] = callback_func
            logger.info(f"Set custom callback: {callback_type}")
        else:
            logger.error(f"Invalid callback type: {callback_type}")
    
    def connect(self, task_id, session_id, source_lang='zh', target_lang='en'):
        """Connect to WebSocket server"""
        try:
            logger.info(f"Connecting to WebSocket for task {task_id}, session {session_id}")
            logger.debug(f"WebSocket URL: {self.ws_url}")
            
            # Prepare connection headers
            headers = {k: v for k, v in self.connect_headers.items()}
            logger.debug(f"Connection headers: {headers}")
            
            # Create WebSocket instance
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                header=headers,
                on_open=lambda ws: self._on_open(ws, task_id, session_id),
                on_message=lambda ws, msg: self._on_message(ws, msg, task_id),
                on_error=lambda ws, err: self._on_error(ws, err, task_id),
                on_close=lambda ws, code, reason: self._on_close(ws, code, reason, task_id)
            )
            
            # Start WebSocket connection in a separate thread
            import threading
            ws_thread = threading.Thread(
                target=self.ws.run_forever,
                kwargs={'ping_timeout': None if self.no_heartbeat else 30}
            )
            ws_thread.daemon = True
            ws_thread.start()
            logger.debug(f"WebSocket thread started for task {task_id}")
            
            # Wait for connection to establish
            timeout = time.time() + self.connect_timeout
            logger.debug(f"Waiting for connection to establish, timeout: {self.connect_timeout}s")
            
            while not self.connected and time.time() < timeout:
                time.sleep(0.1)
            
            if not self.connected:
                logger.error(f"WebSocket connection timeout after {self.connect_timeout}s for task {task_id}")
                raise TimeoutError(f"WebSocket connection timeout after {self.connect_timeout}s")
            
            logger.info(f"WebSocket connection established successfully for task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Error connecting to WebSocket for task {task_id}: {str(e)}")
            self.callbacks['on_error'](task_id, str(e))
            return False
    
    def _on_open(self, ws, task_id, session_id):
        """Internal on_open handler"""
        self.connected = True
        self.connect_time = time.time()
        logger.info(f"WebSocket connection opened for task {task_id}, session {session_id}")
        logger.debug(f"Connection established at: {self.connect_time}")
        self.callbacks['on_open'](task_id, session_id)
    
    def _on_message(self, ws, message, task_id):
        """Internal on_message handler"""
        try:
            logger.debug(f"Received raw message for task {task_id}, size: {len(message)} bytes")
            
            # Parse JSON message
            msg_data = json.loads(message)
            logger.debug(f"Parsed message data for task {task_id}: {msg_data}")
            
            # Extract ASR and translation results
            asr_text = self._extract_field(msg_data, self.result_parser['asr_field'], '')
            trans_text = self._extract_field(msg_data, self.result_parser['trans_field'], '')
            
            # Extract frame sequence (default to 0 if not found)
            frame_seq = msg_data.get('seq', 0)
            
            logger.info(f"Processed message for task {task_id}, frame {frame_seq}: ASR='{asr_text[:30]}...', TRANS='{trans_text[:30]}...'")
            
            # Call user callback
            self.callbacks['on_message'](task_id, frame_seq, asr_text, trans_text, msg_data)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing WebSocket message for task {task_id}: {str(e)}")
            logger.debug(f"Raw message causing parse error: {message}")
            self.callbacks['on_error'](task_id, f"JSON parse error: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message for task {task_id}: {str(e)}")
            self.callbacks['on_error'](task_id, f"Message processing error: {str(e)}")
    
    def _extract_field(self, data, field_path, default=''):
        """Extract field from nested JSON data"""
        keys = field_path.split('.')
        value = data
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def _on_error(self, ws, error, task_id):
        """Internal on_error handler"""
        self.callbacks['on_error'](task_id, str(error))
    
    def _on_close(self, ws, close_code, close_reason, task_id):
        """Internal on_close handler"""
        logger.info(f"WebSocket connection closing for task {task_id}: code={close_code}, reason={close_reason}")
        self.connected = False
        self.callbacks['on_close'](task_id, close_code, close_reason)
    
    def send_frame(self, task_id, frame_seq, frame_data, session_id, source_lang='zh', target_lang='en'):
        """Send audio frame to WebSocket server"""
        try:
            if not self.connected or not self.ws:
                logger.error(f"Cannot send frame {frame_seq}: WebSocket not connected for task {task_id}")
                return False
            
            logger.debug(f"Sending frame {frame_seq} for task {task_id}, audio data size: {len(frame_data)} bytes")
            
            # Prepare frame header
            header = self._prepare_frame_header(frame_seq, session_id, source_lang, target_lang)
            logger.debug(f"Frame header for task {task_id}, frame {frame_seq}: {header}")
            
            # Create frame payload (header + audio data)
            frame_payload = {
                'header': header,
                'payload': frame_data.hex()  # Convert binary to hex string
            }
            
            # Send JSON frame
            self.ws.send(json.dumps(frame_payload))
            
            # Call send callback
            self.callbacks['on_send'](task_id, frame_seq, len(frame_data))
            
            logger.debug(f"Frame {frame_seq} sent successfully for task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending frame {frame_seq} for task {task_id}: {str(e)}")
            self.callbacks['on_error'](task_id, str(e))
            return False
    
    def _prepare_frame_header(self, frame_seq, session_id, source_lang, target_lang):
        """Prepare frame header based on template"""
        # Create a copy of the template
        header = json.loads(json.dumps(self.frame_header_template))
        
        # Replace placeholders
        def replace_placeholders(obj):
            if isinstance(obj, dict):
                return {k: replace_placeholders(v) for k, v in obj.items()}
            elif isinstance(obj, str):
                return v.format(
                    session_id=session_id,
                    source_lang=source_lang,
                    target_lang=target_lang
                )
            else:
                return obj
        
        # Replace seq directly
        header['seq'] = frame_seq
        
        # Replace other placeholders
        if 'request_meta' in header:
            header['request_meta'] = replace_placeholders(header['request_meta'])
        
        return header
    
    def close(self):
        """Close WebSocket connection"""
        if self.ws:
            logger.info("Closing WebSocket connection")
            self.ws.close()
            self.connected = False
            logger.info("WebSocket connection closed successfully")
    
    def is_connected(self):
        """Check if WebSocket is connected"""
        return self.connected
