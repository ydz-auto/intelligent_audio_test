import sys
import os
import argparse

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import time
from utils.config import config
from utils.logger import logger
from services.task_manager import task_manager
from services.audio_processor import audio_processor
from adapters.websocket_adapter import WebSocketAdapter
from adapters.mock_adapter import MockAdapter

# Create Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS

# Global variables
process_threads = {}  # task_id -> thread mapping
task_type_counts = {}  # task_type -> count mapping

def process_audio_task(task):
    """Process audio task in a separate thread"""
    task_id = task['task_id']
    session_id = task['session_id']
    audio_path = task['audio_path']
    trans_direction = task['trans_direction']
    vendor = task['vendor']
    
    try:
        # Update task status to processing
        task_manager.update_task_status(task_id, task_manager.STATUS_PROCESSING)
        
        # Load audio file
        audio_data = audio_processor.load_audio(audio_path)
        
        # Get vendor config
        vendor_config = config['vendor'][vendor]
        
        # Create adapter based on vendor
        if vendor == 'mock':
            # Use mock adapter for testing
            adapter = MockAdapter(vendor_config)
            logger.info(f"Using mock adapter for task {task_id}")
        else:
            # Use WebSocket adapter for real vendors
            adapter = WebSocketAdapter(vendor_config)
            logger.info(f"Using WebSocket adapter for task {task_id}, vendor: {vendor}")
        
        # Set custom callbacks
        def on_message(task_id, frame_seq, asr_text, trans_text, raw_message):
            """Custom on_message callback"""
            logger.info(f"Task {task_id} frame {frame_seq}: {asr_text[:10]}...")
            # Add frame result to task manager
            task_manager.add_frame_result(task_id, frame_seq, asr_text, trans_text)
        
        def on_error(task_id, error):
            """Custom on_error callback"""
            logger.error(f"Task {task_id} error: {str(error)}")
            task_manager.update_task_status(task_id, task_manager.STATUS_FAILED, str(error))
        
        def on_close(task_id, close_code, close_reason):
            """Custom on_close callback"""
            logger.info(f"Task {task_id} connection closed")
            # Set final result by combining all frame results
            finalize_task(task_id)
        
        adapter.set_callback('on_message', on_message)
        adapter.set_callback('on_error', on_error)
        adapter.set_callback('on_close', on_close)
        
        # Connect to server
        source_lang, target_lang = trans_direction.split('2')
        if not adapter.connect(task_id, session_id, source_lang, target_lang):
            raise Exception("Failed to connect to server")
        
        # Send audio frames
        for frame in audio_processor.generate_frames(audio_data):
            # Convert frame data to bytes
            frame_bytes = audio_processor.convert_to_bytes(frame['frame_data'])
            
            # Send frame
            if not adapter.send_frame(
                task_id, 
                frame['frame_seq'], 
                frame_bytes, 
                session_id, 
                source_lang, 
                target_lang
            ):
                logger.error(f"Failed to send frame {frame['frame_seq']} for task {task_id}")
                break
            
            # No delay between frames for immediate processing
        
        # Close adapter
        adapter.close()
        
        # For mock adapter, directly finalize task since on_close callback is not triggered
        if vendor == 'mock':
            finalize_task(task_id)
        
        # No delay for immediate processing of final frames
        
    except Exception as e:
        logger.error(f"Error processing task {task_id}: {str(e)}")
        task_manager.update_task_status(task_id, task_manager.STATUS_FAILED, str(e))
    finally:
        # Remove thread from tracking
        if task_id in process_threads:
            del process_threads[task_id]
        
        # Decrement count for this task type
        if trans_direction in task_type_counts:
            current_count = task_type_counts[trans_direction]
            new_count = max(0, current_count - 1)
            task_type_counts[trans_direction] = new_count
            logger.info(f"Decremented {trans_direction} count to {new_count}")
        else:
            logger.warning(f"Task type {trans_direction} not found in task_type_counts when decrementing")

def finalize_task(task_id):
    """Finalize task by combining frame results"""
    try:
        # Get all frame results
        frame_results = task_manager.frame_results.get(task_id, [])
        
        # Combine ASR and translation results
        final_asr = ''
        final_trans = ''
        
        for frame in frame_results:
            final_asr += frame['asr_text'] + ' '
            final_trans += frame['trans_text'] + ' '
        
        # Trim whitespace
        final_asr = final_asr.strip()
        final_trans = final_trans.strip()
        
        # Set final result
        task_manager.set_final_result(task_id, final_asr, final_trans)
        
        logger.info(f"Finalized task {task_id}, total_frames: {len(frame_results)}")
    except Exception as e:
        logger.error(f"Error finalizing task {task_id}: {str(e)}")
        task_manager.update_task_status(task_id, task_manager.STATUS_FAILED, str(e))


def task_type_concurrency_limit(func):
    """Decorator to limit concurrency based on task type"""
    def wrapper(*args, **kwargs):
        # Get request data
        data = request.get_json()
        if not data or 'trans_direction' not in data:
            return jsonify({
                'code': -1,
                'msg': 'Missing required field: trans_direction',
                'data': {}
            }), 400
        
        # Get task type (trans_direction)
        task_type = data['trans_direction']
        
        # Get max concurrency for this task type from config
        task_concurrency_config = config['server'].get('task_concurrency', {})
        max_concurrency = task_concurrency_config.get(task_type, task_concurrency_config.get('default', 10))
        
        # Get current count for this task type
        current_count = task_type_counts.get(task_type, 0)
        
        # Check if we've reached the limit
        if current_count >= max_concurrency:
            logger.warning(f"Task type {task_type} has reached max concurrency: {current_count}/{max_concurrency}")
            return jsonify({
                'code': -2,
                'msg': f'Task type {task_type} has reached max concurrency limit {max_concurrency}',
                'data': {
                    'task_type': task_type,
                    'current_concurrency': current_count,
                    'max_concurrency': max_concurrency
                }
            }), 429  # Too Many Requests
        
        # Increment count for this task type
        task_type_counts[task_type] = current_count + 1
        logger.info(f"Incremented {task_type} count to {current_count + 1}/{max_concurrency}")
        
        try:
            # Execute the decorated function
            return func(*args, **kwargs)
        finally:
            # Decrement count when task is complete
            # Note: This only handles the case where the request completes normally
            # We also need to decrement when the task thread finishes
            pass
    return wrapper

@app.route('/api/create_task', methods=['POST'])
@task_type_concurrency_limit
def api_create_task():
    """API: Create a new audio processing task"""
    try:
        logger.info(f"Received create_task request from {request.remote_addr}")
        data = request.get_json()
        logger.debug(f"Request data: {data}")
        
        # Validate required fields
        if not data or 'audio_path' not in data or 'trans_direction' not in data:
            logger.warning(f"Missing required fields in create_task request from {request.remote_addr}")
            return jsonify({
                'code': -1,
                'msg': 'Missing required fields: audio_path, trans_direction',
                'data': {}
            }), 400
        
        # Create task
        task = task_manager.create_task(
            audio_path=data['audio_path'],
            trans_direction=data['trans_direction'],
            vendor=data.get('vendor', 'volc_ast')
        )
        
        # Start processing thread
        thread = threading.Thread(target=process_audio_task, args=(task,))
        thread.daemon = True
        thread.start()
        process_threads[task['task_id']] = thread
        
        logger.info(f"Created task {task['task_id']} for {request.remote_addr}, started processing thread")
        
        # Return response
        return jsonify({
            'code': 0,
            'msg': 'success',
            'data': {
                'task_id': task['task_id'],
                'status_url': f"http://localhost:{config['server']['port']}/api/get_status/{task['task_id']}",
                'frame_results_url': f"http://localhost:{config['server']['port']}/api/get_frame_results/{task['task_id']}",
                'final_result_url': f"http://localhost:{config['server']['port']}/api/get_final_result/{task['task_id']}",
                'msg': '任务已创建，处理完成后可分别查询中间帧结果和最终聚合结果'
            }
        })
    except Exception as e:
        logger.error(f"Error creating task for {request.remote_addr}: {str(e)}")
        return jsonify({
            'code': -1,
            'msg': f'Failed to create task: {str(e)}',
            'data': {}
        }), 500

@app.route('/api/get_status/<task_id>', methods=['GET'])
def api_get_status(task_id):
    """API: Get task status"""
    try:
        logger.info(f"Received get_status request for task {task_id} from {request.remote_addr}")
        task = task_manager.get_task(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found in get_status request from {request.remote_addr}")
            return jsonify({
                'code': -1,
                'msg': 'Task not found',
                'data': {}
            }), 404
        
        logger.debug(f"Returning status for task {task_id}: {task['status']}")
        return jsonify({
            'code': 0,
            'msg': 'success',
            'data': {
                'task_id': task['task_id'],
                'status': task['status'],
                'total_frames': task['total_frames'],
                'error_msg': task['error_msg']
            }
        })
    except Exception as e:
        logger.error(f"Error getting status for task {task_id} from {request.remote_addr}: {str(e)}")
        return jsonify({
            'code': -1,
            'msg': f'Failed to get task status: {str(e)}',
            'data': {}
        }), 500

@app.route('/api/get_frame_results/<task_id>', methods=['GET'])
def api_get_frame_results(task_id):
    """API: Get frame intermediate results"""
    try:
        logger.info(f"Received get_frame_results request for task {task_id} from {request.remote_addr}")
        
        # Get query parameters
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', config['result']['default_page_size']))
        all_results = request.args.get('all', 'false').lower() == 'true'
        
        logger.debug(f"Query parameters: page={page}, page_size={page_size}, all={all_results}")
        
        # Get frame results
        result = task_manager.get_frame_results(task_id, page, page_size, all_results)
        if not result:
            logger.warning(f"Frame results not found for task {task_id} in request from {request.remote_addr}")
            return jsonify({
                'code': -1,
                'msg': 'Task not found',
                'data': {}
            }), 404
        
        logger.debug(f"Returning {len(result['frame_results'])} frame results for task {task_id}")
        return jsonify({
            'code': 0,
            'msg': 'success',
            'data': result
        })
    except Exception as e:
        logger.error(f"Error getting frame results for task {task_id} from {request.remote_addr}: {str(e)}")
        return jsonify({
            'code': -1,
            'msg': f'Failed to get frame results: {str(e)}',
            'data': {}
        }), 500

@app.route('/api/get_final_result/<task_id>', methods=['GET'])
def api_get_final_result(task_id):
    """API: Get final aggregated result"""
    try:
        logger.info(f"Received get_final_result request for task {task_id} from {request.remote_addr}")
        
        # Get final result
        result = task_manager.get_final_result(task_id)
        if not result:
            logger.warning(f"Final result not found for task {task_id} in request from {request.remote_addr}")
            return jsonify({
                'code': -1,
                'msg': 'Task not found',
                'data': {}
            }), 404
        
        logger.debug(f"Returning final result for task {task_id}")
        return jsonify({
            'code': 0,
            'msg': 'success',
            'data': result
        })
    except Exception as e:
        logger.error(f"Error getting final result for task {task_id} from {request.remote_addr}: {str(e)}")
        return jsonify({
            'code': -1,
            'msg': f'Failed to get final result: {str(e)}',
            'data': {}
        }), 500

@app.route('/api/delete_task/<task_id>', methods=['DELETE'])
def api_delete_task(task_id):
    """API: Delete task"""
    try:
        logger.info(f"Received delete_task request for task {task_id} from {request.remote_addr}")
        
        if task_manager.delete_task(task_id):
            logger.info(f"Deleted task {task_id} requested by {request.remote_addr}")
            return jsonify({
                'code': 0,
                'msg': f'任务{task_id}已成功删除',
                'data': {
                    'task_id': task_id
                }
            })
        else:
            logger.warning(f"Task {task_id} not found in delete_task request from {request.remote_addr}")
            return jsonify({
                'code': -1,
                'msg': 'Task not found',
                'data': {}
            }), 404
    except Exception as e:
        logger.error(f"Error deleting task {task_id} from {request.remote_addr}: {str(e)}")
        return jsonify({
            'code': -1,
            'msg': f'Failed to delete task: {str(e)}',
            'data': {}
        }), 500

@app.route('/health', methods=['GET'])
def api_health():
    """API: Health check"""
    try:
        logger.info(f"Received health check request from {request.remote_addr}")
        
        # Get current concurrency (number of active threads)
        current_concurrency = len(process_threads)
        # Get max concurrency from config
        max_concurrency = config.get('server.max_concurrency', 100)
        
        response = jsonify({
            'status': 'healthy',
            'service': 'audio-executor',
            'no_heartbeat': config.get('websocket.no_heartbeat', True),
            'frame_duration_ms': config.get('audio.frame_duration_ms', 80),
            'current_concurrency': current_concurrency,
            'max_concurrency': max_concurrency
        })
        
        logger.debug(f"Returning health check response: healthy")
        return response
    except Exception as e:
        logger.error(f"Health check failed for {request.remote_addr}: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run audio-executor server on specified ports')
    parser.add_argument('--ports', type=str, default='8000,8001,8002', help='Comma-separated list of ports to run the server on')
    parser.add_argument('--port', type=int, default=None, help='Single port to run the server on')
    args = parser.parse_args()
    
    # Get host and dev mode from config
    host = config['server']['host']
    dev_mode = config['server']['dev_mode']
    
    # Determine which ports to use
    ports_to_run = []
    
    if args.port:
        # Single port specified
        ports_to_run = [args.port]
    elif args.ports:
        # Multiple ports specified
        ports_to_run = [int(port.strip()) for port in args.ports.split(',')]
    else:
        # Use default port from config
        ports_to_run = [config['server']['port']]
    
    for port in ports_to_run:
        # Create a copy of the app for each port (in case of multiple ports)
        app_copy = Flask(__name__)
        CORS(app_copy)
        
        # Copy all routes from the original app
        for rule in app.url_map.iter_rules():
            if rule.endpoint != 'static':
                view_func = app.view_functions[rule.endpoint]
                app_copy.add_url_rule(rule.rule, rule.endpoint, view_func, methods=rule.methods)
        
        # Update config port for this instance
        config['server']['port'] = port
        
        logger.info(f"Starting audio-executor server on {host}:{port}, dev_mode={dev_mode}")
        logger.info(f"No heartbeat mode: {config.get('websocket.no_heartbeat', True)}")
        
        # Run each server in a separate thread
        def run_server(app_instance, host, port, debug):
            app_instance.run(host=host, port=port, debug=debug, use_reloader=False)
        
        thread = threading.Thread(target=run_server, args=(app_copy, host, port, dev_mode))
        thread.daemon = True
        thread.start()
    
    # Keep the main thread running
    if len(ports_to_run) > 1:
        logger.info(f"Running {len(ports_to_run)} servers. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down servers...")
    else:
        # For single port, run in main thread (easier debugging)
        config['server']['port'] = ports_to_run[0]
        app.run(host=host, port=ports_to_run[0], debug=dev_mode)
