from flask import Blueprint
from api_gateway.controllers.report_controller import ReportController
from shared.utils.log_handler import log_and_emit

report_bp = Blueprint('reports', __name__)

@report_bp.route('', methods=['GET'])
def get_all():
    return ReportController.get_all()

@report_bp.route('/<int:report_id>', methods=['GET'])
def get_one(report_id):
    return ReportController.get_one(report_id)

@report_bp.route('/<int:report_id>', methods=['DELETE'])
def delete(report_id):
    return ReportController.delete(report_id)

@report_bp.route('/<int:report_id>', methods=['PUT'])
def update(report_id):
    return ReportController.update(report_id)

@report_bp.route('/<int:report_id>/publish', methods=['POST'])
def publish(report_id):
    return ReportController.publish(report_id)

@report_bp.route('/batch-delete', methods=['POST'])
def batch_delete():
    return ReportController.batch_delete()

@report_bp.route('/<int:report_id>/progress', methods=['GET'])
def get_progress(report_id):
    return ReportController.get_progress(report_id)

@report_bp.route('/compare', methods=['POST'])
def compare():
    return ReportController.compare()

@report_bp.route('/secondary-compare', methods=['POST'])
def secondary_compare():
    return ReportController.secondary_compare()

@report_bp.route('/generate-task', methods=['POST'])
def generate_task_report():
    return ReportController.generate_task_report()

@report_bp.route('/export', methods=['POST'])
def export():
    return ReportController.export()

@report_bp.route('/case-averages', methods=['POST'])
def get_case_averages_by_filters():
    return ReportController.get_case_averages_by_filters()

@report_bp.route('/<int:report_id>/cases', methods=['GET'])
def get_report_cases(report_id):
    return ReportController.get_report_cases(report_id)

@report_bp.route('/<int:report_id>/cases/search', methods=['POST'])
def search_report_cases(report_id):
    return ReportController.search_report_cases(report_id)

@report_bp.route('/<int:report_id>/cases/<case_id>/logs/download', methods=['GET'])
def download_case_logs(report_id, case_id):
    log_and_emit(
        level='INFO',
        module='report',
        content=f'收到下载日志请求 - report_id: {report_id}, case_id: {case_id}'
    )
    return ReportController.download_case_logs(report_id, case_id)
