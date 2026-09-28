from flask import Blueprint
from backend.controllers.task_controller import TaskController

task_bp = Blueprint('tasks', __name__)

@task_bp.route('', methods=['GET'])
def get_all():
    return TaskController.get_all()

@task_bp.route('/<int:task_id>', methods=['GET'])
def get_one(task_id):
    return TaskController.get_one(task_id)

@task_bp.route('/<int:task_id>/cases/<string:case_id>/detail', methods=['GET'])
def get_case_detail(task_id, case_id):
    return TaskController.get_case_detail(task_id, case_id)

@task_bp.route('/<int:task_id>/cases/<string:case_id>/results', methods=['GET'])
def get_case_results(task_id, case_id):
    return TaskController.get_case_results(task_id, case_id)

@task_bp.route('/<int:task_id>/progress', methods=['GET'])
def get_progress(task_id):
    return TaskController.get_progress(task_id)

@task_bp.route('', methods=['POST'])
def create():
    return TaskController.create()

@task_bp.route('/<int:task_id>/start', methods=['POST'])
def start(task_id):
    return TaskController.start(task_id)

@task_bp.route('/<int:task_id>/retry', methods=['POST'])
def retry(task_id):
    return TaskController.retry(task_id)

@task_bp.route('/<int:task_id>/control', methods=['POST'])
def control(task_id):
    return TaskController.control(task_id)

@task_bp.route('/<int:task_id>/cases', methods=['PATCH'])
def update_cases(task_id):
    return TaskController.update_cases(task_id)

@task_bp.route('/<int:task_id>/stats', methods=['GET'])
def stats(task_id):
    return TaskController.stats(task_id)

@task_bp.route('/batch-action', methods=['POST'])
def batch_action():
    return TaskController.batch_action()

@task_bp.route('/merge', methods=['POST'])
def merge():
    return TaskController.merge()

@task_bp.route('/<int:task_id>/stop', methods=['POST'])
def stop(task_id):
    return TaskController.stop(task_id)

@task_bp.route('/<int:task_id>/reextract', methods=['POST'])
def reextract(task_id):
    return TaskController.reextract(task_id)

@task_bp.route('/<int:task_id>', methods=['DELETE'])
def delete(task_id):
    return TaskController.delete(task_id)

@task_bp.route('/<int:task_id>', methods=['PUT'])
def update(task_id):
    return TaskController.update(task_id)
