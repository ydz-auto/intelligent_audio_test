from flask import Blueprint
from backend.controllers.testcase_controller import TestCaseController

testcase_bp = Blueprint('testcases', __name__)

@testcase_bp.route('', methods=['GET'])
def get_all():
    return TestCaseController.get_all()

@testcase_bp.route('/<tc_id>', methods=['GET'])
def get_one(tc_id):
    return TestCaseController.get_one(tc_id)

@testcase_bp.route('', methods=['POST'])
def create():
    return TestCaseController.create()

@testcase_bp.route('/<tc_id>', methods=['PUT'])
def update(tc_id):
    return TestCaseController.update(tc_id)

@testcase_bp.route('/<tc_id>', methods=['DELETE'])
def delete(tc_id):
    return TestCaseController.delete(tc_id)

@testcase_bp.route('/<tc_id>/copy', methods=['POST'])
def copy(tc_id):
    return TestCaseController.copy(tc_id)

@testcase_bp.route('/<tc_id>/preview', methods=['POST'])
def preview(tc_id):
    return TestCaseController.preview(tc_id)

@testcase_bp.route('/<tc_id>/stop_preview', methods=['POST'])
def stop_preview(tc_id):
    return TestCaseController.stop_preview(tc_id)

@testcase_bp.route('/<tc_id>/stop-preview', methods=['POST'])
def stop_preview_hyphen(tc_id):
    return TestCaseController.stop_preview(tc_id)

@testcase_bp.route('/batch', methods=['POST'])
def batch_action():
    return TestCaseController.batch_action()

@testcase_bp.route('/stats', methods=['GET'])
def get_stats():
    return TestCaseController.get_stats()

@testcase_bp.route('/tags', methods=['GET'])
def get_tags():
    return TestCaseController.get_tags()

@testcase_bp.route('/export', methods=['POST'])
def export_cases():
    return TestCaseController.export_cases()

@testcase_bp.route('/import', methods=['POST'])
def import_cases():
    return TestCaseController.import_cases()

@testcase_bp.route('/template/download', methods=['GET'])
def download_template():
    return TestCaseController.download_template()

@testcase_bp.route('/import/preview', methods=['POST'])
def preview_import():
    return TestCaseController.preview_import()

@testcase_bp.route('/refresh_task/<task_id>', methods=['GET'])
def get_refresh_task_status(task_id):
    from backend.utils.reference_refresh_task import get_reference_refresh_task_status
    return get_reference_refresh_task_status(task_id)
