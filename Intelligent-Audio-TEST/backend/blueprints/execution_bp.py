from flask import Blueprint
from backend.controllers.execution_controller import ExecutionController

execution_bp = Blueprint('execution', __name__)

@execution_bp.route('/<int:task_id>/start', methods=['POST'])
def start(task_id):
    return ExecutionController.start(task_id)

@execution_bp.route('/<int:task_id>/control', methods=['POST'])
def control(task_id):
    return ExecutionController.control(task_id)
