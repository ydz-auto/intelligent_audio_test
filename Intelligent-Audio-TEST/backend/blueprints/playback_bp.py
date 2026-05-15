from flask import Blueprint
from backend.controllers.playback_controller import PlaybackController

playback_bp = Blueprint('playback-devices', __name__)

@playback_bp.route('', methods=['GET'])
def get_all():
    return PlaybackController.get_all()

@playback_bp.route('/<int:device_id>', methods=['GET'])
def get_one(device_id):
    return PlaybackController.get_one(device_id)

@playback_bp.route('', methods=['POST'])
def create():
    return PlaybackController.create()

@playback_bp.route('/<int:device_id>', methods=['PUT'])
def update(device_id):
    return PlaybackController.update(device_id)

@playback_bp.route('/<int:device_id>', methods=['DELETE'])
def delete(device_id):
    return PlaybackController.delete(device_id)

@playback_bp.route('/scan', methods=['POST'])
def scan():
    return PlaybackController.scan()

@playback_bp.route('/<int:device_id>/associate-spl', methods=['POST'])
def associate_spl(device_id):
    return PlaybackController.associate_spl(device_id)

@playback_bp.route('/<int:device_id>/test', methods=['POST'])
def test(device_id):
    return PlaybackController.test(device_id)

@playback_bp.route('/<int:device_id>/stop-test', methods=['POST'])
def stop_test(device_id):
    return PlaybackController.stop_test(device_id)

@playback_bp.route('/check-status', methods=['GET'])
def check_status():
    return PlaybackController.check_status()
