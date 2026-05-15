from flask import Blueprint
from backend.controllers.spl_controller import SPLController

spl_bp = Blueprint('spl', __name__)

@spl_bp.route('', methods=['GET'])
def get_all():
    return SPLController.get_all()

@spl_bp.route('/<int:mapping_id>', methods=['GET'])
def get_one(mapping_id):
    return SPLController.get_one(mapping_id)

@spl_bp.route('', methods=['POST'])
def create():
    return SPLController.create()

@spl_bp.route('/<int:mapping_id>', methods=['PUT'])
def update(mapping_id):
    return SPLController.update(mapping_id)

@spl_bp.route('/<int:mapping_id>', methods=['DELETE'])
def delete(mapping_id):
    return SPLController.delete(mapping_id)

@spl_bp.route('/<int:mapping_id>/calibrate', methods=['POST'])
def calibrate(mapping_id):
    return SPLController.calibrate(mapping_id)

@spl_bp.route('/<int:mapping_id>/history', methods=['GET'])
def get_history(mapping_id):
    return SPLController.get_history(mapping_id)

@spl_bp.route('/<int:mapping_id>/calibration-data', methods=['GET'])
def get_calibration_data(mapping_id):
    return SPLController.get_calibration_data(mapping_id)

@spl_bp.route('/stats', methods=['GET'])
def get_stats():
    return SPLController.get_stats()

@spl_bp.route('/by-device/<int:device_id>', methods=['GET'])
def get_by_device(device_id):
    return SPLController.get_by_device(device_id)

@spl_bp.route('/test-tone', methods=['POST'])
def play_test_tone():
    return SPLController.play_test_tone()

@spl_bp.route('/test-tone/stop', methods=['POST'])
def stop_test_tone():
    return SPLController.stop_test_tone()
