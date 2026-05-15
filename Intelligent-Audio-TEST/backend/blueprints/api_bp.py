from flask import Blueprint
from backend.controllers.api_controller import APIController

api_bp = Blueprint('apis', __name__)

@api_bp.route('', methods=['GET'])
def get_all():
    return APIController.get_all()

@api_bp.route('/<int:api_id>', methods=['GET'])
def get_one(api_id):
    return APIController.get_one(api_id)

@api_bp.route('', methods=['POST'])
def create():
    return APIController.create()

@api_bp.route('/<int:api_id>', methods=['PUT'])
def update(api_id):
    return APIController.update(api_id)

@api_bp.route('/<int:api_id>', methods=['DELETE'])
def delete(api_id):
    return APIController.delete(api_id)

@api_bp.route('/<int:api_id>/health', methods=['POST'])
def health_check(api_id):
    return APIController.health_check(api_id)

@api_bp.route('/<int:api_id>/test', methods=['POST', 'GET'])
def test_connection(api_id):
    return APIController.test_connection(api_id)

@api_bp.route('/<int:api_id>/stop-test', methods=['POST'])
def stop_test(api_id):
    return APIController.stop_test(api_id)
