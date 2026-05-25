import uuid
import time
from collections import defaultdict
from utils.logger import logger

class TaskManager:
    def __init__(self):
        # Task status constants
        self.STATUS_NOT_STARTED = 'processing'  # 初始状态，任务创建后立即开始处理
        self.STATUS_PROCESSING = 'processing'   # 处理中
        self.STATUS_COMPLETED = 'completed'     # 完成
        self.STATUS_FAILED = 'failed'           # 失败
        
        # Task storage
        self.tasks = {}
        self.frame_results = defaultdict(list)
        self.final_results = {}
        
        # Task counter
        self.task_count = 0
    
    def create_task(self, audio_path, trans_direction, vendor):
        """Create a new audio processing task"""
        task_id = f"task_{uuid.uuid4().hex[:10]}"
        session_id = uuid.uuid4().hex
        
        task = {
            'task_id': task_id,
            'session_id': session_id,
            'audio_path': audio_path,
            'trans_direction': trans_direction,
            'vendor': vendor,
            'status': self.STATUS_NOT_STARTED,
            'create_time': time.time(),
            'update_time': time.time(),
            'total_frames': 0,
            'error_msg': '',
            'final_asr_result': '',
            'final_trans_result': ''
        }
        
        self.tasks[task_id] = task
        self.frame_results[task_id] = []
        self.task_count += 1
        
        logger.info(f"Created task: {task_id}, audio_path: {audio_path}")
        return task
    
    def get_task(self, task_id):
        """Get task by ID"""
        task = self.tasks.get(task_id)
        if task:
            logger.debug(f"Retrieved task {task_id}, status: {task['status']}")
        else:
            logger.warning(f"Task {task_id} not found when attempting to retrieve")
        return task
    
    def update_task_status(self, task_id, status, error_msg=''):
        """Update task status"""
        if task_id in self.tasks:
            self.tasks[task_id]['status'] = status
            self.tasks[task_id]['update_time'] = time.time()
            if error_msg:
                self.tasks[task_id]['error_msg'] = error_msg
            logger.info(f"Updated task {task_id} status: {status}")
            return True
        return False
    
    def add_frame_result(self, task_id, frame_seq, asr_text, trans_text):
        """Add frame result"""
        if task_id in self.tasks:
            frame_result = {
                'frame_seq': frame_seq,
                'asr_text': asr_text,
                'trans_text': trans_text,
                'timestamp': time.time()
            }
            self.frame_results[task_id].append(frame_result)
            self.tasks[task_id]['total_frames'] += 1
            self.tasks[task_id]['update_time'] = time.time()
            logger.debug(f"Added frame {frame_seq} result for task {task_id}")
            return True
        logger.warning(f"Task {task_id} not found when attempting to add frame result")
        return False
    
    def set_final_result(self, task_id, final_asr_result, final_trans_result):
        """Set final result"""
        if task_id in self.tasks:
            self.tasks[task_id]['final_asr_result'] = final_asr_result
            self.tasks[task_id]['final_trans_result'] = final_trans_result
            self.tasks[task_id]['status'] = self.STATUS_COMPLETED
            self.tasks[task_id]['update_time'] = time.time()
            
            self.final_results[task_id] = {
                'final_asr_result': final_asr_result,
                'final_trans_result': final_trans_result,
                'total_frames': self.tasks[task_id]['total_frames']
            }
            
            logger.info(f"Set final result for task {task_id}")
            return True
        return False
    
    def get_frame_results(self, task_id, page=1, page_size=1000, all_results=False):
        """Get frame results with pagination"""
        if task_id not in self.frame_results:
            logger.warning(f"Frame results not found for task {task_id}")
            return None
        
        results = self.frame_results[task_id]
        total_frames = len(results)
        logger.debug(f"Retrieved frame results for task {task_id}: total_frames={total_frames}, page={page}, page_size={page_size}, all_results={all_results}")
        
        if all_results:
            return {
                'task_id': task_id,
                'status': self.tasks[task_id]['status'],
                'total_frames': total_frames,
                'frame_results': results
            }
        
        # Calculate pagination
        total_pages = (total_frames + page_size - 1) // page_size
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        return {
            'task_id': task_id,
            'status': self.tasks[task_id]['status'],
            'total_frames': total_frames,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'frame_results': results[start_idx:end_idx]
        }
    
    def get_final_result(self, task_id):
        """Get final result"""
        if task_id not in self.tasks:
            logger.warning(f"Final result not found for task {task_id}")
            return None
        
        task = self.tasks[task_id]
        logger.debug(f"Retrieved final result for task {task_id}, status: {task['status']}")
        return {
            'task_id': task_id,
            'status': task['status'],
            'create_time': task['create_time'],
            'update_time': task['update_time'],
            'final_asr_result': task['final_asr_result'],
            'final_trans_result': task['final_trans_result'],
            'total_frames': task['total_frames'],
            'error_msg': task['error_msg']
        }
    
    def delete_task(self, task_id):
        """Delete task"""
        if task_id in self.tasks:
            del self.tasks[task_id]
            del self.frame_results[task_id]
            if task_id in self.final_results:
                del self.final_results[task_id]
            self.task_count -= 1
            logger.info(f"Deleted task {task_id}, remaining task count: {self.task_count}")
            return True
        logger.warning(f"Task {task_id} not found when attempting to delete")
        return False
    
    def get_task_count(self):
        """Get total task count"""
        logger.debug(f"Retrieved task count: {self.task_count}")
        return self.task_count
    
    def get_all_tasks(self):
        """Get all tasks"""
        tasks = list(self.tasks.values())
        logger.debug(f"Retrieved all tasks, count: {len(tasks)}")
        return tasks

# Singleton instance
task_manager = TaskManager()
