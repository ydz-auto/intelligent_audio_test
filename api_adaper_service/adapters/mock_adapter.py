import time
import random
from utils.logger import logger

class MockAdapter:
    def __init__(self, vendor_config):
        # Mock data
        self.mock_sentences = [
            "今天天气真好",
            "适合出去散步",
            "阳光明媚",
            "温度适宜",
            "空气清新",
            "鸟语花香",
            "心情愉悦",
            "享受大自然",
            "生活真美好",
            "珍惜每一天"
        ]
        
        self.mock_translations = [
            "The weather is nice today",
            "Perfect for a walk",
            "Sunny and bright",
            "Temperature is comfortable",
            "Fresh air",
            "Birds singing and flowers blooming",
            "Feeling happy",
            "Enjoying nature",
            "Life is beautiful",
            "Cherish every day"
        ]
        
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
        
        logger.info(f"Mock adapter initialized")
    
    def _default_on_open(self, task_id, session_id):
        """Default on_open callback"""
        logger.info(f"Mock adapter connected for task {task_id}, session_id: {session_id}")
    
    def _default_on_message(self, task_id, frame_seq, asr_text, trans_text, raw_message):
        """Default on_message callback"""
        logger.debug(f"Mock adapter received message for task {task_id}, frame {frame_seq}: {asr_text[:20]}...")
    
    def _default_on_error(self, task_id, error):
        """Default on_error callback"""
        logger.error(f"Mock adapter error for task {task_id}: {str(error)}")
    
    def _default_on_close(self, task_id, close_code, close_reason):
        """Default on_close callback"""
        logger.info(f"Mock adapter closed for task {task_id}: code={close_code}, reason={close_reason}")
    
    def _default_on_send(self, task_id, frame_seq, frame_size):
        """Default on_send callback"""
        logger.debug(f"Mock adapter sent frame {frame_seq} for task {task_id}, size={frame_size} bytes")
    
    def set_callback(self, callback_type, callback_func):
        """Set custom callback function"""
        if callback_type in self.callbacks:
            self.callbacks[callback_type] = callback_func
            logger.info(f"Set custom callback: {callback_type}")
        else:
            logger.error(f"Invalid callback type: {callback_type}")
    
    def connect(self, task_id, session_id, source_lang='zh', target_lang='en'):
        """Connect to mock server"""
        # No delay for immediate connection
        
        self.connected = True
        self.callbacks['on_open'](task_id, session_id)
        
        logger.info(f"Mock adapter connected for task {task_id}")
        return True
    
    def send_frame(self, task_id, frame_seq, frame_data, session_id, source_lang='zh', target_lang='en'):
        """Send audio frame to mock server"""
        if not self.connected:
            logger.error(f"Cannot send frame: Mock adapter not connected for task {task_id}")
            return False
        
        # No delay for immediate processing
        
        # Generate mock response
        sentence_idx = frame_seq % len(self.mock_sentences)
        asr_text = self.mock_sentences[sentence_idx]
        trans_text = self.mock_translations[sentence_idx]
        
        # Call send callback
        self.callbacks['on_send'](task_id, frame_seq, len(frame_data))
        
        # Call message callback (simulate receiving response)
        raw_message = {
            'header': {
                'session_id': session_id,
                'seq': frame_seq,
                'timestamp': int(time.time() * 1000)
            },
            'source_subtitle_response': {
                'subtitle': asr_text,
                'confidence': round(random.uniform(0.8, 0.99), 2),
                'start_time': frame_seq * 80,
                'end_time': (frame_seq + 1) * 80
            },
            'translation_response': {
                'subtitle': trans_text,
                'confidence': round(random.uniform(0.8, 0.99), 2),
                'start_time': frame_seq * 80,
                'end_time': (frame_seq + 1) * 80
            }
        }
        
        self.callbacks['on_message'](task_id, frame_seq, asr_text, trans_text, raw_message)
        
        # Always return True to ensure all frames are sent successfully
        # Connection close will be handled separately after all frames are sent
        return True
    
    def close(self):
        """Close mock connection"""
        self.connected = False
        # Trigger on_close callback for each task?
        # Since mock adapter doesn't track tasks, we'll just log
        logger.info("Mock adapter connection closed")
    
    def is_connected(self):
        """Check if mock adapter is connected"""
        return self.connected
