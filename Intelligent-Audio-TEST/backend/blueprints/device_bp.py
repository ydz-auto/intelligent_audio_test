from flask import Blueprint
from backend.controllers.device_controller import DeviceController

device_bp = Blueprint('devices', __name__)

@device_bp.route('', methods=['GET'])
def get_all():
    return DeviceController.get_all()

@device_bp.route('/status', methods=['GET'])
def get_statuses():
    return DeviceController.get_statuses()

@device_bp.route('/<int:device_id>', methods=['GET'])
def get_one(device_id):
    return DeviceController.get_one(device_id)

@device_bp.route('', methods=['POST'])
def create():
    return DeviceController.create()

@device_bp.route('/<int:device_id>', methods=['PUT'])
def update(device_id):
    return DeviceController.update(device_id)

@device_bp.route('/<int:device_id>', methods=['DELETE'])
def delete(device_id):
    return DeviceController.delete(device_id)

@device_bp.route('/health-check', methods=['POST'])
def health_check():
    return DeviceController.health_check()

@device_bp.route('/scan', methods=['POST'])
def scan():
    return DeviceController.scan()

@device_bp.route('/<int:device_id>/test', methods=['POST'])
def test(device_id):
    return DeviceController.test(device_id)

@device_bp.route('/<int:device_id>/stop-test', methods=['POST'])
def stop_test(device_id):
    return DeviceController.stop_test(device_id)

@device_bp.route('/driver-keywords', methods=['GET'])
def get_driver_keywords():
    return DeviceController.get_driver_keywords()

@device_bp.route('/serials', methods=['GET'])
def get_available_serials():
    return DeviceController.get_available_serials()
