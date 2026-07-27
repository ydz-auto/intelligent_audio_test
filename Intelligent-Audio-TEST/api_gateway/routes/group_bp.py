from flask import Blueprint
from api_gateway.controllers.group_controller import GroupController

group_bp = Blueprint('groups', __name__)

@group_bp.route('', methods=['GET'])
def get_all():
    return GroupController.get_all()

@group_bp.route('', methods=['POST'])
def create():
    return GroupController.create()

@group_bp.route('/<group_id>', methods=['PUT'])
def update(group_id):
    return GroupController.update(group_id)

@group_bp.route('/<group_id>', methods=['DELETE'])
def delete(group_id):
    return GroupController.delete(group_id)

@group_bp.route('/move-cases', methods=['POST'])
def move_cases():
    return GroupController.move_cases()
