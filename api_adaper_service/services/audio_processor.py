import soundfile as sf
import numpy as np
import os
from utils.logger import logger
from utils.config import config

class AudioProcessor:
    def __init__(self):
        self.frame_duration_ms = config.get('audio.frame_duration_ms', 80)
        self.sample_rate = config.get('audio.sample_rate', 16000)
        self.channels = config.get('audio.channels', 1)
        self.bit_depth = config.get('audio.bit_depth', 16)
        self.frame_send_interval_ms = config.get('audio.frame_send_interval_ms', 10)
        
        # Calculate samples per frame
        self.samples_per_frame = int(self.sample_rate * self.frame_duration_ms / 1000)
        
        logger.info(f"Audio processor initialized: frame_duration={self.frame_duration_ms}ms, sample_rate={self.sample_rate}Hz, samples_per_frame={self.samples_per_frame}")
    
    def load_audio(self, audio_path):
        """Load audio file and convert to required format"""
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        try:
            # Load audio file
            data, sr = sf.read(audio_path)
            
            # Convert to mono if needed
            if len(data.shape) > 1 and data.shape[1] > 1:
                data = np.mean(data, axis=1)
            
            # Resample if needed
            if sr != self.sample_rate:
                logger.warning(f"Resampling audio from {sr}Hz to {self.sample_rate}Hz")
                from scipy.signal import resample
                data = resample(data, int(len(data) * self.sample_rate / sr))
            
            # Normalize to float32
            if data.dtype == np.int16:
                data = data.astype(np.float32) / 32768.0
            elif data.dtype == np.int32:
                data = data.astype(np.float32) / 2147483648.0
            
            logger.info(f"Loaded audio: {audio_path}, duration: {len(data)/self.sample_rate:.2f}s")
            return data
        except Exception as e:
            logger.error(f"Error loading audio: {str(e)}")
            raise
    
    def generate_frames(self, audio_data):
        """Generate audio frames from audio data"""
        total_samples = len(audio_data)
        frame_index = 0
        total_frames = (total_samples + self.samples_per_frame - 1) // self.samples_per_frame
        
        logger.info(f"Generating frames: total_samples={total_samples}, total_frames={total_frames}")
        
        while frame_index < total_samples:
            # Calculate frame boundaries
            start = frame_index
            end = min(frame_index + self.samples_per_frame, total_samples)
            
            # Extract frame data
            frame_data = audio_data[start:end]
            frame_seq = frame_index // self.samples_per_frame
            
            # Pad with zeros if less than full frame
            if len(frame_data) < self.samples_per_frame:
                logger.debug(f"Padding frame {frame_seq} with zeros: current_length={len(frame_data)}, expected={self.samples_per_frame}")
                frame_data = np.pad(frame_data, (0, self.samples_per_frame - len(frame_data)), 'constant')
            
            # Convert to 16-bit PCM
            pcm_data = (frame_data * 32767).astype(np.int16)
            
            logger.debug(f"Generated frame {frame_seq}/{total_frames}: start_sample={start}, end_sample={end}, is_last={end >= total_samples}")
            
            yield {
                'frame_seq': frame_seq,
                'frame_data': pcm_data,
                'is_last': end >= total_samples,
                'timestamp': start / self.sample_rate
            }
            
            frame_index = end
        
        logger.info(f"Frame generation completed: total_frames={total_frames}")
    
    def convert_to_bytes(self, pcm_data):
        """Convert PCM data to bytes"""
        byte_data = pcm_data.tobytes()
        logger.debug(f"Converted PCM to bytes: {len(pcm_data)} samples -> {len(byte_data)} bytes")
        return byte_data
    
    def get_frame_info(self, frame_data):
        """Get frame information"""
        info = {
            'samples': len(frame_data),
            'duration_ms': self.frame_duration_ms,
            'bytes': len(frame_data) * 2,  # 16-bit PCM
            'sample_rate': self.sample_rate
        }
        logger.debug(f"Frame info: {info}")
        return info
    
    def validate_audio(self, audio_path):
        """Validate audio file format"""
        logger.info(f"Validating audio file: {audio_path}")
        try:
            data, sr = sf.read(audio_path)
            channels = 1 if len(data.shape) == 1 else data.shape[1]
            duration = len(data)/sr
            
            is_valid = True
            errors = []
            
            if sr != self.sample_rate:
                is_valid = False
                errors.append(f"Sample rate mismatch: {sr}Hz (expected {self.sample_rate}Hz)")
            
            if channels != self.channels:
                is_valid = False
                errors.append(f"Channel count mismatch: {channels} (expected {self.channels})")
            
            result = {
                'valid': is_valid,
                'sample_rate': sr,
                'channels': channels,
                'duration': duration,
                'errors': errors
            }
            
            if is_valid:
                logger.info(f"Audio validation passed: {audio_path}, duration: {duration:.2f}s, sample_rate: {sr}Hz, channels: {channels}")
            else:
                logger.warning(f"Audio validation failed: {audio_path}, errors: {errors}")
            
            return result
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error validating audio {audio_path}: {error_msg}")
            return {
                'valid': False,
                'sample_rate': 0,
                'channels': 0,
                'duration': 0,
                'errors': [error_msg]
            }

# Singleton instance
audio_processor = AudioProcessor()
