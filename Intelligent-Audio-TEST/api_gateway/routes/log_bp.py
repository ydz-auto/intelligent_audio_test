from flask import Blueprint
from api_gateway.controllers.log_controller import LogController

log_bp = Blueprint('logs', __name__)

@log_bp.route('', methods=['GET'])
def get_logs():
    return LogController.get_logs()

@log_bp.route('/stats', methods=['GET'])
def get_stats():
    return LogController.get_stats()

@log_bp.route('/mark', methods=['PUT'])
def mark_logs():
    return LogController.mark_logs()

@log_bp.route('/export', methods=['GET', 'POST'])
def export_logs():
    return LogController.export_logs()

@log_bp.route('/refresh', methods=['POST'])
def refresh_logs():
    return LogController.refresh_logs()

@log_bp.route('/clear', methods=['POST'])
def clear_logs():
    return LogController.clear_logs()

@log_bp.route('/archive/status', methods=['GET'])
def get_archive_status():
    return LogController.get_archive_status()

@log_bp.route('/archive', methods=['POST'])
def archive_logs():
    return LogController.archive_logs()

@log_bp.route('/archive/logs', methods=['GET'])
def get_archived_logs():
    return LogController.get_archived_logs()

@log_bp.route('/archive/<filename>', methods=['GET'])
def download_archive(filename):
    return LogController.download_archive(filename)

@log_bp.route('/archive/<filename>', methods=['DELETE'])
def delete_archive(filename):
    return LogController.delete_archive(filename)
