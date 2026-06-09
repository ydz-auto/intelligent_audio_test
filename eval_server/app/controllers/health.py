from flask import Blueprint, jsonify
from ..services.task_service import TaskService

health_bp = Blueprint('health', __name__)

@health_bp.route('/health', methods=['GET'])
def health_check():
    concurrency_info = TaskService.get_concurrency_info()
    
    # 构造符合 API_DOCUMENTATION.md 规范的响应
    response_data = {
        "status": "healthy",
        "service": "wer-ser-calculator",
        "role": "master",
        "supported_task_types": ["wer", "ser"],
        "local": {
            "wer": {
                "max_concurrency": concurrency_info['wer']['max'],
                "current_concurrency": concurrency_info['wer']['current']
            },
            "ser": {
                "max_concurrency": concurrency_info['ser']['max'],
                "current_concurrency": concurrency_info['ser']['current']
            }
        }
    }
    return jsonify(response_data), 200
