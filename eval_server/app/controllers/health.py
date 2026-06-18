from flask import Blueprint, jsonify
from ..services.task_service import TaskService
from ..utils.concurrency import ConcurrencyManager

health_bp = Blueprint('health', __name__)

@health_bp.route('/health', methods=['GET'])
def health_check():
    stats = ConcurrencyManager.get_stats()

    supported_types = list(stats.keys())

    type_concurrency = {}
    for task_type, type_stats in stats.items():
        type_concurrency[task_type] = {
            'max_concurrency': type_stats['max'],
            'current_concurrency': type_stats['current'],
            'available': type_stats['max'] - type_stats['current'],
        }

    response_data = {
        "status": "healthy",
        "service": "wer-ser-calculator",
        "role": "master",
        "supported_task_types": supported_types,
        "concurrency": type_concurrency,
    }
    return jsonify(response_data), 200
